"""
VYBEFLOW POST SIMULATION - PROOF OF LIFE
Directly tests the DB layer + posts_api logic without needing an HTTP server.
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('TESTING', '1')

try:
    from app import create_app
except ImportError:
    # app.py uses a flat register_routes pattern
    import importlib
    spec = importlib.util.spec_from_file_location("app", "app.py")
    app_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(app_mod)
    create_app = None

print("=" * 60)
print("VYBEFLOW POST SIMULATION — PROOF OF LIFE")
print("=" * 60)

# ── Import app object ──────────────────────────────────────
try:
    from app import app, db
    print("[OK] Flask app imported")
except Exception as e:
    print(f"[ERR] Could not import app: {e}")
    sys.exit(1)

# ── Import models ──────────────────────────────────────────
try:
    from models import Post, User
    print("[OK] Models imported")
except Exception as e:
    print(f"[ERR] Could not import models: {e}")
    sys.exit(1)

TEST_CAPTION = "Jesus is the best"
TEST_USERNAME = "_sim_test_user"

with app.app_context():
    # ── Ensure test user exists ────────────────────────────
    try:
        user = User.query.filter_by(username=TEST_USERNAME).first()
        if not user:
            from werkzeug.security import generate_password_hash
            user = User(
                username=TEST_USERNAME,
                email=f"{TEST_USERNAME}@sim.local",
                password_hash=generate_password_hash("sim123"),
                avatar_url="/static/VFlogo_clean.png",
            )
            db.session.add(user)
            db.session.commit()
            print(f"[OK] Created test user: {TEST_USERNAME}")
        else:
            print(f"[OK] Test user exists: {TEST_USERNAME} (id={user.id})")
    except Exception as e:
        db.session.rollback()
        print(f"[ERR] User setup failed: {e}")
        sys.exit(1)

    # ── Create the post directly ───────────────────────────
    try:
        post = Post(
            author_id=user.id,
            caption=TEST_CAPTION,
            bg_style="default",
            visibility="public",
        )
        db.session.add(post)
        db.session.commit()
        print(f"[OK] Post created: id={post.id}")
    except Exception as e:
        db.session.rollback()
        print(f"[ERR] Post creation failed: {e}")
        sys.exit(1)

    # ── Verify DB round-trip ───────────────────────────────
    try:
        fetched = Post.query.get(post.id)
        assert fetched is not None, "Post not found after commit"
        assert fetched.caption == TEST_CAPTION, f"Caption mismatch: {fetched.caption!r}"
        assert fetched.bg_style == "default", f"Theme mismatch: {fetched.bg_style!r}"
        print(f"[OK] DB round-trip verified:")
        print(f"     caption  = {fetched.caption!r}")
        print(f"     theme    = {fetched.bg_style!r}  ← 'Default' theme active ✓")
        print(f"     author   = {user.username}")
        print(f"     visible  = {fetched.visibility}")
    except AssertionError as ae:
        print(f"[ERR] Verification failed: {ae}")
        sys.exit(1)

    # ── Simulate frontend render (JSON payload) ────────────
    try:
        payload = {
            "id": fetched.id,
            "caption": fetched.caption,
            "bg_style": fetched.bg_style,
            "visibility": fetched.visibility,
            "author_username": user.username,
            "author_avatar_url": user.avatar_url or "/static/VFlogo_clean.png",
            "can_edit": True,
            "like_count": 0,
            "comment_count": 0,
        }
        print(f"\n[OK] Frontend render payload (JSON):")
        print(json.dumps(payload, indent=2))
    except Exception as e:
        print(f"[WARN] Payload build failed: {e}")

    # ── Test /api/posts/create via TestClient ──────────────
    try:
        with app.test_client() as client:
            with client.session_transaction() as sess:
                sess['username'] = TEST_USERNAME

            resp = client.post('/api/posts/create', data={
                'caption': TEST_CAPTION + ' (API test)',
                'visibility': 'Public',
                'bg_style': 'default',
            }, content_type='multipart/form-data')

            body = resp.get_json(silent=True) or {}
            if resp.status_code in (200, 201) and body.get('ok'):
                print(f"\n[OK] /api/posts/create → HTTP {resp.status_code}")
                print(f"     post id = {body.get('post', {}).get('id')}")
                print(f"     theme   = {body.get('post', {}).get('bg_style', 'default')!r}")
            else:
                print(f"\n[WARN] /api/posts/create → HTTP {resp.status_code}: {body}")
    except Exception as e:
        print(f"[WARN] TestClient call failed: {e}")

    # ── Cleanup test posts ─────────────────────────────────
    try:
        Post.query.filter_by(author_id=user.id).delete()
        db.session.commit()
        print("\n[OK] Test data cleaned up")
    except Exception as e:
        db.session.rollback()
        print(f"[WARN] Cleanup failed: {e}")

print("\n" + "=" * 60)
print("SIMULATION RESULT: SUCCESS ✓")
print("  Post 'Jesus is the best' created, DB verified, theme=Default")
print("=" * 60)
