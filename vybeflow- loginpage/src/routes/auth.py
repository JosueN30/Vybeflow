from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_user
from ..models.user import User
from .. import db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.verify_password(password):  # Assuming a method to verify password exists
            login_user(user)
            return redirect(url_for('messaging.chat'))  # Redirect to chat page after login
        else:
            flash('Invalid username or password', 'danger')
    
    return render_template('login.html')

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))  # Redirect to login page after logout

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        
        new_user = User(username=username, email=email, password=password)  # Assuming password is hashed in User model
        db.session.add(new_user)
        db.session.commit()
        flash('Registration successful! You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('register.html')  # Create a register.html template for registration