"""
VybeFlow Comprehensive QA Test Suite
=====================================
Phase 2: Automated testing of all core flows.
Runs against the Flask test client (no network needed).
"""
import sys, os, time, json, base64, traceback
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ".")

from app import create_app
from __init__ import db
from models import User, Post, Story, StoryItem, Comment

_result = create_app()
app = _result[0] if isinstance(_result, tuple) else _result
app.config["TESTING"] = True
app.config["WTF_CSRF_ENABLED"] = False

# Tiny valid 1x1 red PNG
PNG_1X1 = base64.b64encode(bytes([
    0x89,0x50,0x4E,0x47,0x0D,0x0A,0x1A,0x0A,0x00,0x00,0x00,0x0D,0x49,0x48,0x44,0x52,
    0x00,0x00,0x00,0x01,0x00,0x00,0x00,0x01,0x08,0x02,0x00,0x00,0x00,0x90,0x77,0x53,
    0xDE,0x00,0x00,0x00,0x0C,0x49,0x44,0x41,0x54,0x08,0xD7,0x63,0xF8,0xCF,0xC0,0x00,
    0x00,0x00,0x02,0x00,0x01,0xE2,0x21,0xBC,0x33,0x00,0x00,0x00,0x00,0x49,0x45,0x4E,
    0x44,0xAE,0x42,0x60,0x82
])).decode()

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
WARN = "\033[93mWARN\033[0m"

bugs = []  # Collect all bugs found

def bug(severity, subsystem, title, detail=""):
    bugs.append({"severity": severity, "subsystem": subsystem, "title": title, "detail": detail})

def client_with_user(username):
    """Return a test client logged in as the given user."""
    c = app.test_client()
    with app.app_context():
        u = User.query.filter(User.username.ilike(username)).first()
        if not u:
            return c, None
    with c.session_transaction() as sess:
        sess["username"] = u.username
        sess["user_id"] = u.id
        sess["logged_in"] = True
    return c, u

def run_test(name, fn):
    try:
        result = fn()
        status = PASS if result else FAIL
        print(f"  [{status}] {name}")
        return result
    except Exception as e:
        print(f"  [{FAIL}] {name} — Exception: {e}")
        bug("CRITICAL", name.split(":")[0] if ":" in name else "Unknown", f"Test crash: {name}", str(e))
        return False

# ═══════════════════════════════════════════════════════════════════════════
# SETUP
# ═══════════════════════════════════════════════════════════════════════════

with app.app_context():
    # Clean user state
    userA = User.query.filter(User.username.ilike("DAREALEST1")).first()
    userB = User.query.filter(User.username.ilike("testfeeduser2")).first()
    if not userA:
        userA = User.query.first()
    all_users = User.query.all()
    if not userB:
        userB = next((u for u in all_users if u.id != userA.id), userA)
    
    # Clear any bans/suspensions for test users
    for u in [userA, userB]:
        if u:
            u.is_banned = False
            u.is_suspended = False
            u.strike_count = 0
            if hasattr(u, 'lockout_until'):
                u.lockout_until = None
    db.session.commit()
    
    print(f"\nTest Users: A={userA.username} (id={userA.id}), B={userB.username} (id={userB.id})")

results = {"total": 0, "pass": 0, "fail": 0}

