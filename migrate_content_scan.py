"""
migrate_content_scan.py
Add content_label, content_flags to Story and mature_pin to User.
Safe to run multiple times.
"""
from app import create_app
from __init__ import db
import sqlalchemy as sa

app, socketio = create_app()
with app.app_context():
    insp = sa.inspect(db.engine)
    story_cols = [c["name"] for c in insp.get_columns("story")]
    user_cols  = [c["name"] for c in insp.get_columns("user")]

    with db.engine.connect() as conn:
        if "content_label" not in story_cols:
            conn.execute(sa.text(
                "ALTER TABLE story ADD COLUMN content_label VARCHAR(20) NOT NULL DEFAULT 'clean'"
            ))
            print("Added story.content_label")
        else:
            print("story.content_label already present")

        if "content_flags" not in story_cols:
            conn.execute(sa.text(
                "ALTER TABLE story ADD COLUMN content_flags TEXT"
            ))
            print("Added story.content_flags")
        else:
            print("story.content_flags already present")

        if "mature_pin" not in user_cols:
            conn.execute(sa.text(
                "ALTER TABLE \"user\" ADD COLUMN mature_pin VARCHAR(128)"
            ))
            print("Added user.mature_pin")
        else:
            print("user.mature_pin already present")

        conn.commit()

    print("Migration complete.")
