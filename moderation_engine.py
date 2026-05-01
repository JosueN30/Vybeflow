import re
import logging as _logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

_mod_log = _logging.getLogger('vybeflow.moderation')

# ── Always-block slurs (unambiguous hate speech in any context) ──
SLUR_PATTERNS = [
    r"\b(fag+ot|f[a@]g)\b",
    r"\b(nigg+[ae]r)\b",              # hard-r variant — always blocked
    r"\b(ch[i1]nk)\b",
    r"\b(sp[i1]c|sp[i1]ck)\b",
    r"\b(k[iy]ke)\b",
    r"\b(w[e3]tb[a@]ck)\b",
    r"\b(tr[a@]nn[yi]e?)\b",
    r"\b(r[e3]t[a@]rd)\b",
    r"\b(coon|c00n)\b",
]

# ── "nigga" — only flagged when used AS an insult directed at someone ──
DIRECTED_NIGGA_PATTERNS = [
    r"\b(?:you|your|this|that|stupid|dumb|fucking|fuckin|ugly|fat|dirty|lil|little|punk.ass|bitch.ass)\s+n[i1]gg[a@]\b",
    r"\bn[i1]gg[a@]\s+(?:ass|bitch|hoe)\b",
    r"\bcall(?:ed|ing)?\s+(?:me|him|her|them|us)\s+(?:a\s+)?n[i1]gg[a@]\b",
]

THREAT_PATTERNS = [
    r"\b(?:i(?:'ll| will| wanna| want to| am going to|'m going to|'m gonna|m gonna)\s+(?:kill|murder|shoot|stab|hurt|beat|attack|destroy|end|slaughter|strangle|choke))\b",
    r"\b(?:kill|murder|shoot|stab|hurt|beat up|attack|destroy|slaughter|strangle|choke)\s+(?:you|your|u |ur )",
    r"\bkill yourself\b",
    r"\b(?:go|gonna|going to)\s+(?:kill|murder|shoot|stab|hurt|beat|attack)\b",
    r"\byou(?:'re| are)\s+(?:dead|gonna die|going to die)\b",
    r"\b(?:i(?:'ll| will))\s+(?:find|come for|get)\s+(?:you|your|u)\b",
    r"\b(?:put a bullet|blow your brains|slit your|cut your throat)\b",
    r"\b(?:watch your back|sleep with one eye|you(?:'re| are) next)\b",
    r"\b(?:kill|murder|shoot|stab|hurt|attack|destroy)\s+(?:your|his|her|their)\s+(?:family|mom|dad|mother|father|kids|children|dog|cat|pet)\b",
    r"\b(?:rape|assault|jump|rob|mug)\s+(?:you|your|u |ur )",
    r"\b(?:bomb|blow up|burn down|set fire to|shoot up)\b",
    r"\b(?:school shooting|mass shooting|mass murder)\b",
    r"\b(?:kill yourself|kys|neck yourself|end yourself|hang yourself|drink bleach|jump off)\b",
    r"\b(?:hope you die|wish you were dead|you should die|you deserve to die|drop dead)\b",
    r"\b(?:i(?:'ll| will|'m gonna|m gonna)\s+(?:find you|ruin your life|end your life|make you pay|make you suffer))\b",
    r"\b(?:just die|go die|please die|die already)\b",
    # ── AAVE / street-speech violent threats ──
    # "ima kill", "i'ma kill", "im a kill", "imma kill his/your/their ass"
    r"\bim+[a']?\s+(?:kill|shoot|stab|murder|end|hurt|beat|stomp|catch)\b",
    # "finna kill / finna shoot"
    r"\bfinna\s+(?:kill|shoot|stab|murder|hurt|beat|stomp|catch)\b",
    # "on sight", "catch you slipping", "slide on you"
    r"\b(?:on\s+sight|catch\s+(?:you|him|her)\s+slippin|slide\s+on\s+(?:you|him|her|them))\b",
    # "kill his ass", "shoot his ass", "murder his ass"
    r"\b(?:kill|shoot|stab|murder|hurt|beat|stomp)\s+(?:his|her|your|their|this|that|yo)\s+ass\b",
    # "cap his ass", "clap his ass", "wet his ass" (street slang for shoot)
    r"\b(?:cap|clap|wet|smoke|fade|rock|drop|spin|blick)\s+(?:his|her|your|their|this|that|yo)\b",
    # "send shots", "pull up and", "run up on"
    r"\b(?:send\s+shots|pull\s+up\s+on|run\s+up\s+on|run\s+up\s+with)\b",
    # "catch a body", "catch bodies"
    r"\bcatch\s+(?:a\s+)?bod(?:y|ies)\b",
    # "push his wig back", "push your wig"
    r"\bpush\s+(?:his|her|your|their|yo|tha)\s+wig\b",
    # "clear his/your block"
    r"\bclear\s+(?:his|her|your|their|yo|the)\s+block\b",
]

