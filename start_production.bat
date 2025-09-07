@echo off
REM VybeFlow Production Startup Script for Windows

echo 🚀 Starting VybeFlow in Production Mode...

REM Set environment variables for production
set FLASK_ENV=production
set FLASK_DEBUG=0

REM Optional: Set your own secret key (recommended)
REM set SECRET_KEY=your-super-secret-production-key-here

REM Optional: Set database URL if using external database
REM set DATABASE_URL=postgresql://user:pass@localhost/vybeflow

REM Optional: Set mail server credentials
REM set MAIL_SERVER=smtp.gmail.com
REM set MAIL_USERNAME=your-email@gmail.com
REM set MAIL_PASSWORD=your-app-password

REM Create necessary directories
if not exist "static\uploads" mkdir "static\uploads"
if not exist "instance" mkdir "instance"

echo 📡 Starting Gunicorn server on http://0.0.0.0:8000
echo 🌐 Your VybeFlow app will be available at:
echo    - Local: http://127.0.0.1:8000
echo    - Network: http://10.0.0.249:8000
echo.
echo Press Ctrl+C to stop the server
echo.

gunicorn --config gunicorn.conf.py wsgi:app
