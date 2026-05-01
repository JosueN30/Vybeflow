import os
from flask import Flask
from flask_migrate import Migrate

from models import db
import models  # noqa: F401 - ensure model metadata is loaded


app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///vybeflow.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False


db.init_app(app)
migrate = Migrate(app, db)
