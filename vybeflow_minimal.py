#!/usr/bin/env python3
"""Minimal VybeFlow test"""

from flask import Flask, render_template, redirect, url_for, flash, request, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Email, Length
from flask_wtf import FlaskForm
import os

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'test-secret-key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///vybeflow_test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Initialize database
db = SQLAlchemy(app)

# Simple User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128))

# Simple forms
class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=4, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    submit = SubmitField('Sign Up')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Sign In')

# Routes
@app.route('/')
def home():
    return '''
    <h1 style="color: #ffb400; text-align: center; font-family: Arial;">🎵 VybeFlow - Minimal Test 🎵</h1>
    <div style="text-align: center; margin: 50px;">
        <a href="/register" style="background: #ffb400; color: black; padding: 15px 30px; text-decoration: none; border-radius: 25px; margin: 10px;">Register</a>
        <a href="/login" style="background: #ff8c00; color: black; padding: 15px 30px; text-decoration: none; border-radius: 25px; margin: 10px;">Login</a>
    </div>
    '''

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        username = form.username.data
        email = form.email.data
        password = form.password.data
        
        # Check if user exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists.')
            return redirect(url_for('register'))
        
        # Create user
        password_hash = generate_password_hash(password)
        user = User(username=username, email=email, password_hash=password_hash)
        db.session.add(user)
        db.session.commit()
        
        flash('Registration successful!')
        return redirect(url_for('login'))
    
    return '''
    <div style="max-width: 400px; margin: 50px auto; padding: 30px; background: #222; border-radius: 20px; color: #ffb400;">
        <h2 style="text-align: center;">Register for VybeFlow</h2>
        <form method="post">
            ''' + form.hidden_tag() + '''
            <div style="margin: 15px 0;">
                ''' + str(form.username.label()) + '''<br>
                ''' + str(form.username(style="width: 100%; padding: 10px; border-radius: 5px; border: none; background: rgba(255,255,255,0.9);")) + '''
            </div>
            <div style="margin: 15px 0;">
                ''' + str(form.email.label()) + '''<br>
                ''' + str(form.email(style="width: 100%; padding: 10px; border-radius: 5px; border: none; background: rgba(255,255,255,0.9);")) + '''
            </div>
            <div style="margin: 15px 0;">
                ''' + str(form.password.label()) + '''<br>
                ''' + str(form.password(style="width: 100%; padding: 10px; border-radius: 5px; border: none; background: rgba(255,255,255,0.9);")) + '''
            </div>
            <div style="text-align: center; margin: 20px 0;">
                ''' + str(form.submit(style="background: #ffb400; color: black; padding: 12px 30px; border: none; border-radius: 25px; cursor: pointer;")) + '''
            </div>
        </form>
        <p style="text-align: center;"><a href="/login" style="color: #ffb400;">Already have an account? Login here</a></p>
    </div>
    '''

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            flash('Login successful!')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials.')
    
    return '''
    <div style="max-width: 400px; margin: 50px auto; padding: 30px; background: #222; border-radius: 20px; color: #ffb400;">
        <h2 style="text-align: center;">Login to VybeFlow</h2>
        <form method="post">
            ''' + form.hidden_tag() + '''
            <div style="margin: 15px 0;">
                ''' + str(form.username.label()) + '''<br>
                ''' + str(form.username(style="width: 100%; padding: 10px; border-radius: 5px; border: none; background: rgba(255,255,255,0.9);")) + '''
            </div>
            <div style="margin: 15px 0;">
                ''' + str(form.password.label()) + '''<br>
                ''' + str(form.password(style="width: 100%; padding: 10px; border-radius: 5px; border: none; background: rgba(255,255,255,0.9);")) + '''
            </div>
            <div style="text-align: center; margin: 20px 0;">
                ''' + str(form.submit(style="background: #ffb400; color: black; padding: 12px 30px; border: none; border-radius: 25px; cursor: pointer;")) + '''
            </div>
        </form>
        <p style="text-align: center;"><a href="/register" style="color: #ffb400;">Need an account? Register here</a></p>
    </div>
    '''

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user = User.query.get(session['user_id'])
    return f'''
    <div style="text-align: center; margin: 50px; color: #ffb400;">
        <h1>🎉 Welcome to VybeFlow, {user.username}! 🎉</h1>
        <p>Your minimal VybeFlow is working perfectly!</p>
        <a href="/logout" style="background: #ff8c00; color: black; padding: 10px 20px; text-decoration: none; border-radius: 15px;">Logout</a>
    </div>
    '''

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('Logged out successfully.')
    return redirect(url_for('home'))

@app.route('/profile')
def profile():
    return render_template('profile.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        print("🎵 VybeFlow Minimal Test Starting...")
        print("📍 Visit: http://127.0.0.1:5000")
    
    app.run(debug=True, host='0.0.0.0', port=5000)
