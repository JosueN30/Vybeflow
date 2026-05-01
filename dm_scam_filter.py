"""
VybeFlow DM Scam Filter
========================
High-level anti-scam layer for the Messenger component.

Three-tier defence:
  1. Keyword / pattern scan  — catches common scam phrases & suspicious links
  2. Behavioural analysis    — new accounts (< 24 h) spamming 3+ people in 10 min
  3. Hard-block execution    — permanent ban + IP blacklist + scammer stamp redirect

Public API
----------
  scan_dm_for_scam(sender, content, recipient_ids)
      -> ScamResult(is_scam, reason, signals)

  execute_scam_hard_block(sender_id, recipient_id, reason, sender_ip=None)
      -> dict   (contains "redirect_to_stamp" key when caller should redirect)

Usage in send_message():

    from dm_scam_filter import scan_dm_for_scam, execute_scam_hard_block

    scam_result = scan_dm_for_scam(user, content, [om.user_id for om in other_members])
    if scam_result.is_scam:
        block_result = execute_scam_hard_block(
            sender_id   = user.id,
            recipient_ids = [om.user_id for om in other_members],
            reason      = scam_result.reason,
            sender_ip   = request.headers.get('X-Forwarded-For', request.remote_addr)
        )
        return jsonify(block_result), 403
"""

from __future__ import annotations

import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence

# ---------------------------------------------------------------------------
# Lazy model imports (don't crash on import if DB isn't ready yet)
# ---------------------------------------------------------------------------
_MODELS_OK = False
try:
    from __init__ import db
    from models import User, Block, BlacklistedIP, DeviceFingerprint, DeviceFingerprintBan
    _MODELS_OK = True
except Exception:
    db = None
    User = None
    Block = None
    BlacklistedIP = None
    DeviceFingerprint = None
    DeviceFingerprintBan = None


# ===========================================================================
# 1 ─ KEYWORD + PATTERN DATABASE
# ===========================================================================

# Plain-text phrases — matched case-insensitively anywhere in the message.
_SCAM_PHRASES: list[str] = [
    # Money / payment pressure
    "send money",
    "send me money",
    "wire me",
    "transfer funds",
    "cash app me",
    "zelle me",
    "venmo me",
    "paypal me",
    "send $",
    "send dollars",
    "send pounds",
    "western union",
    "money gram",
    # Gift cards
    "gift card",
    "google play card",
    "itunes card",
    "amazon card",
    "buy me a card",
    "steam card",
    "ebay card",
    # Off-platform redirect
    "whatsapp me",
    "telegram me",
    "text me on whatsapp",
    "add me on whatsapp",
    "message me on telegram",
    "contact me on telegram",
    "kik me",
    "snap me",
    "dm me on ig",
    # Crypto / investment
    "crypto investment",
    "bitcoin investment",
    "invest in crypto",
    "ethereum profit",
    "guaranteed profit",
    "double your money",
    "get rich quick",
    "passive income",
    "forex trading",
    "binary options",
    "investment opportunity",
    "financial advisor",
    "nft investment",
    "token sale",
    "rug pull",
    # Money-making schemes
    "make money weekly",
    "make money from home",
    "earn weekly",
    "weekly earnings",
    "i make money from home",
    "make $",
    "earn $",
    # Account takeover / phishing
    "verify your account",
    "verify your identity",
    "confirm your details",
    "click this link",
    "check this link",
    "claim your prize",
    "you have won",
    "you've been selected",
    "limited time offer",
    "account suspended click",
    "password reset required",
    "update your payment",
    "unusual activity detected",
    # Romance / relationship scams
    "i need a loan",
    "i am stuck",
    "stranded abroad",
    "stuck in the airport",
    "emergency situation",
    "my wallet was stolen",
    "send me airtime",
    "i love you please send",
    # Explicit scammer tells
    "100% safe",
    "100% legit",
    "no risk",
    "trust me i am real",
    "i am not a scammer",
    "send only a small amount",
    "test payment",
    "pay first",
    "advance fee",
]

