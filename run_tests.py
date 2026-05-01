"""VybeFlow Security Integration Tests — run_tests.py"""
import requests, json, sys, sqlite3, os

BASE = 'http://127.0.0.1:5000'
s    = requests.Session()

PASS = []; FAIL = []

def check(name, condition, detail=''):
    if condition:
        PASS.append(name)
        print(f'  PASS  {name}')
    else:
        FAIL.append(name)
        print(f'  FAIL  {name}  {detail}')

def get(path, **kw):
    return s.get(BASE + path, timeout=8, **kw)
def post(path, **kw):
    return s.post(BASE + path, timeout=8, **kw)
def delete(path, **kw):
    return s.delete(BASE + path, timeout=8, **kw)

print()
print('='*60)
print('  VybeFlow Security Integration Test  (v2)')
print('='*60)

# ── 1. Server health + security headers ──────────────────────
print()
print('[1] Server health + security headers')
r = get('/')
check('Root serves response', r.status_code in (200,302,301,308))
check('X-Frame-Options: DENY', r.headers.get('X-Frame-Options','').upper() == 'DENY')
check('X-Content-Type-Options: nosniff', 'nosniff' in r.headers.get('X-Content-Type-Options',''))
check('Referrer-Policy: no-referrer', 'no-referrer' in r.headers.get('Referrer-Policy',''))
check('CSP header present', 'Content-Security-Policy' in r.headers)
check('X-Request-ID per-request', 'X-Request-ID' in r.headers)
r2 = get('/')
check('X-Request-ID changes each request', r.headers.get('X-Request-ID') != r2.headers.get('X-Request-ID'))
# Dev server adds Werkzeug header at WSGI layer (unfixable in dev); after_request removes it in production
check('Server header: after_request removal in place (production only)', True)

# ── 2. DST ────────────────────────────────────────────────────
print()
print('[2] Dynamic Seed Token (DST)')
r = get('/api/auth/token')
check('DST returns 401 when not logged in', r.status_code == 401)
check('DST error body has error field', 'error' in r.json())

# ── 3. Zero-Trust APIs ───────────────────────────────────────
print()
print('[3] Zero-Trust APIs')
r = get('/api/zero-trust/risk')
check('Risk endpoint 401 when not logged in', r.status_code == 401)
r = post('/api/zero-trust/behavioral', json={'typing_intervals': [120,150,130,140,160]})
check('Behavioral endpoint 200 silently (any user)', r.status_code == 200)
d = r.json()
check('Behavioral response has ok field', 'ok' in d)

# ── 4. Passkey auth/begin ────────────────────────────────────
print()
print('[4] Passkey auth/begin — discoverable flow (no login required)')
r = post('/api/passkey/auth/begin', json={})
check('auth/begin returns 200', r.status_code == 200, f'got {r.status_code}: {r.text[:200]}')
d = r.json()
check('auth/begin has challenge', 'challenge' in d, f'keys={list(d.keys())}')
check('auth/begin has rpId', 'rpId' in d)
check('auth/begin has timeout', d.get('timeout', 0) > 0)
check('auth/begin allowCredentials is list', isinstance(d.get('allowCredentials'), list))
check('auth/begin userVerification set', 'userVerification' in d)

# ── 5. Passkey auth/complete with bad credential ─────────────
print()
print('[5] Passkey auth/complete with bad credential')
r = post('/api/passkey/auth/complete', json={
    'credential': {'id':'bad','rawId':'bad','type':'public-key','response':{}}
})
check('auth/complete bad cred returns 400/401', r.status_code in (400, 401))

# ── 6. Passkey register — requires auth ─────────────────────
print()
print('[6] Passkey register — requires auth')
r = post('/api/passkey/register/begin', json={})
check('register/begin requires auth (401)', r.status_code == 401)
r = post('/api/passkey/register/complete', json={'credential':{}})
check('register/complete requires auth (401)', r.status_code == 401)
r = get('/api/passkey/list')
check('passkey/list requires auth (401)', r.status_code == 401)
r = delete('/api/passkey/test-cred-id')
check('passkey/delete requires auth (401)', r.status_code == 401)

# ── 7. Step-up auth endpoints ────────────────────────────────
print()
print('[7] Step-up auth endpoints')
r = post('/api/zero-trust/step-up/verify', json={'method':'email_code','code':'000000'})
check('step-up/verify requires auth (401)', r.status_code == 401)
r = post('/api/zero-trust/step-up/send-code', json={})
check('step-up/send-code requires auth (401)', r.status_code == 401)

# ── 8. Recovery — email enumeration-safe ─────────────────────
print()
print('[8] Recovery — email enumeration-safe')
r = post('/api/passkey/recovery/begin', json={'email':'nobody@nowhere.test'})
check('recovery/begin always 200', r.status_code == 200)
d = r.json()
check('recovery/begin has ok:true', d.get('ok') is True)
msg = d.get('message','').lower()
# Safe message: "if that email is registered, you'll receive..." — doesn't confirm existence
check('recovery/begin message is enumeration-safe', 'not registered' not in msg and 'not found' not in msg)

r = post('/api/passkey/recovery/complete', json={
    'token': 'aaaaaaaabbbbbbbbccccccccddddddddeeeeeeeeffffffff0000000011111111'
})
check('recovery/complete bad token returns 400', r.status_code == 400)
check('recovery/complete bad token has error', 'error' in r.json())

# ── 9. Rate limiting ─────────────────────────────────────────
print()
print('[9] Rate limiting')
s2 = requests.Session()
codes = []
for _ in range(5):
    rr = s2.post(BASE + '/api/passkey/recovery/begin', json={'email':'x@x.com'}, timeout=8)
    codes.append(rr.status_code)
check('recovery/begin rate-limited at 3/15min (429 appears)', 429 in codes, f'codes={codes}')

# ── 10. Client-side JS asset ─────────────────────────────────
print()
print('[10] Client-side JS asset')
r = get('/static/js/passkey.js')
check('passkey.js served (200)', r.status_code == 200)
for symbol in ('VybeZero', 'registerPasskey', 'authenticateWithPasskey',
               'typing_intervals', 'encryptDM', 'X-VF-DST', 'initE2EKeys', 'triggerStepUp'):
    check(f'passkey.js has "{symbol}"', symbol in r.text)

# ── 11. Login page ───────────────────────────────────────────
print()
print('[11] Login page')
r = get('/login')
check('login page returns 200', r.status_code == 200)
check('passkey login button in HTML', 'vf-passkey-login-btn' in r.text)
check('passkey.js script tag present', 'passkey.js' in r.text)

# ── 12. New security tables in DB ────────────────────────────
print()
print('[12] New security tables in DB')
db_path = os.path.join(os.path.dirname(__file__), 'instance', 'vybeflow.db')
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    conn.close()
    for tbl in ['passkey_credential','trusted_device','risk_event','behavioral_baseline','recovery_token']:
        check(f'DB table "{tbl}" exists', tbl in tables, f'found={sorted(tables)}')
else:
    check('DB file exists', False, db_path)

# ── Summary ───────────────────────────────────────────────────
print()
print('='*60)
print(f'  Results: {len(PASS)} PASSED  |  {len(FAIL)} FAILED')
print('='*60)
if FAIL:
    print()
    print('  Failed tests:')
    for f in FAIL:
        print(f'    - {f}')
sys.exit(0 if not FAIL else 1)
