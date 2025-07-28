from .user import User
from .message import Message
from .emoji import Emoji


{% extends "base.html" %}

{% block content %}
<div class="signup-container">
    <h2>Sign Up</h2>
    <form method="POST" action="{{ url_for('auth.signup') }}">
        <div>
            <label for="username">Username:</label>
            <input type="text" name="username" id="username" required>
        </div>
        <div>
            <label for="email">Email:</label>
            <input type="email" name="email" id="email" required>
        </div>
        <div>
            <label for="password">Password:</label>
            <input type="password" name="password" id="password" required>
        </div>
        <button type="submit">Create Account</button>
    </form>
    <p>Already have an account? <a href="{{ url_for('auth.login') }}">Log in here</a>.</p>
</div>
{% endblock %}