# Regex patterns for more structural matching
_SCAM_PATTERNS: list[str] = [
    # Suspicious external links (not common social / media CDNs)
    r"https?://(?!(?:tenor|giphy|media\d*\.tenor|c\.giphy|i\.giphy|"
    r"media\.discordapp|cdn\.discordapp|imgur|i\.imgur|"
    r"youtube|youtu\.be|vimeo|twitch|soundcloud|spotify|"
    r"twitter|x\.com|instagram|facebook|tiktok|"
    r"giphy|reddit|redd\.it|"
    r"google|gstatic|googleapis|"
    r"vybeflow)[^\s]*)"
    r"[^\s]{8,}",
    # Short-link services often used for phishing
    r"bit\.ly/[^\s]+",
    r"tinyurl\.com/[^\s]+",
    r"t\.co/[^\s]+",
    r"rb\.gy/[^\s]+",
    r"ow\.ly/[^\s]+",
    r"cutt\.ly/[^\s]+",
    r"shorturl\.at/[^\s]+",
    # Wallet addresses (crypto)
    r"\b(0x[a-fA-F0-9]{40})\b",           # Ethereum
    r"\b([13][a-km-zA-HJ-NP-Z1-9]{25,34})\b",  # Bitcoin P2PKH/P2SH
    r"\bT[A-Za-z1-9]{33}\b",               # TRON
    # Phone number patterns (off-platform redirect)
    r"\+\d[\d\s\-().]{7,}\d",
    # Dollar / crypto amounts with a request
    r"\$\s*\d+(?:,\d{3})*(?:\.\d{2})?\s+(?:to|for|send|transfer)",
    r"\b\d+(?:\.\d+)?\s*(?:btc|eth|usdt|xrp|sol|bnb|trx)\b",
]

_SCAM_PATTERN_RX = [re.compile(p, re.IGNORECASE) for p in _SCAM_PATTERNS]

# Signals that on their own are moderate risk — combined scoring
_MODERATE_SIGNALS: list[str] = [
    "make money",
    "earn money",
    "earn cash",
    "work from home",
    "side hustle",
    "easy money",
    "quick cash",
    "i can help you earn",
    "join my team",
    "business opportunity",
    "drop your number",
    "drop your email",
    "inbox me",
    "follow my link",
    "check my bio",
    "check my profile",
    "promo code",
    "click here",
    "only today",
    "act now",
    "urgent",
]

# Score threshold above which a message is flagged as a scam
_SCAM_SCORE_THRESHOLD = 2


# ===========================================================================
# 2 ─ BEHAVIOURAL ANALYSIS (in-memory, resets on restart)
#      For persistent tracking use Redis or a DB table.
# ===========================================================================

# { sender_id: [{"ts": float, "recipient_id": int, "had_link": bool}, ...] }
_behaviour_window: dict[int, list[dict]] = defaultdict(list)

_BEHAVIOUR_WINDOW_SECS = 600  # 10 minutes
_NEW_ACCOUNT_HOURS     = 24   # "new account" threshold
_SPREAD_THRESHOLD      = 3    # distinct recipients to trigger behaviour flag


# ===========================================================================
# Feed post URL-spam heuristic (bot detection)
# ===========================================================================
# Tracks distinct URL strings posted per user within a rolling window.
# If the same URL appears ≥ _FEED_URL_MAX_SAME times in _FEED_URL_WINDOW
# seconds, the post looks like bot-driven spam and is flagged.
# These dicts are in-memory; they reset on server restart (intentional —
# bots get flagged per-session, and persistent state would require Redis).


_feed_url_tracker: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
_FEED_URL_WINDOW   = 60   # rolling window in seconds
_FEED_URL_MAX_SAME = 5    # same URL posted this many times = bot behaviour

