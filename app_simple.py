"""
Simple VybeFlow Flask Application
"""
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import os
import sys

# Add VybeFlow_new to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'VybeFlow_new'))

app = Flask(__name__, 
           template_folder='VybeFlow_new/templates',
           static_folder='VybeFlow_new/static')

app.secret_key = 'vybeflow-gangsta-secret-key-2024'

# Import routes from VybeFlow_new
try:
    from VybeFlow_new.routes.main import main_bp
    from VybeFlow_new.routes.auth import auth_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    
except Exception as e:
    print(f"Blueprint import error: {e}")
    
    # Create basic routes if blueprints fail
    @app.route('/')
    def home():
        return render_template('home.html')
    
    @app.route('/profile')
    def profile():
        username = session.get('username', 'User')
        return render_template('profile.html', username=username)
    
    @app.route('/messages')
    def messages():
        return render_template('messages.html')
    
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')
            
            if username and password:
                session['user_id'] = username
                session['username'] = username
                session['logged_in'] = True
                flash(f'Welcome to VybeFlow, {username}!', 'success')
                return redirect(url_for('profile'))
        
        return render_template('login.html')
    
    @app.route('/register', methods=['GET', 'POST'])  
    def register():
        if request.method == 'POST':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            
            if username and email and password:
                session['user_id'] = username
                session['username'] = username
                session['email'] = email
                session['logged_in'] = True
                flash(f'Welcome to VybeFlow, {username}! Registration successful!', 'success')
                return redirect(url_for('profile'))
        
        return render_template('register.html')
    
    @app.route('/logout')
    def logout():
        session.clear()
        flash('You have been logged out.', 'info')
        return redirect(url_for('home'))

# API Routes for AJAX calls
@app.route('/upload_music', methods=['POST'])
def upload_music():
    try:
        if 'music_file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'})
        
        file = request.files['music_file']
        track_name = request.form.get('track_name', file.filename)
        
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # In production, save the file
        # For demo, return success
        return jsonify({
            'success': True,
            'track_name': track_name,
            'file_path': f'/static/uploads/music/{file.filename}',
            'message': 'Track uploaded successfully!'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/search_users')
def search_users():
    return render_template('user_search.html')

@app.route('/customize_profile')
def customize_profile():
    return render_template('profile_customize.html')

# API routes for social search
@app.route('/api/search_facebook')
def search_facebook():
    query = request.args.get('query', '')
    # Simulated Facebook search results
    results = [
        {'name': f'{query} MusicProducer', 'type': 'Music Producer', 'mutual_friends': 5},
        {'name': f'{query} BeatMaker', 'type': 'Beat Maker', 'mutual_friends': 3},
        {'name': f'{query} Rapper', 'type': 'Hip-Hop Artist', 'mutual_friends': 8}
    ]
    return jsonify({'results': results})

@app.route('/api/search_instagram')
def search_instagram():
    query = request.args.get('query', '')
    # Simulated Instagram search results  
    results = [
        {'username': f'@{query}_music', 'followers': '10K', 'type': 'Music Creator'},
        {'username': f'@{query}_beats', 'followers': '25K', 'type': 'Beat Producer'},
        {'username': f'@{query}_rap', 'followers': '50K', 'type': 'Rap Artist'}
    ]
    return jsonify({'results': results})

if __name__ == '__main__':
    print("🎵 Starting VybeFlow Server...")
    print("🚀 Server will be available at: http://127.0.0.1:5000")
    print("🎯 Features available:")
    print("   • Profile customization with themes")  
    print("   • Music upload and playback")
    print("   • 3D animated emojis with sound")
    print("   • Custom chat themes")
    print("   • Voice notes and video calling")
    print("   • Push notifications")
    print("   • Mobile PWA support")
    app.run(debug=True, host='0.0.0.0', port=5000)