"""Quick smoke test — verify feed, posts, and stories are working."""
import requests, sys, re

BASE = "http://127.0.0.1:5000"
s = requests.Session()
ok = True

# 1. Health check
r = s.get(BASE + "/", allow_redirects=True, timeout=5)
print(f"  GET /  -> {r.status_code}")

# 2. Public posts list (unauthenticated)
r = s.get(BASE + "/api/posts/list", timeout=5)
print(f"  GET /api/posts/list -> {r.status_code}")
if r.status_code == 200:
    data = r.json()
    posts = data.get("posts", data if isinstance(data, list) else [])
    print(f"  Posts returned (unauthed): {len(posts)}")
    for p in posts[:3]:
        capped = str(p.get("caption", ""))[:40]
        print(f"    post {p.get('id')}: caption={capped!r}  media={p.get('media_url', 'none')}")
else:
    print(f"  ERROR BODY: {r.text[:200]}")
    ok = False

# 3. Stories page
r = s.get(BASE + "/stories", timeout=5)
print(f"  GET /stories -> {r.status_code}")

# 4. Feed page (unauthed — should redirect to login)
r = s.get(BASE + "/feed", allow_redirects=True, timeout=5)
dest = "login redirect" if "login" in r.url else "feed page"
print(f"  GET /feed -> {r.status_code} ({dest})")

# 5. Login — extract CSRF token first
login_page = s.get(BASE + "/login", timeout=5)
csrf_match = re.search(r'name="csrf_token"\s+value="([^"]+)"', login_page.text)
csrf_token = csrf_match.group(1) if csrf_match else ""
print(f"  CSRF token found: {'yes' if csrf_token else 'NO — login will fail'}")

login = s.post(
    BASE + "/login",
    data={
        "username": "DAREALEST1",
        "password": "VybeFlow2026!",
        "csrf_token": csrf_token,
    },
    allow_redirects=True,
    timeout=5,
)
url_short = login.url.replace(BASE, "") if BASE in login.url else login.url
url_dest = url_short.split("?")[0]
logged_in = "login" not in url_dest
print(f"  POST /login -> {login.status_code} (url={url_dest}, logged_in={'YES' if logged_in else 'NO'})")

# 6. Authenticated posts list
r = s.get(BASE + "/api/posts/list", timeout=5)
print(f"  GET /api/posts/list (authed) -> {r.status_code}")
if r.status_code == 200:
    data = r.json()
    posts = data.get("posts", data if isinstance(data, list) else [])
    print(f"  Posts visible (authed): {len(posts)}")
    if not logged_in:
        print("  NOTE: posts show because they are public (no auth needed)")
else:
    print(f"  ERROR BODY: {r.text[:200]}")
    ok = False

# 7. Feed HTML (authed)
r = s.get(BASE + "/feed", allow_redirects=True, timeout=5)
feed_ok = "login" not in r.url and r.status_code == 200
print(f"  GET /feed (authed) -> {r.status_code} ({'OK' if feed_ok else 'still login redirect'})")
if not feed_ok:
    ok = False

print()
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
