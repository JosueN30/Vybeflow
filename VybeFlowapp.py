from flask import Flask, render_template, redirect, url_for, request, session, flash
import os
import datetime

# A simple placeholder user object for demonstration purposes
class User:
    def __init__(self, username, bio, avatar_url):
        self.username = username
        self.bio = bio
        self.avatar_url = avatar_url

app = Flask(__name__)
# Change this to a secure, randomly generated key in a production environment
app.secret_key = os.urandom(24)

@app.before_request
def check_user_status():
    """
    A simple check to see if a user is logged in.
    In a real app, this would check against a user in your database.
    """
    if 'logged_in' not in session and request.endpoint in ('feed', 'account', 'upload'):
        return redirect(url_for('login'))

# ---------- AUTH ROUTES ----------

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # handle login logic here
        session['logged_in'] = True  # Placeholder for successful login
        return redirect(url_for('feed'))
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # handle registration logic here
        return redirect(url_for('login'))
    return render_template('signup.html')


# ---------- MAIN APP ROUTES ----------

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/feed')
def feed():
    # Create user objects inside the route to avoid application context errors
    logged_in_user = User(
        username='JohnDoe',
        bio='Just a regular VybeFlow user.',
        avatar_url=url_for('static', filename='default_avatar.png')
    )
    users_to_follow = [
        User('JaneSmith', 'Artist and designer.', url_for('static', filename='default_avatar.png')),
        User('Alex_R', 'Tech enthusiast.', url_for('static', filename='default_avatar.png'))
    ]
    return render_template('feed.html', current_user=logged_in_user, users=users_to_follow)

@app.route('/account')
def account():
    logged_in_user = User(
        username='JohnDoe',
        bio='Just a regular VybeFlow user.',
        avatar_url=url_for('static', filename='default_avatar.png')
    )
    return render_template('account.html', user=logged_in_user)

@app.route('/upload')
def upload():
    return render_template('upload.html')


# ---------- SEARCH ROUTE ----------
@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':
        query = request.form.get('query', '')
        # TODO: implement search logic
        return render_template('search_results.html', query=query)
    return render_template('search.html')


# ---------- STORY CREATION ----------
@app.route('/story/create', methods=['GET', 'POST'])
def create_story():
    if request.method == 'POST':
        # handle file upload
        file = request.files.get('theme_video')
        caption = request.form.get('caption')
        # TODO: save story in DB
        return redirect(url_for('feed'))
    return render_template('story_create.html')


# ---------- VIDEO CALL ----------
@app.route('/call/<int:callee_id>')
def call(callee_id):
    # Example: fetch callee user from database
    callee = {"id": callee_id, "username": f"User{callee_id}"}
    return render_template('messenger_video_call.html', callee=callee)


# ---------- ERROR HANDLERS ----------

@app.errorhandler(404)
def not_found(e):
    return render_template('404.html'), 404


if __name__ == "__main__":
    app.run(debug=True)
