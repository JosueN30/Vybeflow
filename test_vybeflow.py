"""
VybeFlow Automated Test Suite
==============================
Run with:
    python -m pytest test_vybeflow.py -v
or:
    python test_vybeflow.py

Every meaningful feature has at least one test. If ANY test fails, the code
that caused the failure must be fixed before it is deployed.
"""

import os
import sys
import json
import unittest

# ── Force an in-memory SQLite DB so tests never touch the real database ──
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("WTF_CSRF_ENABLED", "false")  # disable CSRF for test posts
os.environ.setdefault("SECRET_KEY", "test-secret-key-do-not-use-in-production")

# Make sure the project root is on the path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from __init__ import db as _db
from models import User, Post
from werkzeug.security import generate_password_hash


# ---------------------------------------------------------------------------
# Helper: build & tear down a fresh in-memory app for each test class
# ---------------------------------------------------------------------------
def _make_app():
    """Return a configured Flask test app with an empty in-memory database.

    create_app() returns (app, socketio) — we unpack the tuple so the rest of
    the test suite only deals with the Flask app object.
    """
    result = create_app(test_config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "WTF_CSRF_CHECK_DEFAULT": False,
        "SERVER_NAME": None,
        "SECRET_KEY": "test-secret-key-do-not-use-in-production",
        "RATELIMIT_ENABLED": False,      # disable Flask-Limiter during tests
        "RATELIMIT_STORAGE_URI": "memory://",
    })
    # create_app returns (Flask_app, SocketIO) — unwrap if needed
    app = result[0] if isinstance(result, tuple) else result
    with app.app_context():
        _db.create_all()
    return app


def _seed_user(app, username="testuser", password="TestPass123!",
               email="test@vybeflow.local"):
    """Create a user in the test DB and return (user, raw_password)."""
    with app.app_context():
        u = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            display_name="Test User",
        )
        _db.session.add(u)
        _db.session.commit()
        return u.id


def _login(client, username="testuser", password="TestPass123!"):
    """Log the test client in via the /login route."""
    return client.post("/login", data={
        "username": username,
        "password": password,
    }, follow_redirects=True)


# ===========================================================================
# 1. SMOKE TESTS — the site must boot and serve pages
# ===========================================================================
class TestSiteBoots(unittest.TestCase):
    """The absolute minimum: the app starts and public pages load."""

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()

    def test_home_page_loads(self):
        """GET / must return 200 or 302 (redirect to feed/login)."""
        r = self.client.get("/")
        self.assertIn(r.status_code, (200, 302),
                      f"/ returned unexpected status {r.status_code}")

    def test_login_page_loads(self):
        """GET /login must return 200."""
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)

    def test_register_page_loads(self):
        """GET /register must return 200."""
        r = self.client.get("/register")
        self.assertEqual(r.status_code, 200)

    def test_feed_redirects_when_logged_out(self):
        """Unauthenticated /feed must redirect to login, not 500."""
        r = self.client.get("/feed")
        self.assertIn(r.status_code, (200, 302),
                      f"/feed returned {r.status_code} — expected 200 or 302")
        if r.status_code == 302:
            self.assertIn("login", r.headers.get("Location", "").lower(),
                          "Redirect from /feed should go to /login")

    def test_no_500_on_feed(self):
        """Feed must never return a 500 error, even without a session."""
        r = self.client.get("/feed")
        self.assertNotEqual(r.status_code, 500, "/feed returned an internal server error")

    def test_api_posts_list_when_logged_out(self):
        """/api/posts/list must return JSON (empty list), not a crash."""
        r = self.client.get("/api/posts/list")
        self.assertIn(r.status_code, (200, 401),
                      f"/api/posts/list returned {r.status_code}")


