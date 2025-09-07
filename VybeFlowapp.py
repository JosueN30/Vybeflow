
# ...existing code...



from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from functools import wraps
from datetime import datetime, timedelta
import os, io, re, json, base64, random, requests

app = Flask(__name__)

# ... (your existing code) ...

@app.route('/search')
def search():
    # This function will handle requests to the '/search' URL
    # It will render a template named search.html
    return render_template('search.html')

# ... (your other routes) ...

from flask import Flask, render_template, redirect, url_for, flash, request, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from functools import wraps
from datetime import datetime, timedelta
import os, io, re, json, base64, random, requests

app = Flask(__name__)




@app.route("/")
def home():
    return redirect(url_for('feed'))

@app.route("/feed")
def feed():
    # You might want to get user data here
    # Example:
    # current_user_username = session.get('username')
    # return render_template('feed.html', current_user_username=current_user_username)
    return render_template('feed.html')

@app.route("/messages", defaults={"username": None})
@app.route("/messages/<username>")
def messages(username=None):
    if username:
        return render_template("messages.html", username=username)
    username = session.get("username")
    if username:
        return render_template("messages.html", username=username)
    return "Messages (no username provided)"

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    password2 = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Register')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('VYBEFLOW_DB_URI', 'sqlite:///vybeflow.db')
def get_trending_users():
    # Example: return top 5 users by post count
    return User.query.order_by(db.desc(User.id)).limit(5).all()

from flask_sqlalchemy import SQLAlchemy
# Ensure login_required is defined before any use
from functools import wraps
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function
# Only keep valid code
# Only keep valid code
db = SQLAlchemy(app)

# User model definition
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Add any additional fields as needed

