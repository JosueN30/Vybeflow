import sqlite3
conn = sqlite3.connect('instance/vybeflow.db')
rows = conn.execute("PRAGMA table_info('user')").fetchall()
for r in rows:
    name, notnull, dflt = r[1], r[3], r[4]
    if notnull and dflt is None:
        print(f'REQUIRED (no default): {name}')
conn.close()