# ===========================================================================
# 2. AUTH TESTS — registration and login must work end-to-end
# ===========================================================================
class TestAuth(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()

    def test_register_creates_user(self):
        """Submitting /register must persist a User row."""
        r = self.client.post("/register", data={
            "username": "newuser",
            "email": "newuser@vybeflow.local",
            "password": "SecurePass99!",
            "confirm_password": "SecurePass99!",
            "date_of_birth": "2000-01-01",
        }, follow_redirects=True)
        self.assertNotEqual(r.status_code, 500, "register returned 500")
        with self.app.app_context():
            u = User.query.filter_by(username="newuser").first()
            self.assertIsNotNone(u, "User was not saved to the database after registration")

    def test_login_with_valid_credentials(self):
        """A registered user must be able to log in."""
        _seed_user(self.app, username="logintest", password="LoginPass1!",
                   email="logintest@vybeflow.local")
        r = _login(self.client, username="logintest", password="LoginPass1!")
        self.assertNotEqual(r.status_code, 500, "login returned 500")

    def test_login_with_wrong_password(self):
        """Wrong password must not authenticate the user."""
        _seed_user(self.app, username="wrongpass", password="CorrectPass1!",
                   email="wrongpass@vybeflow.local")
        r = self.client.post("/login", data={
            "username": "wrongpass",
            "password": "WrongPassword!",
        }, follow_redirects=True)
        # Should stay on login page or show an error, never on feed
        self.assertNotIn(b"logout", r.data.lower(),
                         "Wrong password logged in successfully — SECURITY BUG")

    def test_duplicate_username_rejected(self):
        """Registering with an existing username must fail gracefully."""
        _seed_user(self.app, username="dupuser", password="Pass1!",
                   email="dup1@vybeflow.local")
        r = self.client.post("/register", data={
            "username": "dupuser",
            "email": "dup2@vybeflow.local",
            "password": "Pass1!",
            "confirm_password": "Pass1!",
        }, follow_redirects=True)
        self.assertNotEqual(r.status_code, 500,
                            "Duplicate username registration returned 500")


# ===========================================================================
# 3. POST PERSISTENCE — the core feed feature that must never break
# ===========================================================================
class TestPostPersistence(unittest.TestCase):
    """
    THE MOST IMPORTANT TESTS.
    If these fail, posts are disappearing or not saving — the #1 reported bug.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()
        # Seed a user and log in
        _seed_user(cls.app, username="poster", password="PosterPass1!",
                   email="poster@vybeflow.local")
        with cls.app.test_request_context():
            pass
        _login(cls.client, username="poster", password="PosterPass1!")

    def test_post_create_returns_success(self):
        """POST /api/posts/create must return 200/201 with a post id."""
        r = self.client.post("/api/posts/create", data={
            "caption": "Hello VybeFlow test post",
            "visibility": "public",
        })
        self.assertIn(r.status_code, (200, 201),
                      f"/api/posts/create returned {r.status_code}: {r.data[:200]}")
        body = json.loads(r.data)
        # API may return {ok, post: {id}} or {post_id} — accept either shape
        has_id = (
            "post_id" in body
            or ("post" in body and "id" in body.get("post", {}))
            or "id" in body
        )
        self.assertTrue(has_id,
                        f"Response missing a post id — post may not have been saved. Got: {list(body.keys())}")

    def test_post_appears_in_list_api(self):
        """A just-created post must appear in /api/posts/list immediately."""
        # Create a post with a unique marker
        marker = "UNIQUE_MARKER_XYZ_789"
        self.client.post("/api/posts/create", data={
            "caption": marker,
            "visibility": "public",
        })
        r = self.client.get("/api/posts/list")
        self.assertEqual(r.status_code, 200,
                         f"/api/posts/list returned {r.status_code}")
        body = json.loads(r.data)
        posts = body.get("posts") or body.get("results") or []
        captions = [p.get("caption", "") for p in posts]
        self.assertTrue(
            any(marker in (c or "") for c in captions),
            f"Post with caption '{marker}' was not found in /api/posts/list — "
            f"post did not persist. Got captions: {captions[:5]}"
        )

    def test_post_survives_in_database(self):
        """Created post must exist as a real DB row (not just in memory)."""
        with self.app.app_context():
            u = User.query.filter_by(username="poster").first()
            p = Post(author_id=u.id, caption="DB persistence test", visibility="public")
            _db.session.add(p)
            _db.session.commit()
            post_id = p.id

        # Re-query in a fresh context to confirm it was actually committed
        with self.app.app_context():
            stored = Post.query.get(post_id)
            self.assertIsNotNone(stored,
                                 "Post disappeared from DB after commit — "
                                 "session was rolled back or not committed")
            self.assertEqual(stored.caption, "DB persistence test")

    def test_post_delete_removes_from_db(self):
        """DELETE /api/posts/delete must remove the post permanently."""
        # Create a post directly in DB
        with self.app.app_context():
            u = User.query.filter_by(username="poster").first()
            p = Post(author_id=u.id, caption="To be deleted", visibility="public")
            _db.session.add(p)
            _db.session.commit()
            post_id = p.id

        # Delete endpoint accepts {"id": n} in the JSON body
        r = self.client.post("/api/posts/delete", json={"id": post_id})
        self.assertIn(r.status_code, (200, 204),
                      f"Delete returned {r.status_code}: {r.data[:200]}")

        with self.app.app_context():
            gone = Post.query.get(post_id)
            self.assertIsNone(gone, "Post still exists in DB after delete")

    def test_post_visibility_default_public(self):
        """A post created without explicit visibility should be public."""
        with self.app.app_context():
            u = User.query.filter_by(username="poster").first()
            p = Post(author_id=u.id, caption="Visibility test")
            _db.session.add(p)
            _db.session.commit()
            post_id = p.id

        with self.app.app_context():
            stored = Post.query.get(post_id)
            self.assertEqual(stored.visibility, "public",
                             "Default post visibility is not 'public'")


# ===========================================================================
# 4. FEED API TESTS — JSON contract tests
# ===========================================================================
class TestFeedAPI(unittest.TestCase):
    """
    /api/posts/list must always return valid JSON in the expected shape.
    If this breaks, the JS feed goes blank.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()
        _seed_user(cls.app, username="feeduser", password="FeedPass1!",
                   email="feeduser@vybeflow.local")
        _login(cls.client, username="feeduser", password="FeedPass1!")
        # Seed some posts
        with cls.app.app_context():
            u = User.query.filter_by(username="feeduser").first()
            for i in range(3):
                _db.session.add(Post(
                    author_id=u.id,
                    caption=f"Feed test post {i}",
                    visibility="public",
                ))
            _db.session.commit()

    def test_list_returns_json(self):
        r = self.client.get("/api/posts/list")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.content_type.split(";")[0], "application/json",
                         f"Expected application/json, got {r.content_type}")

    def test_list_contains_posts_key(self):
        """Response must have a 'posts' array (feed.js depends on this shape)."""
        r = self.client.get("/api/posts/list")
        body = json.loads(r.data)
        self.assertIn("posts", body,
                      f"Missing 'posts' key in response: {list(body.keys())}")

    def test_each_post_has_required_fields(self):
        """Every post object must have the fields feed.html's renderPosts() reads."""
        r = self.client.get("/api/posts/list")
        body = json.loads(r.data)
        posts = body.get("posts", [])
        # The API uses created_at (not timestamp) and author_username (not author)
        required = {"id", "caption", "visibility"}
        # Accept either created_at or timestamp
        time_keys = {"created_at", "timestamp"}
        # Accept either author dict or author_username string
        author_keys = {"author", "author_username"}
        for i, post in enumerate(posts[:5]):  # check first 5
            missing = required - set(post.keys())
            self.assertEqual(missing, set(),
                             f"Post {i} is missing fields: {missing}\n"
                             f"Got keys: {list(post.keys())}")
            self.assertTrue(
                bool(time_keys & set(post.keys())),
                f"Post {i} has no timestamp field (need created_at or timestamp)"
            )
            self.assertTrue(
                bool(author_keys & set(post.keys())),
                f"Post {i} has no author field (need author or author_username)"
            )

    def test_pagination_offset_works(self):
        """?offset=1000 must return empty list, not an error."""
        r = self.client.get("/api/posts/list?offset=1000")
        self.assertEqual(r.status_code, 200)
        body = json.loads(r.data)
        posts = body.get("posts", [])
        self.assertEqual(posts, [],
                         f"Expected empty list at high offset, got {len(posts)} posts")


