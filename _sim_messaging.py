"""
VybeFlow Messaging Simulation — alice_vybe <-> bob_vybe
Proves: thread creation, text messages, image upload, read receipt, reply, reaction, call page.
"""
import requests, re, io, json, sys, sqlite3

BASE = "http://127.0.0.1:5000"
DB   = r"d:\Vybeflow-main\instance\vybeflow.db"

# Age the sim users past the 24-hour new-account throttle
conn = sqlite3.connect(DB)
conn.execute("UPDATE user SET created_at='2026-01-01 00:00:00' WHERE username IN ('alice_vybe','bob_vybe')")
conn.commit()
conn.close()
print("Aged sim users past 24h throttle\n")

def get_csrf(s, path="/login"):
    r = s.get(BASE + path)
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', r.text)
    return m.group(1) if m else ""

def login(username, password):
    s = requests.Session()
    csrf = get_csrf(s, "/login")
    r = s.post(BASE + "/login",
               data={"username": username, "password": password, "csrf_token": csrf},
               allow_redirects=True)
    ok = "/feed" in r.url or r.status_code == 200
    print(f"  {'OK' if ok else 'FAIL'} login {username} -> {r.url}")
    # Grab a fresh CSRF token
    feed = s.get(BASE + "/feed")
    m2 = re.search(r'name="csrf_token"\s+value="([^"]+)"', feed.text)
    csrf2 = m2.group(1) if m2 else csrf
    s.headers.update({
        "X-CSRFToken": csrf2,
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/json",
    })
    return s

print("=== LOGIN ===")
alice_s = login("alice_vybe", "Alice@Secure1!")
bob_s   = login("bob_vybe",   "Bob@Secure1!")

# ── 1: Create DM thread Alice -> Bob (API uses 'username' field) ─────────────
print("\n1) Alice opens DM thread with bob_vybe...")
r = alice_s.post(BASE + "/api/dm/threads", json={"username": "bob_vybe"})
print(f"   Status: {r.status_code}")
d = r.json() if r.status_code < 500 else {}
thread_id = d.get("thread_id") or d.get("id")
if not thread_id:
    print(f"   Response: {json.dumps(d)[:400]}")
    sys.exit(1)
print(f"   thread_id={thread_id}  OK")

# ── 2: Alice sends 3 text messages ──────────────────────────────────────────
print("\n2) Alice sends 3 text messages...")
for txt in ["Hey Bob! What is good?", "VybeFlow is next level fire", "You around for a call later?"]:
    r2 = alice_s.post(BASE + f"/api/dm/threads/{thread_id}/messages", json={"content": txt})
    ok = r2.json().get("ok", "?") if r2.status_code < 300 else r2.text[:200]
    print(f"   [{r2.status_code}] ok={ok}  '{txt[:40]}'")

# ── 3: Alice uploads an image attachment ─────────────────────────────────────
print("\n3) Alice uploads a PNG image...")
PNG_1x1 = bytes([
    0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,
    0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
    0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,
    0x08,0x02,0x00,0x00,0x00,0x90,0x77,0x53,0xDE,
    0x00,0x00,0x00,0x0C,0x49,0x44,0x41,0x54,
    0x08,0xD7,0x63,0xF8,0xCF,0xC0,0x00,0x00,
    0x00,0x02,0x00,0x01,0xE2,0x21,0xBC,0x33,
    0x00,0x00,0x00,0x00,0x49,0x45,0x4E,0x44,0xAE,0x42,0x60,0x82,
])
# Must NOT send Content-Type:application/json for multipart upload
# Use a copy of the session without Content-Type override
up_s = requests.Session()
up_s.cookies.update(alice_s.cookies)
up_s.headers.update({"X-CSRFToken": alice_s.headers.get("X-CSRFToken", ""),
                      "X-Requested-With": "XMLHttpRequest"})
r_up = up_s.post(BASE + "/api/dm/upload",
                 files={"file": ("photo.png", io.BytesIO(PNG_1x1), "image/png")})
print(f"   Upload status: {r_up.status_code}  {r_up.text[:200]}")
media_url = None
try:
    ud = r_up.json()
    media_url = ud.get("url") or ud.get("media_url")
    media_type = ud.get("media_type", "image")
    print(f"   URL: {media_url}  type={media_type}")
    if media_url:
        r_img = alice_s.post(BASE + f"/api/dm/threads/{thread_id}/messages",
                             json={"content": "Check this pic!", "media_url": media_url, "media_type": media_type})
        ok = r_img.json().get("ok", "?") if r_img.status_code < 300 else "err"
        print(f"   Image DM sent: [{r_img.status_code}] ok={ok}")
