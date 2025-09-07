#!/bin/bash
# VybeFlow Production Startup Script

echo "🚀 Starting VybeFlow in Production Mode..."

# Set environment variables for production
export FLASK_ENV=production
export FLASK_DEBUG=0

# Optional: Set your own secret key (recommended)
# export SECRET_KEY="your-super-secret-production-key-here"

# Optional: Set database URL if using external database
# export DATABASE_URL="postgresql://user:pass@localhost/vybeflow"

# Optional: Set mail server credentials
# export MAIL_SERVER="smtp.gmail.com"
# export MAIL_USERNAME="your-email@gmail.com"
# export MAIL_PASSWORD="your-app-password"

# Create necessary directories
mkdir -p static/uploads
mkdir -p instance

# Start Gunicorn with production settings
echo "📡 Starting Gunicorn server on http://0.0.0.0:8000"
echo "🌐 Your VybeFlow app will be available at:"
echo "   - Local: http://127.0.0.1:8000"
echo "   - Network: http://$(hostname -I | awk '{print $1}'):8000"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

gunicorn --config gunicorn.conf.py wsgi:app
