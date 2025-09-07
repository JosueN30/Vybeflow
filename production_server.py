#!/usr/bin/env python3
"""
Production server startup script using Waitress (Windows-compatible)
"""

import os
import sys
from waitress import serve

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

# Import the Flask app
from wsgi import app

if __name__ == '__main__':
    print("🚀 Starting VybeFlow in Production Mode...")
    print("📡 Using Waitress WSGI Server")
    print("🌐 Your VybeFlow app will be available at:")
    print("   - Local: http://127.0.0.1:8000")
    print("   - Network: http://10.0.0.249:8000")
    print("")
    print("Press Ctrl+C to stop the server")
    print("")
    
    # Enable debug mode temporarily to see errors
    app.config['DEBUG'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = True
    
    # Serve the application
    serve(
        app,
        host='0.0.0.0',
        port=8000,
        threads=6,
        connection_limit=1000,
        cleanup_interval=30,
        channel_timeout=120,
        log_untrusted_proxy_headers=True,
        clear_untrusted_proxy_headers=True,
        url_scheme='http'
    )
