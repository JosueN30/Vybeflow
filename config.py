import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

UPLOAD_ROOT = os.path.join(BASE_DIR, "static", "uploads")
UPLOAD_AUDIO = os.path.join(UPLOAD_ROOT, "audio")
UPLOAD_MEDIA = os.path.join(UPLOAD_ROOT, "stories")
# Main post/story upload root used by the Flask app
POST_UPLOAD_ABS = os.path.join(BASE_DIR, "static", "uploads")

os.makedirs(UPLOAD_AUDIO, exist_ok=True)
os.makedirs(UPLOAD_MEDIA, exist_ok=True)
os.makedirs(POST_UPLOAD_ABS, exist_ok=True)

ALLOWED_AUDIO_EXT = {"mp3", "wav", "m4a", "aac", "ogg"}
ALLOWED_MEDIA_EXT = {"jpg", "jpeg", "png", "webp", "gif", "mp4", "mov", "webm"}

MAX_AUDIO_MB = 25
MAX_MEDIA_MB = 60

def _get_secret_key():
    """Return SECRET_KEY from env, or generate+persist a stable dev key."""
    key = os.environ.get('SECRET_KEY', '')
    if key:
        return key
    # In dev, generate a persistent key stored in instance/secret.key so
    # sessions survive server restarts and aren't lost on every reload.
    key_file = os.path.join(BASE_DIR, 'instance', 'secret.key')
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)
    if os.path.exists(key_file):
        try:
            with open(key_file, 'r') as f:
                stored = f.read().strip()
                if len(stored) >= 32:
                    return stored
        except OSError:
            pass
    import secrets as _sec_mod
    new_key = _sec_mod.token_hex(32)
    try:
        with open(key_file, 'w') as f:
            f.write(new_key)
    except OSError:
        pass
    return new_key

class Config:
    SECRET_KEY = _get_secret_key()
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')

    # ── Stripe Payments ──────────────────────────────────────────────────────
    # Set these environment variables on your server.
    # Get keys from https://dashboard.stripe.com/apikeys
    STRIPE_SECRET_KEY      = os.environ.get('STRIPE_SECRET_KEY', '')
    STRIPE_PUBLISHABLE_KEY = os.environ.get('STRIPE_PUBLISHABLE_KEY', '')
    STRIPE_WEBHOOK_SECRET  = os.environ.get('STRIPE_WEBHOOK_SECRET', '')

    # ── Web Push / VAPID (Vybe Pulses) ───────────────────────────────────────
    # Generate a key pair once with: python -c "from py_vapid import Vapid; v=Vapid(); v.generate_keys(); print(v.public_key, v.private_key)"
    # Then set these environment variables on your server.
    VAPID_PRIVATE_KEY  = os.environ.get('VAPID_PRIVATE_KEY', '')
    VAPID_PUBLIC_KEY   = os.environ.get('VAPID_PUBLIC_KEY', '')
    VAPID_CLAIM_EMAIL  = os.environ.get('VAPID_CLAIM_EMAIL', 'mailto:admin@vybeflow.app')
    # Keep users logged in for 30 days (session.permanent = True set on login)
    from datetime import timedelta
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    # ── Session cookie security ───────────────────────────────────────────────
    # Secure: only send cookie over HTTPS (set False in dev if not using HTTPS)
    SESSION_COOKIE_SECURE   = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() != 'false'
    # HttpOnly: JS cannot read the session cookie → blocks XSS session theft
    SESSION_COOKIE_HTTPONLY = True
    # SameSite=Lax: cookie not sent on cross-origin POSTs → CSRF mitigation
    SESSION_COOKIE_SAMESITE = 'Lax'
    # Use absolute path so DB is always found regardless of CWD
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        'DATABASE_URL',
        'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'vybeflow.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # SQLite + threading: NullPool avoids QueuePool exhaustion — each
    # request/thread gets its own connection, closed immediately after use.
    # check_same_thread is SQLite-only; omit for PostgreSQL/MySQL.
    from sqlalchemy.pool import NullPool
    _db_url = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(BASE_DIR, 'instance', 'vybeflow.db'))
    _connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
    SQLALCHEMY_ENGINE_OPTIONS = {
        "poolclass": NullPool,
        "connect_args": _connect_args,
    }
    BASE_DIR = BASE_DIR
    UPLOAD_ROOT = UPLOAD_ROOT
    UPLOAD_AUDIO = UPLOAD_AUDIO
    UPLOAD_MEDIA = UPLOAD_MEDIA
    # Backing folder for posts, avatars, covers, voice notes, etc.
    POST_UPLOAD_ABS = POST_UPLOAD_ABS
    ALLOWED_AUDIO_EXT = ALLOWED_AUDIO_EXT
    ALLOWED_MEDIA_EXT = ALLOWED_MEDIA_EXT
    MAX_AUDIO_MB = MAX_AUDIO_MB
    MAX_MEDIA_MB = MAX_MEDIA_MB

config = {
    'default': Config
}
