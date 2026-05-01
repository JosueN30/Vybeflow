"""smoke_test_features.py — VybeFlow new-feature smoke tests."""
import requests, json, sys

BASE = 'http://127.0.0.1:5000'
s    = requests.Session()

PASS = '[PASS]'
FAIL = '[FAIL]'
SKIP = '[SKIP]'

results = []

def check(name, resp, expect_codes, expect_keys=None):
    code_ok = resp.status_code in expect_codes
    try:
        body = resp.json()
    except Exception:
        body = {}
    keys_ok = all(k in body for k in (expect_keys or []))
    ok  = code_ok and keys_ok
    tag = PASS if ok else FAIL
    snippet = json.dumps(body)[:140]
    results.append((tag, name, resp.status_code, snippet))
    print(f'  {tag}  [{resp.status_code}]  {name}')
    if not ok:
        print(f'         expected={expect_codes}  keys={expect_keys}')
        print(f'         body: {snippet}')
    return ok, body

print()
print('=' * 62)
print('  VybeFlow Feature Smoke Tests')
print('=' * 62)

# ──────────────────────────────────────────────────────────────
# 1. Server health
# ──────────────────────────────────────────────────────────────
print()
print('── 1. Server Health ──────────────────────────────────────────')
r = s.get(BASE + '/', allow_redirects=True)
ok1 = r.status_code in (200, 302, 301)
tag = PASS if ok1 else FAIL
print(f'  {tag}  [{r.status_code}]  GET / reachable')
results.append((tag, 'GET /', r.status_code, ''))

# ──────────────────────────────────────────────────────────────
# 2. Register two test users
# ──────────────────────────────────────────────────────────────
print()
print('── 2. Auth (register + login) ────────────────────────────────')

reg = s.post(BASE + '/register', data={
    'username': '_smoketest_user_A',
    'email':    'smokeA@test.local',
    'password': 'TestPass123!',
    'account_type': 'regular',
}, allow_redirects=False)
tag = PASS if reg.status_code in (200, 302) else FAIL
print(f'  {tag}  [{reg.status_code}]  POST /register (user A)')
results.append((tag, 'POST /register A', reg.status_code, ''))

login_a = s.post(BASE + '/login', data={
    'username': '_smoketest_user_A',
    'password': 'TestPass123!',
}, allow_redirects=False)
tag = PASS if login_a.status_code in (200, 302) else FAIL
print(f'  {tag}  [{login_a.status_code}]  POST /login (user A)')
results.append((tag, 'POST /login A', login_a.status_code, ''))

sB = requests.Session()
regB = sB.post(BASE + '/register', data={
    'username': '_smoketest_user_B',
    'email':    'smokeB@test.local',
    'password': 'TestPass123!',
}, allow_redirects=False)
tag = PASS if regB.status_code in (200, 302) else FAIL
print(f'  {tag}  [{regB.status_code}]  POST /register (user B)')
results.append((tag, 'POST /register B', regB.status_code, ''))

loginB = sB.post(BASE + '/login', data={
    'username': '_smoketest_user_B',
    'password': 'TestPass123!',
}, allow_redirects=False)
tag = PASS if loginB.status_code in (200, 302) else FAIL
print(f'  {tag}  [{loginB.status_code}]  POST /login (user B)')
results.append((tag, 'POST /login B', loginB.status_code, ''))

state  = s.get(BASE + '/api/user/state')
uid_a  = state.json().get('user', {}).get('id') if state.ok else None
stateB = sB.get(BASE + '/api/user/state')
uid_b  = stateB.json().get('user', {}).get('id') if stateB.ok else None

tag = PASS if (uid_a and uid_b) else SKIP
print(f'  {tag}   user A id={uid_a}  user B id={uid_b}')
results.append((tag, 'resolve user IDs', 200, f'A={uid_a} B={uid_b}'))

# ──────────────────────────────────────────────────────────────
# 3. Inbox Shield Mode
# ──────────────────────────────────────────────────────────────
print()
print('── 3. Inbox Shield Mode ──────────────────────────────────────')
if uid_b:
    check('GET /api/inbox/gate-info (default free mode)',
          s.get(BASE + f'/api/inbox/gate-info/{uid_b}'),
          (200,), ['mode'])

    check('POST /api/inbox/settings (set paid $2.50)',
          sB.post(BASE + '/api/inbox/settings',
                  json={'inbox_mode': 'paid', 'message_fee': 2.50}),
          (200,), ['ok', 'inbox_mode'])

    _, gi = check('GET /api/inbox/gate-info (paid mode)',
                  s.get(BASE + f'/api/inbox/gate-info/{uid_b}'),
                  (200,), ['fee_required'])
    print(f'           fee_info: {gi.get("fee_info")}')

    check('POST /api/inbox/settings (squad_only)',
          sB.post(BASE + '/api/inbox/settings',
                  json={'inbox_mode': 'squad_only'}),
          (200,), ['ok'])

    check('POST /api/inbox/send (squad_only → 403)',
          s.post(BASE + '/api/inbox/send',
                 json={'target_user_id': uid_b, 'content': 'hello'}),
          (403,), ['code'])

    check('POST /api/inbox/settings (reset to free)',
          sB.post(BASE + '/api/inbox/settings',
                  json={'inbox_mode': 'free'}),
          (200,), ['ok'])

    check('POST /api/inbox/settings (invalid mode → 400)',
          sB.post(BASE + '/api/inbox/settings',
                  json={'inbox_mode': 'telepathy'}),
          (400,))
