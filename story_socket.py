import uuid
from flask_socketio import join_room, leave_room, emit


def register_story_socketio(socketio):
    """Register Socket.IO events for real-time story collaboration"""

    @socketio.on("join")
    def on_join(data):
        story_id = (data.get("story_id") or "").strip()
        user = data.get("user") or {"id": str(uuid.uuid4())[:8], "name": "Anon"}

        if not story_id:
            return

        join_room(story_id)
        emit("presence", {"type": "join", "user": user}, room=story_id)

    @socketio.on("leave")
    def on_leave(data):
        story_id = (data.get("story_id") or "").strip()
        user = data.get("user") or {"id": "unknown", "name": "Anon"}
        if not story_id:
            return
        leave_room(story_id)
        emit("presence", {"type": "leave", "user": user}, room=story_id)

    @socketio.on("patch")
    def on_patch(data):
        """
        data: { story_id, patch, user }
        patch is a small update the clients apply.
        """
        story_id = (data.get("story_id") or "").strip()
        patch = data.get("patch")
        user = data.get("user")

        if not story_id or patch is None:
            return

        emit("patch", {"patch": patch, "user": user}, room=story_id, include_self=False)
