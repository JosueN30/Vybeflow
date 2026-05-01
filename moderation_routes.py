from datetime import datetime, timedelta, timezone
from flask import Blueprint, request, jsonify, render_template, session, redirect, url_for, flash
from sqlalchemy import func

from models_moderation import db, ModerationEvent, get_or_create_restriction
from moderation_engine import moderate_text

mod_bp = Blueprint("mod_bp", __name__)

# You need tables for Post/Comment in your app. Replace these imports with yours.
# from your_models import Post, Comment

def _now():
    return datetime.now(timezone.utc)

def _add_event(user_id: int, content_type: str, content_id: int | None, action: str, reason: str, score=None):
    ev = ModerationEvent(
        user_id=user_id, content_type=content_type, content_id=content_id,
        action=action, reason=reason, score=score
    )
    db.session.add(ev)
    db.session.commit()

def _reset_strikes_if_needed(r):
    now = _now()
    reset_at = r.strikes_reset_at
    if reset_at is not None:
        if reset_at.tzinfo is None:
            reset_at = reset_at.replace(tzinfo=timezone.utc)
        if now >= reset_at:
            r.strikes_24h = 0
            r.strikes_reset_at = now + timedelta(hours=24)

def _apply_strike_and_cooldown(user_id: int, kind: str, seconds: int):
    r = get_or_create_restriction(user_id)
    _reset_strikes_if_needed(r)
    r.strikes_24h += 1

    until = _now() + timedelta(seconds=seconds)
    if kind == "post":
        r.can_post_after = max(r.can_post_after or _now(), until)
    else:
        r.can_comment_after = max(r.can_comment_after or _now(), until)

    # escalating penalties (automatic)
    if r.strikes_24h >= 3:
        # short lock
        r.can_comment_after = max(r.can_comment_after or _now(), _now() + timedelta(minutes=30))
    if r.strikes_24h >= 6:
        r.can_post_after = max(r.can_post_after or _now(), _now() + timedelta(hours=6))

    db.session.commit()

def _user_rate_limited(user_id: int, content_type: str) -> bool:
    # per user per minute
    one_min_ago = _now() - timedelta(minutes=1)
    cnt = (db.session.query(func.count(ModerationEvent.id))
           .filter(ModerationEvent.user_id == user_id,
                   ModerationEvent.content_type == content_type,
                   ModerationEvent.created_at >= one_min_ago)
           .scalar())
    return cnt >= 15

def _reply_storm(target_key: str) -> bool:
    # target_key can be "post:123" or "user:45" etc. store it in reason field or content_id mapping
    # We'll use reason tag format: "dogpile_target=<target_key>"
    one_min_ago = _now() - timedelta(seconds=60)
    cnt = (db.session.query(func.count(ModerationEvent.id))
           .filter(ModerationEvent.reason == f"dogpile_target={target_key}",
                   ModerationEvent.created_at >= one_min_ago)
           .scalar())
    return cnt >= 8

@mod_bp.post("/api/moderate/comment")
def moderate_comment_api():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        user_id = int(user_id)
    except (ValueError, TypeError):
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    text = (payload.get("text") or "")[:5000]
    target_post_id = payload.get("post_id")
    target_user_id = payload.get("target_user_id")  # optional: who they reply to

    r = get_or_create_restriction(user_id)
    if r.is_blocked("comment"):
        return jsonify({"ok": False, "error": "cooldown_active"}), 429

    if _user_rate_limited(user_id, "comment"):
        _add_event(user_id, "comment", None, "throttle", "rate_limit_user")
        _apply_strike_and_cooldown(user_id, "comment", 60)
        return jsonify({"ok": False, "error": "slow_down"}), 429

    # Dogpile throttle: too many replies to same target in short time
    if target_post_id and _reply_storm(f"post:{target_post_id}"):
        _add_event(user_id, "comment", None, "throttle", f"dogpile_target=post:{target_post_id}")
        _apply_strike_and_cooldown(user_id, "comment", 120)
        return jsonify({"ok": False, "error": "thread_is_hot_try_later"}), 429

    if target_user_id and _reply_storm(f"user:{target_user_id}"):
        _add_event(user_id, "comment", None, "throttle", f"dogpile_target=user:{target_user_id}")
        _apply_strike_and_cooldown(user_id, "comment", 180)
        return jsonify({"ok": False, "error": "user_is_being_piled_on_try_later"}), 429

    mod = moderate_text(text)

    if mod.decision == "allow":
        _add_event(user_id, "comment", None, "allow", "ok", score=mod.score)
        return jsonify({"ok": True, "action": "allow"}), 200

    if mod.decision == "quarantine":
        _add_event(user_id, "comment", None, "quarantine", mod.reason, score=mod.score)
        # quarantine: save but only show to author + moderators
        return jsonify({"ok": True, "action": "quarantine", "reason": mod.reason}), 200

    # block or throttle
    _add_event(user_id, "comment", None, "block", mod.reason, score=mod.score)
    _apply_strike_and_cooldown(user_id, "comment", 300)
    return jsonify({"ok": False, "error": "blocked", "reason": mod.reason}), 403