from flask_migrate import Migrate
migrate = Migrate(app, db)
# --- Advanced Livestream Features ---
# Live Reaction (emoji, heart, etc.)
class LiveReaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    emoji = db.Column(db.String(16), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Live Poll
# Live Poll model
class LivePollVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('live_poll.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    option = db.Column(db.String(255), nullable=False)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)
class LivePoll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    # ...existing model fields...
    question = db.Column(db.String(255), nullable=False)
    options = db.Column(db.Text, nullable=False)  # Store as JSON string
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- Gangsta/Wild N Out Features ---
    # ...existing code...

# Live Q&A
class LiveQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    question = db.Column(db.String(255), nullable=False)
    is_highlighted = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Virtual Gift
class VirtualGift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    gift_type = db.Column(db.String(32), nullable=False)  # e.g., 'coin', 'sticker', 'rose'
    amount = db.Column(db.Integer, default=1)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# Achievement/Badge
class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.String(255))
    earned_at = db.Column(db.DateTime, default=datetime.utcnow)

# Co-Stream (multi-user live)
class CoStream(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_ids = db.Column(db.Text, nullable=False)  # JSON list of user ids
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)

# Overlay (theme, AR, etc.)
class StreamOverlay(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    overlay_type = db.Column(db.String(32), nullable=False)  # 'theme', 'ar', etc.
    data = db.Column(db.Text, nullable=True)  # JSON or config

# Music Integration
class StreamMusic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    track_url = db.Column(db.String(255), nullable=False)
    added_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# AR Filter
class ARFilter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    file_url = db.Column(db.String(255), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    is_public = db.Column(db.Boolean, default=True)

# VIP/Private Stream
class VIPStreamAccess(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    purchased_at = db.Column(db.DateTime, default=datetime.utcnow)

# Highlight
class StreamHighlight(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    start_time = db.Column(db.Float, nullable=False)
    end_time = db.Column(db.Float, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Live Map (Discovery)
class LiveLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    lat = db.Column(db.Float, nullable=False)
    lng = db.Column(db.Float, nullable=False)
    city = db.Column(db.String(64), nullable=True)
    country = db.Column(db.String(64), nullable=True)

# --- End Advanced Livestream Features ---
# --- Livestream Feature Routes (stubs) ---
@app.route('/live/<int:post_id>/reactions', methods=['POST'])
def live_reaction(post_id):
    # Add a reaction to a live stream
    emoji = request.form.get('emoji')
    if 'user_id' in session and emoji:
        reaction = LiveReaction(post_id=post_id, user_id=session['user_id'], emoji=emoji)
        db.session.add(reaction)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/poll', methods=['POST'])
def live_poll(post_id):
    # Create a poll for a live stream
    question = request.form.get('question')
    options = request.form.get('options')  # JSON list
    if 'user_id' in session and question and options:
        poll = LivePoll(post_id=post_id, question=question, options=options)
        db.session.add(poll)
        db.session.commit()
        return jsonify({'status': 'ok', 'poll_id': poll.id})
    return jsonify({'status': 'error'}), 400

@app.route('/live/poll/<int:poll_id>/vote', methods=['POST'])
def live_poll_vote(poll_id):
    # Vote in a live poll
    option = request.form.get('option')
    if 'user_id' in session and option:
        vote = LivePollVote(poll_id=poll_id, user_id=session['user_id'], option=option)
        db.session.add(vote)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/question', methods=['POST'])
def live_question(post_id):
    # Submit a question for Q&A
    question = request.form.get('question')
    if 'user_id' in session and question:
        q = LiveQuestion(post_id=post_id, user_id=session['user_id'], question=question)
        db.session.add(q)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/gift', methods=['POST'])
def live_gift(post_id):
    # Send a virtual gift
    gift_type = request.form.get('gift_type')
    amount = int(request.form.get('amount', 1))
    if 'user_id' in session and gift_type:
        gift = VirtualGift(post_id=post_id, user_id=session['user_id'], gift_type=gift_type, amount=amount)
        db.session.add(gift)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/highlight', methods=['POST'])
def live_highlight(post_id):
    # Create a highlight for a stream
    start = float(request.form.get('start'))
    end = float(request.form.get('end'))
    if 'user_id' in session:
        highlight = StreamHighlight(post_id=post_id, start_time=start, end_time=end, created_by=session['user_id'])
        db.session.add(highlight)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/music', methods=['POST'])
def live_music(post_id):
    # Add a music track to the stream
    track_url = request.form.get('track_url')
    if 'user_id' in session and track_url:
        music = StreamMusic(post_id=post_id, track_url=track_url, added_by=session['user_id'])
        db.session.add(music)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/overlay', methods=['POST'])
def live_overlay(post_id):
    # Add or update overlay
    overlay_type = request.form.get('overlay_type')
    data = request.form.get('data')
    if 'user_id' in session and overlay_type:
        overlay = StreamOverlay(post_id=post_id, overlay_type=overlay_type, data=data)
        db.session.add(overlay)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/arfilter', methods=['POST'])
def live_arfilter(post_id):
    # Add AR filter to stream
    filter_id = request.form.get('filter_id')
    if 'user_id' in session and filter_id:
        # Just a stub, would link ARFilter to stream
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/vip', methods=['POST'])
def live_vip(post_id):
    # Grant VIP access
    if 'user_id' in session:
        access = VIPStreamAccess(post_id=post_id, user_id=session['user_id'])
        db.session.add(access)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400

@app.route('/live/<int:post_id>/location', methods=['POST'])
def live_location(post_id):
    # Set live location for discovery
    lat = float(request.form.get('lat'))
    lng = float(request.form.get('lng'))
    city = request.form.get('city')
    country = request.form.get('country')
    if 'user_id' in session:
        loc = LiveLocation(post_id=post_id, lat=lat, lng=lng, city=city, country=country)
        db.session.add(loc)
        db.session.commit()
        return jsonify({'status': 'ok'})
    return jsonify({'status': 'error'}), 400
# --- End Livestream Feature Routes ---
import os
import io
import re
import json
import base64
import random
import requests

from datetime import datetime, timedelta
import random
import os
# --- Gangsta/Wild N Out Features ---
# Battle Room model
class BattleRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    description = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)

# Crew model
class Crew(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    banner = db.Column(db.String(255), nullable=True)
    avatar = db.Column(db.String(255), nullable=True)
    description = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# Crew Membership
class CrewMember(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    crew_id = db.Column(db.Integer, db.ForeignKey('crew.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    joined_at = db.Column(db.DateTime, default=datetime.utcnow)

# Battle (Rap Battle, Roast, Freestyle)
class Battle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey('battle_room.id'), nullable=False)
    challenger_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    opponent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    winner_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    battle_type = db.Column(db.String(32), default='freestyle')  # 'freestyle', 'roast', 'wildstyle'
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

# Battle Vote
class BattleVote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    battle_id = db.Column(db.Integer, db.ForeignKey('battle.id'), nullable=False)
    voter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    voted_for_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    voted_at = db.Column(db.DateTime, default=datetime.utcnow)

# --- End Gangsta/Wild N Out Features ---
# Gangsta Profile Badge
def get_gangsta_badge(user):
    # Example: assign badge based on battles won
    battles_won = Battle.query.filter_by(winner_id=user.id).count()
    if battles_won >= 20:
        return 'OG Legend'
    elif battles_won >= 10:
        return 'Wildstyle Champ'
    elif battles_won >= 3:
        return 'Battle Star'
    return None
# --- Gangsta/Wild N Out Routes ---
@app.route('/battlerooms')
def battlerooms():
    rooms = BattleRoom.query.filter_by(is_active=True).all()
    return render_template('battlerooms.html', rooms=rooms)

@app.route('/battleroom/<int:room_id>')
def battleroom(room_id):
    room = BattleRoom.query.get_or_404(room_id)
    battles = Battle.query.filter_by(room_id=room.id).order_by(Battle.started_at.desc()).all()
    return render_template('battleroom.html', room=room, battles=battles)

@app.route('/battle/<int:battle_id>', methods=['GET', 'POST'])
def battle(battle_id):
    battle = Battle.query.get_or_404(battle_id)
    challenger = User.query.get(battle.challenger_id)
    opponent = User.query.get(battle.opponent_id)
    votes_challenger = BattleVote.query.filter_by(battle_id=battle.id, voted_for_id=challenger.id).count()
    votes_opponent = BattleVote.query.filter_by(battle_id=battle.id, voted_for_id=opponent.id).count()
    if request.method == 'POST' and 'user_id' in session:
        voted_for = int(request.form['voted_for'])
        if not BattleVote.query.filter_by(battle_id=battle.id, voter_id=session['user_id']).first():
            vote = BattleVote(battle_id=battle.id, voter_id=session['user_id'], voted_for_id=voted_for)
            db.session.add(vote)
            db.session.commit()
            flash('Vote submitted!')
        return redirect(url_for('battle', battle_id=battle.id))
    return render_template('battle.html', battle=battle, challenger=challenger, opponent=opponent, votes_challenger=votes_challenger, votes_opponent=votes_opponent)

@app.route('/crews')
def crews():
    crews = Crew.query.all()
    return render_template('crews.html', crews=crews)

@app.route('/crew/<int:crew_id>')
def crew(crew_id):
    crew = Crew.query.get_or_404(crew_id)
    members = CrewMember.query.filter_by(crew_id=crew.id).all()
    return render_template('crew.html', crew=crew, members=members)

@app.route('/leaderboard')
def leaderboard():
    # Top battlers and crews
    top_battlers = db.session.query(User, db.func.count(Battle.id).label('wins')).join(Battle, Battle.winner_id == User.id).group_by(User.id).order_by(db.desc('wins')).limit(10).all()
    top_crews = db.session.query(Crew, db.func.count(CrewMember.id).label('members')).join(CrewMember, CrewMember.crew_id == Crew.id).group_by(Crew.id).order_by(db.desc('members')).limit(10).all()
    return render_template('leaderboard.html', top_battlers=top_battlers, top_crews=top_crews)

# --- End Gangsta/Wild N Out Routes ---
@app.route("/login", methods=["POST"])
def login():
    # after verifying login
    # Example: user = User.query.filter_by(username=request.form['username']).first()
    # if user and check_password_hash(user.password_hash, request.form['password']):
    #     session["username"] = user.username
    #     return redirect(url_for("account"))
    # else:
    #     flash("Invalid credentials")
    #     return redirect(url_for("login"))
    pass  # Replace with actual login logic



# Post model definition
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    # Add any other fields you need

# Ensure the Flask app runs when executed directly

if __name__ == "__main__":
    app.run(debug=True)
