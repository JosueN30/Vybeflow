from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), nullable=False, unique=True)
    email = db.Column(db.String(150), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)
    custom_emojis = db.relationship('Emoji', backref='owner', lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"

    def add_custom_emoji(self, emoji):
        self.custom_emojis.append(emoji)
        db.session.commit()