"""
moderation.py – Consent & Takedown System + AI Admin Moderation
================================================================
Blueprint: mod_bp

Platform Policy: Users can ONLY report SCAM accounts/content.
All other moderation (hate speech, threats, fake accounts, etc.)
is handled automatically by VybeFlow's AI systems.

Endpoints
─────────
PUBLIC / USER:
  GET  /takedown                    → Takedown request form
  POST /takedown                    → Submit takedown request
  GET  /takedown/status             → View user's own requests

  POST /api/report                  → Report a post for SCAM only (JSON)

ADMIN (is_admin flag on User):
  GET  /admin/moderation            → Dashboard: reports, takedowns, AI log
  POST /admin/moderation/report/<id>/action   → Resolve a report
  POST /admin/moderation/takedown/<id>/action → Resolve a takedown
  POST /admin/moderation/ai/scan    → Trigger bulk AI scan
  POST /admin/moderation/post/<id>/override   → Override AI action
"""

import re
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    request,
    jsonify,
    session,
    redirect,
    url_for,
    render_template,
    flash,
    current_app,
)

mod_bp = Blueprint("moderation", __name__)


# ──────────────────────────────────────────────────
# Helpers — delegate to utils/auth for session lookups
# ──────────────────────────────────────────────────
from utils.auth import get_session_user as _get_user, require_auth_page, require_auth_json