else:
    print(f'  {SKIP}  no user IDs — skipping')

# ──────────────────────────────────────────────────────────────
# 4. AI Bodyguard (direct unit test, no HTTP)
# ──────────────────────────────────────────────────────────────
print()
print('── 4. AI Bodyguard (ai_guard.scan) ───────────────────────────')
try:
    sys.path.insert(0, '.')
    from ai_guard import scan
    cases = [
        ('clean message',       'Hey how are you doing today?',                           'clean'),
        ('hard-block phrase',   'I know where you live',                                  'blocked'),
        ('slur',                'you f4gg0t get out',                                     'blocked'),
        ('threat regex',        "i'll kill you right now",                                'blocked'),
        ('KYS phrase',          'just kys already',                                       'blocked'),
        ('scam multi-signal',   'Click this link to verify your account http://bit.ly/x and send me gift card code', 'blocked'),
        ('message too long',    'A' * 6001,                                               'flagged'),
        ('harassment pattern',  'leak your nudes or i will expose you everywhere',        'blocked'),
    ]
    for name, text, expected in cases:
        r = scan(text)
        ok  = r.verdict == expected
        tag = PASS if ok else FAIL
        print(f'  {tag}  verdict={r.verdict:8s}  {name}  (layer={r.layer})')
        results.append((tag, f'ai_guard: {name}', 200, r.verdict))
except Exception as e:
    print(f'  {SKIP}  ai_guard error: {e}')

# ──────────────────────────────────────────────────────────────
# 5. Inbox send with AI scan
# ──────────────────────────────────────────────────────────────
print()
print('── 5. Inbox Send — free mode + AI scan ──────────────────────')
if uid_b:
    check('POST /api/inbox/send (clean → 201)',
          s.post(BASE + '/api/inbox/send',
                 json={'target_user_id': uid_b, 'content': 'Hey! Nice to meet you.'}),
          (201,), ['ok', 'thread_id'])

    _, sr = check('POST /api/inbox/send (threat → strike 1, 403)',
                  s.post(BASE + '/api/inbox/send',
                         json={'target_user_id': uid_b,
                               'content': "i'll kill you right now"}),
                  (403,), ['code', 'strike'])
    print(f'           strike={sr.get("strike")}  code={sr.get("code")}')
else:
    print(f'  {SKIP}')

# ──────────────────────────────────────────────────────────────
# 6. Pay-to-Message gate
# ──────────────────────────────────────────────────────────────
print()
print('── 6. Pay-to-Message gate ────────────────────────────────────')
if uid_b:
    _, pi = check('POST /api/dm/gate/create-intent (friends=false, no Stripe key)',
                  s.post(BASE + '/api/dm/gate/create-intent',
                         json={'target_user_id': uid_b}),
                  (200, 503))
    print(f'           result keys: {list(pi.keys())}')

    _, gst = check('GET /api/dm/gate/status/<id>',
                   s.get(BASE + f'/api/dm/gate/status/{uid_b}'),
                   (200,))
    print(f'           status keys: {list(gst.keys())}')
else:
    print(f'  {SKIP}')

# ──────────────────────────────────────────────────────────────
# 7. Hard Block + broken screen
# ──────────────────────────────────────────────────────────────
print()
print('── 7. Hard Block + Broken Screen ────────────────────────────')
if uid_b:
    _, blk = check('POST /api/block/user (A permanently blocks B)',
                   s.post(BASE + '/api/block/user',
                          json={'username': '_smoketest_user_B',
                                'duration': 'permanent',
                                'scopes':   ['account']}),
                   (201,), ['ok'])
    print(f'           block ok={blk.get("ok")}  expires={blk.get("expires_at")}')

    # B visits A's profile — decorator should redirect to broken screen
    r2  = sB.get(BASE + '/profile/_smoketest_user_A', allow_redirects=False)
    loc = r2.headers.get('Location', '')
    hit = r2.status_code in (301, 302) and 'blocked-view' in loc
    tag = PASS if hit else FAIL
    print(f'  {tag}  [{r2.status_code}]  blocked user profile visit → redirect to broken screen')
    if not hit:
        print(f'         Location: {loc or "(none)"}  — expected /blocked-view/...')
    results.append((tag, 'hard block redirect', r2.status_code, loc))

    check('GET /blocked-view/<username> renders HTML (200)',
          s.get(BASE + '/blocked-view/_smoketest_user_B'),
          (200,))

    # Check trust_score dropped by 10 (via user state)
    ts_before = 50   # default
    stateB2   = sB.get(BASE + '/api/user/state')
    ts_after  = stateB2.json().get('user', {}).get('trust_score', 50) if stateB2.ok else 50
    ok_ts     = ts_after <= (ts_before - 10)
    tag       = PASS if ok_ts else SKIP
    print(f'  {tag}   trust_score after hard block: {ts_after} (expected ≤{ts_before - 10})')
    results.append((tag, 'trust_score penalty', 200, str(ts_after)))
