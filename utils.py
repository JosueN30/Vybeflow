# Flask notify utility for VybeFlow
import logging as _logging

_notify_log = _logging.getLogger("vybeflow.utils")


def notify(user_id, message):
    from __init__ import db
    from models import Notification
    note = Notification(user_id=user_id, message=message)
    db.session.add(note)
    try:
        db.session.commit()
    except Exception as _e:
        db.session.rollback()
        _notify_log.error("[notify] Failed to persist notification for user %s: %s", user_id, _e)