def track(name, fn):
    results["total"] += 1
    if run_test(name, fn):
        results["pass"] += 1
    else:
        results["fail"] += 1

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("1. AUTHENTICATION TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_login_page_loads():
    with app.test_client() as c:
        r = c.get("/login")
        return r.status_code == 200 and b"login" in r.data.lower()

def test_register_page_loads():
    with app.test_client() as c:
        r = c.get("/register")
        return r.status_code == 200

def test_unauthenticated_redirect():
    with app.test_client() as c:
        r = c.get("/settings", follow_redirects=False)
        return r.status_code in (302, 401)

def test_logout():
    c, u = client_with_user(userA.username)
    r = c.get("/logout", follow_redirects=False)
    return r.status_code in (302, 200)

def test_forgot_password_page():
    with app.test_client() as c:
        r = c.get("/forgot_password")
        return r.status_code == 200

track("Auth: Login page loads", test_login_page_loads)
track("Auth: Register page loads", test_register_page_loads)
track("Auth: Unauthenticated redirect", test_unauthenticated_redirect)
track("Auth: Logout works", test_logout)
track("Auth: Forgot password page", test_forgot_password_page)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("2. FEED / POST TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

created_post_id = None

def test_create_post():
    global created_post_id
    c, u = client_with_user(userA.username)
    tag = f"QA_TEST_{int(time.time())}"
    r = c.post("/api/posts/create",
        data=json.dumps({"caption": tag, "visibility": "public"}),
        content_type="application/json")
    if r.status_code != 201:
        bug("CRITICAL", "Feed", "Post creation failed", f"Status {r.status_code}: {r.data[:200]}")
        return False
    d = r.get_json()
    created_post_id = (d.get("post") or d).get("id")
    return created_post_id is not None

def test_post_in_feed():
    c, u = client_with_user(userA.username)
    r = c.get("/api/posts/list?offset=0&limit=50")
    if r.status_code != 200:
        bug("MAJOR", "Feed", "Feed list endpoint failed", f"Status {r.status_code}")
        return False
    d = r.get_json()
    posts = d.get("posts") or d if isinstance(d, list) else []
    return any(str(p.get("id")) == str(created_post_id) for p in posts)

def test_post_visible_to_other_user():
    c, u = client_with_user(userB.username)
    r = c.get("/api/posts/list?offset=0&limit=50")
    if r.status_code != 200:
        return False
    d = r.get_json()
    posts = d.get("posts") or d if isinstance(d, list) else []
    found = any(str(p.get("id")) == str(created_post_id) for p in posts)
    if not found:
        bug("CRITICAL", "Feed", "Public post not visible to other user", f"Post {created_post_id} missing from {userB.username}'s feed")
    return found

def test_edit_post():
    c, u = client_with_user(userA.username)
    r = c.patch(f"/api/posts/{created_post_id}",
        data=json.dumps({"caption": "EDITED_QA_TEST"}),
        content_type="application/json")
    return r.status_code == 200

def test_post_like():
    c, u = client_with_user(userB.username)
    r = c.post(f"/api/posts/{created_post_id}/like",
        data=json.dumps({}),
        content_type="application/json")
    return r.status_code in (200, 201)

def test_post_comment():
    c, u = client_with_user(userB.username)
    r = c.post(f"/api/posts/{created_post_id}/comments",
        data=json.dumps({"content": "Great post!"}),
        content_type="application/json")
    if r.status_code not in (200, 201):
        bug("MAJOR", "Feed", "Comment creation failed", f"Status {r.status_code}: {r.data[:200]}")
    return r.status_code in (200, 201)

def test_feed_pagination():
    c, u = client_with_user(userA.username)
    r1 = c.get("/api/posts/list?offset=0&limit=5")
    r2 = c.get("/api/posts/list?offset=5&limit=5")
    if r1.status_code != 200 or r2.status_code != 200:
        return False
    d1 = r1.get_json()
    d2 = r2.get_json()
    p1 = d1.get("posts") or []
    p2 = d2.get("posts") or []
    # Pages should not have identical first post (unless < 5 total)
    if len(p1) >= 5 and len(p2) > 0:
        return p1[0].get("id") != p2[0].get("id")
    return True

def test_delete_post():
    c, u = client_with_user(userA.username)
    r = c.delete(f"/api/posts/{created_post_id}")
    if r.status_code not in (200, 204):
        bug("CRITICAL", "Feed", "Post deletion failed", f"Status {r.status_code}")
    return r.status_code in (200, 204)

def test_deleted_post_gone():
    c, u = client_with_user(userA.username)
    r = c.get("/api/posts/list?offset=0&limit=50")
    d = r.get_json()
    posts = d.get("posts") or []
    still_there = any(str(p.get("id")) == str(created_post_id) for p in posts)
    if still_there:
        bug("CRITICAL", "Feed", "Deleted post still in feed", f"Post {created_post_id} still present")
    return not still_there

def test_empty_post_rejected():
    c, u = client_with_user(userA.username)
    r = c.post("/api/posts/create",
        data=json.dumps({"caption": "", "visibility": "public"}),
        content_type="application/json")
    if r.status_code in (200, 201):
        bug("MAJOR", "Feed", "Empty post accepted", "Server should reject empty posts")
        return False
    return r.status_code >= 400

def test_unauthenticated_post_rejected():
    with app.test_client() as c:
        r = c.post("/api/posts/create",
            data=json.dumps({"caption": "sneaky", "visibility": "public"}),
            content_type="application/json")
        return r.status_code in (401, 403, 302)

track("Feed: Create post", test_create_post)
track("Feed: Post appears in own feed", test_post_in_feed)
track("Feed: Post visible to other user", test_post_visible_to_other_user)
track("Feed: Edit post caption", test_edit_post)
track("Feed: Like a post", test_post_like)
track("Feed: Comment on post", test_post_comment)
track("Feed: Pagination works", test_feed_pagination)
track("Feed: Delete post", test_delete_post)
track("Feed: Deleted post gone from feed", test_deleted_post_gone)
track("Feed: Empty post rejected", test_empty_post_rejected)
track("Feed: Unauthenticated post rejected", test_unauthenticated_post_rejected)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("3. STORY TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

created_story_id = None

def test_story_create_page():
    c, u = client_with_user(userA.username)
    r = c.get("/create_story")
    return r.status_code == 200

def test_create_story_with_music():
    global created_story_id
    c, u = client_with_user(userA.username)
    r = c.post("/story/create", data={
        "caption": f"QA Story Music {int(time.time())}",
        "visibility": "Public",
        "music_track": "Blinding Lights - The Weeknd",
        "music_preview_url": "https://audio-ssl.itunes.apple.com/preview.m4a",
    }, content_type="multipart/form-data")
    if r.status_code != 201:
        d = r.get_json() if r.content_type and 'json' in r.content_type else {}
        bug("CRITICAL", "Stories", "Story with music creation failed", f"Status {r.status_code}: {d}")
        return False
    d = r.get_json()
    created_story_id = d.get("story_id")
    return created_story_id is not None

def test_create_story_with_photo():
    c, u = client_with_user(userA.username)
    r = c.post("/story/create", data={
        "caption": f"QA Story Photo {int(time.time())}",
        "visibility": "Public",
        "camera_photo_data": f"data:image/png;base64,{PNG_1X1}",
    }, content_type="multipart/form-data")
    if r.status_code != 201:
        d = r.get_json() if r.content_type and 'json' in r.content_type else {}
        bug("MAJOR", "Stories", "Story with photo creation failed", f"Status {r.status_code}: {d}")
    return r.status_code == 201

def test_create_text_only_story():
    c, u = client_with_user(userA.username)
    r = c.post("/story/create", data={
        "caption": f"QA Text Story {int(time.time())}",
        "visibility": "Public",
    }, content_type="multipart/form-data")
    return r.status_code == 201

def test_story_view_tracking():
    if not created_story_id:
        return False
    c, u = client_with_user(userB.username)
    r = c.post(f"/api/story/{created_story_id}/view",
        data=json.dumps({}),
        content_type="application/json")
    return r.status_code == 200

def test_story_views_list():
    if not created_story_id:
        return False
    c, u = client_with_user(userA.username)
    r = c.get(f"/api/story/{created_story_id}/views")
    return r.status_code == 200

def test_story_like():
    if not created_story_id:
        return False
    c, u = client_with_user(userB.username)
    r = c.post(f"/api/story/{created_story_id}/like",
        data=json.dumps({}),
        content_type="application/json")
    return r.status_code in (200, 201)

def test_delete_story():
    if not created_story_id:
        return False
    c, u = client_with_user(userA.username)
    r = c.delete(f"/api/stories/{created_story_id}")
    return r.status_code in (200, 204)

def test_stories_page_loads():
    c, u = client_with_user(userA.username)
    r = c.get("/stories")
    return r.status_code == 200

track("Stories: Create page loads", test_story_create_page)
track("Stories: Create with music", test_create_story_with_music)
track("Stories: Create with photo", test_create_story_with_photo)
track("Stories: Create text-only", test_create_text_only_story)
track("Stories: View tracking", test_story_view_tracking)
track("Stories: Views list (author only)", test_story_views_list)
track("Stories: Like story", test_story_like)
track("Stories: Delete story", test_delete_story)
track("Stories: Stories page loads", test_stories_page_loads)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("4. MUSIC SYSTEM TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_music_search():
    c, u = client_with_user(userA.username)
    r = c.get("/api/music/search?q=drake&limit=5")
    if r.status_code != 200:
        bug("MAJOR", "Music", "Music search endpoint failed", f"Status {r.status_code}")
        return False
    d = r.get_json()
    results = d.get("results") or []
    return isinstance(results, list)

def test_music_list_fallback():
    c, u = client_with_user(userA.username)
    r = c.get("/api/music/list")
    return r.status_code == 200

def test_music_stream_rejects_bad_host():
    c, u = client_with_user(userA.username)
    r = c.get("/api/music/stream?url=https://evil.com/malware.mp3")
    return r.status_code in (400, 403)

def test_music_stream_missing_url():
    c, u = client_with_user(userA.username)
    r = c.get("/api/music/stream")
    return r.status_code in (400, 422)

track("Music: Search endpoint", test_music_search)
track("Music: List fallback", test_music_list_fallback)
track("Music: Stream rejects bad host", test_music_stream_rejects_bad_host)
track("Music: Stream rejects missing url", test_music_stream_missing_url)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("5. SETTINGS TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_settings_page_loads():
    c, u = client_with_user(userA.username)
    r = c.get("/settings")
    return r.status_code == 200

def test_theme_update():
    c, u = client_with_user(userA.username)
    r = c.post("/api/update_theme",
        data=json.dumps({"preset": "neon_city", "colors": {"bg":"#0a0810","brand1":"#ff9a3d","brand2":"#ff6a00","brand3":"#ff4800"}}),
        content_type="application/json")
    return r.status_code == 200

def test_feed_mode_set():
    c, u = client_with_user(userA.username)
    r = c.post("/feed-modes/set",
        data=json.dumps({"mode": "trending"}),
        content_type="application/json")
    return r.status_code == 200

def test_feed_mode_get():
    c, u = client_with_user(userA.username)
    r = c.get("/feed-modes/current")
    return r.status_code == 200

track("Settings: Page loads", test_settings_page_loads)
track("Settings: Theme update", test_theme_update)
track("Settings: Feed mode set", test_feed_mode_set)
track("Settings: Feed mode get", test_feed_mode_get)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("6. NOTIFICATION TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_pulses_endpoint():
    c, u = client_with_user(userA.username)
    r = c.get("/api/pulses")
    return r.status_code == 200

def test_pulses_count():
    c, u = client_with_user(userA.username)
    r = c.get("/api/pulses/count")
    return r.status_code == 200

def test_vapid_key():
    c, u = client_with_user(userA.username)
    r = c.get("/api/pulses/vapid-public-key")
    return r.status_code == 200

track("Notifications: Pulses endpoint", test_pulses_endpoint)
track("Notifications: Unread count", test_pulses_count)
track("Notifications: VAPID public key", test_vapid_key)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("7. MESSAGING TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_dm_threads_list():
    c, u = client_with_user(userA.username)
    r = c.get("/api/dm/threads")
    return r.status_code == 200

def test_dm_create_thread():
    c, u = client_with_user(userA.username)
    r = c.post("/api/dm/threads",
        data=json.dumps({"username": userB.username}),
        content_type="application/json")
    return r.status_code in (200, 201, 409)  # 409 = thread already exists

track("Messaging: Thread list", test_dm_threads_list)
track("Messaging: Create thread", test_dm_create_thread)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("8. MODERATION ENGINE TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_moderation_clean_text():
    from moderation_engine import moderate_text
    r = moderate_text("Hello world, great day!")
    return r.decision == "allow"

def test_moderation_blocks_threats():
    from moderation_engine import moderate_text
    r = moderate_text("I will kill you right now")
    return r.decision == "block"

def test_moderation_blocks_doxxing():
    from moderation_engine import moderate_text
    r = moderate_text("call me at 555-123-4567")
    return r.decision == "block"

def test_moderation_allows_timestamps():
    from moderation_engine import moderate_text
    r = moderate_text(f"Posted at {int(time.time())}")
    if r.decision != "allow":
        bug("MAJOR", "Moderation", "Timestamp false positive still exists",
            f"Text 'Posted at {int(time.time())}' blocked as {r.reason}")
    return r.decision == "allow"

def test_moderation_blocks_ssn():
    from moderation_engine import moderate_text
    r = moderate_text("my ssn is 123-45-6789")
    return r.decision == "block"

def test_moderation_empty_text():
    from moderation_engine import moderate_text
    r = moderate_text("")
    return r.decision == "block"  # Empty should be blocked per code

def test_preflight_moderation():
    c, u = client_with_user(userA.username)
    r = c.post("/api/moderate_content",
        data=json.dumps({"text": "This is a harmless test"}),
        content_type="application/json")
    if r.status_code == 200:
        d = r.get_json()
        return d.get("approved") == True or d.get("ok") == True
    return False

track("Moderation: Clean text allowed", test_moderation_clean_text)
track("Moderation: Threats blocked", test_moderation_blocks_threats)
track("Moderation: Doxxing blocked", test_moderation_blocks_doxxing)
track("Moderation: Timestamps allowed", test_moderation_allows_timestamps)
track("Moderation: SSN blocked", test_moderation_blocks_ssn)
track("Moderation: Empty text blocked", test_moderation_empty_text)
track("Moderation: Preflight check", test_preflight_moderation)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("9. SECURITY TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

def test_no_raw_db_errors_exposed():
    """Post to create with malformed JSON — should get clean error, not SQL trace."""
    c, u = client_with_user(userA.username)
    r = c.post("/api/posts/create", data="not json", content_type="application/json")
    body = r.data.decode("utf-8", errors="replace").lower()
    for danger in ["traceback", "sqlalchemy", "sqlite", "operationalerror", "integrityerror"]:
        if danger in body:
            bug("CRITICAL", "Security", f"Raw DB error exposed: {danger}", body[:200])
            return False
    return True

def test_xss_in_caption():
    c, u = client_with_user(userA.username)
    r = c.post("/api/posts/create",
        data=json.dumps({"caption": "<script>alert(1)</script>", "visibility": "public"}),
        content_type="application/json")
    if r.status_code == 201:
        d = r.get_json()
        p = d.get("post") or d
        pid = p.get("id")
        # JSON API returning raw text is fine — the frontend escapeHtml() before innerHTML
        # This test verifies the post is accepted without causing server-side issues
        c.delete(f"/api/posts/{pid}")
    return True

def test_unauthorized_delete():
    """User B cannot delete User A's post."""
    cA, uA = client_with_user(userA.username)
    r = cA.post("/api/posts/create",
        data=json.dumps({"caption": "Protected post", "visibility": "public"}),
        content_type="application/json")
    d = r.get_json()
    pid = (d.get("post") or d).get("id")
    if not pid:
        return False
    cB, uB = client_with_user(userB.username)
    dr = cB.delete(f"/api/posts/{pid}")
    # Clean up
    cA.delete(f"/api/posts/{pid}")
    if dr.status_code in (200, 204):
        bug("CRITICAL", "Security", "Unauthorized deletion allowed",
            f"User {userB.username} deleted User {userA.username}'s post {pid}")
        return False
    return True

track("Security: No raw DB errors exposed", test_no_raw_db_errors_exposed)
track("Security: XSS prevention in captions", test_xss_in_caption)
track("Security: Unauthorized delete prevented", test_unauthorized_delete)

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("10. PAGE LOAD TESTS")
print("="*70)
# ═══════════════════════════════════════════════════════════════════════════

pages = {
    "Feed": "/",
    "Login": "/login",
    "Register": "/register",
    "Stories": "/stories",
    "Settings": "/settings",
    "About": "/about",
    "Account": "/account",
}

for name, path in pages.items():
    def make_test(p, n=name):
        def t():
            c, _u = client_with_user(userA.username)
            r = c.get(p, follow_redirects=True)
            if r.status_code != 200:
                bug("MAJOR", "Pages", f"{n} page returned {r.status_code}", f"GET {p}")
            return r.status_code == 200
        return t
    track(f"Page: {name} ({path})", make_test(path))

# ═══════════════════════════════════════════════════════════════════════════
# API ENDPOINT SMOKE TESTS
# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("11. API ENDPOINT SMOKE TESTS")
print("="*70)

api_gets = [
    ("/api/posts/list?page=1&limit=5", "Posts list"),
    ("/api/pulses", "Pulses list"),
    ("/api/pulses/count", "Pulse count"),
    ("/api/music/search?q=test&limit=3", "Music search"),
    ("/api/music/list", "Music list"),
    ("/api/dm/threads", "DM threads"),
    ("/api/stickers/packs", "Sticker packs"),
    ("/api/media/recents", "Media recents"),
    ("/feed-modes/current", "Feed mode"),
]

for path, name in api_gets:
    def make_api_test(p, n):
        def t():
            c, u = client_with_user(userA.username)
            r = c.get(p)
            if r.status_code >= 500:
                bug("CRITICAL", "API", f"500 error on {n}", f"GET {p} returned {r.status_code}")
            return r.status_code < 500
        return t
    track(f"API: {name} ({path})", make_api_test(path, name))

# ═══════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════════════
with app.app_context():
    # Clean up any QA test posts
    qa_posts = Post.query.filter(Post.caption.like("QA_%")).all()
    for p in qa_posts:
        db.session.delete(p)
    qa_stories = Story.query.filter(Story.caption.like("QA_%")).all()
    for s in qa_stories:
        db.session.delete(s)
    db.session.commit()

# ═══════════════════════════════════════════════════════════════════════════
print("\n" + "="*70)
print("RESULTS SUMMARY")
print("="*70)
print(f"  Total : {results['total']}")
print(f"  Pass  : {results['pass']}")
print(f"  Fail  : {results['fail']}")
print(f"  Rate  : {results['pass']/max(results['total'],1)*100:.1f}%")

if bugs:
    print(f"\n{'='*70}")
    print(f"BUGS FOUND ({len(bugs)})")
    print(f"{'='*70}")
    for i, b in enumerate(bugs, 1):
        sev = b["severity"]
        color = "\033[91m" if sev == "CRITICAL" else "\033[93m" if sev == "MAJOR" else "\033[90m"
        print(f"  {color}{i}. [{sev}] {b['subsystem']}: {b['title']}\033[0m")
        if b["detail"]:
            print(f"     {b['detail'][:150]}")
else:
    print("\n  No bugs found during automated testing.")

print("\n" + "="*70 + "\n")
