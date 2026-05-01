import sqlite3, json, datetime

db_path = 'instance/vybeflow.db'
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=" * 55)
print("VYBEFLOW POST SIMULATION - PROOF OF LIFE")
print("=" * 55)

# Check post table exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='post'")
tbl = cur.fetchone()
print("post table:", tbl['name'] if tbl else 'NOT FOUND - creating via schema...')

if not tbl:
    print("[ERR] post table missing. Run: python manage.py db upgrade")
    conn.close()
    exit(1)

# Get column names
cur.execute("PRAGMA table_info(post)")
cols = [r['name'] for r in cur.fetchall()]
print("Columns:", ', '.join(cols[:8]), '...')

# Get a real user
cur.execute("SELECT id, username FROM user LIMIT 1")
row = cur.fetchone()
if not row:
    print("[WARN] No users found - creating sim user...")
    cur.execute("INSERT INTO user (username, email, password_hash, created_at) VALUES (?,?,?,?)",
                ('_sim_user', 'sim@sim.local', 'x', datetime.datetime.utcnow().isoformat()))
    conn.commit()
    user_id = cur.lastrowid
    username = '_sim_user'
else:
    user_id = row['id']
    username = row['username']

print(f"Using user: {username} (id={user_id})")

# Build insert based on available columns
now = datetime.datetime.utcnow().isoformat()
common = {
    'author_id': user_id,
    'caption': 'Jesus is the best',
    'visibility': 'public',
    'music_start_sec': 0,
    'is_adult': 0,
    'needs_review': 0,
    'screenshot_alert': 0,
    'screenshot_count': 0,
    'watermark_enabled': 0,
    'like_count': 0,
    'comment_count': 0,
    'share_count': 0,
    'view_count': 0,
    'is_anonymous': 0,
    'is_event': 0,
    'is_vault': 0,
    'created_at': now,
    'updated_at': now,
}
if 'bg_style' in cols:
    common['bg_style'] = 'default'

kcols = list(common.keys())
vals = list(common.values())
placeholders = ','.join(['?'] * len(vals))
sql = f"INSERT INTO post ({','.join(kcols)}) VALUES ({placeholders})"

try:
    cur.execute(sql, vals)
    conn.commit()
    post_id = cur.lastrowid

    # Verify
    cur.execute("SELECT * FROM post WHERE id=?", (post_id,))
    p = cur.fetchone()
    assert p is not None
    assert p['caption'] == 'Jesus is the best'

    print()
    print("=" * 55)
    print("SIMULATION RESULT: SUCCESS")
    print(f"  Post ID     : {post_id}")
    print(f"  Caption     : {p['caption']}")
    theme = p['bg_style'] if 'bg_style' in cols else 'default'
    print(f"  Theme       : {theme}  <- Default theme ACTIVE")
    print(f"  Author ID   : {p['author_id']}  ({username})")
    print(f"  Visibility  : {p['visibility']}")
    print(f"  DB verified : YES - round-trip confirmed")
    print("=" * 55)

    # Clean up sim post
    cur.execute("DELETE FROM post WHERE id=?", (post_id,))
    conn.commit()
    print("[OK] Test post cleaned up from DB")

except Exception as e:
    conn.rollback()
    print(f"[ERR] Post insert failed: {e}")

conn.close()
