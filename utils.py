# Flask notify utility for VybeFlow
from flask import session


def notify(user_id, message):
    from VybeFlowapp import Notification, db
    note = Notification(user_id=user_id, message=message)
    db.session.add(note)
    db.session.commit()
