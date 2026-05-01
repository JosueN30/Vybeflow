"""
Direct SQLite cleanup — deletes all test/dummy users and their data via raw SQL.
Safe: keeps DAREALEST1, Thevibeteam, Thedon.
"""
import sqlite3, os

DB_PATH = r"d:\Vybeflow-main\instance\vybeflow.db"
KEEP_USERNAMES = ("DAREALEST1", "Thevibeteam", "Thedon")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA foreign_keys=OFF")  # disable FK enforcement for cleanup

# Get IDs to delete
placeholders = ",".join("?" * len(KEEP_USERNAMES))
rows = c.execute(f"SELECT id, username FROM user WHERE username NOT IN ({placeholders})", KEEP_USERNAMES).fetchall()
delete_ids = [r["id"] for r in rows]
print(f"Users to delete: {[r['username'] for r in rows]}")

if not delete_ids:
    print("Nothing to delete!")
    conn.close()
    exit()

id_placeholders = ",".join("?" * len(delete_ids))

# Tables that reference user.id — delete related rows first
user_ref_tables = [
    "story_item",       # via story → author_id
    "story",            # author_id
    "post",             # author_id
    "thread_member",    # user_id
    "message",          # sender_id
    "device_fingerprint",  # user_id
    "follow",           # follower_id or following_id
    "block",            # blocker_id or blocked_id
    "notification",     # recipient_id
    "friend_request",   # requester_id or requestee_id
    "dm_strike",        # sender_id or target_id
    "dm_communication_ban",  # user_id
    "like",             # user_id
    "comment",          # author_id
    "reaction",         # user_id
    "report",           # reporter_id
    "passkey",          # user_id
    "payment",          # user_id
    "pay_to_message_request",  # sender_id or recipient_id
]

for tbl in user_ref_tables:
    # Check if table exists
    exists = c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)).fetchone()
    if not exists:
        continue
    # Try to find user_id columns
    cols = [col[1] for col in c.execute(f"PRAGMA table_info({tbl})").fetchall()]
    deleted = 0
    for col in ["user_id", "author_id", "sender_id", "requester_id", "blocker_id"]:
        if col in cols:
            n = c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({id_placeholders})", delete_ids).rowcount
            deleted += n
    # Extra: follow has follower_id / following_id
    if tbl == "follow":
        for col in ["following_id"]:
            if col in cols:
                n = c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({id_placeholders})", delete_ids).rowcount
                deleted += n
    if tbl == "block":
        for col in ["blocked_id"]:
            if col in cols:
                n = c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({id_placeholders})", delete_ids).rowcount
                deleted += n
    if tbl == "friend_request":
        for col in ["requestee_id"]:
            if col in cols:
                n = c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({id_placeholders})", delete_ids).rowcount
                deleted += n
    if tbl == "dm_strike":
        for col in ["target_id"]:
            if col in cols:
                n = c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({id_placeholders})", delete_ids).rowcount
                deleted += n
    if tbl == "pay_to_message_request":
        for col in ["recipient_id"]:
            if col in cols:
                n = c.execute(f"DELETE FROM {tbl} WHERE {col} IN ({id_placeholders})", delete_ids).rowcount
                deleted += n
    if deleted:
        print(f"  Deleted {deleted} rows from {tbl}")

# Now delete threads that have NO remaining members (orphan threads)
c.execute("""
    DELETE FROM thread WHERE id NOT IN (SELECT DISTINCT thread_id FROM thread_member)
""")

# Delete the users themselves
n = c.execute(f"DELETE FROM user WHERE id IN ({id_placeholders})", delete_ids).rowcount
print(f"Deleted {n} users")

conn.commit()
conn.execute("PRAGMA foreign_keys=ON")

# Verify
remaining = c.execute("SELECT id, username FROM user").fetchall()
print(f"\nRemaining users ({len(remaining)}):")
for r in remaining:
    print(f"  id={r['id']} username={r['username']}")

stories = c.execute("SELECT COUNT(*) FROM story").fetchone()[0]
print(f"Stories remaining: {stories}")

conn.close()
print("\n✅ Cleanup complete")
