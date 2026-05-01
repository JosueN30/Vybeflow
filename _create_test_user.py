import sqlite3
from werkzeug.security import generate_password_hash

pw = generate_password_hash('TestPass123!', method='pbkdf2:sha256:260000')
conn = sqlite3.connect('instance/vybeflow.db')

existing = conn.execute('SELECT id FROM user WHERE username=?', ('testproof',)).fetchone()
if existing:
    print('User testproof already exists, id=' + str(existing[0]))
    conn.close()
else:
    # Copy all columns from user id=1, then override username/email/password
    template = conn.execute('SELECT * FROM user WHERE id=1').fetchone()
    col_names = [d[0] for d in conn.execute('SELECT * FROM user WHERE id=1').description]
    row = dict(zip(col_names, template))
    row.pop('id')
    row['username'] = 'testproof'
    row['email'] = 'testproof@vybeflow.local'
    row['password_hash'] = pw
    row['is_admin'] = 0
    row['is_banned'] = 0
    row['is_suspended'] = 0
    row['trust_score'] = 50
    cols = list(row.keys())
    placeholders = ', '.join(['?' for _ in cols])
    vals = [row[c] for c in cols]
    conn.execute(f'INSERT INTO user ({chr(44).join(cols)}) VALUES ({placeholders})', vals)
    conn.commit()
    uid = conn.execute('SELECT id FROM user WHERE username=?', ('testproof',)).fetchone()[0]
    print('Created user testproof id=' + str(uid))
    conn.close()
