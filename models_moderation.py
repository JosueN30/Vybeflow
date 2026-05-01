from datetime import datetime, timedelta, timezone
from functools import wraps
from flask import jsonify, session
from __init__ import db


# ─────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────

_BLOCK_DURATIONS = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

SLOW_MODE_GAP_SECONDS = 10  # enforced gap between a user's messages


# ─────────────────────────────────────────────────────────
# Models
# ─────────────────────────────────────────────────────────

class ModerationEvent(db.Model):
    __tablename__ = "moderation_event"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, index=True, nullable=False)
    content_type = db.Column(db.String(24), nullable=False)   # post/comment/dm
    content_id = db.Column(db.Integer, nullable=True)
    action = db.Column(db.String(24), nullable=False)         # allow/block/quarantine/throttle
    reason = db.Column(db.String(255), nullable=False)
    score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)


class UserRestriction(db.Model):
    __tablename__ = "user_restriction"
    user_id = db.Column(db.Integer, primary_key=True)
    can_post_after = db.Column(db.DateTime, nullable=True)
    can_comment_after = db.Column(db.DateTime, nullable=True)
    strikes_24h = db.Column(db.Integer, default=0, nullable=False)
    strikes_reset_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    # Temporary full block applied by apply_block()
    restricted_until = db.Column(db.DateTime, nullable=True)
    # Slow-mode: timestamp of the user's most recent message
    last_message_at = db.Column(db.DateTime, nullable=True)

    @staticmethod
    def _as_aware(dt):
        """Normalise a potentially naive datetime to UTC-aware."""
        if dt is not None and dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt

    def is_blocked(self, kind: str) -> bool:
        """Return True if the user is currently blocked from the given action.

        Checks restricted_until first (full block), then action-specific columns.
        kind: 'post' | 'comment' | 'message'
        """
        now = datetime.now(timezone.utc)
        ru = self._as_aware(self.restricted_until)
        if ru and now < ru:
            return True
        if kind == "post":
            cpa = self._as_aware(self.can_post_after)
            if cpa and now < cpa:
                return True
        if kind == "comment":
            cca = self._as_aware(self.can_comment_after)
            if cca and now < cca:
                return True
        return False


# ─────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────

def get_or_create_restriction(user_id: int) -> UserRestriction:
    r = db.session.get(UserRestriction, user_id)
    if not r:
        try:
            r = UserRestriction(user_id=user_id)
            db.session.add(r)
            db.session.commit()
        except Exception:
            db.session.rollback()
            # Another concurrent request may have inserted first — retry fetch
            r = db.session.get(UserRestriction, user_id)
            if not r:
                raise
    return r


# ─────────────────────────────────────────────────────────
# 1. Soft Mute (24 h)
# ─────────────────────────────────────────────────────────

def apply_soft_mute(user_id: int) -> datetime:
    """Mute a user for 24 hours by setting User.muted_until.

    Returns the muted_until timestamp that was set.
    Raises ValueError if the user does not exist.
    """
    from models import User
    user = db.session.get(User, user_id)
    if not user:
        raise ValueError(f"User {user_id} not found")
    user.muted_until = datetime.now(timezone.utc) + timedelta(hours=24)
    db.session.commit()
    return user.muted_until


def check_soft_mute(user) -> tuple:
    """Check whether a User is currently soft-muted.

    Args:
        user: a User model instance

    Returns:
        (is_muted: bool, muted_until: datetime | None)
    """
    if user.muted_until:
        _muted = user.muted_until
        _now_muted = datetime.utcnow() if _muted.tzinfo is None else datetime.now(timezone.utc)
        if _now_muted < _muted:
            return True, _muted
    return False, None


# ─────────────────────────────────────────────────────────
# 2. Temporary Block (1 h / 1 d / 1 w)
# ─────────────────────────────────────────────────────────

def apply_block(user_id: int, duration: str) -> datetime:
    """Block a user for a fixed interval by setting UserRestriction.restricted_until.

    Args:
        user_id:  target user's ID
        duration: '1h', '1d', or '1w'

    Returns:
        The restricted_until datetime that was set.
    Raises:
        ValueError if duration is not one of the supported values.
    """
    if duration not in _BLOCK_DURATIONS:
        raise ValueError(
            f"Invalid duration '{duration}'. Supported values: {list(_BLOCK_DURATIONS)}"
        )
    r = get_or_create_restriction(user_id)
    r.restricted_until = datetime.now(timezone.utc) + _BLOCK_DURATIONS[duration]
    db.session.commit()
    return r.restricted_until


# ─────────────────────────────────────────────────────────
# 3. Slow Mode (10-second message gap)
# ─────────────────────────────────────────────────────────

def slow_mode_required(fn):
    """Route decorator that enforces a 10-second gap between a user's messages.

    Reads session['user_id'] to identify the caller. If the gap since
    UserRestriction.last_message_at has not elapsed, returns HTTP 429 with a
    JSON body containing 'retry_after' (seconds to wait).

    Usage::

        @messaging_bp.route("/api/messages/send", methods=["POST"])
        @slow_mode_required
        def send_message():
            ...
    """
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user_id = session.get("user_id")
        if user_id:
            r = get_or_create_restriction(user_id)
            now = datetime.now(timezone.utc)
            if r.last_message_at:
                lma = r.last_message_at
                if lma.tzinfo is None:
                    lma = lma.replace(tzinfo=timezone.utc)
                elapsed = (now - lma).total_seconds()
                if elapsed < SLOW_MODE_GAP_SECONDS:
                    wait = int(SLOW_MODE_GAP_SECONDS - elapsed) + 1
                    return jsonify(
                        error="slow_mode",
                        message=f"Slow mode is on. Wait {wait}s before sending another message.",
                        retry_after=wait,
                    ), 429
            # Execute the route first; only consume the slow-mode slot on success
            response = fn(*args, **kwargs)
            status_code = response[1] if isinstance(response, tuple) and len(response) > 1 else 200
            if status_code < 300:
                r.last_message_at = now
                try:
                    db.session.commit()
                except Exception:
                    db.session.rollback()
            return response
        return fn(*args, **kwargs)
    return wrapper
