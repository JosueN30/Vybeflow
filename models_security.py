"""
models_security.py — VybeFlow Zero-Trust Security Models
=========================================================
Defines database models for:
  - PasskeyCredential  : WebAuthn credentials per user/device
  - TrustedDevice      : remembered device fingerprints
  - RiskEvent          : log of scored security events
  - BehavioralBaseline : per-user typing/touch/session pattern baseline
  - RecoveryToken      : secure email-based passkey recovery tokens
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from __init__ import db


class PasskeyCredential(db.Model):
    """
    Stores a single WebAuthn credential (passkey) for a user.
    A user may have multiple passkeys across different devices.
    """
    __tablename__ = "passkey_credential"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # WebAuthn credential ID (base64url-encoded bytes from the authenticator)
    credential_id   = db.Column(db.Text, unique=True, nullable=False)

    # CBOR-encoded public key stored as base64url (from attestation)
    public_key      = db.Column(db.Text, nullable=False)

    # Signature counter: must be ≥ last seen value; mismatch = cloned authenticator
    sign_count      = db.Column(db.Integer, default=0, nullable=False)

    # Transports the authenticator supports (JSON list: ["internal","hybrid","usb"])
    transports      = db.Column(db.Text, nullable=True)

    # Human-readable label so users can identify which device this is
    device_name     = db.Column(db.String(120), nullable=True)

    # Whether this is synced/multi-device (platform passkey) vs roaming (hardware key)
    is_synced       = db.Column(db.Boolean, default=True, nullable=False)

    # Backup credentials (multi-device passkeys can be backed up by the OS)
    backup_eligible = db.Column(db.Boolean, default=False, nullable=False)
    backup_state    = db.Column(db.Boolean, default=False, nullable=False)

    # User verification performed during registration
    uv_performed    = db.Column(db.Boolean, default=False, nullable=False)

    # AAGUID: identifies the authenticator model (optional, for display)
    aaguid          = db.Column(db.String(64), nullable=True)

    # Last time this credential was successfully used for authentication
    last_used_at    = db.Column(db.DateTime, nullable=True)

    # Device fingerprint bound at registration (partial — for anomaly detection)
    device_fp       = db.Column(db.String(64), nullable=True)

    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_active       = db.Column(db.Boolean, default=True, nullable=False)

    def transports_list(self) -> list:
        try:
            return json.loads(self.transports) if self.transports else []
        except Exception:
            return []

    def __repr__(self):
        return f"<PasskeyCredential uid={self.user_id} device={self.device_name!r}>"


class TrustedDevice(db.Model):
    """
    A device that has been explicitly trusted by a user (after step-up auth).
    Each device gets a long-lived trust token stored in a httponly cookie.
    """
    __tablename__ = "trusted_device"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # Opaque device trust token stored in a separate httponly cookie (`vf_dt`)
    trust_token     = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Device fingerprint components (partial — no PII)
    fp_hash         = db.Column(db.String(64), nullable=False)      # sha256 of composite fingerprint
    ua_tag          = db.Column(db.String(80), nullable=True)        # abbreviated UA string
    ip_prefix       = db.Column(db.String(20), nullable=True)        # first two octets only

    # Human-readable label
    device_name     = db.Column(db.String(120), nullable=True)
    platform        = db.Column(db.String(40), nullable=True)        # "iPhone", "Windows", etc.

    # Geo (country-level only — no street/city)
    country_code    = db.Column(db.String(2), nullable=True)

    # Lifecycle
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    last_seen_at    = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at      = db.Column(db.DateTime, nullable=True)          # None = never expires
    is_active       = db.Column(db.Boolean, default=True, nullable=False)
    revoked_at      = db.Column(db.DateTime, nullable=True)
    revoke_reason   = db.Column(db.String(80), nullable=True)

    def __repr__(self):
        return f"<TrustedDevice uid={self.user_id} fp={self.fp_hash[:8]}>"


class RiskEvent(db.Model):
    """
    Immutable log of every risk-scored action.
    Used for anomaly trend analysis and audit.
    """
    __tablename__ = "risk_event"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=True, index=True)

    # Null user_id = unauthenticated attempt
    session_id      = db.Column(db.String(64), nullable=True)
    request_id      = db.Column(db.String(64), nullable=True)

    # What triggered this event
    event_type      = db.Column(db.String(40), nullable=False)       # "login","message","account_change","passkey_auth",...
    action_path     = db.Column(db.String(200), nullable=True)       # request path

    # Risk assessment output
    risk_score      = db.Column(db.Integer, default=0, nullable=False)   # 0-100
    risk_level      = db.Column(db.String(10), nullable=False)           # "low"|"medium"|"high"
    action_taken    = db.Column(db.String(20), nullable=False)           # "allow"|"silent_verify"|"step_up"|"block"

    # Contributing signals (JSON dict of signal name → contribution)
    signals         = db.Column(db.Text, nullable=True)

    # Context
    ip_address      = db.Column(db.String(45), nullable=True)
    country_code    = db.Column(db.String(2), nullable=True)
    device_fp       = db.Column(db.String(64), nullable=True)
    user_agent      = db.Column(db.String(200), nullable=True)

    # Outcome
    resolved        = db.Column(db.Boolean, default=False, nullable=False)
    resolved_by     = db.Column(db.String(20), nullable=True)   # "step_up_passed","admin","auto_expire"

    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    def signals_dict(self) -> dict:
        try:
            return json.loads(self.signals) if self.signals else {}
        except Exception:
            return {}

    def __repr__(self):
        return f"<RiskEvent uid={self.user_id} score={self.risk_score} level={self.risk_level}>"


class BehavioralBaseline(db.Model):
    """
    Per-user passive behavioral baseline: typing cadence, touch patterns, session rhythms.
    Updated incrementally after each verified session — the baseline becomes the user's
    invisible "behavioral password".
    """
    __tablename__ = "behavioral_baseline"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"),
                                nullable=False, unique=True, index=True)

    # Typing cadence (inter-key intervals in ms): mean & stdev
    typing_mean_ms  = db.Column(db.Float, nullable=True)
    typing_stdev_ms = db.Column(db.Float, nullable=True)
    typing_samples  = db.Column(db.Integer, default=0, nullable=False)

    # Touch/click pressure proxy: mean time between tap-down and tap-up
    touch_dwell_mean_ms  = db.Column(db.Float, nullable=True)
    touch_dwell_stdev_ms = db.Column(db.Float, nullable=True)

    # Session timing: typical active hours (JSON sorted list of UTC hours 0-23)
    active_hours    = db.Column(db.Text, nullable=True)          # JSON list e.g. [9,10,11,19,20,21,22]

    # Typical session duration in seconds
    session_dur_mean  = db.Column(db.Float, nullable=True)
    session_dur_stdev = db.Column(db.Float, nullable=True)

    # Rolling average scroll velocity (px/s) — unique to each user
    scroll_vel_mean  = db.Column(db.Float, nullable=True)
    scroll_vel_stdev = db.Column(db.Float, nullable=True)

    # Trusted device fingerprints seen across ≥3 sessions (JSON list of fp_hash)
    known_devices   = db.Column(db.Text, nullable=True)

    # Known countries the user has accessed from (JSON list of ISO-3166-1 alpha-2)
    known_countries = db.Column(db.Text, nullable=True)

    # Confidence level: how many sessions contributed to this baseline (>10 = high confidence)
    confidence      = db.Column(db.Integer, default=0, nullable=False)

    updated_at      = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    def active_hours_list(self) -> list:
        try:
            return json.loads(self.active_hours) if self.active_hours else []
        except Exception:
            return []

    def known_devices_list(self) -> list:
        try:
            return json.loads(self.known_devices) if self.known_devices else []
        except Exception:
            return []

    def known_countries_list(self) -> list:
        try:
            return json.loads(self.known_countries) if self.known_countries else []
        except Exception:
            return []

    def __repr__(self):
        return f"<BehavioralBaseline uid={self.user_id} confidence={self.confidence}>"


class RecoveryToken(db.Model):
    """
    Secure email-based passkey recovery tokens.
    Single-use, short-lived, tied to a specific user + device fingerprint.
    """
    __tablename__ = "recovery_token"

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True)

    # Cryptographically random 32-byte token (hex-encoded)
    token_hash      = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # What this recovery token unlocks
    purpose         = db.Column(db.String(30), nullable=False)   # "passkey_enroll" | "step_up" | "device_trust"

    # Device fingerprint that triggered this recovery (for binding)
    requesting_fp   = db.Column(db.String(64), nullable=True)

    # Rate-limiting: IP that requested this token
    requesting_ip   = db.Column(db.String(45), nullable=True)

    # Lifecycle
    created_at      = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    expires_at      = db.Column(db.DateTime, nullable=False)
    used_at         = db.Column(db.DateTime, nullable=True)
    is_used         = db.Column(db.Boolean, default=False, nullable=False)
    is_revoked      = db.Column(db.Boolean, default=False, nullable=False)

    def is_valid(self) -> bool:
        return (
            not self.is_used
            and not self.is_revoked
            and (datetime.utcnow() if self.expires_at.tzinfo is None else datetime.now(timezone.utc)) < self.expires_at
        )

    def __repr__(self):
        return f"<RecoveryToken uid={self.user_id} purpose={self.purpose!r} valid={self.is_valid()}>"