DOXX_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",
    # Phone numbers: require at least one separator (dash, dot, space) or
    # a country code prefix (+1) or parenthetical area code — otherwise a plain
    # 10-digit number like a Unix timestamp false-positives.
    r"\b\+?1[-.\s]\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b",            # +1 or 1 prefix with separator
    r"\b\(?\d{3}\)?[-.\s]\d{3}[-.\s]?\d{4}\b",                        # area code then separator
    r"\b\(?\d{3}\)?[-.\s]?\d{3}[-.\s]\d{4}\b",                        # separator before last 4
    r"\b\(\d{3}\)\s?\d{3}[-.\s]?\d{4}\b",                             # (xxx) area code
    r"\b\d{1,5}\s+[A-Za-z0-9.\s]+(?:St|Street|Ave|Avenue|Blvd|Road|Rd|Dr|Drive)\b",
]

# ── Scam / spam detection (enhanced with AI-like heuristic scoring) ──
SCAM_PATTERNS = [
    r"\b(?:send|wire|transfer)\s+(?:me|us)\s+(?:\$|money|cash|bitcoin|btc|eth|crypto)",
    r"\b(?:nigerian|foreign)\s+prince\b",
    r"\b(?:you(?:'ve| have)? won|congratulations.*(?:winner|prize|lottery))\b",
    r"\b(?:act now|limited time|urgent|don'?t miss)\b.*(?:\$|money|cash|prize|reward)",
    r"\b(?:paypal|venmo|cashapp|zelle)\s*(?:me|@)\b",
    r"\b(?:give\s*away|giveaway)\b.*(?:click|link|dm|follow)",
    r"\b(?:investment|invest)\s+(?:opportunity|guaranteed|returns|profit)\b",
    r"\b(?:make\s+)?\$\d{3,}\s*(?:per|a|every)\s*(?:day|hour|week)\b",
    r"\b(?:free\s+)?(?:iphone|macbook|gift\s*card)\s*(?:give|click|link|dm)\b",
    r"\bhttps?://(?:bit\.ly|tinyurl|t\.co|shorturl|rb\.gy)/\S+",
]

# ── Extended scam phrases for auto-blocking ──
SCAM_PHRASES_AUTOBLOCK = [
    r"\b(?:sugar\s*(?:daddy|mama|mommy))\b.*(?:allowance|pay|send|cashapp|venmo|\$)",
    r"\b(?:double\s+your\s+(?:money|crypto|bitcoin|investment))\b",
    r"\b(?:100%\s+(?:guaranteed|profit|returns|legit))\b",
    r"\b(?:work\s+from\s+home|easy\s+money|passive\s+income)\b.*(?:dm|link|click|message)",
    r"\b(?:bank\s+(?:account|details|info|verification))\b.*(?:send|verify|confirm|update)",
    r"\b(?:whatsapp|telegram)\s+(?:me|@|\+)\b",
    r"\b(?:recovery|restore)\s+(?:lost|stolen)\s+(?:crypto|bitcoin|funds|money)\b",
    r"\b(?:hacked|hack)\s+(?:any|someone'?s?)\s+(?:account|instagram|facebook|snapchat)\b",
    r"\b(?:clone|cloned)\s+(?:card|credit card|debit card)\b",
    r"\b(?:earn|make)\s+\$?\d+k?\+?\s*(?:daily|weekly|monthly)\b.*(?:dm|link|join)",
    r"\b(?:forex|binary\s+options?|nft)\s+(?:trading|signal|opportunity|mentor)\b",
    r"\b(?:i'?m?\s+(?:a|an)\s+)?(?:hacker|carder)\b.*(?:dm|services|contact)",
    r"\b(?:age\s+(?:verification|verify))\b.*(?:link|click|visit|website)",
    r"\b(?:verify\s+(?:your|ur)\s+(?:identity|account))\b.*(?:link|click|here|now)",
    r"\b(?:customer\s+(?:support|service|care))\b.*(?:call|contact|reach)\b.*\d{5,}",
    r"\b(?:get\s+rich|financial\s+freedom)\b.*(?:dm|click|join|link)",
]