# ---------------------------------------------------------------------------
# Duplicate promo-script fingerprint tracker
# Catches fake music promos / copy-paste spam: same normalised message text
# sent by the same user to ≥ _PROMO_SCRIPT_MIN_TARGETS distinct recipients
# within _PROMO_SCRIPT_WINDOW seconds.
# ---------------------------------------------------------------------------
_promo_tracker: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
_PROMO_SCRIPT_WINDOW     = 900   # 15 minute rolling window
_PROMO_SCRIPT_MIN_TARGETS = 2    # identical script to this many users → flag
# Music-promo keywords — sending these to multiple users is high-risk
_PROMO_KEYWORDS = re.compile(
    r"\b(stream|listen|check out|new\s+(?:song|track|music|single|ep|album|drop)|"
    r"spotify|apple\s+music|soundcloud|audiomack|tidal|youtube|music\s+video|"
    r"link\s+in\s+(?:bio|my\s+bio|profile)|out\s+now|dropping\s+(?:soon|now|tonight)|"
    r"new\s+(?:drop|release)|(?:free|paid)\s+(?:promo|promotion|feature|verse))\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Urgency-spike tracker for new users (first 5 DMs)
# If high-risk urgency finance language appears early, silently flag the user
# and cap DM spread for 24h.
# ---------------------------------------------------------------------------
_URGENCY_KEYWORDS_RX = re.compile(
    r"\b(account|accounts|money|urgent|invest|investing|investment|wallet|bank|transfer)\b",
    re.IGNORECASE,
)
_FIRST_MESSAGES_WINDOW_SECS = 24 * 3600
_FIRST_MESSAGES_CHECK_COUNT = 5
_SILENT_FLAG_HOURS = 24
_SILENT_FLAG_MAX_RECIPIENTS = 3

# sender_id -> [{"ts": monotonic, "urgency_hits": int}]
_early_dm_tracker: dict[int, list[dict]] = defaultdict(list)

# sender_id -> {
#   "until": datetime,
#   "max_recipients": int,
#   "allowed_recipients": set[int],
#   "reason": str,
# }
_silent_flag_state: dict[int, dict] = {}


def _normalize_text_for_fingerprint(text: str) -> str:
    """Collapse whitespace, lowercase, strip URLs and punctuation to get a canonical form."""
    t = text.lower().strip()
    t = re.sub(r"https?://\S+", "_URL_", t)  # replace all URLs with placeholder
    t = re.sub(r"[^\w\s_]", " ", t)          # strip punctuation
    t = re.sub(r"\s+", " ", t).strip()        # normalise whitespace
    return t


def check_promo_script_spam(user_id: int, content: str, recipient_id: int) -> bool:
    """Return True if this user is sending the same promotional script
    to multiple distinct recipients (fake music promo / copy-paste spam).

    Call BEFORE recording the message.  Pair with record_promo_script().
    """
    if not user_id or not content:
        return False
    # Only apply to messages that contain music/promo keywords
    if not _PROMO_KEYWORDS.search(content):
        return False
    now = time.monotonic()
    cutoff = now - _PROMO_SCRIPT_WINDOW
    fingerprint = _normalize_text_for_fingerprint(content)
    if len(fingerprint) < 20:  # too short to be a promo script
        return False
    # Count distinct recipients that received this exact script within window
    prior = [
        e for e in _promo_tracker[user_id][fingerprint]
        if e["ts"] > cutoff and e["rid"] != recipient_id
    ]
    return len(set(e["rid"] for e in prior)) >= _PROMO_SCRIPT_MIN_TARGETS - 1


def record_promo_script(user_id: int, content: str, recipient_id: int) -> None:
    """Record that user_id sent content to recipient_id (for promo script tracking)."""
    if not user_id or not content:
        return
    if not _PROMO_KEYWORDS.search(content):
        return
    now = time.monotonic()
    cutoff = now - _PROMO_SCRIPT_WINDOW
    fingerprint = _normalize_text_for_fingerprint(content)
    if len(fingerprint) < 20:
        return
    # Prune stale entries
    _promo_tracker[user_id][fingerprint] = [
        e for e in _promo_tracker[user_id][fingerprint] if e["ts"] > cutoff
    ]
    _promo_tracker[user_id][fingerprint].append({"ts": now, "rid": recipient_id})
    # Clean up empty fingerprints to prevent memory leak
    dead = [fp for fp, entries in _promo_tracker[user_id].items() if not entries]
    for fp in dead:
        del _promo_tracker[user_id][fp]


def check_feed_url_spam(user_id: int, url: str) -> bool:
    """Return True if *user_id* has posted *url* ≥ _FEED_URL_MAX_SAME times
    in the last _FEED_URL_WINDOW seconds (bot heuristic).

    Call this BEFORE saving a new feed post.  Pair with record_feed_url().
    The check is deliberately conservative (5 identical URLs in 60 s) so
    ordinary re-posts or test users are never false-positives.
    """
    if not url or not user_id:
        return False
    now = time.monotonic()
    cutoff = now - _FEED_URL_WINDOW
    times = [t for t in _feed_url_tracker[user_id][url] if t > cutoff]
    return len(times) >= _FEED_URL_MAX_SAME


def record_feed_url(user_id: int, url: str) -> None:
    """Record that *user_id* just posted *url*.  Call AFTER check_feed_url_spam."""
    if not url or not user_id:
        return
    now = time.monotonic()
    cutoff = now - _FEED_URL_WINDOW
    # Prune stale entries first to keep memory bounded
    _feed_url_tracker[user_id][url] = [
        t for t in _feed_url_tracker[user_id][url] if t > cutoff
    ]
    _feed_url_tracker[user_id][url].append(now)

    # Also clean up URLs with zero remaining entries to prevent memory leak
    dead = [u for u, ts in _feed_url_tracker[user_id].items() if not ts]
    for u in dead:
        del _feed_url_tracker[user_id][u]


def _purge_early_dm_tracker(sender_id: int) -> None:
    cutoff = time.monotonic() - _FIRST_MESSAGES_WINDOW_SECS
    _early_dm_tracker[sender_id] = [
        e for e in _early_dm_tracker[sender_id] if e["ts"] > cutoff
    ]


def _activate_silent_flag(sender_id: int, recipient_ids: Sequence[int], reason: str) -> datetime:
    until = datetime.now(timezone.utc) + timedelta(hours=_SILENT_FLAG_HOURS)
    state = _silent_flag_state.get(sender_id) or {
        "until": until,
        "max_recipients": _SILENT_FLAG_MAX_RECIPIENTS,
        "allowed_recipients": set(),
        "reason": reason,
    }
    state["until"] = max(state.get("until", until), until)
    state["reason"] = reason
    allowed = state.setdefault("allowed_recipients", set())
    for rid in recipient_ids:
        if len(allowed) >= int(state.get("max_recipients", _SILENT_FLAG_MAX_RECIPIENTS)):
            break
        allowed.add(int(rid))
    _silent_flag_state[sender_id] = state
    return state["until"]


def _is_silent_flag_active(sender_id: int) -> bool:
    state = _silent_flag_state.get(sender_id)
    if not state:
        return False
    now = datetime.now(timezone.utc)
    until = state.get("until")
    if until and now <= until:
        return True
    _silent_flag_state.pop(sender_id, None)
    return False


def check_silent_flag_limit(sender_id: int, recipient_ids: Sequence[int]) -> dict:
    """Enforce recipient fan-out cap for silently flagged users.

    Returns a dict:
      {
        "active": bool,
        "allowed": bool,
        "limited": bool,
        "until": iso or None,
        "max_recipients": int,
        "used_recipients": int,
      }
    """
    if not _is_silent_flag_active(sender_id):
        return {
            "active": False,
            "allowed": True,
            "limited": False,
            "until": None,
            "max_recipients": _SILENT_FLAG_MAX_RECIPIENTS,
            "used_recipients": 0,
        }

    state = _silent_flag_state[sender_id]
    allowed = state.setdefault("allowed_recipients", set())
    max_recips = int(state.get("max_recipients", _SILENT_FLAG_MAX_RECIPIENTS))

    # If all recipients are already in the allow-list, permit delivery.
    incoming = [int(rid) for rid in recipient_ids]
    unseen = [rid for rid in incoming if rid not in allowed]
    if unseen and (len(allowed) + len(unseen) > max_recips):
        return {
            "active": True,
            "allowed": False,
            "limited": True,
            "until": state["until"].isoformat() if state.get("until") else None,
            "max_recipients": max_recips,
            "used_recipients": len(allowed),
        }

    for rid in unseen:
        allowed.add(rid)

    return {
        "active": True,
        "allowed": True,
        "limited": False,
        "until": state["until"].isoformat() if state.get("until") else None,
        "max_recipients": max_recips,
        "used_recipients": len(allowed),
    }


def _check_urgency_spike(sender: object, content: str, recipient_ids: Sequence[int]) -> tuple[bool, Optional[datetime]]:
    """Detect urgency-finance spike in a new user's first 5 DMs and activate silent-flag mode."""
    if not sender or not content or not getattr(sender, "id", None):
        return False, None
    if not _is_new_account(sender):
        return False, None

    sender_id = int(sender.id)
    _purge_early_dm_tracker(sender_id)
    entries = _early_dm_tracker[sender_id]
    if len(entries) >= _FIRST_MESSAGES_CHECK_COUNT:
        return False, None

    urgency_terms = set(m.group(0).lower() for m in _URGENCY_KEYWORDS_RX.finditer(content or ""))
    urgency_hits = len(urgency_terms)
    has_link = bool(re.search(r"https?://", content, re.I))

    entries.append({"ts": time.monotonic(), "urgency_hits": urgency_hits})
    _early_dm_tracker[sender_id] = entries

    if len(entries) <= _FIRST_MESSAGES_CHECK_COUNT and (urgency_hits >= 2 or (urgency_hits >= 1 and has_link)):
        until = _activate_silent_flag(sender_id, recipient_ids, "urgency_spike_first_5")
        return True, until
    return False, None


def build_scam_mirror_reply(content: str) -> str:
    """Return a decoy reply that keeps scammers occupied in shadow mode."""
    low = (content or "").lower()
    if any(k in low for k in ("bitcoin", "crypto", "invest", "investment", "wallet")):
        return "Interesting. Before I invest, can you share your audited 12-month ROI and exchange proof?"
    if any(k in low for k in ("urgent", "send money", "transfer", "cash app", "zelle", "paypal")):
        return "I can help. Please break down the payment process step by step and include your full legal name."
    if any(k in low for k in ("account", "verify", "password", "login")):
        return "I need to validate this request. What official ticket ID and support case reference can you provide?"
    return "Got it. Can you explain the full process in more detail so I can confirm everything first?"


def _purge_behaviour(sender_id: int) -> None:
    cutoff = time.monotonic() - _BEHAVIOUR_WINDOW_SECS
    _behaviour_window[sender_id] = [
        e for e in _behaviour_window[sender_id] if e["ts"] > cutoff
    ]


def _is_new_account(sender: object) -> bool:
    """True if the user account was created less than 24 hours ago."""
    try:
        _ca = sender.created_at
        _now_scam = datetime.utcnow() if _ca.tzinfo is None else datetime.now(timezone.utc)
        age = _now_scam - _ca
        return age < timedelta(hours=_NEW_ACCOUNT_HOURS)
    except Exception:
        return False


def _record_behaviour(sender_id: int, recipient_id: int, had_link: bool) -> None:
    _purge_behaviour(sender_id)
    _behaviour_window[sender_id].append({
        "ts": time.monotonic(),
        "recipient_id": recipient_id,
        "had_link": had_link,
    })


def _check_behaviour_flag(sender: object, content: str, recipient_ids: Sequence[int]) -> bool:
    """Return True if the sender's behaviour matches new-account mass-spam pattern."""
    if not _is_new_account(sender):
        return False

    has_link = bool(re.search(r"https?://", content, re.I))
    has_scam_phrase = _quick_scam_phrase_check(content)

    if not (has_link or has_scam_phrase):
        return False

    _purge_behaviour(sender.id)
    existing = _behaviour_window[sender.id]
    # Count distinct recipients within the window (including this message)
    targeted = set(e["recipient_id"] for e in existing) | set(recipient_ids)
    return len(targeted) >= _SPREAD_THRESHOLD


# ===========================================================================
# 3 ─ SCANNER
# ===========================================================================

@dataclass
class ScamResult:
    is_scam: bool
    reason: str
    signals: list[str] = field(default_factory=list)
    score: int = 0
    silent_flag_triggered: bool = False
    silent_flag_until: Optional[str] = None
    scam_mirror_reply: Optional[str] = None


def _quick_scam_phrase_check(text: str) -> bool:
    low = text.lower()
    return any(phrase in low for phrase in _SCAM_PHRASES)


def scan_dm_for_scam(
    sender: object,
    content: str,
    recipient_ids: Sequence[int],
) -> ScamResult:
    """
    Scan a DM before it is committed to the database.

    Parameters
    ----------
    sender        : User model instance
    content       : Raw (pre-encryption) message text
    recipient_ids : IDs of everyone else in the thread

    Returns
    -------
    ScamResult — check .is_scam to decide whether to block.
    """
    if not content or not content.strip():
        return ScamResult(is_scam=False, reason="clean", signals=[], score=0)

    signals: list[str] = []
    score = 0
    low = content.lower()
    urgency_flagged, urgency_until = _check_urgency_spike(sender, content, recipient_ids)
    if urgency_flagged:
        signals.append("behaviour:urgency_spike_first_5")
        score += 3

    # ── Pass 1: high-confidence keyword hits ────────────────────────────────
    for phrase in _SCAM_PHRASES:
        if phrase in low:
            signals.append(f"phrase:{phrase}")
            score += 2  # each keyword is a strong signal

    # ── Pass 2: regex patterns ───────────────────────────────────────────────
    for rx in _SCAM_PATTERN_RX:
        m = rx.search(content)
        if m:
            signals.append(f"pattern:{rx.pattern[:40]}")
            score += 2

    # ── Pass 3: moderate signals (lower individual weight) ──────────────────
    for phrase in _MODERATE_SIGNALS:
        if phrase in low:
            signals.append(f"moderate:{phrase}")
            score += 1

    # ── Pass 4: behavioural spread detection ────────────────────────────────
    behaviour_flagged = _check_behaviour_flag(sender, content, recipient_ids)
    if behaviour_flagged:
        signals.append("behaviour:new_account_mass_spam")
        score += 4  # overrides threshold on its own

    # ── Pass 5: duplicate promo-script detection ─────────────────────────────
    for rid in recipient_ids:
        if check_promo_script_spam(sender.id, content, rid):
            signals.append("behaviour:duplicate_promo_script")
            score += 5  # identical promo sent to multiple users → strong signal
            break

    # Record this message's behaviour and promo data regardless
    has_link = bool(re.search(r"https?://", content, re.I))
    for rid in recipient_ids:
        _record_behaviour(sender.id, rid, has_link)
        record_promo_script(sender.id, content, rid)

    if score >= _SCAM_SCORE_THRESHOLD:
        reason_parts = []
        if any(s.startswith("phrase:") for s in signals):
            reason_parts.append("scam_phrase")
        if any(s.startswith("pattern:") for s in signals):
            reason_parts.append("suspicious_link_or_address")
        if behaviour_flagged:
            reason_parts.append("new_account_mass_spam")
        return ScamResult(
            is_scam=True,
            reason=",".join(reason_parts) or "scam_detected",
            signals=signals,
            score=score,
            silent_flag_triggered=urgency_flagged,
            silent_flag_until=urgency_until.isoformat() if urgency_until else None,
            scam_mirror_reply=build_scam_mirror_reply(content),
        )

    return ScamResult(
        is_scam=False,
        reason="clean",
        signals=signals,
        score=score,
        silent_flag_triggered=urgency_flagged,
        silent_flag_until=urgency_until.isoformat() if urgency_until else None,
    )


# ===========================================================================
# 4 ─ HARD BLOCK EXECUTION
# ===========================================================================

def execute_scam_hard_block(
    sender_id: int,
    recipient_ids: Sequence[int],
    reason: str,
    sender_ip: Optional[str] = None,
) -> dict:
    """
    Execute the full hard-block sequence when a scam is detected:

    1. Ban the sender globally (is_banned = True, scam_flags += 1).
    2. Auto-block the sender in every recipient's blocked_users list.
    3. Blacklist the sender's IP to prevent ban evasion.
    4. Return a response dict the caller can return as JSON.
       The dict contains  "redirect_to_stamp": True  so the client
       knows to navigate to /blocked-scammer.
    """
    if not _MODELS_OK:
        return {
            "error": "Message blocked — scam detected.",
            "code": "scam_blocked",
            "redirect_to_stamp": True,
        }

    try:
        sender = db.session.get(User, sender_id)
        if sender:
            # ── 1. Permanent global ban ──────────────────────────────────────
            sender.scam_flags   = (getattr(sender, "scam_flags", 0) or 0) + 1
            sender.is_banned    = True
            sender.ban_reason   = f"SCAM BAN: {reason}"
            sender.is_suspended = True
            sender.suspension_reason = sender.ban_reason
            try:
                sender.banned_at = datetime.now(timezone.utc)
            except Exception:
                pass

            # ── 2. Auto-block sender in every recipient's block list ─────────
            for rid in recipient_ids:
                try:
                    if Block is not None and not Block.is_blocked(rid, sender_id):
                        new_block = Block(
                            blocker_id=rid,
                            blocked_id=sender_id,
                        )
                        db.session.add(new_block)
                except Exception:
                    pass  # Don't let one bad recipient abort the whole ban

            # ── 3. IP blacklisting ──────────────────────────────────────────
            if sender_ip and BlacklistedIP is not None:
                try:
                    _raw_ip = sender_ip.split(",")[0].strip()  # handle X-Forwarded-For chains
                    if _raw_ip:
                        BlacklistedIP.add(
                            ip=_raw_ip,
                            reason=f"scam_ban:{reason}",
                            source_user_id=sender_id,
                        )
                except Exception:
                    pass

            # ── 4. Hardware lock: ban all known device fingerprints used by sender
            if DeviceFingerprint is not None and DeviceFingerprintBan is not None:
                try:
                    fp_rows = DeviceFingerprint.query.filter_by(user_id=sender_id).all()
                    for fp_row in fp_rows:
                        fp_hash = (getattr(fp_row, "fingerprint_hash", "") or "").strip()
                        if fp_hash:
                            DeviceFingerprintBan.ban(
                                fingerprint_hash=fp_hash,
                                reason=f"scam_device_lock:{reason}",
                                source_user_id=sender_id,
                            )
                except Exception:
                    pass

        db.session.commit()

    except Exception as exc:
        try:
            db.session.rollback()
        except Exception:
            pass
        print(f"[ScamFilter] Hard block DB error: {exc}")

    return {
        "error": "Your message was intercepted by VybeFlow Security. "
                 "Scam activity has been detected on your account.",
        "code": "scam_hard_blocked",
        "reason": reason,
        "redirect_to_stamp": True,
        "scam_banned": True,
    }


# ===========================================================================
# 5 ─ RECIPIENT NOTIFICATION PAYLOAD
# ===========================================================================

def scam_blocked_notification(sender_username: str) -> dict:
    """
    Return a structured notification dict for the recipient.
    The client renders this as a themed toast.
    """
    return {
        "security_event": True,
        "event_type":     "scam_blocked",
        "sender":         sender_username,
        "toast_title":    "VybeFlow Security",
        "toast_message":  (
            "A potential scammer was blocked and removed for your safety."
        ),
        "toast_type":     "security",  # client applies --user-theme-color glow
    }
