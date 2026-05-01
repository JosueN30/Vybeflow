"""WSGI entry point for VybeFlow application.

This uses the main create_app() factory in app.py so that
the same configuration and blueprints are loaded for both
development and production.
"""

from app import create_app

app, socketio = create_app()

if __name__ == "__main__":
    # Run with SocketIO so realtime features keep working
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