SPAM_PATTERNS = [
    r"(.{10,})\1{2,}",
    r"(?:follow|sub|subscribe)\s+(?:me|my|@)\b.*(?:follow|sub|subscribe)\s+(?:me|my|@)",
    r"\b(?:check\s+(?:out\s+)?my|visit\s+my)\b.*(?:link|bio|profile)\b.*\bhttps?://",
]

# ── Negativity / toxicity patterns – ONLY directed attacks at people ──
# Standalone cursing ("this shit fire", "fucking awesome") is intentionally allowed.
NEGATIVITY_PATTERNS = [
    # "you're [insult]" — directly calling someone out
    r"\b(?:you(?:'re| are| look| sound)\s+(?:ugly|disgusting|pathetic|worthless|terrible|horrible|useless|dumb|stupid|annoying|trash|garbage|fat|a\s+loser|a\s+clown|a\s+joke|a\s+bitch|a\s+hoe|a\s+whore|a\s+slut))\b",
    # nobody likes you, etc.
    r"\b(?:nobody|no one)\s+(?:likes|loves|cares about|wants)\s+you\b",
    # directed dismissals
    r"\b(?:shut up|stfu|gtfo|piss off|go to hell)\b",
    # "i hate you"
    r"\b(?:i hate you|hate you so much|everyone hates you)\b",
    # self-harm encouragement
    r"\b(?:kys|kill yourself|neck yourself|end yourself)\b",
    # directed death wishes
    r"\b(?:hope you die|wish you were dead|you should die|you deserve to die)\b",
    # "fuck you / screw you" — clearly aimed at someone
    r"\b(?:fuck you|fuck off|screw you|eat a dick|suck my dick|suck my cock)\b",
    # "you suck / you're nothing"
    r"\b(?:you suck|you(?:'re| are) a joke|you(?:'re| are) nothing)\b",
    # "[someone] is a [insult]" — talking about a specific person
    r"\b(?:he|she|they|that (?:guy|girl|dude|person|kid|man|woman))\s+(?:is|are)\s+(?:a\s+)?(?:loser|idiot|moron|clown|bitch|hoe|whore|slut|trash|garbage|joke|waste)\b",
    # "your [insult] ass / your ugly ass"
    r"\byour\s+(?:ugly|stupid|dumb|fat|bitch|punk|lame|goofy|clown|worthless|pathetic)\s+(?:ass|self)\b",
    # calling someone out: "you [insult]" (with or without second word)
    r"\byou\s+(?:stupid|ugly|dumb|fat|lame|goofy|worthless|pathetic)\s+(?:bitch|ass|hoe|mf|mfer|idiot|moron|clown|piece of)\b",
    # "you trash / you garbage / you lame" — slang without "are"
    r"\byou\s+(?:trash|garbage|worthless|pathetic|stupid|ugly|dumb|lame|goofy|corny|wack|weak|a joke|nothing|disgusting)\b",
    # indirect: "they suck", "this person trash", etc.
    r"\b(?:he|she|they|this person|that (?:guy|girl|dude|person|kid))\s+(?:suck|sucks|trash|garbage|lame|ugly|stupid|dumb|worthless|pathetic|a joke|disgust)\b",
]

DOGPILE_WINDOW_SECONDS = 60
DOGPILE_MAX_REPLIES_PER_TARGET_PER_WINDOW = 8     # per target user or per post
USER_COMMENT_RATE_PER_MIN = 15                    # per user, per minute
USER_REPLY_TO_SAME_TARGET_PER_10MIN = 6           # harassment pattern

@dataclass
class ModResult:
    decision: str          # allow | quarantine | block | throttle
    reason: str
    score: float | None = None
    cooldown_seconds: int = 0

