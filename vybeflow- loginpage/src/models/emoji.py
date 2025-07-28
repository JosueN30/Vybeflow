class Emoji(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    emoji_character = db.Column(db.String(10), nullable=False)

    user = db.relationship('User', backref=db.backref('emojis', lazy=True))

    def __repr__(self):
        return f"<Emoji {self.emoji_character}>"