import pytest
from flask import session
from VybeFlowapp import app, db, User

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False  # Disable CSRF for test POSTs
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.session.remove()
            db.drop_all()

def register(client, username, email, password):
    return client.post('/register', data={
        'username': username,
        'email': email,
        'password': password,
        'password2': password
    }, follow_redirects=True)

def login(client, username, password):
    return client.post('/login', data={
        'username': username,
        'password': password
    }, follow_redirects=True)

def logout(client):
    return client.get('/logout', follow_redirects=True)

def test_register_login_logout(client):
    # Register
    rv = register(client, 'testuser', 'test@example.com', 'TestPassword123')
    assert b'Registration successful' in rv.data
    # Login
    rv = login(client, 'testuser', 'TestPassword123')
    assert b'feed' in rv.data or b'Welcome' in rv.data
    # Session should have user_id
    with client.session_transaction() as sess:
        assert 'user_id' in sess
    # Logout
    rv = logout(client)
    assert b'Logged out successfully' in rv.data
    with client.session_transaction() as sess:
        assert 'user_id' not in sess

def test_csrf_protection(client):
    app.config['WTF_CSRF_ENABLED'] = True
    # Try POST without CSRF token
    rv = client.post('/register', data={
        'username': 'csrfuser',
        'email': 'csrf@example.com',
        'password': 'TestPassword123',
        'password2': 'TestPassword123'
    })
    assert rv.status_code == 400 or b'CSRF' in rv.data

def test_protected_route_requires_login(client):
    rv = client.get('/feed', follow_redirects=True)
    assert b'login' in rv.data or b'Sign In' in rv.data
