"""Debug login form + stories endpoint."""
import requests, re

BASE = "http://127.0.0.1:5000"
s = requests.Session()

# Check login form fields
r = s.get(BASE + "/login", timeout=5)
fields = list(set(re.findall(r'name=["\']([^"\']+)["\']', r.text)))
print("Login form fields:", sorted(fields))

# Try login with username field
r2 = s.post(BASE + "/login",
            data={"username": "DAREALEST1", "password": "VybeFlow2026!"},
            allow_redirects=True, timeout=5)
dest = r2.url.replace(BASE, "") if BASE in r2.url else r2.url
print(f"Login (username field): {r2.status_code} -> {dest.split('?')[0]}")

# Try login with email
r3 = s.post(BASE + "/login",
            data={"email": "chatcirclebusiness16@gmail.com", "password": "VybeFlow2026!"},
            allow_redirects=True, timeout=5)
dest3 = r3.url.replace(BASE, "") if BASE in r3.url else r3.url
print(f"Login (email field):   {r3.status_code} -> {dest3.split('?')[0]}")

# Stories endpoints
for url in ["/api/stories", "/stories", "/api/story/list", "/api/stories/list"]:
    r4 = s.get(BASE + url, timeout=5)
    print(f"  {url} -> {r4.status_code}")
