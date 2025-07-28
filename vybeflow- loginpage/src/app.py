from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from routes.auth import auth_bp
from routes.messaging import messaging_bp
from routes.emoji import emoji_bp

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///site.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "supersecretkey"

db = SQLAlchemy(app)

login_manager = LoginManager(app)
login_manager.login_view = "auth.login"

app.register_blueprint(auth_bp)
app.register_blueprint(messaging_bp)
app.register_blueprint(emoji_bp)

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)