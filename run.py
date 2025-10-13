#!/usr/bin/env python3
"""
VybeFlow Application Runner
"""

from __init__ import create_app

# Create the Flask application using the factory pattern
app = create_app()

if __name__ == '__main__':
    # Run the application in debug mode for development
    app.run(debug=True, host='127.0.0.1', port=5000)