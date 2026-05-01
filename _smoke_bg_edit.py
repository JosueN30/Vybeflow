import re
import requests

BASE = "http://127.0.0.1:5000"
USER = "DAREALEST1"
PASS = "VybeFlow2026!"

s = requests.Session()

# login page csrf
lp = s.get(BASE + "/login", timeout=8)
m = re.search(r'name="csrf_token"\s+value="([^"]+)"', lp.text)
csrf = m.group(1) if m else ""
if not csrf:
    raise SystemExit("FAIL: no login csrf token")

r = s.post(BASE + "/login", data={"username": USER, "password": PASS, "csrf_token": csrf}, allow_redirects=True, timeout=8)
if r.status_code != 200:
    raise SystemExit(f"FAIL: login status {r.status_code}")

# feed page csrf meta for API patch
feed = s.get(BASE + "/feed", timeout=8)
m2 = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]*)"', feed.text)
api_csrf = m2.group(1) if m2 else ""
if not api_csrf:
    raise SystemExit("FAIL: no feed csrf meta token")

lst = s.get(BASE + "/api/posts/list", timeout=8)
obj = lst.json()
posts = obj.get("posts", obj if isinstance(obj, list) else [])
target = next((p for p in posts if p.get("can_edit")), None)
if not target:
    raise SystemExit("FAIL: no editable post found")

pid = target["id"]
old_caption = target.get("caption") or ""
old_style = target.get("bg_style") or "default"
old_color = target.get("bg_color")
old_vis = target.get("visibility") or "Public"

new_color = "#12ab9c"
patch_payload = {
    "caption": old_caption,
    "bg_style": "default",
    "bg_color": new_color,
    "visibility": old_vis,
}

pr = s.patch(
    f"{BASE}/api/posts/{pid}",
    json=patch_payload,
    headers={"X-CSRFToken": api_csrf},
    timeout=8,
)
if pr.status_code != 200:
    raise SystemExit(f"FAIL: patch status {pr.status_code} body={pr.text[:200]}")

patched = pr.json().get("post", {})
if patched.get("bg_color") != new_color:
    raise SystemExit(f"FAIL: patch response bg_color={patched.get('bg_color')} expected={new_color}")

# verify persisted in list
lst2 = s.get(BASE + "/api/posts/list", timeout=8)
obj2 = lst2.json()
posts2 = obj2.get("posts", obj2 if isinstance(obj2, list) else [])
after = next((p for p in posts2 if p.get("id") == pid), None)
if not after:
    raise SystemExit("FAIL: updated post not found in list")
if after.get("bg_color") != new_color:
    raise SystemExit(f"FAIL: list bg_color={after.get('bg_color')} expected={new_color}")

print(f"PASS: post {pid} bg_color updated to {new_color} and visible in feed API")

# revert change to avoid leaving test artifacts
revert_payload = {
    "caption": old_caption,
    "bg_style": old_style,
    "bg_color": old_color,
    "visibility": old_vis,
}
rr = s.patch(
    f"{BASE}/api/posts/{pid}",
    json=revert_payload,
    headers={"X-CSRFToken": api_csrf},
    timeout=8,
)
print(f"REVERT: status={rr.status_code}")
