"""
VybeFlow — shared SQLAlchemy + Migrate instances.

The real application factory is in app.py (create_app).
All blueprints and routes import `db` from here to avoid circular imports.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

db = SQLAlchemy()
migrate = Migrate()
