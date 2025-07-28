from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'supersecretkey'

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'

from routes import auth, messaging, emoji

app.register_blueprint(auth.bp)
app.register_blueprint(messaging.bp)
app.register_blueprint(emoji.bp)

if __name__ == "__main__":
    db.create_all()
    app.run(debug=True)