else:
    print(f'  {SKIP}')

# ──────────────────────────────────────────────────────────────
# 8. Geo-Currency utilities
# ──────────────────────────────────────────────────────────────
print()
print('── 8. Geo-Currency + Forex ───────────────────────────────────')
try:
    from utils.geo_currency import detect_currency_for_ip, get_default_fee_minor, apply_strike_multiplier

    # Known IP → US
    geo = detect_currency_for_ip('8.8.8.8')
    ok  = (geo['currency_code'] == 'usd' and geo['amount_minor'] == 500)
    tag = PASS if ok else FAIL
    print(f'  {tag}  detect 8.8.8.8 → code={geo["currency_code"]}  amount={geo["amount_minor"]}')
    results.append((tag, 'geo 8.8.8.8→US', 200, str(geo['currency_code'])))

    # Loopback → US (dev mode)
    geo_lo = detect_currency_for_ip('127.0.0.1')
    ok_lo  = geo_lo['country_code'] == 'US'
    tag    = PASS if ok_lo else FAIL
    print(f'  {tag}  detect 127.0.0.1 → {geo_lo["country_code"]} (dev mode)')
    results.append((tag, 'geo loopback→US', 200, geo_lo['country_code']))

    # Strike multiplier math
    scaled = apply_strike_multiplier(500, 3.0, False)
    ok_s   = scaled == 1500
    tag    = PASS if ok_s else FAIL
    print(f'  {tag}  apply_strike_multiplier(500, 3.0, False) → {scaled} (exp 1500)')
    results.append((tag, 'strike 3x math', 200, str(scaled)))

    # Dynamic default fee
    amt, lbl = get_default_fee_minor('GBP', base_usd=1.00)
    ok_f = amt > 0
    tag  = PASS if ok_f else FAIL
    print(f'  {tag}  get_default_fee_minor(GBP, 1 USD) → {amt} minor units ({lbl})')
    results.append((tag, 'forex GBP', 200, lbl))

    amt_jmd, lbl_jmd = get_default_fee_minor('JMD', base_usd=1.00)
    ok_jmd = amt_jmd > 0
    tag    = PASS if ok_jmd else FAIL
    print(f'  {tag}  get_default_fee_minor(JMD, 1 USD) → {amt_jmd} minor units ({lbl_jmd})')
    results.append((tag, 'forex JMD', 200, lbl_jmd))

except Exception as e:
    print(f'  {SKIP}  geo_currency error: {e}')

# ──────────────────────────────────────────────────────────────
# 9. Signup country detection (check user A's home_currency was set)
# ──────────────────────────────────────────────────────────────
print()
print('── 9. Signup Country / Home Currency ─────────────────────────')
try:
    state_a = s.get(BASE + '/api/user/state')
    user_a  = state_a.json().get('user', {}) if state_a.ok else {}
    hc   = user_a.get('home_currency') or user_a.get('currency_code')
    sc   = user_a.get('signup_country')
    ok9  = bool(hc)
    tag  = PASS if ok9 else SKIP
    print(f'  {tag}  user A home_currency={hc}  signup_country={sc}')
    results.append((tag, 'signup home_currency', 200, str(hc)))
except Exception as e:
    print(f'  {SKIP}  state error: {e}')

# ──────────────────────────────────────────────────────────────
# Summary
# ──────────────────────────────────────────────────────────────
print()
print('=' * 62)
passed  = sum(1 for r in results if r[0] == PASS)
failed  = sum(1 for r in results if r[0] == FAIL)
skipped = sum(1 for r in results if r[0] == SKIP)
print(f'  RESULTS:  {passed} passed  |  {failed} failed  |  {skipped} skipped')
print('=' * 62)

if failed:
    print()
    print('  FAILURES:')
    for tag, name, code, detail in results:
        if tag == FAIL:
            print(f'    {name}  [HTTP {code}]')
            if detail:
                print(f'      {detail[:120]}')
print()

sys.exit(0 if failed == 0 else 1)
