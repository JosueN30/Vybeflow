import re
import requests

BASE = "http://127.0.0.1:5000"
s = requests.Session()

lp = s.get(BASE + "/login", timeout=8)
csrf = re.search(r'name="csrf_token"\s+value="([^"]+)"', lp.text).group(1)

r = s.post(
    BASE + "/login",
    data={"username": "DAREALEST1", "password": "VybeFlow2026!", "csrf_token": csrf},
    allow_redirects=True,
    timeout=8,
)
print("login final", r.url, r.status_code)

lo = s.get(BASE + "/logout", allow_redirects=True, timeout=8)
print("logout final", lo.url, lo.status_code)

a = s.get(BASE + "/feed", allow_redirects=True, timeout=8)
print("feed after logout", a.url, a.status_code)