def _hit_any(patterns, text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)

def moderate_text(text: str) -> ModResult:
    if not text or not text.strip():
        _mod_log.info('[MODERATION] Empty content submitted')
        return ModResult("block", "empty_content")

    _mod_log.debug('[MODERATION] Scanning text (len=%d): %r', len(text), text[:120])

    if _hit_any(DOXX_PATTERNS, text):
        _mod_log.warning('[MODERATION] BLOCKED reason=possible_doxxing text=%r', text[:120])
        return ModResult("block", "possible_doxxing")

    if _hit_any(THREAT_PATTERNS, text):
        _mod_log.warning('[MODERATION] BLOCKED reason=threat_or_self_harm_encouragement text=%r', text[:120])
        return ModResult("block", "threat_or_self_harm_encouragement")

    if _hit_any(SLUR_PATTERNS, text):
        _mod_log.warning('[MODERATION] BLOCKED reason=hate_speech_slur text=%r', text[:120])
        return ModResult("block", "hate_speech_slur")

    # "nigga" used as a directed insult → block
    if _hit_any(DIRECTED_NIGGA_PATTERNS, text):
        _mod_log.warning('[MODERATION] BLOCKED reason=hate_speech_slur (directed_nigga) text=%r', text[:120])
        return ModResult("block", "hate_speech_slur")

    # ── Scam / spam detection ──
    if _hit_any(SCAM_PATTERNS, text):
        _mod_log.warning('[MODERATION] BLOCKED reason=scam_detected text=%r', text[:120])
        return ModResult("block", "scam_detected")

    # NOTE: Repetitive posting / spam patterns are ALLOWED on VybeFlow.
    # Users can post the same thing repeatedly, copy-paste comments,
    # share the same link in many groups, and promote aggressively.
    # Only scams, threats, hate speech, and doxxing are blocked.

    # ── Directed negativity (cursing someone OUT, not just cursing) ──
    if _hit_any(NEGATIVITY_PATTERNS, text):
        _mod_log.info('[MODERATION] WARN reason=negative_content (matched NEGATIVITY_PATTERNS) text=%r', text[:120])
        return ModResult("warn", "negative_content", score=0.5)

    # ── Heuristic: directed insults with profanity aimed at a person ──
    # Stand-alone profanity is FINE ("this shit fire", "fucking awesome").
    # Only flag when insults are AIMED at someone ("you" / "your" / "@user").
    lower = text.lower()

    directed = len(re.findall(
        r"\b(you|your|you're|youre|u r\b|ur\s|@\w+|he|she|they|this person|that guy|that girl|that dude|that person)\b", lower))

    insults = len(re.findall(
        r"\b(idiot|stupid|loser|trash|garbage|pathetic|worthless|"
        r"ugly|disgusting|dumbass|dumb|moron|clown|lame|wack|"
        r"weirdo|creep|freak|psycho|delusional|braindead|brainless|"
        r"clueless|useless|incompetent|fool|foolish|dimwit|halfwit|"
        r"imbecile|bitch|hoe|whore|slut)\b", lower))

    profanity = len(re.findall(
        r"\b(fuck|fucking|fucked|fucker|fuckin|fck|"
        r"shit|shitty|shitting|bullshit|"
        r"ass|asshole|bitch|bitches|bitchy|"
        r"damn|damned|damnit|"
        r"dick|dickhead|cock|prick|"
        r"wtf|stfu|gtfo|lmfao)\b", lower))

    caps = sum(1 for c in text if c.isupper())
    cap_ratio = caps / max(1, len(text))

    # Score only counts when there is a DIRECTED indicator (you/your/@someone)
    # If nobody is being addressed, curse words and insults are just vibes.
    if directed > 0 and (insults + profanity) >= 2:
        score = min(1.0, (insults * 0.20) + (profanity * 0.10) + (0.15 if cap_ratio > 0.35 else 0.0))
    else:
        score = 0.0

    _mod_log.debug(
        '[MODERATION] Heuristic scores — directed=%d insults=%d profanity=%d cap_ratio=%.2f score=%.3f',
        directed, insults, profanity, cap_ratio, score
    )

    if score >= 0.6:
        _mod_log.info(
            '[MODERATION] QUARANTINE reason=high_toxicity_borderline score=%.3f '
            '(directed=%d insults=%d profanity=%d) text=%r',
            score, directed, insults, profanity, text[:120]
        )
        return ModResult("quarantine", "high_toxicity_borderline", score=score)

    if score >= 0.3:
        _mod_log.info(
            '[MODERATION] WARN reason=mild_negativity score=%.3f '
            '(directed=%d insults=%d profanity=%d) text=%r',
            score, directed, insults, profanity, text[:120]
        )
        return ModResult("warn", "mild_negativity", score=score)

    _mod_log.debug('[MODERATION] ALLOWED score=%.3f text=%r', score, text[:80])
    return ModResult("allow", "ok", score=score)


