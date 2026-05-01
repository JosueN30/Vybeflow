"""Quick endpoint smoke test for VybeFlow"""
from app import create_app

result = create_app()
app = result[0] if isinstance(result, tuple) else result

# Collect all routes
rules = list(app.url_map.iter_rules())

# Key routes to verify
required = [
    '/messenger',
    '/api/messenger/send',
    '/api/messenger/thread',
    '/api/comments/<int:comment_id>',
    '/api/comments/<int:comment_id>/voice-note',
    '/api/comments/<int:comment_id>/like',
    '/api/comments/<int:comment_id>/notes',
    '/api/comments/<int:comment_id>/visibility',
    '/api/posts/create',
    '/api/posts/list',
    '/api/posts/delete',
    '/api/posts/<int:post_id>',
    '/api/posts/<int:post_id>/react',
    '/api/posts/<int:post_id>/like',
    '/api/profile/music',
    '/api/profile/music/list',
    '/api/profile/music/<int:track_id>',
    '/banned',
    '/create_story_page',
    '/uploads/<path:filename>',
    '/search',
    '/login',
    '/register',
    '/logout',
    '/forgot_password',
    '/reset_password/<token>',
    '/feed',
    '/',
    '/settings',
    '/account',
]

rule_strings = {str(r) for r in rules}
all_ok = True
print("Checking required routes:")
for r in required:
    if r in rule_strings:
        print(f"  OK  {r}")
    else:
        print(f"  MISSING  {r}")
        all_ok = False

if all_ok:
    print("\nAll required routes are registered!")
else:
    print("\nSome routes are missing!")

# Check for duplicate paths (same path+method combo)
from collections import defaultdict
path_methods = defaultdict(list)
for rule in rules:
    for method in rule.methods:
        if method not in ('HEAD', 'OPTIONS'):
            path_methods[(str(rule), method)].append(rule.endpoint)

print("\nDuplicate path+method combinations:")
found_dupes = False
for (path, method), endpoints in sorted(path_methods.items()):
    if len(endpoints) > 1:
        print(f"  {method} {path}: {endpoints}")
        found_dupes = True
if not found_dupes:
    print("  None!")