# ── Admin Moderation Dashboard ───────────────────────────────────────────────

def _require_admin():
    """Return None if the current session user is an admin (per DB), otherwise a redirect."""
    username = (session.get("username") or "").strip()
    if not username:
        flash("Admin access required.", "error")
        return redirect(url_for("login"))
    from models import User
    user = User.query.filter_by(username=username).first()
    if not user or not getattr(user, "is_admin", False):
        flash("Admin access required.", "error")
        return redirect(url_for("login"))
    return None


@mod_bp.get("/admin/moderation")
def admin_moderation_dashboard():
    gate = _require_admin()
    if gate:
        return gate

    try:
        from models import User, Post
        # Recent moderation events
        recent_events = (
            ModerationEvent.query.order_by(ModerationEvent.created_at.desc()).limit(100).all()
        )

        # Users with highest strike counts
        flagged_users = (
            db.session.query(ModerationEvent.user_id, func.count(ModerationEvent.id).label("cnt"))
            .filter(ModerationEvent.action.in_(["block", "quarantine"]))
            .group_by(ModerationEvent.user_id)
            .order_by(func.count(ModerationEvent.id).desc())
            .limit(20)
            .all()
        )

        # Banned / suspended users
        banned_users = User.query.filter(
            (User.is_banned == True) | (User.is_suspended == True)
        ).order_by(User.id.desc()).limit(50).all() if hasattr(User, "is_banned") else []

        # Posts pending review (shadowbanned / flagged)
        flagged_posts = Post.query.filter(
            Post.is_shadowbanned == True
        ).order_by(Post.id.desc()).limit(50).all() if hasattr(Post, "is_shadowbanned") else []

        stats = {
            "total_events": ModerationEvent.query.count(),
            "blocked_today": ModerationEvent.query.filter(
                ModerationEvent.action == "block",
                ModerationEvent.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            ).count(),
            "quarantined_today": ModerationEvent.query.filter(
                ModerationEvent.action == "quarantine",
                ModerationEvent.created_at >= datetime.now(timezone.utc) - timedelta(hours=24),
            ).count(),
            "banned_users": len(banned_users),
            "flagged_posts": len(flagged_posts),
        }

    except Exception as e:
        recent_events, flagged_users, banned_users, flagged_posts = [], [], [], []
        stats = {"error": str(e)}

    return render_template(
        "admin_moderation.html",
        recent_events=recent_events,
        flagged_users=flagged_users,
        banned_users=banned_users,
        flagged_posts=flagged_posts,
        stats=stats,
    )


@mod_bp.post("/admin/moderation/lift-ban/<int:user_id>")
def admin_lift_ban(user_id: int):
    gate = _require_admin()
    if gate:
        return gate
    try:
        from models import User
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"ok": False, "error": "User not found"}), 404
        if hasattr(user, "is_banned"):
            user.is_banned = False
        if hasattr(user, "is_suspended"):
            user.is_suspended = False
        if hasattr(user, "negativity_warnings"):
            user.negativity_warnings = 0
        if hasattr(user, "appeal_pending"):
            user.appeal_pending = False
        db.session.commit()
        return jsonify({"ok": True, "message": f"Ban lifted for {user.username}"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500


@mod_bp.post("/admin/moderation/delete-post/<int:post_id>")
def admin_delete_post(post_id: int):
    gate = _require_admin()
    if gate:
        return gate
    try:
        from models import Post
        post = db.session.get(Post, post_id)
        if not post:
            return jsonify({"ok": False, "error": "Post not found"}), 404
        db.session.delete(post)
        db.session.commit()
        return jsonify({"ok": True, "message": f"Post {post_id} deleted"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"ok": False, "error": str(e)}), 500
