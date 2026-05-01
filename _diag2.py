"""Feed API diagnostic — python _diag2.py"""
import sys, os, json
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from app import create_app
app, _sk = create_app()
with app.test_client() as c:
    # test unauthenticated
    r = c.get('/api/posts/list?offset=0&limit=10',
              headers={'X-Requested-With': 'XMLHttpRequest'})
    data = json.loads(r.data)
    print(f"[UNAUTH] status={r.status_code} posts={len(data.get('posts',[]))} has_more={data.get('has_more')}")
    if data.get('posts'):
        p = data['posts'][0]
        print(f"  first post id={p.get('id')} vis={p.get('visibility')!r} avatar={p.get('author_avatar_url')!r}")
    
    # test authenticated as first user
    with c.session_transaction() as sess:
        sess['username'] = 'DAREALEST1'
        sess['logged_in'] = True
        sess['user_id'] = 1
    
    r2 = c.get('/api/posts/list?offset=0&limit=10',
               headers={'X-Requested-With': 'XMLHttpRequest'})
    data2 = json.loads(r2.data)
    print(f"[AUTH as DAREALEST1] status={r2.status_code} posts={len(data2.get('posts',[]))} has_more={data2.get('has_more')}")
    for p in data2.get('posts', [])[:3]:
        print(f"  post id={p.get('id')} vis={p.get('visibility')!r} avatar={p.get('author_avatar_url')!r}")

print("DONE")
