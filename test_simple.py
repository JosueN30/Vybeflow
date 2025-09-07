#!/usr/bin/env python3
"""Simplified VybeFlow startup to isolate issues"""

import os
from flask import Flask

# Simple test Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-key'

@app.route('/')
def test_home():
    return "VybeFlow Test - Basic Flask is working!"

@app.route('/test')
def test_route():
    return "Test route is working!"

if __name__ == '__main__':
    print("Starting simplified VybeFlow test...")
    app.run(debug=True, host='0.0.0.0', port=5000)
