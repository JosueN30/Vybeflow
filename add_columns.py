"""
One-time script to add new columns to the existing SQLite database.
Run once: python add_columns.py
"""
from app import create_app

app, _ = create_app()
with app.app_context():
    from __init__ import db
    engine = db.engine

    columns = [
        ("user", "ALTER TABLE user ADD COLUMN business_category VARCHAR(80)"),
        ("user", "ALTER TABLE user ADD COLUMN portfolio_url TEXT"),
        ("user", "ALTER TABLE user ADD COLUMN skills_list TEXT"),
        ("user", "ALTER TABLE user ADD COLUMN professional_verified BOOLEAN DEFAULT 0"),
        ("message", "ALTER TABLE message ADD COLUMN is_ghosted_scam BOOLEAN DEFAULT 0 NOT NULL"),
        # Onboarding walkthrough — added 2026
        ("user", "ALTER TABLE user ADD COLUMN is_new_user BOOLEAN DEFAULT 1 NOT NULL"),
    ]

    with engine.connect() as conn:
        for table, sql in columns:
            try:
                conn.execute(db.text(sql))
                conn.commit()
                print(f"[OK] Added column to {table}: {sql.split('ADD COLUMN')[1].split()[0]}")
            except Exception as e:
                msg = str(e)
                if "duplicate column" in msg.lower() or "already exists" in msg.lower():
                    print(f"[SKIP] Column already exists in {table}: {sql.split('ADD COLUMN')[1].split()[0]}")
                else:
                    print(f"[ERROR] {table}: {e}")

    print("\nDone. All columns are present.")