# ═══════════════════════════════════════════════════════
#  AI-like Scam Detection Scoring Engine
# ═══════════════════════════════════════════════════════
SCAM_SIGNAL_WEIGHTS = {
    "urgency_words":     0.15,   # "act now", "limited time", "hurry"
    "money_mention":     0.20,   # $, cash, crypto, bitcoin
    "external_link":     0.15,   # any URL
    "short_link":        0.25,   # bit.ly, tinyurl, etc.
    "contact_offsite":   0.20,   # "dm me", "whatsapp", "telegram"
    "too_good":          0.25,   # "guaranteed", "100%", "free money"
    "impersonation":     0.30,   # "official", "admin", "support team"
    "identity_request":  0.35,   # asking for passwords, SSN, bank info
    "pattern_match":     0.50,   # matched known scam pattern
    "autoblock_match":   0.80,   # matched hard-block scam phrase
}

_URGENCY_RE = re.compile(r"\b(act now|limited time|hurry|urgent|don'?t wait|immediately|asap|last chance|final warning)\b", re.I)
_MONEY_RE = re.compile(r"(\$\d+|\bcash\b|\bcrypto\b|\bbitcoin\b|\bbtc\b|\beth\b|\bmoney\b|\bpayment\b|\bfunds\b)", re.I)
_LINK_RE = re.compile(r"https?://\S+", re.I)
_SHORT_LINK_RE = re.compile(r"https?://(?:bit\.ly|tinyurl|t\.co|shorturl|rb\.gy|is\.gd|v\.gd|ow\.ly)/\S+", re.I)
_CONTACT_OFFSITE_RE = re.compile(r"\b(dm\s*me|whatsapp|telegram|text\s*me|call\s*me|snapchat\s*me)\b", re.I)
_TOO_GOOD_RE = re.compile(r"\b(guaranteed|100%|risk.free|free money|double your|no risk|easy money|passive income)\b", re.I)
_IMPERSONATION_RE = re.compile(r"\b(official|admin|support team|customer service|moderator|staff|verified account)\b", re.I)
_IDENTITY_REQ_RE = re.compile(r"\b(password|ssn|social security|bank account|credit card|routing number|pin number|login|credentials)\b", re.I)


def scan_scam_score(text: str) -> dict:
    """AI-like heuristic scam scorer. Returns a dict with total score (0-1),
    signals detected, and whether the message should be blocked/warned/allowed."""
    if not text or not text.strip():
        return {"score": 0, "signals": [], "decision": "allow"}

    signals = []
    total = 0.0

    # Hard pattern matches (highest priority)
    if _hit_any(SCAM_PHRASES_AUTOBLOCK, text):
        signals.append("autoblock_match")
        total += SCAM_SIGNAL_WEIGHTS["autoblock_match"]

    if _hit_any(SCAM_PATTERNS, text):
        signals.append("pattern_match")
        total += SCAM_SIGNAL_WEIGHTS["pattern_match"]

    # Heuristic signals
    if _URGENCY_RE.search(text):
        signals.append("urgency_words")
        total += SCAM_SIGNAL_WEIGHTS["urgency_words"]

    if _MONEY_RE.search(text):
        signals.append("money_mention")
        total += SCAM_SIGNAL_WEIGHTS["money_mention"]

    if _SHORT_LINK_RE.search(text):
        signals.append("short_link")
        total += SCAM_SIGNAL_WEIGHTS["short_link"]
    elif _LINK_RE.search(text):
        signals.append("external_link")
        total += SCAM_SIGNAL_WEIGHTS["external_link"]

    if _CONTACT_OFFSITE_RE.search(text):
        signals.append("contact_offsite")
        total += SCAM_SIGNAL_WEIGHTS["contact_offsite"]

    if _TOO_GOOD_RE.search(text):
        signals.append("too_good")
        total += SCAM_SIGNAL_WEIGHTS["too_good"]

    if _IMPERSONATION_RE.search(text):
        signals.append("impersonation")
        total += SCAM_SIGNAL_WEIGHTS["impersonation"]

    if _IDENTITY_REQ_RE.search(text):
        signals.append("identity_request")
        total += SCAM_SIGNAL_WEIGHTS["identity_request"]

    total = min(1.0, total)

    if total >= 0.6:
        decision = "block"
    elif total >= 0.3:
        decision = "warn"
    else:
        decision = "allow"

    return {"score": round(total, 2), "signals": signals, "decision": decision}


