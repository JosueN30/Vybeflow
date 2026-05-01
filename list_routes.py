"""Quick route lister without starting server"""
from app import create_app

app, socketio = create_app()

print("\n=== VybeFlow Available Routes ===\n")
print(f"Total: {len(list(app.url_map.iter_rules()))} routes\n")

# Key routes
key_routes = [
    ('/', 'GET', 'Home (redirects to feed)'),
    ('/feed', 'GET', 'Main feed page'),
    ('/login', 'GET/POST', 'Login page'),
    ('/register', 'GET/POST', 'Registration page'),
    ('/api/posts', 'GET/POST', 'Posts API'),
    ('/api/games', 'GET/POST', 'Games API'),
    ('/api/story/save', 'POST', 'Story save endpoint'),
    ('/api/music/search', 'GET', 'Music search'),
]

print("KEY ROUTES:")
for path, method, desc in key_routes:
    print(f"  {method:12s} {path:30s} - {desc}")

print("\n\nTo view all routes, check the output above.")
print("\nTo start server: python app.py")
print("Server will run on: http://localhost:5000\n")
