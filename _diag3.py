"""Test feed page response — python _diag3.py"""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from app import create_app
app, _sk = create_app()
with app.test_client() as c:
    # simulate logged-in user
    with c.session_transaction() as sess:
        sess['username'] = 'DAREALEST1'
        sess['logged_in'] = True
        sess['user_id'] = 1

    r = c.get('/feed')
    print(f"Feed page status: {r.status_code}")
    html = r.data.decode('utf-8', 'ignore')
    
    # Check for key DOM elements
    checks = [
        'mvp-posts-list',
        'mvp-post-create',
        'refreshPosts',
        '_loadPostsBatch',
        'renderPosts',
        'api/posts/list',
        'mvp-post-caption',
    ]
    for c_str in checks:
        found = c_str in html
        print(f"  {'✓' if found else '✗'} {c_str}")
    
    # Check for any Jinja2 render errors
    if '{{' in html or '{%' in html:
        print("  ! Unrendered Jinja2 tags found - template error")
    
    # Check for JS errors in template
    if 'UndefinedError' in html or 'TemplateError' in html:
        print("  ! Template error found in HTML")
    else:
        print("  ✓ No template errors in HTML")
    
    print(f"  HTML length: {len(html)} chars")
    
    # Check avatar URL in API
    import json
    r2 = c.get('/api/posts/list?offset=0&limit=5',
               headers={'X-Requested-With': 'XMLHttpRequest'})
    data = json.loads(r2.data)
    print(f"\nAPI posts count: {len(data.get('posts', []))}")
    for p in data.get('posts', [])[:2]:
        av = p.get('author_avatar_url', '')
        print(f"  post {p.get('id')}: avatar={av!r}")
        # check if path starts with correct prefix
        if av and not av.startswith(('/static/', 'http', '/uploads/')):
            print(f"    !! BAD avatar path prefix")
            
print("DONE")