# ═══════════════════════════════════════════════════════
#  Trust Score Calculator
# ═══════════════════════════════════════════════════════
def calculate_trust_score(user) -> int:
    """Calculate a 0-100 trust score for a user based on account signals.
    Higher = more trustworthy. Factors:
      - Account age (older = more trust)
      - Email verified (bonus)
      - Verified human badge (big bonus)
      - Scam flags (penalty)
      - Negativity warnings (penalty)
      - Profile completeness (bonus)
      - Has avatar (bonus)
    """
    score = 50  # baseline

    # Account age bonus (up to +20)
    created = getattr(user, 'created_at', None)
    if created:
        from datetime import datetime
        now = datetime.now(timezone.utc)
        # SQLite returns naive datetimes — normalise before subtracting
        if created.tzinfo is None:
            now = datetime.utcnow()
        age_days = (now - created).days
        score += min(20, age_days // 7)  # +1 per week, max +20

    # Verified human badge (+15)
    if getattr(user, 'is_verified_human', False):
        score += 15

    # Profile completeness
    if getattr(user, 'bio', None):
        score += 3
    if getattr(user, 'avatar_url', None):
        score += 3
    if getattr(user, 'display_name', None):
        score += 2

    # Professional account bonus
    if getattr(user, 'account_type', '') == 'professional':
        score += 5

    # Scam flags penalty (-15 each)
    scam_flags = getattr(user, 'scam_flags', 0) or 0
    score -= scam_flags * 15

    # Negativity warnings penalty (-8 each)
    warnings = getattr(user, 'negativity_warnings', 0) or 0
    score -= warnings * 8

    # Burn account penalty
    if getattr(user, 'is_burn_account', False):
        score -= 20

    return max(0, min(100, score))


# ═══════════════════════════════════════════════════════
#  Anonymous Alias Generator
# ═══════════════════════════════════════════════════════
_ANON_ADJECTIVES = [
    "Shadow", "Ghost", "Phantom", "Mystic", "Silent", "Hidden",
    "Neon", "Cosmic", "Eclipse", "Vapor", "Storm", "Crystal",
    "Velvet", "Cyber", "Lunar", "Solar", "Arctic", "Ember",
]
_ANON_NOUNS = [
    "Viper", "Wolf", "Fox", "Hawk", "Raven", "Phoenix",
    "Tiger", "Panther", "Cobra", "Falcon", "Dragon", "Lynx",
    "Owl", "Bear", "Eagle", "Shark", "Lion", "Jaguar",
]

def generate_anonymous_alias() -> str:
    """Generate a random anonymous alias like 'Shadow Viper' or 'Cosmic Phoenix'."""
    import random
    return f"{random.choice(_ANON_ADJECTIVES)} {random.choice(_ANON_NOUNS)}"


def get_trust_badge(score: int) -> dict:
    """Return badge info based on trust score."""
    if score >= 85:
        return {"label": "Trusted", "icon": "🛡️", "color": "#00e676", "tier": "trusted"}
    elif score >= 65:
        return {"label": "Established", "icon": "✓", "color": "#4fc3f7", "tier": "established"}
    elif score >= 40:
        return {"label": "New", "icon": "●", "color": "#ffa726", "tier": "new"}
    else:
        return {"label": "Caution", "icon": "⚠", "color": "#ef5350", "tier": "caution"}
