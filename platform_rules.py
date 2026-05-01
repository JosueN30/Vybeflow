"""
platform_rules.py – VybeFlow Platform Policy Engine
=====================================================
Enforces VybeFlow's unique platform rules:

ALLOWED (no restrictions):
  - Multiple accounts from same device / IP / phone / computer
  - Rapid friend requests (no rate limit on friend requests)
  - Posting same content repeatedly (copy-paste, same link in groups, promo)
  - Logging in from any location or different device
  - Creative / artistic usernames (any name you want)

AI-ENFORCED (automatic detection):
  - Fake accounts → 3 warnings then ban
  - Fake identity / impersonation → strict AI detection
  - Scam accounts → the ONLY thing users can report

MESSAGING RULE:
  - Anyone can message anyone, BUT messages to strangers are held
    in a "message request" queue until the recipient:
    (a) accepts the friend request, OR
    (b) manually approves the message
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone


# ═══════════════════════════════════════════════════════
#  Fake Account Detection (AI Heuristic Engine)
# ═══════════════════════════════════════════════════════

@dataclass
class FakeAccountSignal:
    signal: str
    weight: float
    description: str


FAKE_ACCOUNT_SIGNALS = {
    "no_avatar":           FakeAccountSignal("no_avatar",           0.10, "No profile picture uploaded"),
    "no_bio":              FakeAccountSignal("no_bio",              0.08, "Empty bio"),
    "generic_bio":         FakeAccountSignal("generic_bio",         0.12, "Bio matches generic bot patterns"),
    "spam_username":       FakeAccountSignal("spam_username",       0.15, "Username follows spam patterns (random chars, numbers)"),
    "rapid_mass_follow":   FakeAccountSignal("rapid_mass_follow",   0.20, "Following hundreds of users rapidly"),
    "no_posts_high_follow":FakeAccountSignal("no_posts_high_follow",0.18, "Following many users but zero posts"),
    "duplicate_content":   FakeAccountSignal("duplicate_content",   0.15, "Sending identical messages/posts to many users"),
    "scam_content":        FakeAccountSignal("scam_content",        0.25, "Content flagged as scam by AI"),
    "zero_engagement":     FakeAccountSignal("zero_engagement",     0.10, "Account has no real engagement (no likes, no real replies)"),
    "new_account_burst":   FakeAccountSignal("new_account_burst",   0.12, "Brand new account with burst of activity"),
}

# Threshold: >= 0.55 triggers a warning
FAKE_ACCOUNT_WARN_THRESHOLD = 0.55
# Max warnings before ban
FAKE_ACCOUNT_MAX_WARNINGS = 3

# Generic bot bio patterns
_GENERIC_BIO_PATTERNS = [
    r"^(hi|hello|hey)\s*$",
    r"^follow\s+(me|back|4follow)\b",
    r"^f4f\b",
    r"^dm\s+(?:me|for)\b.*(?:promo|collab|deals?|business)",
    r"^(?:i\s+)?follow\s+back\b",
    r"^(?:click|visit|check)\s+(?:my\s+)?(?:link|bio|profile)\b",
]

# Spam username patterns (random alphanumeric, excessive numbers)
_SPAM_USERNAME_PATTERNS = [
    r"^[a-z]{2,4}\d{5,}$",           # ab12345
    r"^user\d{4,}$",                  # user8274628
    r"^\d{6,}$",                      # 827462816
    r"^[a-z]{1,3}[_\-]\d{4,}$",      # ab_12345
    r"^(?:bot|spam|fake|test)\d*$",   # bot123
]


def scan_fake_account(user) -> dict:
    """AI heuristic scanner for fake accounts.

    Returns:
        {
            "score": float (0.0 - 1.0),
            "signals": [str],
            "is_suspicious": bool,
            "recommendation": "ok" | "warn" | "ban"
        }
    """
    signals = []
    total = 0.0

    username = getattr(user, 'username', '') or ''
    bio = getattr(user, 'bio', '') or ''
    avatar_url = getattr(user, 'avatar_url', '') or ''
    trust_score = getattr(user, 'trust_score', 50) or 50
    scam_flags = getattr(user, 'scam_flags', 0) or 0
    fake_warnings = getattr(user, 'fake_account_warnings', 0) or 0

    # No avatar
    if not avatar_url or 'VFlogo_clean' in avatar_url:
        signals.append("no_avatar")
        total += FAKE_ACCOUNT_SIGNALS["no_avatar"].weight

    # No bio or default bio
    _empty_bios = {'', 'vybeflow member ✨', 'vybeflow member.', 'vybeflow member'}
    if not bio or bio.strip().lower() in _empty_bios:
        signals.append("no_bio")
        total += FAKE_ACCOUNT_SIGNALS["no_bio"].weight

    # Generic bot bio
    for pattern in _GENERIC_BIO_PATTERNS:
        if re.search(pattern, bio.strip(), re.IGNORECASE):
            signals.append("generic_bio")
            total += FAKE_ACCOUNT_SIGNALS["generic_bio"].weight
            break

    # Spam-like username
    for pattern in _SPAM_USERNAME_PATTERNS:
        if re.search(pattern, username, re.IGNORECASE):
            signals.append("spam_username")
            total += FAKE_ACCOUNT_SIGNALS["spam_username"].weight
            break

    # Previous scam flags compound the score
    if scam_flags >= 2:
        signals.append("scam_content")
        total += FAKE_ACCOUNT_SIGNALS["scam_content"].weight

    # Low trust score bonus penalty
    if trust_score < 30:
        signals.append("zero_engagement")
        total += FAKE_ACCOUNT_SIGNALS["zero_engagement"].weight

    # Account age factor
    created = getattr(user, 'created_at', None)
    if created:
        _now_pr = datetime.utcnow() if created.tzinfo is None else datetime.now(timezone.utc)
        age_hours = (_now_pr - created).total_seconds() / 3600
        if age_hours < 24 and scam_flags > 0:
            signals.append("new_account_burst")
            total += FAKE_ACCOUNT_SIGNALS["new_account_burst"].weight

    total = min(1.0, total)

    # Determine recommendation
    if fake_warnings >= FAKE_ACCOUNT_MAX_WARNINGS:
        recommendation = "ban"
    elif total >= FAKE_ACCOUNT_WARN_THRESHOLD:
        recommendation = "warn"
    else:
        recommendation = "ok"

    return {
        "score": round(total, 2),
        "signals": signals,
        "is_suspicious": total >= FAKE_ACCOUNT_WARN_THRESHOLD,
        "recommendation": recommendation,
    }


def apply_fake_account_warning(user) -> dict:
    """Issue a fake account warning to a user. Returns status.
    After 3 warnings, the account is banned."""
    from __init__ import db

    scan = scan_fake_account(user)
    if scan["recommendation"] == "ok":
        return {"action": "none", "scan": scan}

    # Increment warning count
    user.fake_account_warnings = (user.fake_account_warnings or 0) + 1

    # Track reasons
    existing_reasons = []
    if user.fake_account_reasons:
        try:
            existing_reasons = json.loads(user.fake_account_reasons)
        except (json.JSONDecodeError, TypeError):
            existing_reasons = []
    existing_reasons.append({
        "warning_number": user.fake_account_warnings,
        "signals": scan["signals"],
        "score": scan["score"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    user.fake_account_reasons = json.dumps(existing_reasons)

    # Trust score penalty per warning
    user.trust_score = max(0, (user.trust_score or 50) - 15)

    action = "warning"

    # Ban after 3 warnings
    if user.fake_account_warnings >= FAKE_ACCOUNT_MAX_WARNINGS:
        user.is_banned = True
        user.banned_at = datetime.now(timezone.utc)
        user.ban_reason = f"AI detected fake account after {FAKE_ACCOUNT_MAX_WARNINGS} warnings. Signals: {', '.join(scan['signals'])}"
        action = "banned"

    db.session.commit()

    return {
        "action": action,
        "warnings": user.fake_account_warnings,
        "max_warnings": FAKE_ACCOUNT_MAX_WARNINGS,
        "remaining": max(0, FAKE_ACCOUNT_MAX_WARNINGS - user.fake_account_warnings),
        "scan": scan,
    }


# ═══════════════════════════════════════════════════════
#  Fake Identity / Impersonation Detection
# ═══════════════════════════════════════════════════════
# People can create ANY name they want (creative names are fine).
# The AI only blocks fake IDENTITIES — impersonating real people,
# brands, officials, or claiming to be someone you're not.

_IMPERSONATION_PATTERNS = [
    # Claiming to be official staff / support
    r"\b(?:official\s+)?(?:vybeflow|vybe\s*flow)\s+(?:admin|staff|support|team|ceo|founder|mod|moderator)\b",
    # Claiming to be verified / blue check
    r"\b(?:verified|✓|✔|☑)\s*(?:account|official|real)\b",
    # Impersonating known roles
    r"\b(?:i\s+am|i'm|im)\s+(?:the\s+)?(?:admin|owner|founder|ceo|staff|moderator|support)\s+(?:of|at|for)\b",
    # Posing as customer support
    r"\b(?:customer\s+(?:support|service|care)|tech\s+support|help\s+desk)\b.*(?:contact|call|dm|message)\b",
    # Celebrity impersonation patterns (claiming to be specific famous people)
    r"\b(?:i\s+am|i'm|im)\s+(?:the\s+real|actually)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b",
]

# These are ALLOWED — creative names, nicknames, stage names, anything artistic
_ALLOWED_NAME_PATTERNS = [
    r".*",  # Literally anything — the rule is: any name you want is fine
]


def check_fake_identity(display_name: str = "", bio: str = "") -> dict:
    """Check if a user's profile indicates fake identity / impersonation.

    NOTE: Creative names are ALWAYS allowed. Only impersonation is flagged.

    Returns:
        {
            "is_impersonation": bool,
            "reason": str or None,
            "severity": "none" | "warning" | "block"
        }
    """
    combined = f"{display_name} {bio}".strip()
    if not combined:
        return {"is_impersonation": False, "reason": None, "severity": "none"}

    for pattern in _IMPERSONATION_PATTERNS:
        if re.search(pattern, combined, re.IGNORECASE):
            return {
                "is_impersonation": True,
                "reason": f"Profile appears to impersonate an official role or identity. Pattern: {pattern[:50]}",
                "severity": "block",
            }

    return {"is_impersonation": False, "reason": None, "severity": "none"}


# ═══════════════════════════════════════════════════════
#  Message Gating: Stranger Messages
# ═══════════════════════════════════════════════════════
# Anyone can send a message to anyone, but messages from strangers
# go into a "message request" queue. The recipient must accept the
# friend request or approve the message for it to appear in their inbox.

def check_message_permission(sender_id: int, recipient_id: int) -> dict:
    """Determine whether a message should be delivered directly or held.

    Rules:
    - If they are friends (accepted FriendRequest) → deliver immediately
    - If sender follows recipient AND recipient follows sender → deliver
    - Otherwise → hold in message request queue

    Returns:
        {
            "allowed": True/False (always True — anyone CAN message),
            "delivery": "direct" | "request",
            "reason": str
        }
    """
    from models import FriendRequest, Follow
    from __init__ import db

    # Check if they are friends (accepted friend request in either direction)
    friendship = FriendRequest.query.filter(
        db.or_(
            db.and_(FriendRequest.sender_id == sender_id,
                    FriendRequest.receiver_id == recipient_id,
                    FriendRequest.status == "accepted"),
            db.and_(FriendRequest.sender_id == recipient_id,
                    FriendRequest.receiver_id == sender_id,
                    FriendRequest.status == "accepted"),
        )
    ).first()

    if friendship:
        return {
            "allowed": True,
            "delivery": "direct",
            "reason": "friends",
        }

    # Check mutual follows (they know each other)
    mutual = (
        Follow.query.filter_by(follower_id=sender_id, following_id=recipient_id).first()
        and Follow.query.filter_by(follower_id=recipient_id, following_id=sender_id).first()
    )

    if mutual:
        return {
            "allowed": True,
            "delivery": "direct",
            "reason": "mutual_followers",
        }

    # Stranger — message goes to request queue
    return {
        "allowed": True,
        "delivery": "request",
        "reason": "stranger_message_held_for_approval",
    }


# ═══════════════════════════════════════════════════════
#  Login Policy: No Device / IP / Location Restrictions
# ═══════════════════════════════════════════════════════
# VybeFlow explicitly allows:
#   - Multiple accounts from same device, phone, computer, IP
#   - Login from any location or different device
#   - No IP bans, no device bans, no geo-blocks

def check_login_allowed(user) -> dict:
    """Check if a user is allowed to log in.

    Only hard-banned accounts (3 AI fake-account strikes) are blocked here.
    Suspended accounts (negativity timeout) are allowed to log in so the user
    can see the suspension notice and submit an appeal while authenticated.
    IP / device / location checks do NOT belong here — VybeFlow explicitly
    allows login from any device or network.
    """
    if getattr(user, 'is_banned', False):
        return {
            "allowed": False,
            "reason": f"BANNED: {getattr(user, 'ban_reason', 'Account banned for repeated violations')}",
        }

    return {"allowed": True, "reason": "ok"}


# ═══════════════════════════════════════════════════════
#  Content Policy: Repetitive Posting is ALLOWED
# ═══════════════════════════════════════════════════════
# VybeFlow allows:
#   - Same link posted in many groups
#   - Copy-paste comments everywhere
#   - Promoting something aggressively
#   - Rapid friend requests to anyone (including strangers)
#
# The moderation engine only blocks: scams, threats, hate speech,
# doxxing — NOT repetitive posting or aggressive promotion.

def check_content_allowed(text: str) -> dict:
    """Check if content is allowed under VybeFlow rules.

    Repetitive posting, copy-paste comments, same links in many groups,
    and aggressive promotion are ALL ALLOWED.

    Only scam content, threats, doxxing, and hate speech are blocked.
    """
    from moderation_engine import moderate_text, scan_scam_score

    # Run scam detection
    scam = scan_scam_score(text)
    if scam['decision'] == 'block':
        return {
            "allowed": False,
            "reason": "scam_detected",
            "scam_scan": scam,
        }

    # Run hate speech / threat detection
    mod = moderate_text(text)
    if mod.decision == 'block':
        return {
            "allowed": False,
            "reason": mod.reason,
        }

    # Everything else is allowed — including repetitive/promotional content
    return {"allowed": True, "reason": "ok"}


# ═══════════════════════════════════════════════════════
#  Platform Rules Summary (for API / UI display)
# ═══════════════════════════════════════════════════════

PLATFORM_RULES = {
    "multiple_accounts": {
        "allowed": True,
        "description": "Multiple accounts from the same device, phone, computer, or internet connection are allowed.",
    },
    "rapid_friend_requests": {
        "allowed": True,
        "description": "Sending many friend requests quickly (including to strangers) is allowed.",
    },
    "messaging_strangers": {
        "allowed": True,
        "description": "You can message anyone, but messages to strangers are held as 'message requests' until the recipient accepts your friend request or approves the message.",
    },
    "repetitive_posting": {
        "allowed": True,
        "description": "You can post the same content repeatedly, share the same link in many groups, copy-paste comments, and promote aggressively.",
    },
    "reporting": {
        "scam_only": True,
        "description": "The only accounts/content users can report are scam accounts. All other moderation is handled by AI.",
    },
    "creative_names": {
        "allowed": True,
        "description": "You can create any username or display name you want. Creative and artistic names are welcome.",
    },
    "fake_identity": {
        "blocked": True,
        "description": "AI strictly detects fake identities and impersonation. You cannot claim to be an official, admin, or impersonate another person.",
    },
    "fake_accounts": {
        "ai_detected": True,
        "warnings_before_ban": 3,
        "description": "AI detects fake/bot accounts. You get 3 warnings before being permanently banned.",
    },
    "login_anywhere": {
        "allowed": True,
        "description": "You can log in from any location, any device, anywhere in the world. No IP or device restrictions.",
    },
}
