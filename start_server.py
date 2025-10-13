
import os
import sys
import subprocess

# Quick test to start server
if __name__ == "__main__":
    print("Starting Flask application via WSGI configuration (wsgi.py)...")
    try:
        # FIX: Use subprocess to correctly and reliably execute the WSGI entry point
        subprocess.run([sys.executable, "wsgi.py"])
    except FileNotFoundError:
        print("Error: wsgi.py not found or Python interpreter failed to start.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
