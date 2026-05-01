"""migrate_new_columns.py — adds the 3 new DmPayment columns + system_log table."""
from app import create_app
from sqlalchemy import text, inspect

app, _ = create_app()
with app.app_context():
    from __init__ import db

    engine = db.engine
    insp   = inspect(engine)

    # ── dm_payment ────────────────────────────────────────────────────────────
    existing = {c["name"] for c in insp.get_columns("dm_payment")}
    adds = {
        "idempotency_key":     "VARCHAR(64)",
        "webhook_confirmed":   "BOOLEAN DEFAULT 0",
        "unlocked_message_id": "INTEGER",
    }
    with engine.connect() as conn:
        for col, typedef in adds.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE dm_payment ADD COLUMN {col} {typedef}"))
                print(f"  + dm_payment.{col}")
            else:
                print(f"  = dm_payment.{col} already exists")
        conn.commit()

    # ── system_log ────────────────────────────────────────────────────────────
    if "system_log" not in insp.get_table_names():
        sql = (
            "CREATE TABLE system_log ("
            "id         INTEGER PRIMARY KEY AUTOINCREMENT,"
            "level      VARCHAR(10)  NOT NULL DEFAULT 'error',"
            "source     VARCHAR(80)  NOT NULL DEFAULT '',"
            "message    TEXT         NOT NULL DEFAULT '',"
            "detail     TEXT,"
            "user_id    INTEGER,"
            "ip_address VARCHAR(45),"
            "request_id VARCHAR(36),"
            "created_at DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP"
            ")"
        )
        with engine.connect() as conn:
            conn.execute(text(sql))
            conn.commit()
        print("  + system_log table created")
    else:
        print("  = system_log already exists")

    print("Migration complete.")
