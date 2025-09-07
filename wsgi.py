#!/usr/bin/env python3
"""
WSGI entry point for VybeFlow production deployment
"""

import os
import sys

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(__file__))

from VybeFlowapp import app

# Production configuration
app.config.update(
    # Security settings for production
    SECRET_KEY=os.environ.get('SECRET_KEY', os.urandom(24)),
    
    # Database
    SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL', 'sqlite:///vybeflow.db'),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    
    # Session security
    SESSION_COOKIE_SECURE=True,  # Set to True for HTTPS
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_SECURE=True,  # Set to True for HTTPS
    
    # File uploads
    MAX_CONTENT_LENGTH=16 * 1024 * 1024,  # 16MB max upload
    UPLOAD_FOLDER=os.path.join(os.path.dirname(__file__), 'static', 'uploads'),
    
    # Mail settings (update with your actual mail server)
    MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
    MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME', 'vybeflow@gmail.com'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD', 'yourpassword'),
    MAIL_DEFAULT_SENDER=os.environ.get('MAIL_DEFAULT_SENDER', 'vybeflow@gmail.com'),
)

# Create upload directory if it doesn't exist
try:
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
except FileExistsError:
    pass  # Directory already exists

# Initialize database tables
with app.app_context():
    from VybeFlowapp import db
    db.create_all()

if __name__ == "__main__":
    # Production: do not use debug mode
    app.run(host="0.0.0.0", port=8000, debug=False)

# For Gunicorn: run with
#   gunicorn -w 4 -b 0.0.0.0:8000 wsgi:app
#
# For Nginx reverse proxy, use a config like:
#
# server {
#     listen 443 ssl;
#     server_name yourdomain.com;
#     ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
#     ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
#     location / {
#         proxy_pass http://127.0.0.1:8000;
#         proxy_set_header Host $host;
#         proxy_set_header X-Real-IP $remote_addr;
#         proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
#         proxy_set_header X-Forwarded-Proto $scheme;
#     }
# }
