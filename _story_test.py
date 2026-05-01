import requests, re, sys

s = requests.Session()
BASE = 'http://127.0.0.1:5000'

# Get CSRF from login page
page = s.get(BASE + '/login')
pat = r'name="csrf_token"\s+value="([^"]+)"'
m = re.search(pat, page.text)
csrf = m.group(1) if m else ''
print('CSRF:', csrf[:20] + '...' if csrf else 'NOT FOUND')

# Login
r = s.post(BASE + '/login', data={
    'username': 'testuser',
    'password': 'TestPass@12345!',
    'csrf_token': csrf
}, allow_redirects=True)
print('Login status:', r.status_code, '| url:', r.url)

# Get fresh CSRF from create_story page
page2 = s.get(BASE + '/create_story')
m2 = re.search(pat, page2.text)
csrf2 = m2.group(1) if m2 else csrf

# POST a text-only story
r2 = s.post(BASE + '/story/create',
    data={'caption': 'Test story from script', 'csrf_token': csrf2},
    headers={'X-Requested-With': 'XMLHttpRequest', 'X-CSRFToken': csrf2})
print('Story POST status:', r2.status_code)
print('Response:', r2.text[:800])