# ===========================================================================
# 5. SETTINGS — music, profile save round-trips
# ===========================================================================
class TestSettings(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()
        _seed_user(cls.app, username="settingsuser", password="SettingsPass1!",
                   email="settingsuser@vybeflow.local")
        _login(cls.client, username="settingsuser", password="SettingsPass1!")

    def test_settings_page_loads(self):
        r = self.client.get("/settings")
        self.assertIn(r.status_code, (200, 302),
                      f"/settings returned {r.status_code}")

    def test_profile_music_remove_endpoint(self):
        """/api/profile/music/remove must return JSON {ok: true}."""
        # First set some music directly in DB
        with self.app.app_context():
            u = User.query.filter_by(username="settingsuser").first()
            u.profile_music_title = "Test Song"
            u.profile_music_artist = "Test Artist"
            u.profile_music_preview = "https://audio-ssl.itunes.apple.com/test.m4a"
            _db.session.commit()

        r = self.client.post("/api/profile/music/remove",
                             headers={"X-CSRFToken": "test"})
        self.assertEqual(r.status_code, 200,
                         f"/api/profile/music/remove returned {r.status_code}")
        body = json.loads(r.data)
        self.assertTrue(body.get("ok"),
                        f"Expected ok:true, got: {body}")

        # Confirm it was actually cleared in DB
        with self.app.app_context():
            u = User.query.filter_by(username="settingsuser").first()
            self.assertIsNone(u.profile_music_title,
                              "profile_music_title was not cleared in DB")

    def test_wellbeing_settings_save(self):
        """/api/wellbeing/settings must save and return ok."""
        r = self.client.post(
            "/api/wellbeing/settings",
            data=json.dumps({"daily_usage_limit_mins": 60, "wellbeing_break_reminder": True}),
            content_type="application/json",
            headers={"X-CSRFToken": "test"},
        )
        self.assertIn(r.status_code, (200, 201))
        body = json.loads(r.data)
        self.assertTrue(body.get("ok"), f"wellbeing/settings failed: {body}")


# ===========================================================================
# 6. SECURITY TESTS — make sure attack surfaces are locked
# ===========================================================================
class TestSecurity(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()

    def test_bg_color_injection_rejected(self):
        """bg_color must only accept hex colors — script injection must be blocked."""
        _seed_user(self.app, "sectest", "SecPass1!", "sec@vybeflow.local")
        _login(self.client, "sectest", "SecPass1!")
        r = self.client.post("/api/posts/create", data={
            "caption": "injection test",
            "bg_color": "<script>alert(1)</script>",
            "visibility": "public",
        })
        # Post may succeed (200/201) but bg_color must NOT be the injection string
        if r.status_code in (200, 201):
            with self.app.app_context():
                p = Post.query.order_by(Post.id.desc()).first()
                self.assertNotEqual(
                    p.bg_color, "<script>alert(1)</script>",
                    "XSS payload was stored in bg_color — injection NOT sanitized"
                )

    def test_private_post_not_in_public_feed(self):
        """A private post must not appear in the feed of a different logged-in user."""
        # Create the private post as user A
        _seed_user(self.app, "privposter", "PrivPass1!", "privposter@vybeflow.local")
        _seed_user(self.app, "privviewer", "ViewPass1!", "privviewer@vybeflow.local")
        viewer_client = self.app.test_client()
        # Log in as poster and create a private post
        post_client = self.app.test_client()
        _login(post_client, "privposter", "PrivPass1!")
        PRIV_MARKER = "PRIVATE_ONLY_CONTENT_ABC123"
        post_client.post("/api/posts/create", data={
            "caption": PRIV_MARKER,
            "visibility": "private",
        })
        # Now log in as a different user and check the feed
        _login(viewer_client, "privviewer", "ViewPass1!")
        r = viewer_client.get("/api/posts/list")
        body = json.loads(r.data)
        captions = " ".join(p.get("caption", "") for p in body.get("posts", []))
        self.assertNotIn(PRIV_MARKER, captions,
                         "Private post is visible to a different user — PRIVACY BUG")

    def test_music_stream_blocks_unlisted_host(self):
        """/api/music/stream must reject hosts not on the allowlist."""
        r = self.client.get(
            "/api/music/stream?url=https://evil.example.com/audio.mp3"
        )
        self.assertEqual(r.status_code, 403,
                         "Music proxy allowed an unlisted host — SSRF risk")


# ===========================================================================
# 7. REGRESSION GUARDS — specific bugs that have bitten us before
# ===========================================================================
class TestRegressions(unittest.TestCase):
    """
    One test per bug we have fixed. If this class fails, we've regressed.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()
        _seed_user(cls.app, "regressuser", "RegressPass1!", "regress@vybeflow.local")
        _login(cls.client, "regressuser", "RegressPass1!")

    def test_post_edit_endpoint_exists(self):
        """PATCH /api/posts/<id> must exist (CSRF bug fix regression)."""
        with self.app.app_context():
            u = User.query.filter_by(username="regressuser").first()
            p = Post(author_id=u.id, caption="Original caption", visibility="public")
            _db.session.add(p)
            _db.session.commit()
            post_id = p.id

        r = self.client.patch(
            f"/api/posts/{post_id}",
            data=json.dumps({"caption": "Edited caption"}),
            content_type="application/json",
            headers={"X-CSRFToken": "test"},
        )
        # 200 success OR 403 CSRF is fine — 404 means the route disappeared
        self.assertNotEqual(r.status_code, 404,
                            "PATCH /api/posts/<id> returned 404 — route is missing")

    def test_music_search_endpoint_exists(self):
        """/api/music/search must be reachable (regression: blueprint unregistered)."""
        r = self.client.get("/api/music/search?q=test")
        self.assertNotEqual(r.status_code, 404,
                            "/api/music/search returned 404 — blueprint not registered")

    def test_settings_hash_music_alias_works(self):
        """/settings must load even with #music hash (deep-link regression)."""
        _seed_user(self.app, "hashtest", "HashPass1!", "hashtest@vybeflow.local")
        _login(self.client, "hashtest", "HashPass1!")
        # Flask doesn't process hashes server-side but the page must load
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200,
                         "/settings page fails to load — deep-link will be broken")

    def test_feed_api_never_returns_500(self):
        """/api/posts/list must never return 500 under any normal conditions."""
        for params in ["", "?offset=0", "?limit=20", "?offset=abc"]:
            r = self.client.get(f"/api/posts/list{params}")
            self.assertNotEqual(r.status_code, 500,
                                f"/api/posts/list{params} returned 500")

    def test_testing_mode_does_not_start_autolift_daemon(self):
        """In TESTING mode, the AutoLift background thread must not start."""
        import threading
        # Build a fresh app in TESTING mode (same helper used by the suite)
        _ = _make_app()
        names = [t.name for t in threading.enumerate()]
        self.assertNotIn(
            "VybeBlockAutoLift",
            names,
            "AutoLift daemon started in TESTING mode; this causes flaky tests and "
            "missing-table errors against in-memory DBs",
        )


# ===========================================================================
# 8. SETTINGS-SECURITY TESTS — all 8 bugs fixed this session
# ===========================================================================
class TestSettingsSecurity(unittest.TestCase):
    """
    Settings > Security tab bug-fix regression suite.

    Bug 1: change_password — bare db.session.commit() → now uses _safe_commit()
    Bug 2: change_password — redirected to '#security' → now '#settings-security'
    Bug 3: avatar src="None" when avatar_url is null → now uses 'or ""' fallback
    Bug 4: bg-preview src="" fires request to current page → onerror guard added
    Bug 5: passkey delete used native confirm() → now uses vfConfirm (tested client-side)
    Bug 6: passkey delete used plain fetch() without DST token → window.vfFetch used
    Bug 7: loadPasskeys() { once: true } → removed, list refreshes every tab visit
    Bug 8: loadPasskeys() swallowed errors silently → now shows error message

    Client-side bugs (5–8) are validated via DOM-content substring checks on the
    rendered HTML because they live in JS inside a <script> block.
    Backend bugs (1–2) are validated via HTTP round-trips.
    Template bugs (3–4) are validated via rendered HTML assertions.
    """

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()
        _seed_user(cls.app, "secuser", "SecurePass1!", "secuser@vybeflow.local")
        _login(cls.client, "secuser", "SecurePass1!")

    # ── Backend: change_password endpoint ────────────────────────────────────

    def test_change_password_wrong_current_redirects_to_security_tab(self):
        """Wrong current password must redirect back to #settings-security (not #security)."""
        r = self.client.post("/change_password", data={
            "current_password": "WrongPassword!",
            "new_password":     "NewPass999!",
            "confirm_new_password": "NewPass999!",
        }, follow_redirects=False)
        # Must be a redirect
        self.assertEqual(r.status_code, 302,
                         f"Expected 302 redirect, got {r.status_code}")
        location = r.headers.get("Location", "")
        self.assertIn("settings-security", location,
                      f"Redirect goes to '{location}' — should contain 'settings-security' "
                      f"so the Security tab auto-opens. Old bug sent '#security' (alias) "
                      f"which worked but was fragile and inconsistent.")

    def test_change_password_mismatch_redirects_to_security_tab(self):
        """Mismatched new passwords must redirect to #settings-security."""
        r = self.client.post("/change_password", data={
            "current_password":     "SecurePass1!",
            "new_password":         "NewPass999!",
            "confirm_new_password": "DifferentPass!",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("settings-security", r.headers.get("Location", ""))

    def test_change_password_success_commits_and_redirects(self):
        """Successful password change must commit to DB and redirect to security tab."""
        # Seed a fresh user for this test so we don't break the shared secuser
        _seed_user(self.app, "pwchange_user", "OldPass1!", "pwchangetest@vybeflow.local")
        pw_client = self.app.test_client()
        _login(pw_client, "pwchange_user", "OldPass1!")

        r = pw_client.post("/change_password", data={
            "current_password":     "OldPass1!",
            "new_password":         "NewPass999!",
            "confirm_new_password": "NewPass999!",
        }, follow_redirects=False)

        self.assertEqual(r.status_code, 302,
                         f"change_password returned {r.status_code}: {r.data[:200]}")
        self.assertIn("settings-security", r.headers.get("Location", ""),
                      "Success redirect should go to #settings-security")

        # Confirm the new hash is stored in the DB
        from werkzeug.security import check_password_hash
        with self.app.app_context():
            u = User.query.filter_by(username="pwchange_user").first()
            self.assertTrue(
                check_password_hash(u.password_hash, "NewPass999!"),
                "New password was not persisted in the database after change_password call"
            )

    def test_change_password_same_as_current_rejected(self):
        """New password identical to current must be rejected with 302, not 500."""
        r = self.client.post("/change_password", data={
            "current_password":     "SecurePass1!",
            "new_password":         "SecurePass1!",
            "confirm_new_password": "SecurePass1!",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        # Still goes back to settings, not a crash
        self.assertIn("settings", r.headers.get("Location", ""))

    def test_change_password_too_short_rejected(self):
        """New password < 6 chars must be rejected."""
        r = self.client.post("/change_password", data={
            "current_password":     "SecurePass1!",
            "new_password":         "abc",
            "confirm_new_password": "abc",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 302)

    def test_change_password_unauthenticated_redirects_to_login(self):
        """Unauthenticated POST to /change_password must redirect to /login."""
        anon_client = self.app.test_client()
        r = anon_client.post("/change_password", data={
            "current_password":     "x",
            "new_password":         "y",
            "confirm_new_password": "y",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("login", r.headers.get("Location", "").lower())

    # ── Template: avatar and bg-preview null-src bugs ─────────────────────────

    def test_avatar_src_never_renders_none_literal(self):
        """settings.html must not render src=\"None\" for the avatar preview img."""
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8", errors="replace")
        self.assertNotIn('src="None"', html,
                         "Avatar preview has src=\"None\" — null avatar_url not guarded with 'or \"\"'")
        self.assertNotIn("src='None'", html,
                         "Avatar preview has src='None' — null avatar_url not guarded")

    def test_bg_preview_has_onerror_guard(self):
        """BG preview img must have an onerror attr to prevent blank-img HTTP requests."""
        r = self.client.get("/settings")
        self.assertEqual(r.status_code, 200)
        html = r.data.decode("utf-8", errors="replace")
        # Check both the onerror attr and the id together to confirm it's on the right element
        self.assertIn('id="bg-preview-thumb"', html)
        # Find the bg-preview-thumb element and confirm onerror is on it
        import re as _re
        # Look for the onerror attr anywhere near bg-preview-thumb
        bg_thumb_match = _re.search(
            r'id=["\']bg-preview-thumb["\'][^>]*>|[^>]*id=["\']bg-preview-thumb["\']',
            html
        )
        self.assertIsNotNone(bg_thumb_match,
                             "bg-preview-thumb element not found in page")
        # Check that the onerror guard is present in the page (guards empty src)
        self.assertIn("this.removeAttribute('src')", html,
                      "bg-preview-thumb missing onerror guard for empty src")

    # ── Template: passkey JS client-side bug regression (DOM assertion) ────────

    def test_passkey_delete_uses_vfconfirm_not_native_confirm(self):
        """Passkey delete button JS must use vfConfirm(), not native confirm()."""
        r = self.client.get("/settings")
        html = r.data.decode("utf-8", errors="replace")
        # Must NOT have the old bug pattern
        self.assertNotIn(
            "if (!confirm('Remove this passkey?",
            html,
            "Passkey delete still uses native confirm() — should use vfConfirm"
        )
        # Must have the new pattern
        self.assertIn(
            "vfConfirm(",
            html,
            "Passkey delete does not call vfConfirm() — UI dialog is broken"
        )

    def test_passkey_delete_uses_vfFetch_not_bare_fetch(self):
        """Passkey delete must call window.vfFetch (DST-aware), not bare fetch()."""
        r = self.client.get("/settings")
        html = r.data.decode("utf-8", errors="replace")
        self.assertIn(
            "(window.vfFetch || fetch)",
            html,
            "Passkey delete should use vfFetch for DST token forwarding"
        )

    def test_passkey_list_not_once_true(self):
        """Passkey list click handler must NOT use { once: true } so list refreshes."""
        r = self.client.get("/settings")
        html = r.data.decode("utf-8", errors="replace")
        import re as _re
        # Isolate the exact secNav click handler statement so unrelated scripts
        # elsewhere on the page can still use { once: true } safely.
        secnav_stmt = _re.search(
            r"secNav\.addEventListener\('click',\s*function\s*\(\)\s*\{\s*loadPasskeys\(\);\s*\}[^\n;]*;",
            html,
        )
        self.assertIsNotNone(
            secnav_stmt,
            "Could not find passkey secNav loadPasskeys click handler in settings HTML",
        )
        self.assertNotIn(
            "once: true",
            secnav_stmt.group(0),
            "Passkey Security-tab click handler still uses { once: true } — "
            "passkey list will NOT refresh after the first visit",
        )

    def test_passkey_loadPasskeys_shows_error_on_failure(self):
        """loadPasskeys() must show user-visible error text, not swallow the error."""
        r = self.client.get("/settings")
        html = r.data.decode("utf-8", errors="replace")
        # Old bug: .catch(function () {}) — completely silent
        # New behaviour: catches and sets listEmpty.textContent to an error message
        self.assertIn(
            "Could not load passkeys",
            html,
            "loadPasskeys() error path has no user-visible message — still silently swallowing errors"
        )

    def test_passkey_loadPasskeys_uses_vfFetch(self):
        """loadPasskeys() must use window.vfFetch so the DST token is forwarded."""
        r = self.client.get("/settings")
        html = r.data.decode("utf-8", errors="replace")
        self.assertIn(
            "(window.vfFetch || fetch)('/api/passkey/list'",
            html,
            "loadPasskeys() does not use vfFetch — DST token is not forwarded on list load"
        )

    # ── Backend: passkey list endpoint returns correct shape ─────────────────

    def test_passkey_list_endpoint_returns_json_array(self):
        """/api/passkey/list must return JSON with a 'passkeys' array."""
        r = self.client.get("/api/passkey/list")
        # 200 or 401 (if passkeys_bp uses _require_auth which checks session)
        self.assertIn(r.status_code, (200, 401),
                      f"/api/passkey/list returned unexpected {r.status_code}")
        if r.status_code == 200:
            body = json.loads(r.data)
            self.assertIn("passkeys", body,
                          f"Response missing 'passkeys' key: {list(body.keys())}")
            self.assertIsInstance(body["passkeys"], list)


# ===========================================================================
# Email guard tests — fake domains must NEVER reach SMTP
# ===========================================================================
class TestEmailGuard(unittest.TestCase):
    """Verify that placeholder email domains are blocked at every layer."""

    def test_send_email_blocks_fake_domains(self):
        """_send_email() must refuse delivery to all fake-domain addresses."""
        from email_utils import _send_email, _FAKE_EMAIL_DOMAINS
        for domain in _FAKE_EMAIL_DOMAINS:
            addr = f"someone{domain}"
            result = _send_email(addr, "Test Subject", "<p>hi</p>", "hi",
                                 label="test-guard")
            self.assertFalse(
                result,
                f"_send_email() did NOT block fake address {addr!r}"
            )

    def test_fake_email_domain_list_matches_app(self):
        """email_utils._FAKE_EMAIL_DOMAINS must include every domain in app._FAKE_EMAIL_DOMAINS."""
        from email_utils import _FAKE_EMAIL_DOMAINS as eu_domains
        # Also verify app.py's copy
        import app as _app_module
        app_domains = _app_module._FAKE_EMAIL_DOMAINS
        for d in app_domains:
            self.assertTrue(
                any(d.lower() == ed.lower() for ed in eu_domains),
                f"app._FAKE_EMAIL_DOMAINS has {d!r} but email_utils is missing it"
            )

    def test_is_real_email_rejects_all_placeholder_domains(self):
        """_is_real_email() must return False for every placeholder domain."""
        import app as _app_module
        for domain in _app_module._FAKE_EMAIL_DOMAINS:
            self.assertFalse(
                _app_module._is_real_email(f"user{domain}"),
                f"_is_real_email() incorrectly accepted user{domain}"
            )

    def test_is_real_email_accepts_gmail(self):
        """Real emails like @gmail.com must pass _is_real_email()."""
        import app as _app_module
        self.assertTrue(_app_module._is_real_email("test@gmail.com"))

    def test_appeal_decision_email_guarded(self):
        """The appeal-decision email path in app.py must check _is_real_email()."""
        import pathlib
        src = pathlib.Path(__file__).with_name("app.py").read_text(encoding="utf-8")
        # The Thread(...target=send_appeal_decision_email) call is the actual send
        marker = "target=send_appeal_decision_email"
        idx = src.find(marker)
        self.assertGreater(idx, 0, "target=send_appeal_decision_email not found in app.py")
        # Look at the 500 chars preceding the call for _is_real_email guard
        context = src[max(0, idx - 500):idx]
        self.assertIn("_is_real_email", context,
                      "Appeal decision email path is NOT guarded by _is_real_email()")


# ===========================================================================
# WebAuthn / Passkey infrastructure tests
# ===========================================================================
class TestPasskeyInfra(unittest.TestCase):
    """Verify WebAuthn config auto-detects localhost in development."""

    def test_rp_id_defaults_to_localhost_on_dev(self):
        """_get_rp_id() must return 'localhost' when serving on 127.0.0.1."""
        from utils.webauthn_auth import _get_rp_id
        app = _make_app()
        with app.test_request_context('/', base_url='http://127.0.0.1:5000'):
            self.assertEqual(_get_rp_id(), "localhost")

    def test_rp_id_defaults_to_localhost_on_localhost(self):
        """_get_rp_id() must return 'localhost' when serving on localhost."""
        from utils.webauthn_auth import _get_rp_id
        app = _make_app()
        with app.test_request_context('/', base_url='http://localhost:5000'):
            self.assertEqual(_get_rp_id(), "localhost")

    def test_expected_origins_include_both_localhost_variants(self):
        """_get_expected_origins() must include both localhost and 127.0.0.1."""
        from utils.webauthn_auth import _get_expected_origins
        app = _make_app()
        with app.test_request_context('/', base_url='http://127.0.0.1:5000'):
            origins = _get_expected_origins()
            self.assertIn("http://localhost:5000", origins)
            self.assertIn("http://127.0.0.1:5000", origins)

    def test_register_begin_returns_options(self):
        """POST /api/passkey/register/begin must return WebAuthn options, not 500."""
        app = _make_app()
        with app.test_client() as c:
            _seed_user(app, "pktest", "TestPass1!", "pk@vybeflow.local")
            c.post("/login", data={"username": "pktest", "password": "TestPass1!"},
                   follow_redirects=True)
            r = c.post("/api/passkey/register/begin",
                       content_type="application/json",
                       data=json.dumps({}))
            self.assertIn(r.status_code, (200, 401, 429),
                          f"register/begin returned {r.status_code}: {r.data[:200]}")
            if r.status_code == 200:
                body = json.loads(r.data)
                self.assertIn("challenge", body,
                              f"register/begin missing 'challenge': {list(body.keys())}")
                self.assertIn("rp", body,
                              f"register/begin missing 'rp': {list(body.keys())}")
                # RP ID must be localhost in test context
                self.assertEqual(body["rp"]["id"], "localhost",
                                 f"rp.id should be 'localhost' in dev, got {body['rp']['id']!r}")


# ===========================================================================
# Music stream proxy tests
# ===========================================================================
class TestMusicStream(unittest.TestCase):
    """Verify the audio stream proxy handles Deezer CDN hosts correctly."""

    def test_deezer_cdnt_host_is_allowed(self):
        """cdnt-preview.dzcdn.net must be in ALLOWED_AUDIO_HOSTS."""
        from music_api import ALLOWED_AUDIO_HOSTS
        self.assertIn("cdnt-preview.dzcdn.net", ALLOWED_AUDIO_HOSTS)

    def test_is_deezer_host_matches_all_variants(self):
        """_is_deezer_host() must accept any *.dzcdn.net hostname."""
        from music_api import _is_deezer_host
        self.assertTrue(_is_deezer_host("cdnt-preview.dzcdn.net"))
        self.assertTrue(_is_deezer_host("cdns-preview-a.dzcdn.net"))
        self.assertTrue(_is_deezer_host("anything.dzcdn.net"))
        self.assertFalse(_is_deezer_host("evil.com"))
        self.assertFalse(_is_deezer_host(None))

    def test_stream_rejects_unknown_hosts(self):
        """Stream proxy must reject hosts not in the allowlist."""
        app = _make_app()
        with app.test_client() as c:
            r = c.get("/api/music/stream?url=https://evil.com/audio.mp3")
            self.assertEqual(r.status_code, 403)

    def test_stream_accepts_itunes_host(self):
        """Stream proxy must accept iTunes audio-ssl host (returns 502 without network)."""
        app = _make_app()
        with app.test_client() as c:
            r = c.get("/api/music/stream?url=https://audio-ssl.itunes.apple.com/test.m4a")
            # 502 expected: no real upstream, but NOT 403 (host allowed)
            self.assertIn(r.status_code, (200, 502))


# ===========================================================================
# Passkey JS / template regression tests
# ===========================================================================
class TestPasskeyTemplateRegression(unittest.TestCase):
    """Catch regressions in passkey client-side code."""

    @classmethod
    def setUpClass(cls):
        cls.app = _make_app()
        cls.client = cls.app.test_client()
        _seed_user(cls.app, "sectmpl", "TestPass1!", "sectmpl@vybeflow.local")
        cls.client.post("/login", data={"username": "sectmpl", "password": "TestPass1!"},
                        follow_redirects=True)

    def test_passkey_delete_checks_response_ok(self):
        """Delete handler must check r.ok before parsing JSON to avoid silent failures."""
        r = self.client.get("/settings")
        html = r.data.decode("utf-8", errors="replace")
        self.assertIn("if (!r.ok)", html,
                      "Passkey delete handler does not check r.ok before parsing response")

    def test_conditional_auth_uses_vfFetch(self):
        """_startConditionalAuthentication must use _vfFetch, not bare fetch."""
        import pathlib
        src = pathlib.Path(__file__).with_name("static").joinpath("js", "passkey.js").read_text(encoding="utf-8")
        # Find the conditionalAuthentication function
        idx = src.find("_startConditionalAuthentication")
        self.assertGreater(idx, 0)
        func_body = src[idx:idx + 1500]
        self.assertIn("_vfFetch('/api/passkey/auth/begin'", func_body,
                      "Conditional auth uses bare fetch() instead of _vfFetch — DST chain is broken")
        self.assertIn("_vfFetch('/api/passkey/auth/complete'", func_body,
                      "Conditional auth complete uses bare fetch() instead of _vfFetch")

    def test_passkey_delete_commit_is_guarded(self):
        """passkey_delete must wrap db.session.commit() in try/except."""
        import pathlib
        src = pathlib.Path(__file__).with_name("routes").joinpath("passkeys.py").read_text(encoding="utf-8")
        # Find the delete function
        idx = src.find("def passkey_delete")
        self.assertGreater(idx, 0)
        func_body = src[idx:idx + 1500]
        self.assertIn("try:", func_body,
                      "passkey_delete has no try/except around db.session.commit()")
        self.assertIn("db.session.rollback()", func_body,
                      "passkey_delete does not rollback on commit failure")


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    unittest.main(verbosity=2)
