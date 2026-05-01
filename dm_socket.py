"""
DM SocketIO handlers — real-time encrypted messaging
=====================================================
Events:
  dm:join       — join a thread room
  dm:leave      — leave a thread room
  dm:send       — send a message (with AI moderation)
  dm:typing     — broadcast typing indicator
  dm:read       — mark thread as read
  user:online   — broadcast when a user connects
  user:offline  — broadcast when a user disconnects
  live:join     — join a live stream room (viewer counter)
  live:leave    — leave a live stream room (viewer counter)
  live:chat     — send a live stream chat message
  live:kick     — (server→client) eject a blocked viewer from a live stream
"""

from flask_socketio import join_room, leave_room, emit
from flask import session
from datetime import timezone
from utils.auth import get_session_username, get_session_user

# Track online users: { user_id: set(sid, ...) }
_online_users = {}

# Live stream viewer registry: { stream_id: { session_key: username } }
_live_viewers: dict = {}

# Module-level socketio reference (set by register_dm_socketio)
_socketio = None


def register_dm_socketio(socketio):
    """Register Socket.IO events for real-time DM."""
    global _socketio
    _socketio = socketio

    @socketio.on("dm:join")
    def on_dm_join(data):
        thread_id = data.get("thread_id")
        if not thread_id:
            emit("dm:error", {"error": "Missing thread ID"})
            return
        username = get_session_username()
        if not username:
            emit("dm:error", {"error": "Session expired. Please refresh the page."})
            return

        # Verify membership
        try:
            from models import ThreadMember, User
            user = User.query.filter_by(username=username).first()
            if not user:
                emit("dm:error", {"error": "User not found"})
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                emit("dm:error", {"error": "Access denied"})
                return
        except Exception:
            emit("dm:error", {"error": "Failed to join thread"})
            return

        room = f"dm:{thread_id}"
        join_room(room)
        emit("dm:presence", {"type": "join", "user": username}, room=room)

    @socketio.on("dm:leave")
    def on_dm_leave(data):
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        room = f"dm:{thread_id}"
        leave_room(room)
        emit("dm:presence", {"type": "leave", "user": username}, room=room)

    @socketio.on("dm:screenshot")
    def on_dm_screenshot(data):
        """Notify all other members of a thread that the sender took a screenshot."""
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        # Verify thread membership before broadcasting
        try:
            from models import ThreadMember, User
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                return
        except Exception:
            return
        room = f"dm:{thread_id}"
        emit("dm:screenshot_alert", {"by": username, "thread_id": thread_id}, room=room, include_self=False)

    @socketio.on("dm:typing")
    def on_dm_typing(data):
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        room = f"dm:{thread_id}"
        emit("dm:typing", {"user": username}, room=room, include_self=False)

    @socketio.on("dm:ghost_typing")
    def on_dm_ghost_typing(data):
        """Ghost Write: broadcast real-time typing preview to thread room."""
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        # Verify membership before broadcasting
        try:
            from models import ThreadMember, User
            from __init__ import db
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                return
        except Exception:
            return
        text = (data.get("text") or "")[:500]  # cap at 500 chars for safety
        enabled = bool(data.get("enabled", True))
        emit("dm:ghost_typing", {
            "thread_id": thread_id,
            "text": text,
            "enabled": enabled,
            "user": username,
        }, room=f"dm:{thread_id}", include_self=False)

    @socketio.on("dm:send")
    def on_dm_send(data):
        """Real-time message send via socket (mirrors the REST endpoint)."""
        thread_id = data.get("thread_id")
        if not isinstance(thread_id, int):
            emit("dm:error", {"error": "Invalid thread ID"})
            return
        content = (data.get("content") or "").strip()
        if not thread_id or not content:
            emit("dm:error", {"error": "Message cannot be empty"})
            return
        if len(content) > 5000:
            emit("dm:error", {"error": "Message too long (max 5000 characters)"})
            return

        username = get_session_username()
        if not username:
            emit("dm:error", {"error": "Not authenticated"})
            return

        try:
            from models import ThreadMember, Message, Thread, User
            from __init__ import db
            from datetime import datetime

            user = User.query.filter_by(username=username).first()
            if not user:
                emit("dm:error", {"error": "User not found"})
                return

            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                emit("dm:error", {"error": "Not a member"})
                return

            # ── Connection Gate — friends-only check (Req 2/3) ─────────────────────
            try:
                from routes.messaging import (_check_friendship, _record_bypass_attempt,
                                              _check_dm_communication_ban, _check_stalker_pattern,
                                              _issue_dm_strike)
                _ws_others = ThreadMember.query.filter(
                    ThreadMember.thread_id == thread_id,
                    ThreadMember.user_id != user.id
                ).all()
                for _ws_om in _ws_others:
                    _ws_is_f, _ws_fs = _check_friendship(user.id, _ws_om.user_id)
                    if not _ws_is_f:
                        _ws_shadow = _record_bypass_attempt(user, _ws_om.user_id)
                        _ws_code = 'not_friends' if _ws_fs == 'none' else 'pending_approval'
                        emit("dm:error", {
                            "error": "You must be friends with this user to send a private message.",
                            "code": _ws_code,
                            "shadow_banned": _ws_shadow,
                        })
                        return
                    # Per-pair DM communication ban check
                    if _check_dm_communication_ban(user.id, _ws_om.user_id):
                        emit("dm:error", {
                            "error": "You are permanently banned from messaging this person.",
                            "code": "dm_comm_banned",
                            "dm_comm_banned": True,
                        })
                        return
                    # Block check — DB Block model (covers timed + permanent blocks)
                    try:
                        from models import Block as _WsBlock
                        from routes.messaging import _TIMED_BLOCKS as _ws_timed
                        from datetime import datetime as _ws_dt
                        if _WsBlock is not None and _WsBlock.is_blocked(_ws_om.user_id, user.id):
                            emit("dm:error", {"error": "You have been blocked by this user", "code": "blocked"})
                            return
                        if _WsBlock is not None and _WsBlock.is_blocked(user.id, _ws_om.user_id):
                            emit("dm:error", {"error": "You have blocked this user", "code": "blocked"})
                            return
                        # Legacy in-memory timed blocks fast-path
                        _blk_exp = _ws_timed.get((_ws_om.user_id, user.id))
                        if _blk_exp:
                            if _ws_dt.utcnow() < _blk_exp:
                                emit("dm:error", {"error": "You have been blocked by this user", "code": "blocked"})
                                return
                            else:
                                del _ws_timed[(_ws_om.user_id, user.id)]
                    except Exception:
                        pass  # non-critical — let REST path enforce on retry
            except Exception as _gate_err:
                print(f"[WS] dm:send friends-gate check failed: {_gate_err}; blocking message")
                emit("dm:error", {"error": "Connection required to message."})
                return
            # ────────────────────────────────────────────────────────────────────────

            # AI moderation + stalker detection
            mod_status = "clean"
            mod_reason = None
            try:
                from routes.messaging import _moderate_dm, _check_rate_limit, _check_stalker_pattern, _issue_dm_strike
                allowed, reason = _check_rate_limit(user.id)
                if not allowed:
                    emit("dm:error", {"error": "Rate limited", "reason": reason})
                    return
                # Stalker pattern check
                _ws_stalk_others = ThreadMember.query.filter(
                    ThreadMember.thread_id == thread_id,
                    ThreadMember.user_id != user.id
                ).all()
                for _st_om in _ws_stalk_others:
                    if _check_stalker_pattern(user.id, _st_om.user_id):
                        _sn, _ib = _issue_dm_strike(user.id, _st_om.user_id, "stalker_pattern")
                        emit("dm:error", {
                            "error": (f"⚠️ STRIKE {_sn}/3 — You are sending messages too rapidly to this person."
                                      if not _ib else
                                      "You are permanently banned from messaging this person due to repeated stalking."),
                            "code": "dm_comm_banned" if _ib else "dm_strike",
                            "dm_strike": True,
                            "strike_number": _sn,
                            "dm_comm_banned": _ib,
                        })
                        return
                # ── VybeFlow Anti-Scam Filter (WebSocket path) ───────────────
                try:
                    from dm_scam_filter import (
                        scan_dm_for_scam,
                        execute_scam_hard_block,
                        scam_blocked_notification,
                    )
                    _ws_scam_recipients = [om.user_id for om in _ws_stalk_others]
                    _ws_scam_result = scan_dm_for_scam(user, content, _ws_scam_recipients)
                    if _ws_scam_result.is_scam:
                        _ws_ip = ""
                        try:
                            from flask import request as _wsr
                            _ws_ip = _wsr.headers.get("X-Forwarded-For", _wsr.remote_addr or "")
                        except Exception:
                            pass
                        execute_scam_hard_block(
                            sender_id     = user.id,
                            recipient_ids = _ws_scam_recipients,
                            reason        = _ws_scam_result.reason,
                            sender_ip     = _ws_ip,
                        )
                        # Notify recipient(s) via socket before booting sender
                        _room_ws = f"dm:{thread_id}"
                        _ws_notif = scam_blocked_notification(username)
                        try:
                            from flask_socketio import emit as _ws_emit
                            _ws_emit("dm:security_event", _ws_notif, room=_room_ws)
                        except Exception:
                            pass
                        emit("dm:error", {
                            "error": "Scam activity detected. Your account has been terminated.",
                            "code": "scam_hard_blocked",
                            "redirect_to_stamp": True,
                        })
                        return
                except ImportError:
                    pass
                # ─────────────────────────────────────────────────────────────
                mod_status, mod_reason = _moderate_dm(content)
            except Exception as _mod_err:
                print(f"[WS] dm:send moderation import failed: {_mod_err}; allowing through")

            if mod_status == "blocked":
                # L3 credible threats → global ban (mirrors REST endpoint)
                try:
                    from routes.messaging import _classify_threat, _issue_dm_strike
                    _tl = _classify_threat(content)
                    if _tl == 3:
                        from __init__ import db as _db
                        user.negativity_warnings = (getattr(user, "negativity_warnings", 0) or 0) + 1
                        user.is_banned = True
                        user.ban_reason = "BANNED: Credible threat (L3) detected via DM"
                        user.is_suspended = True
                        user.suspension_reason = user.ban_reason
                        try:
                            from datetime import datetime as _dt2
                            user.banned_at = _dt2.utcnow()
                        except Exception:
                            pass
                        _db.session.commit()
                        emit("dm:error", {
                            "error": "You have been BANNED. A credible threat was detected.",
                            "banned": True,
                        })
                        return
                    # L1/L2/dm_harassment → per-pair DM strike
                    _per_pair_reasons = {"threat_level_1_aggressive", "threat_level_2_direct", "dm_harassment"}
                    if mod_reason in _per_pair_reasons:
                        if _tl in (1, 2):
                            from __init__ import db as _db2
                            _cur_w = (getattr(user, "negativity_warnings", 0) or 0)
                            if _cur_w < 3:  # cap at 3 — never increment past the ban threshold
                                _cur_w += 1
                                user.negativity_warnings = _cur_w
                                if _cur_w >= 3:
                                    user.is_banned = True
                                    user.is_suspended = True
                                    user.ban_reason = "BANNED: 3 strikes for harassment via DM"
                                    user.suspension_reason = user.ban_reason
                                    from datetime import datetime as _dt_ban
                                    user.banned_at = _dt_ban.utcnow()
                            try:
                                _db2.session.commit()
                            except Exception:
                                _db2.session.rollback()
                        _strike_ws_others = ThreadMember.query.filter(
                            ThreadMember.thread_id == thread_id,
                            ThreadMember.user_id != user.id
                        ).all()
                        for _sdk_om in _strike_ws_others:
                            _sn, _ib = _issue_dm_strike(user.id, _sdk_om.user_id, mod_reason)
                            _strike_ws_msgs = {
                                1: (f"⚠️ STRIKE 1/3 — Message blocked for harassment. "
                                    "Two more strikes will permanently ban you from messaging this person."),
                                2: (f"⚠️ STRIKE 2/3 — Message blocked again. "
                                    "ONE MORE strike will permanently ban you."),
                            }
                            emit("dm:error", {
                                "error": ("You are PERMANENTLY BANNED from messaging this person."
                                          if _ib else
                                          _strike_ws_msgs.get(_sn, f"⚠️ Strike {_sn}/3 — Message blocked.")),
                                "code": "dm_comm_banned" if _ib else "dm_strike",
                                "dm_strike": True,
                                "strike_number": _sn,
                                "dm_comm_banned": _ib,
                                "reason": mod_reason,
                            })
                            return
                except Exception:
                    pass
                _tl_msgs = {
                    "threat_level_3_credible": "Blocked: credible threats are reported and result in a permanent ban.",
                    "threat_level_2_direct":   "Blocked: direct threats are not allowed. Strike applied.",
                    "threat_level_1_aggressive": "Blocked: aggressive threatening language is not allowed. Strike applied.",
                }
                emit("dm:error", {"error": _tl_msgs.get(mod_reason, "Message blocked"), "reason": mod_reason})
                return

            # Encrypt
            thread = db.session.get(Thread, thread_id)
            encrypted_content = content
            nonce = None
            try:
                from routes.messaging import _encrypt_message
                if getattr(thread, "is_encrypted", False):
                    encrypted_content, nonce = _encrypt_message(content, thread_id)
            except Exception:
                pass  # Store plaintext if encryption unavailable

            msg = Message(
                thread_id=thread_id,
                sender_id=user.id,
                content=encrypted_content,
                is_encrypted=bool(nonce),  # only encrypted if nonce was generated
                encryption_nonce=nonce,
                moderation_status=mod_status,
            )
            db.session.add(msg)
            thread.last_message_at = datetime.now(timezone.utc)
            member.last_read_at = datetime.now(timezone.utc)
            db.session.commit()

            room = f"dm:{thread_id}"
            emit("dm:message", {
                "id": msg.id,
                "thread_id": thread_id,
                # For encrypted threads emit the ciphertext so the client can
                # decrypt it client-side.  Sending plaintext alongside the
                # ciphertext would defeat the purpose of E2E encryption.
                "content": encrypted_content if getattr(msg, "is_encrypted", False) else content,
                "sender": username,
                "sender_id": user.id,
                "sender_display": getattr(user, "display_name", None) or username,
                "sender_avatar": getattr(user, "avatar_url", None) or "",
                "is_encrypted": getattr(msg, "is_encrypted", False),
                "nonce": nonce,
                "moderation": mod_status,
                "created_at": msg.created_at.isoformat() if msg.created_at else None,
            }, room=room)

            # ── Vybe Pulse: Web Push for offline/background recipients ────────
            # Notify every thread member who is NOT the sender so they get a
            # browser / smartphone push notification even when the tab is closed.
            try:
                from routes.notifications import create_pulse
                _other_members = ThreadMember.query.filter(
                    ThreadMember.thread_id == thread_id,
                    ThreadMember.user_id != user.id,
                ).all()
                for _om in _other_members:
                    _preview = (content[:60] + "…") if len(content) > 60 else content
                    _pulse = create_pulse(
                        recipient_id=_om.user_id,
                        actor_id=user.id,
                        pulse_type="dm",
                        message=f"{username}: {_preview}",
                        emoji="💬",
                        push=True,
                    )
                    if _pulse and _socketio:
                        _socketio.emit(
                            "vybe_pulse",
                            _pulse.to_dict(),
                            room=f"user_{_om.user_id}",
                        )
            except Exception as _pulse_err:
                print(f"[WS] dm pulse error: {_pulse_err}")
            # ──────────────────────────────────────────────────────────────────

        except Exception as e:
            db.session.rollback()
            print(f"[WS] dm:send error: {e}")
            emit("dm:error", {"error": "Message send failed. Please try again."})

    @socketio.on("dm:send_notify")
    def on_dm_send_notify(data):
        """Lightweight relay: after REST save, broadcast to the thread room."""
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        # Verify membership before broadcasting
        try:
            from models import ThreadMember, User
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                return
        except Exception:
            return

        room = f"dm:{thread_id}"
        emit("dm:message", {
            "id": data.get("id"),
            "thread_id": thread_id,
            "content": data.get("content", ""),
            "sender": username,
            "sender_id": user.id,
            "sender_display": getattr(user, "display_name", None) or username,
            "sender_avatar": getattr(user, "avatar_url", None) or "",
            "media_type": data.get("media_type"),
            "media_url": data.get("media_url"),
            "sensitive": bool(data.get("sensitive")),
            "has_pin": bool(data.get("has_pin")),
            "voice_duration": data.get("voice_duration"),
            "voice_summary": data.get("voice_summary"),
            "created_at": data.get("created_at"),
        }, room=room, include_self=False)

    # ─── Screenshot Alert ─────────────────────────────────────────────────────

    @socketio.on("dm:screenshot")
    def on_dm_screenshot(data):
        """Recipient tells the server they screenshotted — notify the sender."""
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        try:
            from models import ThreadMember, Thread, User
            from __init__ import db
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                return
            thread = db.session.get(Thread, thread_id)
            if not thread or not getattr(thread, "screenshot_notify", False):
                return
            # Notify every OTHER member in this thread
            from models import ThreadMember as TM
            other_members = TM.query.filter(
                TM.thread_id == thread_id,
                TM.user_id != user.id
            ).all()
            for m in other_members:
                emit("dm:screenshot_alert", {
                    "thread_id": thread_id,
                    "by": username,
                    "by_id": user.id,
                }, room=f"user:{m.user_id}")
        except Exception as e:
            print(f"[WS] dm:screenshot error: {e}")

    # ─── Message View + Ephemeral / Replay Limit ──────────────────────────────

    @socketio.on("dm:message_view")
    def on_dm_message_view(data):
        """
        Called when a message is displayed in the client.
        - Increments replay_count; enforces replay_limit.
        - If first view of an ephemeral message, schedules auto-delete.
        - Notifies room if message is now burnt.
        """
        msg_id = data.get("msg_id")
        thread_id = data.get("thread_id")
        if not msg_id or not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        try:
            from models import ThreadMember, Message, User
            from __init__ import db
            from datetime import datetime, timedelta

            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if not member:
                return

            msg = db.session.get(Message, msg_id)
            if not msg or msg.thread_id != int(thread_id):
                return
            # Don't track views for own messages (sender sees their own)
            if msg.sender_id == user.id:
                return

            already_burnt = getattr(msg, "is_burnt", False)
            if already_burnt:
                emit("dm:message_burnt", {"msg_id": msg_id}, room=f"dm:{thread_id}")
                return

            # Increment replay count atomically to avoid race conditions
            Message.query.filter_by(id=msg_id).update(
                {"replay_count": (Message.replay_count or 0) + 1}
            )
            db.session.flush()
            db.session.refresh(msg)

            # Record first view time for ephemerals
            if msg.viewed_at is None:
                msg.viewed_at = datetime.now(timezone.utc)
                ephemeral_seconds = getattr(msg, "ephemeral_seconds", None)
                if ephemeral_seconds:
                    msg.expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(ephemeral_seconds))
                    # Tell the room about the countdown
                    emit("dm:ephemeral_start", {
                        "msg_id": msg_id,
                        "expires_at": msg.expires_at.isoformat(),
                        "seconds": int(ephemeral_seconds),
                    }, room=f"dm:{thread_id}")

            # Enforce replay limit
            replay_limit = getattr(msg, "replay_limit", None)
            if replay_limit is not None and msg.replay_count >= int(replay_limit):
                msg.is_burnt = True
                msg.content = None   # wipe plaintext
                db.session.commit()
                emit("dm:message_burnt", {"msg_id": msg_id}, room=f"dm:{thread_id}")
                return

            db.session.commit()

            # If replay limit exists, tell the viewer how many views remain
            if replay_limit is not None:
                remaining = max(0, int(replay_limit) - msg.replay_count)
                emit("dm:replay_remaining", {
                    "msg_id": msg_id,
                    "remaining": remaining,
                }, room=request_sid_room())  # only to the viewer
        except Exception as e:
            print(f"[WS] dm:message_view error: {e}")

    def request_sid_room():
        """Helper: return the current socket's own SID as a room (self-only emit)."""
        from flask import request as _req
        return _req.sid

    # ─── WebRTC Call Signaling ────────────────────────────────────────────────

    @socketio.on("connect")
    def on_connect():
        """Join user-specific room so incoming calls can find this socket."""
        from flask import request as flask_request
        user_id = session.get("user_id")
        username = get_session_username()

        # Fallback: if session doesn't have user info, try auth data from client
        if not user_id and not username:
            auth = getattr(flask_request, 'auth', None) or {}
            if isinstance(auth, dict):
                user_id = auth.get("user_id")
                if user_id:
                    try:
                        user_id = int(user_id)
                    except (ValueError, TypeError):
                        user_id = None

        if not user_id and not username:
            print(f"[WS] connect: no identity in session or auth, skipping room join. session keys={list(session.keys())}")
            return
        try:
            from models import User
            from __init__ import db
            user = None
            if user_id:
                user = db.session.get(User, user_id)
            if not user and username:
                user = User.query.filter_by(username=username).first()
            if user:
                join_room(f"user:{user.id}")
                join_room(f"user_{user.id}")  # Also join underscore format used by vybe_pulse / feed emits
                # Store user info in socketio session for later use
                session["user_id"] = user.id
                session["username"] = user.username
                print(f"[WS] connect: {user.username} (id={user.id}) joined room user:{user.id}")
                # Track online status
                sid = flask_request.sid
                if user.id not in _online_users:
                    _online_users[user.id] = set()
                _online_users[user.id].add(sid)
                # Broadcast to everyone that user came online
                emit("user:online", {"user_id": user.id}, broadcast=True)
                # Send back the full online list to this socket
                online_ids = list(_online_users.keys())
                emit("user:online_list", {"user_ids": online_ids})
            else:
                print(f"[WS] connect: user not found (user_id={user_id}, username='{username}')")
        except Exception as e:
            print(f"[WS] connect error: {e}")
            import traceback; traceback.print_exc()

    @socketio.on("disconnect")
    def on_disconnect():
        """Remove user from online tracking on disconnect."""
        from flask import request as flask_request
        username = get_session_username()
        if not username:
            return
        try:
            from models import User
            user = User.query.filter_by(username=username).first()
            if user:
                sid = flask_request.sid
                if user.id in _online_users:
                    _online_users[user.id].discard(sid)
                    if not _online_users[user.id]:
                        del _online_users[user.id]
                        emit("user:offline", {"user_id": user.id}, broadcast=True)
        except Exception:
            pass

    @socketio.on("post:typing")
    def on_post_typing(data):
        """Broadcast 'X people typing' to all feed viewers when someone types on a post comment."""
        if not data or not data.get("post_id"):
            return
        username = get_session_username() or (data.get("user") or "")
        emit("post:typing", {
            "post_id": data["post_id"],
            "user": username,
        }, broadcast=True, include_self=False)

    @socketio.on("post:typing_stop")
    def on_post_typing_stop(data):
        """Broadcast typing stopped event."""
        if not data or not data.get("post_id"):
            return
        emit("post:typing_stop", {
            "post_id": data["post_id"],
        }, broadcast=True, include_self=False)

    @socketio.on("dm:delete")
    def on_dm_delete(data):
        """Broadcast a message deletion to all members of the thread room.

        The REST DELETE route already performed auth + DB deletion.
        Here we only verify the caller is a thread member, then fan-out
        the 'dm:deleted' event so every connected client removes the row.
        """
        thread_id = data.get("thread_id")
        msg_id = data.get("msg_id")
        if not thread_id or not msg_id:
            return
        username = get_session_username()
        if not username:
            return
        try:
            from models import ThreadMember, User
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(
                thread_id=thread_id, user_id=user.id
            ).first()
            if not member:
                return  # not a member — ignore
        except Exception:
            return
        room = f"dm:{thread_id}"
        emit("dm:deleted", {
            "msg_id": msg_id,
            "thread_id": thread_id,
            "by": username,
        }, room=room)

    @socketio.on("dm:edit")
    def on_dm_edit(data):
        """Broadcast a message edit to all members of the thread room.

        The REST PATCH route already updated the DB.  Here we fan-out
        the 'dm:edited' event so every connected client updates the bubble.
        """
        thread_id = data.get("thread_id")
        msg_id    = data.get("msg_id")
        new_text  = (data.get("content") or "").strip()
        if not thread_id or not msg_id:
            return
        username = get_session_username()
        if not username:
            return
        try:
            from models import ThreadMember, User
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            if not ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first():
                return
        except Exception:
            return
        emit("dm:edited", {
            "msg_id":    msg_id,
            "thread_id": thread_id,
            "content":   new_text,
            "by":        username,
        }, room=f"dm:{thread_id}")

    # ── In-memory vibe state per thread ──────────────────────────────────────
    # { (thread_id, user_id): "hype" }
    _vibe_state: dict = {}

    # Vibe → compatible peer vibes (when user A and user B both match any entry
    # they get a shared atmosphere).  Matching = same vibe OR paired vibes.
    _VIBE_PAIRS = {
        "hype":     {"hype"},
        "deep":     {"deep"},
        "chill":    {"chill"},
        "love":     {"love"},
        "creative": {"creative"},
        "grind":    {"grind", "focused"},
        "focused":  {"grind", "focused"},
        "sad":      {"sad"},
        "lit":      {"lit", "hype"},
        "flex":     {"flex"},
    }

    @socketio.on("dm:vibe_update")
    def on_dm_vibe_update(data):
        """User broadcasts their current vibe for this thread.
        If the other user's vibe matches (same category), emit dm:vibe_sync to both."""
        thread_id = data.get("thread_id")
        vibe      = (data.get("vibe") or "").strip().lower()
        if not thread_id or not vibe:
            return
        username = get_session_username()
        if not username:
            return
        try:
            from models import ThreadMember, User
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            if not ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first():
                return
            # Store this user's vibe
            _vibe_state[(thread_id, user.id)] = vibe
            # Find the other member's vibe
            other_member = ThreadMember.query.filter(
                ThreadMember.thread_id == thread_id,
                ThreadMember.user_id != user.id
            ).first()
            if not other_member:
                return
            other_vibe = _vibe_state.get((thread_id, other_member.user_id))
            # Check for match
            compatible = _VIBE_PAIRS.get(vibe, {vibe})
            if other_vibe and other_vibe in compatible:
                # SYNC! Both users share a compatible vibe — broadcast to room
                emit("dm:vibe_sync", {
                    "thread_id": thread_id,
                    "vibe":      vibe,
                    "synced":    True,
                }, room=f"dm:{thread_id}")
            else:
                # No match yet — tell only this user their vibe was recorded
                emit("dm:vibe_sync", {
                    "thread_id": thread_id,
                    "vibe":      vibe,
                    "synced":    False,
                })
        except Exception as _ve:
            print(f"[WS] dm:vibe_update error: {_ve}")

    @socketio.on("call:ring")
    def on_call_ring(data):
        """Notify callee of an incoming call."""
        callee_id = data.get("callee_id")
        caller_username = get_session_username()
        print(f"[WS] call:ring from '{caller_username}' to callee_id={callee_id}")
        if not callee_id or not caller_username:
            print(f"[WS] call:ring REJECTED: callee_id={callee_id}, caller={caller_username}")
            return
        # Look up caller's avatar & display name for the call UI
        caller_avatar = ""
        caller_display = caller_username
        try:
            from models import User
            u = User.query.filter_by(username=caller_username).first()
            if u:
                caller_avatar = u.avatar_url or ""
                caller_display = u.display_name or caller_username
        except Exception:
            pass
        emit("call:ring", {
            "caller": caller_username,
            "caller_id": data.get("caller_id"),
            "call_type": data.get("call_type", "audio"),
            "caller_avatar": caller_avatar,
            "caller_display": caller_display,
        }, room=f"user:{callee_id}")
        print(f"[WS] call:ring emitted to room user:{callee_id}")

    @socketio.on("call:offer")
    def on_call_offer(data):
        """Relay WebRTC SDP offer from caller to callee."""
        caller_username = get_session_username()
        if not caller_username:
            return
        callee_id = data.get("callee_id")
        sdp = data.get("sdp")
        if not callee_id or not isinstance(sdp, dict) or not sdp.get("type") or not sdp.get("sdp"):
            return
        caller_avatar = ""
        caller_display = caller_username
        try:
            from models import User
            u = User.query.filter_by(username=caller_username).first()
            if u:
                caller_avatar = u.avatar_url or ""
                caller_display = u.display_name or caller_username
        except Exception:
            pass
        emit("call:offer", {
            "sdp": sdp,
            "caller": caller_username,
            "caller_id": data.get("caller_id"),
            "call_type": data.get("call_type", "audio"),
            "caller_avatar": caller_avatar,
            "caller_display": caller_display,
        }, room=f"user:{callee_id}")

    @socketio.on("call:answer")
    def on_call_answer(data):
        """Relay WebRTC SDP answer from callee back to caller."""
        if not (session.get("username") or "").strip():
            return
        caller_id = data.get("caller_id")
        sdp = data.get("sdp")
        if not caller_id or not isinstance(sdp, dict) or not sdp.get("type") or not sdp.get("sdp"):
            return
        emit("call:answer", {
            "sdp": sdp,
        }, room=f"user:{caller_id}")

    @socketio.on("call:ice")
    def on_call_ice(data):
        """Relay ICE candidate between peers."""
        if not (session.get("username") or "").strip():
            return
        target_id = data.get("target_id")
        candidate = data.get("candidate")
        if not target_id or not isinstance(candidate, dict):
            return
        emit("call:ice", {
            "candidate": candidate,
        }, room=f"user:{target_id}")

    @socketio.on("call:end")
    def on_call_end(data):
        """Signal that a call has ended."""
        if not (session.get("username") or "").strip():
            return
        target_id = data.get("target_id")
        if not target_id:
            return
        emit("call:end", {}, room=f"user:{target_id}")

    @socketio.on("call:reaction")
    def on_call_reaction(data):
        """Relay in-call emoji reaction to the other participant."""
        if not (session.get("username") or "").strip():
            return
        target_id = data.get("target_id")
        emoji = (data.get("emoji") or "").strip()
        if not target_id or not emoji:
            return
        emit("call:reaction", {"emoji": emoji}, room=f"user:{target_id}")

    @socketio.on("dm:reaction")
    def on_dm_reaction(data):
        """Broadcast a message reaction to thread members."""
        thread_id = data.get("thread_id")
        msg_id = data.get("message_id")
        emoji = (data.get("emoji") or "").strip()
        if not thread_id or not msg_id or not emoji:
            return
        if len(emoji) > 10:
            return
        # Reject if it contains HTML-like content
        if '<' in emoji or '>' in emoji or '&' in emoji:
            return
        username = get_session_username()
        if not username:
            return
        # Simple rate limit: max 1 reaction per second via session timestamp
        import time
        last_react = session.get("_last_reaction_ts", 0)
        now = time.time()
        if now - last_react < 1.0:
            return
        session["_last_reaction_ts"] = now
        room = f"dm:{thread_id}"
        emit("dm:reaction", {
            "message_id": msg_id,
            "emoji": emoji,
            "user": username,
            "intensity": max(1, min(5, data.get("intensity", 3))),
        }, room=room)

    @socketio.on("dm:read")
    def on_dm_read(data):
        thread_id = data.get("thread_id")
        if not thread_id:
            return
        username = get_session_username()
        if not username:
            return
        try:
            from models import ThreadMember, User
            from __init__ import db
            from datetime import datetime

            user = User.query.filter_by(username=username).first()
            if not user:
                return
            member = ThreadMember.query.filter_by(thread_id=thread_id, user_id=user.id).first()
            if member:
                member.last_read_at = datetime.now(timezone.utc)
                db.session.commit()

            room = f"dm:{thread_id}"
            emit("dm:read", {"user": username}, room=room, include_self=False)
        except Exception:
            pass

    # ─── Nude Content Consent SocketIO Events ─────────────────────────

    @socketio.on("dm:nude_consent_request")
    def on_nude_consent_request(data):
        """Sender requests consent — notify receiver in real time."""
        username = get_session_username()
        if not username:
            return
        try:
            from models import User, NudeContentConsent
            from __init__ import db

            user = User.query.filter_by(username=username).first()
            if not user:
                return
            receiver_id = data.get("receiver_id")
            if not receiver_id:
                return

            # Emit to receiver's personal room
            emit("dm:nude_consent_incoming", {
                "requester_id": user.id,
                "requester_name": getattr(user, "display_name", None) or user.username,
                "requester_avatar": getattr(user, "avatar_url", None) or "",
            }, room=f"user:{receiver_id}")
        except Exception:
            pass

    @socketio.on("dm:nude_consent_response")
    def on_nude_consent_response(data):
        """Receiver responds — notify sender in real time."""
        username = get_session_username()
        if not username:
            return
        try:
            from models import User
            user = User.query.filter_by(username=username).first()
            if not user:
                return
            requester_id = data.get("requester_id")
            decision = data.get("decision")  # "approved" or "denied"
            if not requester_id or decision not in ("approved", "denied"):
                return

            emit("dm:nude_consent_result", {
                "approver_id": user.id,
                "approver_name": getattr(user, "display_name", None) or user.username,
                "decision": decision,
            }, room=f"user:{requester_id}")
        except Exception:
            pass

    # ─── Live Stream — viewer counter + live chat ──────────────────────────────
    # Viewer counts are tracked in _live_viewers (module-level dict).

    @socketio.on("live:join")
    def on_live_join(data):
        """Viewer joins a live stream room. Broadcasts updated viewer count.
        Also joins the personal user room so the host can target this socket via live:kick."""
        stream_id = str(data.get("stream_id") or "global")
        username = get_session_username() or "Viewer"
        room = f"live:{stream_id}"
        join_room(room)
        # Join personal user room so live:kick can target this socket
        if username and username != "Viewer":
            join_room(f"user:{username.lower()}")
        _live_viewers.setdefault(stream_id, {})[id(session)] = username
        viewer_count = len(_live_viewers[stream_id])
        emit("live:viewer_count", {"count": viewer_count, "stream_id": stream_id}, room=room)
        emit("live:user_joined", {"username": username, "count": viewer_count}, room=room, include_self=False)

    @socketio.on("live:leave")
    def on_live_leave(data):
        """Viewer leaves a live stream room. Broadcasts updated viewer count."""
        stream_id = str(data.get("stream_id") or "global")
        username = get_session_username() or "Viewer"
        room = f"live:{stream_id}"
        leave_room(room)
        viewers = _live_viewers.get(stream_id, {})
        viewers.pop(id(session), None)
        viewer_count = len(viewers)
        emit("live:viewer_count", {"count": viewer_count, "stream_id": stream_id}, room=room)
        emit("live:user_left", {"username": username, "count": viewer_count}, room=room, include_self=False)

    @socketio.on("live:chat")
    def on_live_chat(data):
        """Broadcast a live chat message to all viewers in the stream room."""
        stream_id = str(data.get("stream_id") or "global")
        message = (data.get("message") or "").strip()[:500]
        username = get_session_username() or "Viewer"
        if not message:
            return
        room = f"live:{stream_id}"
        emit("live:chat_message", {
            "username": username,
            "message": message,
            "stream_id": stream_id,
        }, room=room)

    # ──────────────────────────────────────────────────────────────────────────


def kick_viewer_from_live(blocked_username: str, stream_id: str) -> None:
    """Emit live:kick to the blocked user's personal socket room.

    Called by the block API after a block is committed. The kicked viewer
    sees a brief overlay then gets redirected to the blocked screen.

    blocked_username  — lowercase username of the viewer to eject
    stream_id         — the stream they were watching (host's username)
    """
    if _socketio is None:
        return
    user_room = f"user:{blocked_username.lower()}"
    _socketio.emit(
        "live:kick",
        {"reason": "blocked", "stream_id": stream_id},
        room=user_room,
    )
    # Remove them from the in-memory viewer count
    viewers = _live_viewers.get(stream_id, {})
    evict_keys = [k for k, v in viewers.items() if v.lower() == blocked_username.lower()]
    for k in evict_keys:
        viewers.pop(k, None)
    if evict_keys:
        room = f"live:{stream_id}"
        viewer_count = len(viewers)
        _socketio.emit(
            "live:viewer_count",
            {"count": viewer_count, "stream_id": stream_id},
            room=room,
        )
