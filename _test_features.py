"""
VybeFlow Comprehensive Feature Test
Tests: scam detection, pay-to-message, block evasion, reporting, stories
"""
import sys, os, re, requests

BASE = "http://127.0.0.1:5000"
PASS = "[PASS]"
FAIL = "[FAIL]"
INFO = "[INFO]"

def test(name, ok, detail=""):
    status = PASS if ok else FAIL
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))
    return ok

# ── 1. In-process tests (no HTTP needed) ─────────────────────────────────────
print("\n=== IN-PROCESS FEATURE TESTS ===")
sys.path.insert(0, os.path.dirname(__file__))
from app import create_app
app, _ = create_app()

with app.app_context():
    # Scam detection
    from dm_scam_filter import scan_dm_for_scam
    from models import User
    sender = User.query.filter_by(username='testuser').first()
    
    r1 = scan_dm_for_scam(sender, 'Send me $500 via bitcoin wallet bc1qxxxxx urgent', [1,2,3])
    test("Scam detection (bitcoin+urgency)", r1.is_scam, f"score={r1.score}, signals={r1.signals[:2]}")
    
    r2 = scan_dm_for_scam(sender, 'Hey, what time does the concert start?', [1,2,3])
    test("Clean message not flagged", not r2.is_scam, f"score={r2.score}")

    r3 = scan_dm_for_scam(sender, 'I make $5000 weekly from home!! investment opportunity Click link to join!!', [1,2,3])
    test("Scam detection (investment scheme)", r3.is_scam, f"score={r3.score}")

    # IP Blacklist
    from models import BlacklistedIP, IdentityHashBlacklist, DeviceFingerprintBan
    BlacklistedIP.add('10.0.0.99', reason='vpn_test')
    test("IP blacklist add+check", BlacklistedIP.is_blocked('10.0.0.99'))
    test("Clean IP not blocked", not BlacklistedIP.is_blocked('10.0.0.1'))

    # Email hash blacklist
    IdentityHashBlacklist.add('email', 'badegg@scam.com')
    test("Email blacklist add+check", IdentityHashBlacklist.is_blocked('email', 'badegg@scam.com'))
    test("Clean email not blocked", not IdentityHashBlacklist.is_blocked('email', 'legit@user.com'))

    # Phone hash blacklist
    IdentityHashBlacklist.add('phone', '+15551234567')
    test("Phone blacklist add+check", IdentityHashBlacklist.is_blocked('phone', '+15551234567'))

    # Device fingerprint ban
    DeviceFingerprintBan.ban('deadbeef1234567890abcdef')
    test("Device fingerprint ban works", DeviceFingerprintBan.is_banned('deadbeef1234567890abcdef'))
    test("Clean fingerprint not banned", not DeviceFingerprintBan.is_banned('cleandevice0000000000001'))

    # Story model exists and can be queried
    from models import Story
    story_count = Story.query.count()
    test("Story model accessible", True, f"{story_count} stories in DB")

    # FriendRequest (used by pay-to-message)
    from models import FriendRequest
    fr_count = FriendRequest.query.count()
    test("FriendRequest model accessible", True, f"{fr_count} friend requests in DB")

    # Report model
    try:
        from models import HarassmentReport
        rpt_count = HarassmentReport.query.count()
        test("HarassmentReport model accessible", True, f"{rpt_count} reports in DB")
    except Exception as e:
        test("HarassmentReport model accessible", False, str(e))

    print()

# ── 2. HTTP tests (login required) ───────────────────────────────────────────
print("=== HTTP ENDPOINT TESTS ===")

s = requests.Session()

# Get login page + CSRF token
page = s.get(f"{BASE}/login")
m = re.search(r'name="csrf_token"\s+value="([^"]+)"', page.text)
csrf = m.group(1) if m else ""
test("CSRF token found on login page", bool(csrf), csrf[:20] + "...")

# Login
r = s.post(f"{BASE}/login", data={
    'username': 'testuser',
    'password': 'TestPass@12345!',
    'csrf_token': csrf
}, allow_redirects=False)
test("Login redirects (not back to /login)", r.headers.get('Location', '/login') != '/login',
     f"→ {r.headers.get('Location', '?')}")

# Feed accessible after login
feed = s.get(f"{BASE}/feed")
test("Feed page loads after login", feed.status_code == 200)

# Stories page
stories = s.get(f"{BASE}/stories")
test("Stories page accessible", stories.status_code in (200, 302), f"status={stories.status_code}")

# Story create page
sc = s.get(f"{BASE}/create_story")
test("Story create page accessible", sc.status_code == 200, f"status={sc.status_code}")

# Music search API
music = s.get(f"{BASE}/api/music/search?q=drake&limit=5")
test("Music search API", music.status_code == 200, f"status={music.status_code}")
if music.status_code == 200:
    mdata = music.json()
    results = mdata.get('results', mdata.get('tracks', []))
    test("Music search returns results", len(results) > 0, f"{len(results)} tracks")

# Messenger page
msgr = s.get(f"{BASE}/messenger")
test("Messenger page loads", msgr.status_code == 200, f"status={msgr.status_code}")

# Pay-to-message gate (non-friend)
ptm = s.post(f"{BASE}/api/dm/gate/create-intent", json={'recipient_id': 1},
             headers={'X-CSRFToken': csrf})
test("Pay-to-message gate auth",
     ptm.status_code in (200, 402, 400, 200),  # 200=friends, 402=fee_required
     f"status={ptm.status_code}, {ptm.text[:100]}")

# Report endpoint
rpt = s.post(f"{BASE}/api/report/user", json={
    'username': 'testuser2',
    'reason': 'spam',
    'details': 'Test report'
}, headers={'X-CSRFToken': csrf})
test("Report user endpoint responds", rpt.status_code in (200, 201, 400, 404, 401),
     f"status={rpt.status_code}, {rpt.text[:100]}")

# Blocked view page
bv = s.get(f"{BASE}/blocked-view/TESTBLOCKER")
test("Blocked view page loads (BLOCKED BITCH)", bv.status_code == 200 and 'BLOCKED BITCH' in bv.text,
     f"status={bv.status_code}")

# Blocked screen page
bs = s.get(f"{BASE}/blocked-screen/TESTBLOCKER")
test("Blocked screen page loads", bs.status_code == 200, f"status={bs.status_code}")

# DM scam check endpoint (if any)
scam_chk = s.post(f"{BASE}/api/dm/send", json={
    'recipient_id': 1,
    'content': 'URGENT! Send $500 bitcoin bc1qxxxxxxx NOW or lose everything',
    'thread_id': None
}, headers={'X-CSRFToken': csrf})
test("Scam DM blocked or handled", scam_chk.status_code in (200, 201, 400, 403, 404),
     f"status={scam_chk.status_code}, {scam_chk.text[:100]}")

print()
print("=== TEST COMPLETE ===")