# Backward-compatible aliases used by routes in this file
def login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user = _get_user()
        if not user:
            flash("Please log in first.", "warning")
            return redirect(url_for("login"))
        return fn(*a, _user=user, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        user = _get_user()
        if not user:
            return jsonify(error="Login required"), 401
        if not getattr(user, "is_admin", False):
            return jsonify(error="Admin access required"), 403
        return fn(*a, _user=user, **kw)
    return wrapper


# ──────────────────────────────────────────────────
#  AI Content Scanner (rule-based + keyword heuristic)
# ──────────────────────────────────────────────────
# Categories that the scanner can flag
AI_CATEGORIES = {
    "hate_speech":   0.0,
    "harassment":    0.0,
    "violence":      0.0,
    "self_harm":     0.0,
    "sexual":        0.0,
    "spam":          0.0,
    "misinformation": 0.0,
}

# Weighted keyword lists (kept intentionally mild for the codebase)
_HATE_WORDS = [
    r"\bslur\b", r"\bracist\b", r"\bbigot\b",
]
_HARASS_WORDS = [
    r"\bkill\s*yourself\b", r"\bkys\b", r"\bthreat(?:en)?\b",
]
_VIOLENCE_WORDS = [
    r"\bbomb\b", r"\bshoot(?:ing)?\b", r"\bmassacre\b",
]
_SPAM_WORDS = [
    r"\bfree\s*money\b", r"\bcrypto\s*airdrop\b", r"\bclick\s*(?:here|now)\b",
    r"\bfollow\s*(?:me|back)\b.*\bfollow\s*(?:me|back)\b",
]

# ── Energy Filter: high-intensity / aggressive language ──────────────────────
# Triggered when user.energy_filter_enabled is True (opt-in).
_ENERGY_WORDS = [
    r"\bkill\b", r"\bdestroy\b", r"\bannihilate\b", r"\bwreck\b",
    r"\bsmash\b", r"\bcrush\b", r"\bobliterate\b",
    r"\brage\b", r"\bberserk\b", r"\bfurious\b",
    r"!{3,}",        # three or more consecutive exclamation marks
    r"[A-Z]{5,}",    # five or more consecutive uppercase letters
]

ENERGY_FILTER_THRESHOLD = 2   # minimum pattern hits to block


def energy_filter_check(text: str, user=None) -> dict:
    """Check whether *text* contains high-intensity language.

    If *user* is provided and ``user.energy_filter_enabled`` is ``False`` the
    check is skipped and the content is allowed immediately.

    Returns::

        {
            "allowed": bool,
            "hits": int,               # number of energy patterns matched
            "blocked_reason": str|None # human-readable reason when blocked
        }
    """
    if user is not None and not getattr(user, "energy_filter_enabled", False):
        return {"allowed": True, "hits": 0, "blocked_reason": None}

    if not text:
        return {"allowed": True, "hits": 0, "blocked_reason": None}

    hits = sum(1 for pat in _ENERGY_WORDS if re.search(pat, text))
    if hits >= ENERGY_FILTER_THRESHOLD:
        return {
            "allowed": False,
            "hits": hits,
            "blocked_reason": (
                f"High-intensity language detected ({hits} signal(s)). "
                "Calm your tone and try again."
            ),
        }
    return {"allowed": True, "hits": hits, "blocked_reason": None}
# ─────────────────────────────────────────────────────────────────────────────


def ai_scan_text(text):
    """
    Lightweight AI-style content scanner.  Returns dict of
    {category: confidence} where confidence is 0.0-1.0.
    In production replace with a real ML model (OpenAI Moderation, Perspective API, etc.).
    """
    if not text:
        return dict(AI_CATEGORIES)

    scores = dict(AI_CATEGORIES)
    lower = text.lower()

    # Keyword matching with confidence scoring
    for pat in _HATE_WORDS:
        if re.search(pat, lower):
            scores["hate_speech"] = min(1.0, scores["hate_speech"] + 0.45)
    for pat in _HARASS_WORDS:
        if re.search(pat, lower):
            scores["harassment"] = min(1.0, scores["harassment"] + 0.55)
    for pat in _VIOLENCE_WORDS:
        if re.search(pat, lower):
            scores["violence"] = min(1.0, scores["violence"] + 0.40)
    for pat in _SPAM_WORDS:
        if re.search(pat, lower):
            scores["spam"] = min(1.0, scores["spam"] + 0.50)

    # Excessive caps = possible rage / harassment
    if len(text) > 20:
        caps_ratio = sum(1 for c in text if c.isupper()) / len(text)
        if caps_ratio > 0.7:
            scores["harassment"] = min(1.0, scores["harassment"] + 0.25)

    # Repetition detection (spam)
    words = lower.split()
    if len(words) > 10:
        unique = set(words)
        if len(unique) / len(words) < 0.3:
            scores["spam"] = min(1.0, scores["spam"] + 0.45)

    # URL flood = spam
    url_count = len(re.findall(r"https?://", lower))
    if url_count >= 3:
        scores["spam"] = min(1.0, scores["spam"] + 0.35)

    return scores


AUTO_ACTION_THRESHOLD = 0.70   # Above this → auto-flag
AUTO_REMOVE_THRESHOLD = 0.90   # Above this → auto-remove


def ai_moderate_post(post, user):
    """Run the AI scanner on a post and optionally take automatic action.
    Returns (action, reason, confidence) or None."""
    from __init__ import db
    from models import ModerationLog

    text = (getattr(post, "caption", "") or "")
    scores = ai_scan_text(text)

    top_category = max(scores, key=scores.get)
    top_score = scores[top_category]

    if top_score < AUTO_ACTION_THRESHOLD:
        return None  # nothing to act on

    action = "flag"
    if top_score >= AUTO_REMOVE_THRESHOLD:
        action = "remove"
        # Hide the post
        try:
            post.visibility = "removed"
        except Exception:
            pass

    reason = f"AI detected {top_category} (confidence {top_score:.0%})"

    log = ModerationLog(
        post_id=post.id,
        user_id=user.id if user else None,
        action=action,
        reason=reason,
        ai_confidence=top_score,
        auto=True,
    )
    db.session.add(log)
    db.session.commit()

    return action, reason, top_score


# ──────────────────────────────────────────────────
#  USER: Report a post
# ──────────────────────────────────────────────────
VALID_REPORT_REASONS = [
    "scam",
]


@mod_bp.route("/api/report", methods=["POST"])
@login_required
def report_post(_user=None):
    """Report a post/account for SCAM activity.

    VybeFlow Policy: The ONLY thing users can report is scam accounts/content.
    All other moderation is handled by VybeFlow's AI systems automatically.
    """
    from __init__ import db
    from models import ContentReport, Post

    data = request.get_json(silent=True) or {}
    post_id = data.get("post_id")
    reason = (data.get("reason") or "scam").lower()
    details = (data.get("details") or "").strip()[:2000]

    if not post_id:
        return jsonify(error="post_id is required"), 400

    # Only scam reports are accepted — all other moderation is AI-handled
    if reason not in VALID_REPORT_REASONS:
        return jsonify(
            error="Only scam reports are accepted. All other content issues are handled automatically by our AI.",
            valid=VALID_REPORT_REASONS,
            hint="VybeFlow only allows reporting scam accounts. Hate speech, threats, and fake accounts are detected by AI.",
        ), 400

    post = db.session.get(Post, post_id)
    if not post:
        return jsonify(error="Post not found"), 404

    # Prevent duplicate reports
    existing = ContentReport.query.filter_by(
        reporter_id=_user.id, post_id=post_id, status="pending"
    ).first()
    if existing:
        return jsonify(error="You already reported this post"), 409

    report = ContentReport(
        reporter_id=_user.id,
        post_id=post_id,
        reason=reason,
        details=details,
    )
    db.session.add(report)
    db.session.commit()

    # Also flag the post author for AI scam review
    from models import User
    author = db.session.get(User, post.author_id)
    if author:
        author.scam_flags = (author.scam_flags or 0) + 1
        # Trigger fake account scan after scam report
        from platform_rules import scan_fake_account, apply_fake_account_warning
        scan = scan_fake_account(author)
        warning_result = None
        if scan["is_suspicious"]:
            warning_result = apply_fake_account_warning(author)
        else:
            db.session.commit()

    return jsonify(
        ok=True,
        report_id=report.id,
        message="Scam report submitted. Our AI will review it.",
    ), 201


# ──────────────────────────────────────────────────
#  USER: Takedown request form
# ──────────────────────────────────────────────────
VALID_TAKEDOWN_TYPES = [
    "dmca_copyright", "consent_likeness", "consent_intimate", "other",
]


@mod_bp.route("/takedown", methods=["GET", "POST"])
@login_required
def takedown_form(_user=None):
    from __init__ import db
    from models import TakedownRequest

    if request.method == "POST":
        req_type = (request.form.get("request_type") or "").strip()
        post_id = request.form.get("post_id", type=int)
        full_name = (request.form.get("full_name") or "").strip()[:120]
        email = (request.form.get("email") or "").strip()[:200]
        description = (request.form.get("description") or "").strip()[:5000]
        sworn = "sworn_statement" in request.form
        evidence_url = (request.form.get("evidence_url") or "").strip()[:1000]

        errors = []
        if req_type not in VALID_TAKEDOWN_TYPES:
            errors.append("Invalid request type.")
        if not full_name:
            errors.append("Full legal name is required.")
        if not email or "@" not in email:
            errors.append("Valid email is required.")
        if not description or len(description) < 20:
            errors.append("Description must be at least 20 characters.")
        if req_type == "dmca_copyright" and not sworn:
            errors.append("DMCA requests require a sworn statement under penalty of perjury.")

        if errors:
            flash(" ".join(errors), "danger")
            return redirect(url_for("moderation.takedown_form"))

        td = TakedownRequest(
            requester_id=_user.id,
            post_id=post_id if post_id else None,
            request_type=req_type,
            full_name=full_name,
            email=email,
            description=description,
            sworn_statement=sworn,
            evidence_url=evidence_url,
        )
        db.session.add(td)
        db.session.commit()

        flash("Takedown request submitted. We'll review it within 48 hours.", "success")
        return redirect(url_for("moderation.takedown_status"))

    return render_template("takedown.html")


@mod_bp.route("/takedown/status")
@login_required
def takedown_status(_user=None):
    from models import TakedownRequest
    requests_list = TakedownRequest.query.filter_by(
        requester_id=_user.id
    ).order_by(TakedownRequest.created_at.desc()).all()
    return render_template("takedown_status.html", requests=requests_list)


# ──────────────────────────────────────────────────
#  ADMIN: Moderation Dashboard
# ──────────────────────────────────────────────────
@mod_bp.route("/admin/moderation")
@admin_required
def admin_dashboard(_user=None):
    from models import ContentReport, TakedownRequest, ModerationLog, Post

    tab = request.args.get("tab", "reports")

    reports = ContentReport.query.order_by(
        ContentReport.created_at.desc()
    ).limit(200).all()

    takedowns = TakedownRequest.query.order_by(
        TakedownRequest.created_at.desc()
    ).limit(200).all()

    ai_logs = ModerationLog.query.order_by(
        ModerationLog.created_at.desc()
    ).limit(200).all()

    # Flagged posts (AI or user reports pending)
    flagged_posts = Post.query.filter(
        (Post.visibility == "removed") | (Post.needs_review == True)
    ).order_by(Post.created_at.desc()).limit(100).all()

    stats = {
        "pending_reports": ContentReport.query.filter_by(status="pending").count(),
        "pending_takedowns": TakedownRequest.query.filter_by(status="pending").count(),
        "ai_flags_today": ModerationLog.query.filter(
            ModerationLog.created_at >= datetime.now(timezone.utc).replace(hour=0, minute=0, second=0)
        ).count(),
        "total_removed": ModerationLog.query.filter_by(action="remove").count(),
    }

    return render_template(
        "admin_moderation.html",
        tab=tab,
        reports=reports,
        takedowns=takedowns,
        ai_logs=ai_logs,
        flagged_posts=flagged_posts,
        stats=stats,
        user=_user,
    )


# ──────────────────────────────────────────────────
#  ADMIN: Resolve content report
# ──────────────────────────────────────────────────
@mod_bp.route("/admin/moderation/report/<int:report_id>/action", methods=["POST"])
@admin_required
def resolve_report(report_id, _user=None):
    from __init__ import db
    from models import ContentReport, Post, ModerationLog

    report = ContentReport.query.get_or_404(report_id)
    action = (request.form.get("action") or "").strip()

    if action not in ("dismiss", "warn", "remove", "ban"):
        flash("Invalid action.", "danger")
        return redirect(url_for("moderation.admin_dashboard", tab="reports"))

    report.status = "actioned" if action != "dismiss" else "dismissed"
    report.reviewed_by = _user.id
    report.reviewed_at = datetime.now(timezone.utc)
    report.action_taken = action

    if action == "remove" and report.post_id:
        post = db.session.get(Post, report.post_id)
        if post:
            post.visibility = "removed"

    # Log it
    log = ModerationLog(
        post_id=report.post_id,
        user_id=_user.id,
        action=action,
        reason=f"Human review of report #{report.id}: {report.reason}",
        auto=False,
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Report #{report.id} — action: {action}", "success")
    return redirect(url_for("moderation.admin_dashboard", tab="reports"))


# ──────────────────────────────────────────────────
#  ADMIN: Resolve takedown request
# ──────────────────────────────────────────────────
@mod_bp.route("/admin/moderation/takedown/<int:td_id>/action", methods=["POST"])
@admin_required
def resolve_takedown(td_id, _user=None):
    from __init__ import db
    from models import TakedownRequest, Post, ModerationLog

    td = TakedownRequest.query.get_or_404(td_id)
    action = (request.form.get("action") or "").strip()
    note = (request.form.get("resolution_note") or "").strip()[:2000]

    if action not in ("approve", "deny"):
        flash("Invalid action.", "danger")
        return redirect(url_for("moderation.admin_dashboard", tab="takedowns"))

    td.status = "approved" if action == "approve" else "denied"
    td.reviewed_by = _user.id
    td.reviewed_at = datetime.now(timezone.utc)
    td.resolution_note = note

    if action == "approve" and td.post_id:
        post = db.session.get(Post, td.post_id)
        if post:
            post.visibility = "removed"

    log = ModerationLog(
        post_id=td.post_id,
        user_id=_user.id,
        action="remove" if action == "approve" else "none",
        reason=f"Takedown #{td.id} ({td.request_type}) — {action}",
        auto=False,
    )
    db.session.add(log)
    db.session.commit()

    flash(f"Takedown #{td.id} — {action}", "success")
    return redirect(url_for("moderation.admin_dashboard", tab="takedowns"))


# ──────────────────────────────────────────────────
#  ADMIN: AI bulk scan
# ──────────────────────────────────────────────────
@mod_bp.route("/admin/moderation/ai/scan", methods=["POST"])
@admin_required
def ai_bulk_scan(_user=None):
    from __init__ import db
    from models import Post, User

    limit = min(int(request.form.get("limit", 100)), 500)
    posts = Post.query.filter(
        Post.visibility != "removed"
    ).order_by(Post.created_at.desc()).limit(limit).all()

    flagged = 0
    removed = 0
    for post in posts:
        author = db.session.get(User, post.author_id)
        result = ai_moderate_post(post, author)
        if result:
            action, reason, confidence = result
            if action == "remove":
                removed += 1
            else:
                flagged += 1

    flash(f"AI scan complete: {len(posts)} posts scanned, {flagged} flagged, {removed} removed.", "success")
    return redirect(url_for("moderation.admin_dashboard", tab="ai"))


# ──────────────────────────────────────────────────
#  ADMIN: Override AI action
# ──────────────────────────────────────────────────
@mod_bp.route("/admin/moderation/post/<int:post_id>/override", methods=["POST"])
@admin_required
def override_ai(post_id, _user=None):
    from __init__ import db
    from models import Post, ModerationLog

    post = Post.query.get_or_404(post_id)
    new_action = (request.form.get("action") or "").strip()

    if new_action == "restore":
        post.visibility = "public"
        post.needs_review = False
    elif new_action == "remove":
        post.visibility = "removed"

    # Mark related AI logs as overridden
    logs = ModerationLog.query.filter_by(post_id=post_id, auto=True, overridden=False).all()
    for log in logs:
        log.overridden = True
        log.overridden_by = _user.id

    # Record the human override
    new_log = ModerationLog(
        post_id=post_id,
        user_id=_user.id,
        action=new_action,
        reason=f"Admin override: {new_action}",
        auto=False,
    )
    db.session.add(new_log)
    db.session.commit()

    flash(f"Post #{post_id} — {new_action}", "success")
    return redirect(url_for("moderation.admin_dashboard", tab="ai"))