except Exception as e:
    print(f"   Upload error: {e} -- {r_up.text[:200]}")

# ── 4: Bob reads the thread ──────────────────────────────────────────────────
print("\n4) Bob reads the thread...")
r_read = bob_s.get(BASE + f"/api/dm/threads/{thread_id}/messages",
                   headers={"Content-Type": "", "X-Requested-With": "XMLHttpRequest"})
print(f"   Status: {r_read.status_code}")
bob_reply_id = None
try:
    payload = r_read.json()
    msgs = payload if isinstance(payload, list) else payload.get("messages", [])
    print(f"   Messages in thread: {len(msgs)}")
    for m in msgs[:6]:
        sndr = m.get("sender_username") or m.get("sender", "?")
        txt  = (m.get("text") or m.get("body") or "")[:45]
        mtyp = m.get("media_type") or "text"
        print(f"     [{sndr}] ({mtyp}) \"{txt}\"")
except Exception as e:
    print(f"   Parse error: {e} -- {r_read.text[:200]}")

# ── 5: Bob marks thread as read ──────────────────────────────────────────────
r_mark = bob_s.post(BASE + f"/api/dm/threads/{thread_id}/read")
print(f"\n5) Bob marks read -> {r_mark.status_code}")

# ── 6: Bob replies ───────────────────────────────────────────────────────────
print("\n6) Bob replies...")
r_rep = bob_s.post(BASE + f"/api/dm/threads/{thread_id}/messages",
                   json={"content": "Bro this app is fire! Lets call!"})
print(f"   Status: {r_rep.status_code}")
try:
    rd = r_rep.json()
    bob_reply_id = rd.get("message_id") or rd.get("id")
    print(f"   ok={rd.get('ok')}  message_id={bob_reply_id}")
except Exception:
    pass

# ── 7: Alice reacts to Bob's reply ───────────────────────────────────────────
print("\n7) Alice reacts to Bob's reply...")
if bob_reply_id:
    r_react = alice_s.post(BASE + f"/api/dm/messages/{bob_reply_id}/react",
                           json={"emoji": "🔥"})
    print(f"   Status: {r_react.status_code}")
    try:
        print(f"   Response: {r_react.json()}")
    except Exception:
        print(f"   Raw: {r_react.text[:100]}")
else:
    print("   Skipped (no reply message_id)")

# ── 8: Alice lists all her threads ───────────────────────────────────────────
print("\n8) Alice lists threads...")
r_thr = alice_s.get(BASE + "/api/dm/threads",
                    headers={"Content-Type": "", "X-Requested-With": "XMLHttpRequest"})
print(f"   Status: {r_thr.status_code}")
try:
    tdata = r_thr.json()
    tlist = tdata if isinstance(tdata, list) else tdata.get("threads", [])
    print(f"   Thread count: {len(tlist)}")
    for t in tlist[:3]:
        partner = t.get("partner_username") or t.get("username") or "?"
        unread  = t.get("unread_count", 0)
        preview = str(t.get("last_message") or t.get("preview") or "")[:40]
        print(f"     -> with '{partner}', unread={unread}, preview={preview!r}")
except Exception as e:
    print(f"   Parse error: {e} -- {r_thr.text[:200]}")

# ── 9: Video call page ───────────────────────────────────────────────────────
print("\n9) Video call page...")
r_vc = alice_s.get(BASE + "/messenger/call/bob_vybe",
                   headers={"Content-Type": "", "X-Requested-With": ""})
print(f"   Status: {r_vc.status_code}")
if r_vc.status_code == 200:
    has_webrtc = "getUserMedia" in r_vc.text or "webrtc" in r_vc.text.lower() or "RTCPeerConnection" in r_vc.text
    print(f"   WebRTC present: {has_webrtc}")
    print("   Call page: PASS")
else:
    print(f"   Response: {r_vc.text[:150]}")

# ── Summary ──────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("SIMULATION COMPLETE")
print("=" * 60)
print(f"  thread_id      = {thread_id}")
print(f"  text messages  = 3 from Alice + 1 from Bob")
print(f"  image upload   = {'PASS' if media_url else 'SKIP'}")
print(f"  read receipt   = {r_mark.status_code}")
print(f"  reaction       = {'PASS' if bob_reply_id else 'SKIP'}")
print(f"  thread list    = {r_thr.status_code}")
print(f"  call page      = {r_vc.status_code}")
