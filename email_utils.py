"""
VybeFlow Email Utilities
========================
Handles password-reset tokens and SMTP email delivery.

Uses itsdangerous for secure time-limited tokens and
smtplib for direct SMTP sending (no Flask-Mail dependency needed at runtime).
"""

import os
import base64
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

# Load .env from the same directory (or parent) so SMTP vars are available
_this_dir = Path(__file__).resolve().parent
for _candidate in (_this_dir / ".env", _this_dir.parent / ".env"):
    if _candidate.exists():
        load_dotenv(_candidate)
        break

# ─── Token helpers ───────────────────────────────────────────────

_SECRET = os.environ.get("VYBEFLOW_SECRET_KEY") or os.environ.get("SECRET_KEY") or ""
if not _SECRET:
    # Fall back to the same persistent dev key that config.py generates, so
    # password-reset tokens remain valid across server restarts.
    _key_file = Path(__file__).resolve().parent / "instance" / "secret.key"
    try:
        _stored = _key_file.read_text().strip()
        if len(_stored) >= 32:
            _SECRET = _stored
    except OSError:
        pass
if not _SECRET:
    # Last resort — generate a session-scoped key (tokens won't survive restarts)
    import secrets as _sec_mod
    _SECRET = _sec_mod.token_hex(32)
_SALT = "password-reset-salt"
_APPEAL_SALT = "appeal-action-salt"
_TOKEN_MAX_AGE = 86400  # 24 hours
_APPEAL_MAX_AGE = 604800  # 7 days for appeal tokens

_serializer = URLSafeTimedSerializer(_SECRET)


def generate_reset_token(email: str) -> str:
    """Create a URL-safe, time-limited token that embeds the user's email."""
    return _serializer.dumps(email, salt=_SALT)


