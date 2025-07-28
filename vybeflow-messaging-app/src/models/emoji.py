from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Emoji(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    unicode = db.Column(db.String(10), nullable=False)

    def __repr__(self):
        return f"<Emoji {self.name} ({self.unicode})>"

    @staticmethod
    def add_emoji(name, unicode):
        new_emoji = Emoji(name=name, unicode=unicode)
        db.session.add(new_emoji)
        db.session.commit()

    @staticmethod
    def edit_emoji(emoji_id, name=None, unicode=None):
        emoji = Emoji.query.get(emoji_id)
        if emoji:
            if name:
                emoji.name = name
            if unicode:
                emoji.unicode = unicode
            db.session.commit()

    @staticmethod
    def delete_emoji(emoji_id):
        emoji = Emoji.query.get(emoji_id)
        if emoji:
            db.session.delete(emoji)
            db.session.commit()