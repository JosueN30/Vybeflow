import os
import sys
import json
from datetime import datetime

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from app import create_app
from models import User

app, _socketio = create_app()

with app.app_context():
    user = User.query.filter_by(username='DAREALEST1').first() or User.query.first()
    if not user:
        print('PROOF_FAIL: no users found')
        raise SystemExit(1)

    uname = user.username
    uid = user.id

stamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
caption = f'PROOF_POST_{stamp}_people_can_see_posts'

with app.test_client() as c:
    with c.session_transaction() as sess:
        sess['username'] = uname
        sess['user_id'] = uid
        sess['logged_in'] = True

    create_resp = c.post(
        '/api/posts/create',
        data={
            'caption': caption,
            'visibility': 'public'
        },
        headers={'X-Requested-With': 'XMLHttpRequest'}
    )

    create_text = create_resp.get_data(as_text=True)
    try:
        create_data = json.loads(create_text)
    except Exception:
        create_data = {'raw': create_text[:500]}

    feed_resp = c.get('/api/posts/list?offset=0&limit=50', headers={'X-Requested-With': 'XMLHttpRequest'})
    feed_data = feed_resp.get_json(silent=True) or {}
    posts = feed_data.get('posts') or []

    found = [p for p in posts if (p.get('caption') or '') == caption]
    post_id = None
    if found:
        post_id = found[0].get('id')

    page_resp = c.get('/feed')

    print('PROOF: create_status=', create_resp.status_code)
    print('PROOF: create_ok=', bool(create_data.get('ok')))
    print('PROOF: created_post_id=', (create_data.get('post') or {}).get('id'))
    print('PROOF: list_status=', feed_resp.status_code)
    print('PROOF: list_count=', len(posts))
    print('PROOF: new_caption_found_in_feed_list=', bool(found))
    print('PROOF: found_post_id=', post_id)
    print('PROOF: feed_page_status=', page_resp.status_code)
    print('PROOF: sample_new_caption=', caption)

    if create_resp.status_code != 201 or not create_data.get('ok') or not found or page_resp.status_code != 200:
        print('PROOF_FAIL: posting or visibility check failed')
        raise SystemExit(2)

print('PROOF_PASS')