def verify_reset_token(token: str) -> str | None:
    """Return the email embedded in *token*, or None if invalid / expired."""
    try:
        return _serializer.loads(token, salt=_SALT, max_age=_TOKEN_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


# ─── Email delivery ──────────────────────────────────────────────

SMTP_HOST = os.environ.get("VYBEFLOW_SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("VYBEFLOW_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("VYBEFLOW_SMTP_USER", "")
SMTP_PASS = os.environ.get("VYBEFLOW_SMTP_PASS", "")
SMTP_USE_TLS = os.environ.get("VYBEFLOW_SMTP_USE_TLS", "true").lower() == "true"
SMTP_USE_SSL = os.environ.get("VYBEFLOW_SMTP_USE_SSL", "false").lower() == "true"
MAIL_FROM = os.environ.get("VYBEFLOW_MAIL_FROM", f"VybeFlow <{SMTP_USER}>")
OVERRIDE_EMAIL = os.environ.get("PASSWORD_RESET_OVERRIDE_EMAIL", "").strip()
APP_BASE_URL = os.environ.get("VYBEFLOW_APP_BASE_URL", "http://127.0.0.1:5000")


# ─── Logo — embedded as base64 so it works even on localhost ────────

def _logo_data_uri() -> str:
    """Return a data:image/png;base64,... URI for the VybeFlow logo.

    Searches all plausible paths so the logo loads correctly regardless of
    whether the app is started from the project root, a sub-directory, or
    via a WSGI server with a different working directory.
    """
    _here = Path(__file__).resolve().parent
    candidates = [
        _here / "static" / "VFlogo_clean.png",
        _here.parent / "static" / "VFlogo_clean.png",
        Path(os.getcwd()) / "static" / "VFlogo_clean.png",
        Path(os.getcwd()).parent / "static" / "VFlogo_clean.png",
    ]
    # Also honour an explicit override env-var for production deployments
    _env_logo = os.environ.get("VYBEFLOW_LOGO_PATH", "")
    if _env_logo:
        candidates.insert(0, Path(_env_logo))

    for p in candidates:
        if p.exists():
            try:
                encoded = base64.b64encode(p.read_bytes()).decode("ascii")
                return f"data:image/png;base64,{encoded}"
            except OSError:
                continue

    # Fallback: branded VybeFlow SVG so emails always have *something* good-looking
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<defs>'
        '<linearGradient id="vfg" x1="0%" y1="0%" x2="100%" y2="100%">'
        '<stop offset="0%" style="stop-color:#ff9a3d"/>'
        '<stop offset="50%" style="stop-color:#ff6a00"/>'
        '<stop offset="100%" style="stop-color:#ff4800"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="64" height="64" rx="16" fill="url(#vfg)"/>'
        '<text x="32" y="41" text-anchor="middle" font-family="Arial Black,Arial" '
        'font-weight="900" font-size="30" fill="#fff" letter-spacing="-1">VF</text>'
        '</svg>'
    )
    encoded = base64.b64encode(svg.encode()).decode("ascii")
    return f"data:image/svg+xml;base64,{encoded}"

# Re-evaluate at call time so a temporarily-missing file at import doesn't
# bake in the SVG fallback forever — the PNG will be found once the WSGI
# process has the correct working directory.
def _get_logo_data_uri() -> str:
    global _LOGO_DATA_URI
    if not _LOGO_DATA_URI.startswith("data:image/png"):
        _LOGO_DATA_URI = _logo_data_uri()
    return _LOGO_DATA_URI

_LOGO_DATA_URI = _logo_data_uri()


# ─── Shared email header / footer ────────────────────────────────────

def _email_header() -> str:
    """Return the branded email header HTML with the VybeFlow logo (base64 embedded)."""
    logo = _get_logo_data_uri()
    return f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#0a0810;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <div style="max-width:520px;margin:40px auto;padding:0;">
    <!-- header bar -->
    <div style="background:linear-gradient(90deg,#ff9a3d,#ff6a00,#ff4800);border-radius:20px 20px 0 0;padding:28px 32px;text-align:center;">
      <img src="{logo}" alt="VybeFlow" width="64" height="64"
           style="display:block;margin:0 auto 10px;border-radius:16px;object-fit:contain;" />
      <h1 style="margin:0;color:#fff;font-size:24px;font-weight:800;letter-spacing:.3px;">VybeFlow</h1>
    </div>
    <!-- body -->
    <div style="background:linear-gradient(135deg,#0f0a1a,#1a1030);padding:32px;border:1px solid rgba(255,170,112,.15);border-top:none;border-radius:0 0 20px 20px;">"""


def _email_footer() -> str:
    """Return the branded email footer HTML."""
    return """\
      <hr style="border:none;border-top:1px solid rgba(255,255,255,.08);margin:28px 0 16px;" />
      <p style="color:rgba(255,255,255,.3);font-size:11px;text-align:center;margin:0;">
        &copy; VybeFlow &mdash; Your vibe, your flow.
      </p>
    </div>
  </div>
</body>
</html>"""


# ─── Low-level send helper ───────────────────────────────────────────

# Domains that are auto-generated placeholders — never deliverable.
_FAKE_EMAIL_DOMAINS = ("@vybeflow.local", "@ob.test", "@pk.test", "@sec.test",
                       "@lock.test", "@vault.test", "@audit.local", "@test.local")


def _send_email(to_email: str, subject: str, html_body: str,
                plain_body: str, label: str = "email") -> bool:
    """Send an email via SMTP.  Returns True on success."""
    destination = OVERRIDE_EMAIL or to_email

    # ── Permanent guard: never attempt delivery to placeholder domains ──
    if any(destination.lower().endswith(d) for d in _FAKE_EMAIL_DOMAINS):
        print(f"[VybeFlow] Skipped {label} — {destination!r} is a placeholder address.")
        return False

    if not SMTP_USER or not SMTP_PASS:
        print(f"[VybeFlow] SMTP not configured — {label} not sent.")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = MAIL_FROM
    msg["To"] = destination
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    try:
        if SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15)
        else:
            server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15)
            if SMTP_USE_TLS:
                server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, [destination], msg.as_string())
        server.quit()
        print(f"[VybeFlow] ✅ {label} sent to {destination}")
        return True
    except Exception as exc:
        print(f"[VybeFlow] ❌ Failed to send {label}: {exc}")
        return False


# ─── Password-reset email ────────────────────────────────────────────

def send_reset_email(to_email: str, reset_url: str) -> bool:
    """Send a password-reset email.  Returns True on success."""
    if not SMTP_USER or not SMTP_PASS:
        print(f"[VybeFlow] SMTP not configured — reset link printed to console:")
        print(f"[VybeFlow] → {reset_url}")
        return False

    html_body = _email_header() + f"""\
      <h2 style="color:#fff;font-size:20px;margin:0 0 12px;">Reset Your Password</h2>
      <p style="color:rgba(255,255,255,.85);font-size:15px;line-height:1.6;margin:0 0 24px;">
        Hey! We received a request to reset your password. Click the button below to create a new one:
      </p>
      <div style="text-align:center;margin:28px 0;">
        <a href="{reset_url}"
           style="display:inline-block;padding:14px 36px;
                  background:linear-gradient(90deg,#ff9a3d,#ff6a00,#ff4800);
                  color:#fff;border-radius:999px;text-decoration:none;font-weight:700;font-size:15px;
                  box-shadow:0 4px 20px rgba(255,106,0,.35);">Reset My Password</a>
      </div>
      <p style="color:rgba(255,255,255,.5);font-size:13px;line-height:1.5;">
        This link expires in <strong style="color:rgba(255,255,255,.7);">24 hours</strong>.
        If you didn't request a password reset, you can safely ignore this email.
      </p>
      <p style="color:rgba(255,255,255,.35);font-size:12px;margin-top:20px;text-align:center;">
        Can't click the button? Copy this link:<br>
        <a href="{reset_url}" style="color:#ffd8a0;word-break:break-all;font-size:11px;">{reset_url}</a>
      </p>
""" + _email_footer()

    plain_body = (
        f"VybeFlow — Password Reset\n\n"
        f"Click the link below to reset your password:\n{reset_url}\n\n"
        f"This link expires in 24 hours.\n"
        f"If you didn't request this, ignore this email."
    )

    ok = _send_email(to_email, "VybeFlow — Reset Your Password",
                     html_body, plain_body, label="Password reset email")
    if not ok:
        print(f"[VybeFlow] → Fallback reset link: {reset_url}")
    return ok


# ─── Welcome email ───────────────────────────────────────────────────

def send_welcome_email(to_email: str, username: str) -> bool:
    """Send a branded welcome email after registration.  Returns True on success."""
    base = APP_BASE_URL.rstrip('/')
    feed_url = f"{base}/feed"
    profile_url = f"{base}/account"

    html_body = _email_header() + f"""\
      <h2 style="color:#fff;font-size:22px;margin:0 0 8px;text-align:center;">Welcome to VybeFlow! 🔥</h2>
      <p style="color:rgba(255,255,255,.6);font-size:13px;text-align:center;margin:0 0 24px;">Your vibe, your flow — let's go.</p>

      <p style="color:rgba(255,255,255,.85);font-size:15px;line-height:1.6;">
        Hey <strong style="color:#ffa552;">{username}</strong>, thanks for joining the VybeFlow community!
        Your account is all set up and ready to roll.
      </p>

      <div style="background:rgba(255,170,112,.08);border-radius:14px;padding:20px;margin:24px 0;border:1px solid rgba(255,170,112,.12);">
        <p style="color:rgba(255,255,255,.9);font-size:14px;margin:0 0 12px;font-weight:600;">Here's what you can do next:</p>
        <table style="width:100%;border:none;border-collapse:collapse;">
          <tr>
            <td style="padding:6px 0;color:rgba(255,255,255,.85);font-size:14px;">🎵&nbsp; Discover music &amp; share your vibe</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:rgba(255,255,255,.85);font-size:14px;">📸&nbsp; Post photos, videos &amp; stories</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:rgba(255,255,255,.85);font-size:14px;">🎨&nbsp; Customize your profile wallpaper</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:rgba(255,255,255,.85);font-size:14px;">💬&nbsp; Connect with the community</td>
          </tr>
          <tr>
            <td style="padding:6px 0;color:rgba(255,255,255,.85);font-size:14px;">🔴&nbsp; Go live and show the world your talent</td>
          </tr>
        </table>
      </div>

      <div style="text-align:center;margin:28px 0;">
        <a href="{feed_url}"
           style="display:inline-block;padding:14px 40px;
                  background:linear-gradient(90deg,#ff9a3d,#ff6a00,#ff4800);
                  color:#fff;border-radius:999px;text-decoration:none;font-weight:700;font-size:15px;
                  box-shadow:0 4px 20px rgba(255,106,0,.35);">Explore Your Feed</a>
      </div>

      <div style="text-align:center;margin-bottom:8px;">
        <a href="{profile_url}"
           style="color:#ffd8a0;font-size:13px;text-decoration:underline;">Set up your profile &rarr;</a>
      </div>
""" + _email_footer()

    plain_body = (
        f"Welcome to VybeFlow, {username}!\n\n"
        f"Your account is all set up and ready to roll.\n\n"
        f"Here's what you can do:\n"
        f"  - Discover music & share your vibe\n"
        f"  - Post photos, videos & stories\n"
        f"  - Customize your profile wallpaper\n"
        f"  - Connect with the community\n"
        f"  - Go live and show the world your talent\n\n"
        f"Start exploring: {feed_url}\n"
        f"Set up your profile: {profile_url}\n\n"
        f"— The VybeFlow Team"
    )

    return _send_email(to_email, f"Welcome to VybeFlow, {username}! 🔥",
                       html_body, plain_body, label="Welcome email")


# ─── Email verification ──────────────────────────────────────────

_VERIFY_SALT    = "email-verify-salt"
_VERIFY_MAX_AGE = 86400  # 24 hours


def generate_email_verify_token(user_id: int, email: str) -> str:
    """Create a URL-safe 24-hour token for email address verification."""
    return _serializer.dumps({"uid": user_id, "email": email}, salt=_VERIFY_SALT)


def verify_email_token(token: str) -> dict | None:
    """Decode and validate an email verification token.
    Returns {"uid": int, "email": str} or None if invalid/expired."""
    try:
        return _serializer.loads(token, salt=_VERIFY_SALT, max_age=_VERIFY_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


def send_email_verification(to_email: str, display_name: str, verify_url: str) -> bool:
    """Send the email verification link to a newly registered user."""
    subject = "Verify your VybeFlow email"
    html = (
        _email_header()
        + f"""
<p>Hi <strong>{display_name}</strong>,</p>
<p>Welcome to VybeFlow! Please verify your email address to unlock sending messages and posting.</p>
<p style="text-align:center; margin:28px 0;">
  <a href="{verify_url}"
     style="background:linear-gradient(135deg,#ff6b35,#f7c59f);color:#1a1a2e;padding:14px 32px;
            border-radius:25px;text-decoration:none;font-weight:700;font-size:16px;display:inline-block;">
    Verify My Email
  </a>
</p>
<p style="font-size:13px;color:#aaa;">This link expires in 24 hours. If you didn't sign up, you can ignore this email.</p>
"""
        + _email_footer()
    )
    return _send_email(to_email, subject, html,
                       f"Verify your VybeFlow email:\n{verify_url}\n\nThis link expires in 24 hours.",
                       label="Email verification")


# ─── Appeal tokens ───────────────────────────────────────────────────

def generate_appeal_token(username: str, action: str) -> str:
    """Create a URL-safe token for approve/deny appeal links.
    action: 'approve' or 'deny'"""
    return _serializer.dumps({"username": username, "action": action}, salt=_APPEAL_SALT)


def verify_appeal_token(token: str) -> dict | None:
    """Return {'username': ..., 'action': ...} or None if invalid/expired."""
    try:
        return _serializer.loads(token, salt=_APPEAL_SALT, max_age=_APPEAL_MAX_AGE)
    except (SignatureExpired, BadSignature):
        return None


# ─── Appeal admin email (with approve/deny buttons) ─────────────────

def send_appeal_admin_email(
    to_email: str,
    username: str,
    appeal_type: str,
    reason_text: str,
    strikes: int = 0,
    ban_reason: str = "",
) -> bool:
    """Send an appeal notification email to an admin with one-click Approve/Deny buttons."""
    import html as html_mod

    base = APP_BASE_URL.rstrip('/')
    approve_token = generate_appeal_token(username, "approve")
    deny_token = generate_appeal_token(username, "deny")
    approve_url = f"{base}/api/appeal/decide/{approve_token}"
    deny_url = f"{base}/api/appeal/decide/{deny_token}"

    type_label = "BAN Appeal" if appeal_type == "ban" else "Block Appeal"
    icon = "\U0001f6a8" if appeal_type == "ban" else "\u26a0\ufe0f"
    accent = "#ff4040" if appeal_type == "ban" else "#ffa552"

    safe_reason = html_mod.escape(reason_text)
    safe_ban_reason = html_mod.escape(ban_reason) if ban_reason else ""
    safe_username = html_mod.escape(username)

    strikes_html = ""
    if appeal_type == "ban" and strikes:
        strikes_html = f"""
      <div style="background:rgba(255,30,30,.05);border:1px solid rgba(255,30,30,.15);border-radius:14px;padding:16px;margin:16px 0;">
        <p style="color:rgba(255,255,255,.6);font-size:12px;margin:0 0 4px;">STRIKES</p>
        <p style="color:{accent};font-size:16px;font-weight:700;margin:0;">{strikes} / 3 \u2014 BANNED</p>
      </div>"""

    ban_reason_html = ""
    if safe_ban_reason:
        ban_reason_html = f"""
      <div style="background:rgba(255,100,0,.05);border:1px solid rgba(255,100,0,.15);border-radius:14px;padding:16px;margin:16px 0;">
        <p style="color:rgba(255,255,255,.6);font-size:12px;margin:0 0 4px;">ORIGINAL BAN REASON</p>
        <p style="color:rgba(255,255,255,.8);font-size:13px;line-height:1.5;margin:0;">{safe_ban_reason}</p>
      </div>"""

    html_body = _email_header() + f"""\
      <h2 style="color:#fff;font-size:20px;margin:0 0 12px;">{icon} {type_label} Received</h2>
      <p style="color:rgba(255,255,255,.55);font-size:12px;margin:0 0 16px;">A user is requesting to be unbanned. Review and take action below.</p>
      <div style="background:rgba(255,68,68,.08);border:1px solid rgba(255,68,68,.15);border-radius:14px;padding:16px;margin:16px 0;">
        <p style="color:rgba(255,255,255,.6);font-size:12px;margin:0 0 4px;">USERNAME</p>
        <p style="color:{accent};font-size:16px;font-weight:700;margin:0;">@{safe_username}</p>
      </div>
      {strikes_html}
      {ban_reason_html}
      <div style="background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.08);border-radius:14px;padding:16px;margin:16px 0;">
        <p style="color:rgba(255,255,255,.6);font-size:12px;margin:0 0 4px;">APPEAL REASON</p>
        <p style="color:rgba(255,255,255,.9);font-size:14px;line-height:1.6;margin:0;white-space:pre-wrap;">{safe_reason}</p>
      </div>

      <!-- APPROVE / DENY BUTTONS -->
      <div style="text-align:center;margin:28px 0 12px;">
        <a href="{approve_url}"
           style="display:inline-block;padding:14px 36px;
                  background:linear-gradient(90deg,#22c55e,#16a34a);
                  color:#fff;border-radius:999px;text-decoration:none;font-weight:700;font-size:15px;
                  box-shadow:0 4px 20px rgba(34,197,94,.35);margin-right:12px;">\u2705 Approve Appeal</a>
        <a href="{deny_url}"
           style="display:inline-block;padding:14px 36px;
                  background:linear-gradient(90deg,#ef4444,#dc2626);
                  color:#fff;border-radius:999px;text-decoration:none;font-weight:700;font-size:15px;
                  box-shadow:0 4px 20px rgba(239,68,68,.35);">\u274c Deny Appeal</a>
      </div>
      <p style="color:rgba(255,255,255,.35);font-size:11px;text-align:center;">These links expire in 7 days.</p>
""" + _email_footer()

    plain_body = (
        f"{type_label}\n"
        f"Username: {username}\n"
        f"Strikes: {strikes}/3\n"
        f"Ban reason: {ban_reason}\n"
        f"Appeal reason: {reason_text}\n\n"
        f"APPROVE: {approve_url}\n"
        f"DENY: {deny_url}\n"
    )

    return _send_email(to_email, f"VybeFlow {type_label} \u2014 @{username}",
                       html_body, plain_body, label=f"{type_label} email")


def send_appeal_decision_email(to_email: str, username: str, approved: bool) -> bool:
    """Notify a user that their appeal has been approved or denied."""
    if approved:
        decision_html = """\
      <div style="text-align:center;margin:24px 0;">
        <div style="font-size:48px;margin-bottom:12px;">\u2705</div>
        <h2 style="color:#22c55e;font-size:22px;margin:0 0 12px;">Appeal Approved!</h2>
        <p style="color:rgba(255,255,255,.85);font-size:15px;line-height:1.6;">
          Great news! Your appeal has been reviewed and <strong>approved</strong>.
          Your account has been reinstated. You can now log in and use VybeFlow again.
        </p>
        <p style="color:rgba(255,255,255,.55);font-size:13px;margin-top:16px;">
          Please be mindful of the community guidelines going forward.
          Further violations may result in a permanent ban.
        </p>
      </div>"""
        subject = f"VybeFlow \u2014 Your appeal has been APPROVED, @{username}!"
        plain = f"Hey {username}, your appeal has been approved! Your account is back. Please follow the rules."
    else:
        decision_html = """\
      <div style="text-align:center;margin:24px 0;">
        <div style="font-size:48px;margin-bottom:12px;">\u274c</div>
        <h2 style="color:#ef4444;font-size:22px;margin:0 0 12px;">Appeal Denied</h2>
        <p style="color:rgba(255,255,255,.85);font-size:15px;line-height:1.6;">
          After careful review, your appeal has been <strong>denied</strong>.
          The original decision stands. Your account remains suspended.
        </p>
        <p style="color:rgba(255,255,255,.55);font-size:13px;margin-top:16px;">
          If you believe this was an error, you may submit a new appeal after 30 days.
        </p>
      </div>"""
        subject = f"VybeFlow \u2014 Your appeal has been denied, @{username}"
        plain = f"Hey {username}, after review your appeal has been denied. The ban remains in effect."

    html_body = _email_header() + decision_html + _email_footer()
    return _send_email(to_email, subject, html_body, plain, label="Appeal decision email")


# ─── Generic plain-text email helper (used by passkeys recovery) ─────

def send_email(to_email: str, subject: str, plain_body: str) -> bool:
    """Send a plain-text email.  Wraps the body in branded HTML.
    Returns True on success.  Used by passkeys and step-up verification."""
    import html as _html_mod
    safe_body = _html_mod.escape(plain_body).replace("\n", "<br>")
    html_body = _email_header() + f"""\
      <div style="color:rgba(255,255,255,.85);font-size:15px;line-height:1.7;white-space:pre-wrap;">
        {safe_body}
      </div>
""" + _email_footer()
    return _send_email(to_email, subject, html_body, plain_body, label="transactional email")
