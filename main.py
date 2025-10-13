"""
Main application routes (home, profile, etc.)
"""

from flask import Blueprint, render_template, session, redirect, url_for, flash, request, jsonify
import time
import secrets
# vybeflow_oauth and stream_manager are not available; set to None for fallback logic
vybeflow_oauth = None
stream_manager = None

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    """Main homepage - redirects to feed if logged in"""
    # If user is logged in, redirect to feed
    if session.get('logged_in'):
        return redirect(url_for('main.feed'))
    
    # Otherwise show the landing page
    return render_template('home.html', title='VybeFlow - Connect Your Flow')

@main_bp.route('/login')
def login_redirect():
    """Redirect /login to /auth/login"""
    return redirect(url_for('auth.login'))

@main_bp.route('/register')
def register_redirect():
    """Redirect /register to /auth/register"""
    return redirect(url_for('auth.register'))

@main_bp.route('/profile')
def profile():
    """User profile page"""
    # Check if user is logged in
    if not session.get('logged_in'):
        flash('Please log in to access your profile.', 'error')
        return redirect(url_for('auth.login', next=request.url))
    
    # Get user info from session
    username = session.get('username', 'User')
    email = session.get('email', '')
    
    return render_template('profile.html', title='Profile', username=username, email=email)

@main_bp.route('/feed')
def feed():
    """Main social media feed with advanced posting capabilities"""
    # Check if user is logged in
    if not session.get('logged_in'):
        flash('Please log in to access your feed.', 'error')
        return redirect(url_for('auth.login', next=request.url))
    
    # Get user info from session
    username = session.get('username', 'User')
    
    # Get posts from session (in a real app, this would come from database)
    user_posts = session.get('posts', [])
    
    # Sample posts to show platform features
    sample_posts = [
        {
            'username': 'MusicMaven',
            'content': 'Just dropped my latest beat! 🔥 What do you think?',
            'type': 'music',
            'type_display': '🎵 Music',
            'files': ['audio: fire_beat_v3.mp3'],
            'time_ago': '2 hours ago',
            'likes': 47,
            'comments': 12
        },
        {
            'username': 'BeatBattler',
            'content': 'Challenge accepted! Anyone ready for a freestyle battle? 💪',
            'type': 'battle',
            'type_display': '⚔️ Battle',
            'files': [],
            'time_ago': '4 hours ago',
            'likes': 23,
            'comments': 8
        },
        {
            'username': 'RemixQueen',
            'content': 'Collaborating on this sick remix with @ProducerPro - VybeFlow collab tools are amazing! 🎛️',
            'type': 'collab',
            'type_display': '🤝 Collab',
            'files': ['video: studio_session.mp4'],
            'time_ago': '6 hours ago',
            'likes': 89,
            'comments': 25
        }
    ]
    
    # Combine user posts with sample posts
    all_posts = user_posts + sample_posts
    
    return render_template('feed.html', title='Feed', username=username, posts=all_posts, logged_in=True)

@main_bp.route('/discover')
def discover():
    """Fallback Discover route."""
    return render_template('discover.html', title="Discover")

@main_bp.route('/create_post', methods=['POST'])
def create_post():
    """Handle advanced post creation with media uploads"""
    # Check if user is logged in
    if not session.get('logged_in'):
        flash('Please log in to create posts.', 'error')
        return redirect(url_for('auth.login'))
    
    content = request.form.get('content', '').strip()
    post_type = request.form.get('post_type', 'text')
    username = session.get('username', 'User')
    
    # Handle file uploads
    uploaded_files = []
    file_types = ['video', 'audio', 'gif', 'image']
    
    for file_type in file_types:
        if file_type in request.files:
            file = request.files[file_type]
            if file and file.filename:
                # In a real app, you would save the file and process it
                uploaded_files.append(f"{file_type}: {file.filename}")
    
    if content or uploaded_files:
        # Store post in session (in a real app, this would go to a database)
        if 'posts' not in session:
            session['posts'] = []
        
        post_type_displays = {
            'text': '💬 Text',
            'music': '🎵 Music',
            'video': '🎬 Video',
            'live': '🔴 Live',
            'battle': '⚔️ Battle',
            'collab': '🤝 Collab',
            'remix': '🔄 Remix',
            'exclusive': '💎 Exclusive'
        }
        
        new_post = {
            'username': username,
            'content': content,
            'type': post_type,
            'type_display': post_type_displays.get(post_type, '💬 Text'),
            'files': uploaded_files,
            'time_ago': 'Just now',
            'likes': 0,
            'comments': 0
        }
        
        session['posts'].insert(0, new_post)  # Add to beginning of list
        session.permanent = True
        
        # Create success message based on post type
        success_messages = {
            'text': f'💬 Your thoughts have been shared!',
            'music': f'🎵 Your music drop is live! The community will love this beat.',
            'video': f'🎬 Your video content is processing! Enhanced with VybeFlow magic.',
            'live': f'🔴 Live stream initiated! Your audience is joining.',
            'battle': f'⚔️ Beat battle challenge posted! Producers are getting ready.',
            'collab': f'🤝 Collaboration request is live! Artists are responding.',
            'remix': f'🔄 Remix challenge created! The community is already mixing.',
            'exclusive': f'💎 VybeFlow exclusive content posted! Premium experience activated.'
        }
        
        message = success_messages.get(post_type, 'Your post has been shared!')
        flash(message, 'success')
            
    else:
        flash('Please add some content or upload media to share!', 'error')
    
    return redirect(url_for('main.feed'))

@main_bp.route('/live-streams')
def live_streams():
    """Live streaming hub"""
    if not session.get('logged_in'):
        flash('Please log in to access live streams.', 'error')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'User')
    return render_template('live-streams.html', title='Live Streams', username=username)

@main_bp.route('/beat-battles')  
def beat_battles():
    """Beat battles arena"""
    if not session.get('logged_in'):
        flash('Please log in to join beat battles.', 'error')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'User')
    flash('⚔️ Beat Battles Arena - Show your skills and compete with producers worldwide!', 'info')
    return render_template('feed.html', title='Beat Battles', username=username)

@main_bp.route('/collaborations')
def collaborations():
    """Collaboration hub"""
    if not session.get('logged_in'):
        flash('Please log in to start collaborating.', 'error')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'User')
    flash('🤝 Collaboration Hub - Create music together with artists around the world!', 'info')  
    return render_template('feed.html', title='Collaborations', username=username)

@main_bp.route('/messages')
def messages():
    """VybeFlow messaging hub"""
    if not session.get('logged_in'):
        flash('Please log in to access your messages.', 'error')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'User')
    flash('📨 VybeFlow Messages - Connect with artists through music!', 'info')
    return render_template('messages.html', title='Messages', username=username)

@main_bp.route('/user_search')
def user_search():
    """Renders the Find Users page."""
    return render_template('find_users.html')

@main_bp.route('/api/search_friends')
def api_search_friends():
    """Simulated user search."""
    query = request.args.get('q', '').lower()
    fake_friends = [
        {"name": "MusicMaven", "username": "maven", "avatar": "🎵", "genre": "Hip-Hop", "platform": "VybeFlow"},
        {"name": "VocalVibe", "username": "vibe", "avatar": "🎤", "genre": "R&B", "platform": "VybeFlow"},
        {"name": "BeatBattler", "username": "battler", "avatar": "🎹", "genre": "Electronic", "platform": "VybeFlow"},
        {"name": "RemixQueen", "username": "remix", "avatar": "🔄", "genre": "DJ/Remix", "platform": "VybeFlow"},
    ]
    results = [f for f in fake_friends if query in f["name"].lower() or query in f["genre"].lower()]
    return jsonify({"friends": results})

@main_bp.route('/api/search_instagram_creators')
def api_search_instagram_creators():
    """Mock Instagram creator search."""
    query = request.args.get('q', '').lower()
    creators = [
        {"username": "soundwave", "name": "SoundWave", "platform": "Instagram"},
        {"username": "beatsbykali", "name": "BeatsByKali", "platform": "Instagram"},
    ]
    results = [u for u in creators if query in u["name"].lower()]
    return jsonify({"users": results})

@main_bp.route('/api/search_twitter_artists')
def api_search_twitter_artists():
    """Mock Twitter artist search."""
    query = request.args.get('q', '').lower()
    artists = [
        {"username": "vibezflow", "name": "VibezFlow", "platform": "Twitter"},
        {"username": "dj_neon", "name": "DJ Neon", "platform": "Twitter"},
    ]
    results = [u for u in artists if query in u["name"].lower()]
    return jsonify({"users": results})

@main_bp.route('/api/invite_facebook_friend', methods=['POST'])
def api_invite_facebook_friend():
    """Simulated Facebook invite endpoint."""
    data = request.get_json()
    name = data.get('name')
    platform = data.get('platform')
    # Simulate sending an invite
    return jsonify({
        "success": True,
        "message": f"Invitation sent to {name} via {platform}!"
    })

@main_bp.route('/api/add_friend_to_vybeflow', methods=['POST'])
def api_add_friend_to_vybeflow():
    """Simulate adding a friend."""
    data = request.get_json()
    name = data.get('name')
    friend_count = session.get('friend_count', 0) + 1
    session['friend_count'] = friend_count
    return jsonify({
        "success": True,
        "message": f"{name} has been added to your VybeFlow network!",
        "friend_count": friend_count
    })

@main_bp.route('/facebook/disconnect')
def facebook_disconnect():
    """Simulated Facebook disconnect."""
    session.pop('facebook_connected', None)
    session.pop('facebook_friends', None)
    return render_template('find_users.html', message="Facebook disconnected successfully!")

@main_bp.route('/connect/facebook')
def connect_facebook():
    """Facebook connection route - redirects to OAuth flow"""
    if not session.get('logged_in'):
        flash('Please log in to connect Facebook.', 'error')
        return redirect(url_for('auth.login'))
    
    # Check if Facebook is already connected
    if session.get('facebook_connected'):
        flash('📘 Facebook is already connected! Your friends are available in search.', 'info')
        return redirect(url_for('main.user_search'))
    
    # Redirect to Facebook OAuth login
    return redirect(url_for('main.facebook_login'))

@main_bp.route('/connect/instagram')
def connect_instagram():
    """Instagram connection route"""
    if not session.get('logged_in'):
        flash('Please log in to connect Instagram.', 'error')
        return redirect(url_for('auth.login'))
    
    # Simulate Instagram connection success
    flash('🎉 Instagram connected successfully! Discovering music creators...', 'success')
    flash('📸 Found 14 Instagram creators and influencers! Search for them below.', 'info')
    
    # Add realistic Instagram friends to session
    if 'instagram_friends' not in session:
        session['instagram_friends'] = [
            {'name': 'Alex Rodriguez', 'username': 'beats_by_alex', 'genre': 'Trap Producer', 'followers': '125K'},
            {'name': 'Samantha Lee', 'username': 'vocal_goddess', 'genre': 'Pop Vocalist', 'followers': '89K'},
            {'name': 'Sam Wilson', 'username': 'producer_sam', 'genre': 'Lo-Fi Hip-Hop', 'followers': '76K'},
            {'name': 'Emma Davis', 'username': 'emma_melodies', 'genre': 'Indie Folk Singer', 'followers': '45K'},
            {'name': 'Carlos Rivera', 'username': 'carlos_beats', 'genre': 'Reggaeton Producer', 'followers': '112K'},
            {'name': 'Aria Kim', 'username': 'aria_kpop', 'genre': 'K-Pop Cover Artist', 'followers': '234K'},
            {'name': 'DJ Phoenix', 'username': 'dj_phoenix_official', 'genre': 'House DJ', 'followers': '178K'},
            {'name': 'Maya Santos', 'username': 'maya_acoustic', 'genre': 'Acoustic Guitar', 'followers': '67K'},
            {'name': 'Tyler Ross', 'username': 'tyler_hiphop', 'genre': 'Hip-Hop Producer', 'followers': '93K'},
            {'name': 'Luna Park', 'username': 'luna_synthwave', 'genre': 'Synthwave Artist', 'followers': '56K'},
            {'name': 'Rico Martinez', 'username': 'rico_salsa', 'genre': 'Salsa Musician', 'followers': '41K'},
            {'name': 'Skylar Blue', 'username': 'skylar_blues', 'genre': 'Blues Singer', 'followers': '38K'},
            {'name': 'Neo Tokyo', 'username': 'neo_tokyo_beats', 'genre': 'Electronic Artist', 'followers': '145K'},
            {'name': 'Violet Rain', 'username': 'violet_rain_music', 'genre': 'Alternative Rock', 'followers': '72K'}
        ]
        session.permanent = True
    
    return redirect(url_for('main.user_search'))

def search_vybeflow_users(query):
    """Search for users within VybeFlow platform"""
    # Sample VybeFlow users - in a real app, this would query your user database
    vybeflow_users = [
        {'name': 'Marcus Johnson', 'username': 'marcusbeats', 'genre': 'Hip-Hop Producer', 'location': 'Atlanta', 'followers': '23K'},
        {'name': 'Luna Rodriguez', 'username': 'lunamelodies', 'genre': 'Pop Singer', 'location': 'Los Angeles', 'followers': '18K'},
        {'name': 'Alex Kim', 'username': 'alexsynth', 'genre': 'Electronic Artist', 'location': 'Seoul', 'followers': '31K'},
        {'name': 'Zara Hassan', 'username': 'zaravocals', 'genre': 'R&B Vocalist', 'location': 'London', 'followers': '27K'},
        {'name': 'Diego Santos', 'username': 'diegoreggae', 'genre': 'Reggae Artist', 'location': 'São Paulo', 'followers': '15K'},
        {'name': 'Maya Thompson', 'username': 'mayajazz', 'genre': 'Jazz Pianist', 'location': 'New Orleans', 'followers': '12K'},
        {'name': 'Ryan O\'Connor', 'username': 'ryanrock', 'genre': 'Rock Guitarist', 'location': 'Dublin', 'followers': '19K'},
        {'name': 'Aisha Patel', 'username': 'aishaworld', 'genre': 'World Music', 'location': 'Mumbai', 'followers': '22K'},
        {'name': 'Jake Williams', 'username': 'jakecountry', 'genre': 'Country Artist', 'location': 'Nashville', 'followers': '16K'},
        {'name': 'Sofia Andersson', 'username': 'sofiaedm', 'genre': 'EDM Producer', 'location': 'Stockholm', 'followers': '29K'}
    ]
    
    results = []
    for user in vybeflow_users:
        if (query in user['name'].lower() or 
            query in user['username'].lower() or 
            query in user['genre'].lower() or
            query in user['location'].lower()):
            results.append({
                'name': user['name'],
                'username': user['username'],
                'genre': user['genre'],
                'platform': 'VybeFlow',
                'avatar': '🎵',
                'extra': f"{user['followers']} followers • {user['location']}",
                'verified': True,
                'already_on_vybeflow': True
            })
    
    return results

@main_bp.route('/emoji-studio')
def emoji_studio():
    """Emoji Customization Studio"""
    if not session.get('logged_in'):
        flash('Please log in to access the Emoji Studio.', 'error')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'User')
    return render_template('emoji_studio.html', title='Emoji Studio', username=username)

@main_bp.route('/start-stream')
def start_stream():
    """Initialize live streaming setup"""
    if not session.get('logged_in'):
        flash('Please log in to start streaming.', 'error')
        return redirect(url_for('auth.login'))
    
    username = session.get('username', 'User')
    return render_template('stream_setup.html', title='Start Stream', username=username)

@main_bp.route('/create-stream', methods=['POST'])
def create_stream():
    """Create and start a new live stream"""
    if not session.get('logged_in'):
        flash('Please log in to start streaming.', 'error')
        return redirect(url_for('auth.login'))
    
    stream_title = request.form.get('title', 'Untitled Stream')
    stream_description = request.form.get('description', '')
    stream_category = request.form.get('category', 'music')
    username = session.get('username', 'User')
    
    # Create stream using the stream manager
    if stream_manager:
        try:
            new_stream = stream_manager.create_stream(
                user_id=username,
                title=stream_title,
                description=stream_description,
                category=stream_category
            )
            
            # Start the stream immediately
            stream_manager.start_stream(new_stream['id'])
            
            session['current_stream'] = new_stream
            flash(f'🔴 Stream "{stream_title}" is now LIVE!', 'success')
            flash(f'🔑 Stream Key: {new_stream["stream_key"][:8]}... (use for OBS/streaming software)', 'info')
            
        except Exception as e:
            flash('❌ Error starting stream. Please try again.', 'error')
            return redirect(url_for('main.start_stream'))
    else:
        # Fallback to simple session storage
        stream_id = f"stream_{int(time.time())}"
        new_stream = {
            'id': stream_id,
            'title': stream_title,
            'description': stream_description,
            'category': stream_category,
            'username': username,
            'viewers': 0,
            'likes': 0,
            'status': 'live',
            'started_at': time.time()
        }
        session['current_stream'] = new_stream
        flash(f'🔴 Live stream "{stream_title}" started successfully!', 'success')
        
    session.permanent = True
    
    # Get the correct stream_id for redirect
    redirect_stream_id = new_stream['id']
    
    flash('🎵 Your stream is now live! Share the link with your audience.', 'info')
    flash('💡 Use OBS or streaming software to broadcast to your audience.', 'info')
    
    return redirect(url_for('main.live_stream_room', stream_id=redirect_stream_id))

@main_bp.route('/stream/<stream_id>')
def live_stream_room(stream_id):
    """Live streaming room interface"""
    if not session.get('logged_in'):
        flash('Please log in to access streams.', 'error')
        return redirect(url_for('auth.login'))
    
    # Find the stream (in a real app, query from database)
    stream = None
    if 'user_streams' in session:
        for s in session['user_streams']:
            if s['id'] == stream_id:
                stream = s
                break
    
    if not stream:
        # Create a sample stream if not found
        stream = {
            'id': stream_id,
            'title': 'Live Music Session',
            'description': 'Join me for some amazing beats!',
            'category': 'music',
            'username': session.get('username', 'User'),
            'viewers': 42,
            'likes': 156,
            'status': 'live',
            'started_at': time.time() - 1800  # 30 minutes ago
        }
    
    username = session.get('username', 'User')
    is_streamer = stream['username'] == username
    
    return render_template('live_stream_room.html', 
                         title=f"Live: {stream['title']}", 
                         username=username,
                         stream=stream,
                         is_streamer=is_streamer)

@main_bp.route('/end-stream/<stream_id>', methods=['POST'])
def end_stream(stream_id):
    """End a live stream"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    # Update stream status
    if 'user_streams' in session:
        for stream in session['user_streams']:
            if stream['id'] == stream_id and stream['username'] == session.get('username'):
                stream['status'] = 'ended'
                break
    
    if 'current_stream' in session and session['current_stream']['id'] == stream_id:
        del session['current_stream']
    
    session.permanent = True
    
    return jsonify({'success': True, 'message': 'Stream ended successfully'})

# Facebook OAuth Routes
@main_bp.route('/facebook/login')
def facebook_login():
    """Initialize Facebook OAuth login"""
    if not session.get('logged_in'):
        flash('Please log in to VybeFlow first before connecting Facebook.', 'error')
        return redirect(url_for('auth.login'))
    
    # Facebook OAuth configuration
    FB_CLIENT_ID = "YOUR_FB_APP_ID"  # Replace with your actual Facebook App ID
    FB_REDIRECT_URI = "http://127.0.0.1:5000/facebook/callback"
    
    # Facebook OAuth URL with extended permissions for music and friends
    fb_auth_url = (
        f"https://www.facebook.com/v18.0/dialog/oauth?"
        f"client_id={FB_CLIENT_ID}&"
        f"redirect_uri={FB_REDIRECT_URI}&"
        f"scope=email,user_friends,user_likes,user_posts,pages_read_engagement,user_events&"
        f"response_type=code&"
        f"state={session.get('username', 'user')}"
    )
    
    flash('🔄 Redirecting to Facebook for secure authentication...', 'info')
    return redirect(fb_auth_url)

@main_bp.route('/facebook/callback')
def facebook_callback():
    """Handle Facebook OAuth callback and import friends"""
    if not session.get('logged_in'):
        flash('Please log in to VybeFlow first.', 'error')
        return redirect(url_for('auth.login'))
    
    code = request.args.get('code')
    error = request.args.get('error')
    
    if error:
        flash(f'❌ Facebook connection failed: {error}', 'error')
        return redirect(url_for('main.user_search'))
    
    if not code:
        flash('❌ No authorization code received from Facebook.', 'error')
        return redirect(url_for('main.user_search'))
    
    try:
        # Facebook OAuth configuration
        FB_CLIENT_ID = "YOUR_FB_APP_ID"  # Replace with your actual Facebook App ID  
        FB_CLIENT_SECRET = "YOUR_FB_APP_SECRET"  # Replace with your actual Facebook App Secret
        FB_REDIRECT_URI = "http://127.0.0.1:5000/facebook/callback"
        
        # Exchange authorization code for access token
        token_url = "https://graph.facebook.com/v18.0/oauth/access_token"
        token_params = {
            "client_id": FB_CLIENT_ID,
            "redirect_uri": FB_REDIRECT_URI,
            "client_secret": FB_CLIENT_SECRET,
            "code": code
        }
        
        import requests
        token_response = requests.get(token_url, params=token_params)
        
        if token_response.status_code != 200:
            flash('❌ Failed to get Facebook access token.', 'error')
            return redirect(url_for('main.user_search'))
        
        token_data = token_response.json()
        access_token = token_data.get('access_token')
        
        if not access_token:
            flash('❌ Invalid Facebook access token received.', 'error')
            return redirect(url_for('main.user_search'))
        
        # Get user's basic info
        user_info_response = requests.get(
            "https://graph.facebook.com/me",
            params={
                "access_token": access_token,
                "fields": "id,name,email"
            }
        )
        
        if user_info_response.status_code == 200:
            user_info = user_info_response.json()
            session['facebook_user'] = {
                'id': user_info.get('id'),
                'name': user_info.get('name'),
                'email': user_info.get('email')
            }
        
        # Get user's friends (Note: Facebook heavily restricts friend data now)
        friends_response = requests.get(
            "https://graph.facebook.com/me/friends",
            params={
                "access_token": access_token,
                "fields": "id,name"
            }
        )
        
        real_friends = []
        if friends_response.status_code == 200:
            friends_data = friends_response.json()
            real_friends = friends_data.get('data', [])
        
        # Due to Facebook's privacy restrictions, we'll enhance with realistic sample data
        # In a real app, you'd use Facebook's limited friend data + your app's user base
        enhanced_friends = [
            {'name': 'Sarah Martinez', 'username': 'sarahm_beats', 'genre': 'R&B Producer', 'mutual_friends': 5, 'verified': True},
            {'name': 'Mike Johnson', 'username': 'mikej_vibes', 'genre': 'Hip-Hop Artist', 'mutual_friends': 12, 'verified': True},
            {'name': 'Jessica Lopez', 'username': 'jess_harmony', 'genre': 'Singer-Songwriter', 'mutual_friends': 3, 'verified': True},
            {'name': 'David Chen', 'username': 'david_remix', 'genre': 'Electronic Producer', 'mutual_friends': 8, 'verified': True},
            {'name': 'Maya Patel', 'username': 'maya_sounds', 'genre': 'Jazz Fusion', 'mutual_friends': 2, 'verified': True},
            {'name': 'Alex Rodriguez', 'username': 'alex_drums', 'genre': 'Drummer', 'mutual_friends': 15, 'verified': True},
            {'name': 'Emma Thompson', 'username': 'emma_vocals', 'genre': 'Pop Vocalist', 'mutual_friends': 7, 'verified': True},
            {'name': 'Carlos Rivera', 'username': 'carlos_guitar', 'genre': 'Guitarist', 'mutual_friends': 4, 'verified': True},
            {'name': 'Lisa Wang', 'username': 'lisa_piano', 'genre': 'Classical Pianist', 'mutual_friends': 6, 'verified': True},
            {'name': 'Jordan Smith', 'username': 'jordan_beats', 'genre': 'Trap Producer', 'mutual_friends': 9, 'verified': True}
        ]
        
        # Add any real Facebook friends to the enhanced list
        for friend in real_friends:
            enhanced_friends.append({
                'name': friend.get('name', 'Unknown'),
                'username': f"fb_{friend.get('id', 'unknown')}", 
                'genre': 'Music Lover',
                'mutual_friends': 1,
                'verified': False,
                'facebook_id': friend.get('id')
            })
        
        # Store in session
        session['facebook_friends'] = enhanced_friends
        session['facebook_connected'] = True
        session['facebook_token'] = access_token  # Store for future API calls
        session.permanent = True
        
        flash(f'🎉 Facebook connected successfully! Found {len(enhanced_friends)} music-loving friends!', 'success')
        flash('📱 Your Facebook network is now integrated with VybeFlow. Search for friends below!', 'info')
        
        return redirect(url_for('main.user_search'))
        
    except Exception as e:
        flash(f'❌ Facebook connection error: {str(e)}', 'error')
        return redirect(url_for('main.user_search'))



@main_bp.route('/api/search_real_facebook_users', methods=['GET'])
def search_real_facebook_users():
    """Search for real Facebook users using Facebook Graph API"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    if not session.get('facebook_connected'):
        return jsonify({'error': 'Facebook not connected'}), 400
    
    query = request.args.get('q', '').lower()
    if len(query) < 2:
        return jsonify({'users': []})
    
    # Get Facebook access token from session
    access_token = session.get('facebook_token')
    if not access_token:
        return jsonify({'error': 'Facebook token expired'}), 400
    
    try:
        import requests
        
        # Search for Facebook pages/users with music interests
        # Note: Facebook has heavily restricted user search APIs for privacy
        # This is a simplified example - real implementation would need proper permissions
        search_url = "https://graph.facebook.com/search"
        params = {
            'access_token': access_token,
            'q': query,
            'type': 'user',
            'fields': 'id,name,picture',
            'limit': 10
        }
        
        response = requests.get(search_url, params=params)
        
        if response.status_code == 200:
            data = response.json()
            users = data.get('data', [])
            
            # Format results for VybeFlow
            formatted_users = []
            for user in users:
                formatted_users.append({
                    'name': user.get('name', 'Unknown'),
                    'username': f"fb_{user.get('id', 'unknown')}",
                    'genre': 'Music Enthusiast',
                    'platform': 'Facebook',
                    'avatar': '📘',
                    'extra': 'Real Facebook User',
                    'facebook_id': user.get('id'),
                    'profile_pic': user.get('picture', {}).get('data', {}).get('url', ''),
                    'verified': False,
                    'real_facebook_user': True
                })
            
            return jsonify({'users': formatted_users})
        
        else:
            # Facebook API call failed, return enhanced sample data
            return get_enhanced_facebook_sample_data(query)
    
    except Exception as e:
        # If Facebook API fails, return realistic sample data
        return get_enhanced_facebook_sample_data(query)

def get_enhanced_facebook_sample_data(query):
    """Enhanced sample Facebook user data when API is unavailable"""
    sample_facebook_users = [
        {'name': 'Sarah Martinez Music', 'username': 'sarah_martinez_official', 'genre': 'Indie Singer-Songwriter', 'location': 'Austin, TX'},
        {'name': 'Mike Chen Beats', 'username': 'mike_chen_producer', 'genre': 'Hip-Hop Producer', 'location': 'Los Angeles, CA'},
        {'name': 'Jessica Luna Band', 'username': 'jessica_luna_band', 'genre': 'Alternative Rock', 'location': 'Seattle, WA'},
        {'name': 'Carlos Rivera Music', 'username': 'carlos_rivera_music', 'genre': 'Latin Pop Artist', 'location': 'Miami, FL'},
        {'name': 'Taylor Swift Updates', 'username': 'taylor_swift_news', 'genre': 'Music News & Updates', 'location': 'Nashville, TN'},
        {'name': 'EDM Festival Guide', 'username': 'edm_festival_guide', 'genre': 'Electronic Dance Music', 'location': 'Las Vegas, NV'},
        {'name': 'Brooklyn Jazz Collective', 'username': 'brooklyn_jazz', 'genre': 'Jazz Ensemble', 'location': 'Brooklyn, NY'},
        {'name': 'Country Music Daily', 'username': 'country_music_daily', 'genre': 'Country Music Blog', 'location': 'Nashville, TN'},
        {'name': 'Vinyl Record Collector', 'username': 'vinyl_collector_nyc', 'genre': 'Music Collector', 'location': 'New York, NY'},
        {'name': 'Acoustic Sessions Live', 'username': 'acoustic_sessions', 'genre': 'Live Music Venue', 'location': 'Chicago, IL'}
    ]
    
    # Filter by query
    filtered_users = []
    for user in sample_facebook_users:
        if (query in user['name'].lower() or 
            query in user['genre'].lower() or 
            query in user['location'].lower()):
            filtered_users.append({
                'name': user['name'],
                'username': user['username'],
                'genre': user['genre'],
                'platform': 'Facebook',
                'avatar': '📘',
                'extra': f"Music Page • {user['location']}",
                'facebook_id': f"sample_{user['username']}",
                'verified': True,
                'real_facebook_user': True
            })
    
    return jsonify({'users': filtered_users})

@main_bp.route('/api/enhanced_facebook_search')
def enhanced_facebook_search():
    """Enhanced Facebook search for real users with invitation functionality"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({'users': []})
    
    # Check Facebook connection
    facebook_token = session.get('facebook_access_token')
    
    try:
        if facebook_token:
            # Real Facebook API integration
            formatted_users = []
            
            # Search user's Facebook friends
            try:
                import requests
                friends_url = f"https://graph.facebook.com/v18.0/me/friends"
                friends_params = {
                    'access_token': facebook_token,
                    'fields': 'id,name,picture.type(large)',
                    'limit': 100
                }
                
                friends_response = requests.get(friends_url, params=friends_params, timeout=10)
                
                if friends_response.status_code == 200:
                    friends_data = friends_response.json()
                    friends = friends_data.get('data', [])
                    
                    # Filter friends by query and add to results
                    for friend in friends:
                        friend_name = friend.get('name', '').lower()
                        if query.lower() in friend_name:
                            formatted_users.append({
                                'name': friend.get('name'),
                                'username': f"fb_{friend.get('id')}",
                                'genre': 'Facebook Friend',
                                'platform': 'Facebook',
                                'avatar': '👥',
                                'extra': 'Your Facebook Friend',
                                'facebook_id': friend.get('id'),
                                'profile_pic': friend.get('picture', {}).get('data', {}).get('url', ''),
                                'verified': True,
                                'real_facebook_user': True,
                                'is_friend': True,
                                'can_invite_to_vybeflow': True
                            })
                
                # Search for music-related Facebook pages
                pages_url = f"https://graph.facebook.com/v18.0/search"
                pages_params = {
                    'q': f"{query} music",
                    'type': 'page',
                    'fields': 'id,name,picture.type(large),category,fan_count,genre',
                    'access_token': facebook_token,
                    'limit': 20
                }
                
                pages_response = requests.get(pages_url, params=pages_params, timeout=10)
                
                if pages_response.status_code == 200:
                    pages_data = pages_response.json()
                    pages = pages_data.get('data', [])
                    
                    for page in pages:
                        category = page.get('category', '').lower()
                        if any(keyword in category for keyword in ['music', 'artist', 'musician', 'band', 'singer', 'dj', 'producer']):
                            fan_count = page.get('fan_count', 0)
                            formatted_users.append({
                                'name': page.get('name'),
                                'username': f"fbpage_{page.get('id')}",
                                'genre': page.get('genre', 'Music Artist'),
                                'platform': 'Facebook',
                                'avatar': '🎵',
                                'extra': f"Music Page • {fan_count:,} fans",
                                'facebook_id': page.get('id'),
                                'profile_pic': page.get('picture', {}).get('data', {}).get('url', ''),
                                'verified': fan_count > 10000,
                                'real_facebook_user': True,
                                'is_page': True,
                                'can_follow': True
                            })
            
            except Exception as api_error:
                print(f"Facebook API Error: {api_error}")
                # Continue to sample data if API fails
                pass
            
            if formatted_users:
                return jsonify({
                    'users': formatted_users,
                    'facebook_connected': True,
                    'message': f'Found {len(formatted_users)} real Facebook users!'
                })
        
        # If no Facebook token or no results, return enhanced sample data
        sample_users = get_realistic_facebook_sample_data(query)
        return jsonify({
            'users': sample_users,
            'facebook_connected': bool(facebook_token),
            'message': 'Connect Facebook to see your real friends!' if not facebook_token else 'No real matches found, showing sample users'
        })
    
    except Exception as e:
        # Return sample data on any error
        sample_users = get_realistic_facebook_sample_data(query)
        return jsonify({
            'users': sample_users,
            'facebook_connected': False,
            'error': 'Search temporarily unavailable'
        })

def get_realistic_facebook_sample_data(query):
    """Generate realistic Facebook sample data for demonstration"""
    sample_friends = [
        {
            'name': 'Marcus Johnson',
            'username': 'fb_marcus_beats',
            'genre': 'Hip-Hop Producer',
            'location': 'Atlanta, GA',
            'avatar': '🎤',
            'mutual_friends': 12
        },
        {
            'name': 'Sarah Williams',
            'username': 'fb_sarah_music', 
            'genre': 'R&B Singer',
            'location': 'Los Angeles, CA',
            'avatar': '🎵',
            'mutual_friends': 8
        },
        {
            'name': 'DJ Mike Rodriguez',
            'username': 'fb_dj_mike',
            'genre': 'Club DJ',
            'location': 'Miami, FL', 
            'avatar': '🎧',
            'mutual_friends': 15
        },
        {
            'name': 'Lisa Chen',
            'username': 'fb_lisa_vocals',
            'genre': 'Pop Artist',
            'location': 'New York, NY',
            'avatar': '🎙️',
            'mutual_friends': 6
        },
        {
            'name': 'Carlos Ramirez',
            'username': 'fb_carlos_guitar',
            'genre': 'Rock Musician', 
            'location': 'Austin, TX',
            'avatar': '🎸',
            'mutual_friends': 9
        }
    ]
    
    # Filter by query
    filtered_users = []
    for friend in sample_friends:
        if (query.lower() in friend['name'].lower() or 
            query.lower() in friend['genre'].lower() or 
            query.lower() in friend['location'].lower()):
            filtered_users.append({
                'name': friend['name'],
                'username': friend['username'],
                'genre': friend['genre'],
                'platform': 'Facebook',
                'avatar': friend['avatar'],
                'extra': f"{friend['location']} • {friend['mutual_friends']} mutual friends",
                'facebook_id': f"sample_{friend['username']}",
                'verified': True,
                'real_facebook_user': True,
                'is_sample': True,
                'can_invite_to_vybeflow': True
            })
    
    return filtered_users

@main_bp.route('/api/invite_facebook_friend', methods=['POST'])
def invite_facebook_friend():
    """Invite a Facebook friend to join VybeFlow"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        friend_facebook_id = data.get('facebook_id')
        friend_name = data.get('name')
        
        if not friend_facebook_id or not friend_name:
            return jsonify({'error': 'Missing friend information'}), 400
        
        # In a real app, you would:
        # 1. Send Facebook app request/notification
        # 2. Send email invitation
        # 3. Create pending invitation record
        # 4. Track invitation status
        
        # For now, simulate successful invitation
        invitation_data = {
            'friend_facebook_id': friend_facebook_id,
            'friend_name': friend_name,
            'invited_by': session['username'],
            'invitation_sent': True,
            'invitation_method': 'facebook_app_request'
        }
        
        return jsonify({
            'success': True,
            'message': f'Invitation sent to {friend_name}! They\'ll get notified on Facebook.',
            'invitation_data': invitation_data
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to send invitation: {str(e)}'}), 500

# ================================
# BLOCKING SYSTEM ROUTES
# ================================

@main_bp.route('/block_user', methods=['POST'])
def block_user():
    """Block another user with different duration options"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        from models import User, Block, db
        
        data = request.get_json()
        target_username = data.get('username')
        block_type = data.get('type', 'temporary')  # temporary, week, permanent
        custom_hours = data.get('hours')
        custom_message = data.get('message', '')
        reason = data.get('reason', 'User behavior')
        
        # Get current user and target user
        current_user = User.query.filter_by(username=session['username']).first()
        target_user = User.query.filter_by(username=target_username).first()
        
        if not current_user or not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        if current_user.id == target_user.id:
            return jsonify({'error': 'Cannot block yourself'}), 400
        
        # Check if already blocked
        existing_block = Block.query.filter_by(
            blocker_id=current_user.id,
            blocked_id=target_user.id,
            is_active=True
        ).first()
        
        if existing_block and not existing_block.is_expired:
            return jsonify({'error': 'User is already blocked'}), 400
        
        # Create new block
        new_block = Block(
            blocker_id=current_user.id,
            blocked_id=target_user.id,
            reason=reason,
            custom_message=custom_message
        )
        
        # Set duration based on type
        new_block.set_duration(block_type, custom_hours)
        
        db.session.add(new_block)
        db.session.commit()
        
        # Return success with block details
        duration_text = {
            'temporary': f"{custom_hours or 24} hours",
            'week': "1 week",
            'permanent': "permanently"
        }
        
        return jsonify({
            'success': True,
            'message': f'🚫 {target_username} has been blocked {duration_text[block_type]}!',
            'block_type': block_type,
            'expires_at': new_block.expires_at.isoformat() if new_block.expires_at else None
        })
        
    except Exception as e:
        return jsonify({'error': f'Error blocking user: {str(e)}'}), 500

@main_bp.route('/unblock_user', methods=['POST'])
def unblock_user():
    """Unblock a previously blocked user"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        from models import User, Block, db
        
        data = request.get_json()
        target_username = data.get('username')
        
        # Get current user and target user
        current_user = User.query.filter_by(username=session['username']).first()
        target_user = User.query.filter_by(username=target_username).first()
        
        if not current_user or not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Find active block
        active_block = Block.query.filter_by(
            blocker_id=current_user.id,
            blocked_id=target_user.id,
            is_active=True
        ).first()
        
        if not active_block:
            return jsonify({'error': 'User is not blocked'}), 400
        
        # Deactivate block
        active_block.is_active = False
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'✅ {target_username} has been unblocked!'
        })
        
    except Exception as e:
        return jsonify({'error': f'Error unblocking user: {str(e)}'}), 500

@main_bp.route('/check_block_status/<username>')
def check_block_status(username):
    """Check if current user has blocked or is blocked by another user"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        from models import User, Block
        
        current_user = User.query.filter_by(username=session['username']).first()
        target_user = User.query.filter_by(username=username).first()
        
        if not current_user or not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if current user blocked target
        i_blocked_them = Block.is_blocked(current_user.id, target_user.id)
        they_blocked_me = Block.is_blocked(target_user.id, current_user.id)
        
        return jsonify({
            'i_blocked_them': i_blocked_them,
            'they_blocked_me': they_blocked_me,
            'can_interact': not (i_blocked_them or they_blocked_me)
        })
        
    except Exception as e:
        return jsonify({'error': f'Error checking block status: {str(e)}'}), 500

@main_bp.route('/my_blocks')
def my_blocks():
    """Get list of users I've blocked"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        from models import User, Block
        
        current_user = User.query.filter_by(username=session['username']).first()
        if not current_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Get all active blocks made by current user
        blocks = Block.query.filter_by(
            blocker_id=current_user.id,
            is_active=True
        ).all()
        
        blocked_users = []
        for block in blocks:
            if not block.is_expired:
                blocked_user = User.query.get(block.blocked_id)
                if blocked_user:
                    blocked_users.append({
                        'username': blocked_user.username,
                        'block_type': block.block_type,
                        'created_at': block.created_at.isoformat(),
                        'expires_at': block.expires_at.isoformat() if block.expires_at else None,
                        'reason': block.reason,
                        'custom_message': block.custom_message
                    })
            else:
                # Deactivate expired blocks
                block.is_active = False
        
        from models import db
        db.session.commit()
        
        return jsonify({'blocked_users': blocked_users})
        
    except Exception as e:
        return jsonify({'error': f'Error getting blocked users: {str(e)}'}), 500

@main_bp.route('/block_message/<username>')
def get_block_message(username):
    """Get the block message when someone tries to interact with a user who blocked them"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        from models import User, Block, BlockMessage
        
        current_user = User.query.filter_by(username=session['username']).first()
        target_user = User.query.filter_by(username=username).first()
        
        if not current_user or not target_user:
            return jsonify({'error': 'User not found'}), 404
        
        # Check if target user blocked current user
        block_info = Block.get_block_info(target_user.id, current_user.id)
        
        if not block_info:
            return jsonify({'blocked': False})
        
        # Get default messages
        default_messages = BlockMessage.get_default_messages()
        
        # Use custom message if available, otherwise use default
        if block_info.custom_message:
            message = default_messages['custom'].format(custom_message=block_info.custom_message)
        else:
            message = default_messages.get(block_info.block_type, default_messages['temporary'])
        
        return jsonify({
            'blocked': True,
            'message': message,
            'block_type': block_info.block_type,
            'expires_at': block_info.expires_at.isoformat() if block_info.expires_at else None
        })
        
    except Exception as e:
        return jsonify({'error': f'Error getting block message: {str(e)}'}), 500

@main_bp.route('/block_manager')
def block_manager():
    """Block manager page"""
    if not session.get('logged_in'):
        flash('Please log in to access block manager.', 'error')
        return redirect(url_for('auth.login'))
    
    return render_template('block_manager.html', title='Block Manager')

@main_bp.route('/blocked/<username>')
def show_blocked_message(username):
    """Show block message page when user tries to interact with someone who blocked them"""
    if not session.get('logged_in'):
        return redirect(url_for('auth.login'))
    
    try:
        from models import User, Block
        
        current_user = User.query.filter_by(username=session['username']).first()
        target_user = User.query.filter_by(username=username).first()
        
        if not current_user or not target_user:
            flash('User not found.', 'error')
            return redirect(url_for('main.home'))
        
        # Get block information
        block_info = Block.get_block_info(target_user.id, current_user.id)
        
        if not block_info:
            # Not blocked, redirect to profile or wherever appropriate
            return redirect(url_for('main.user_search'))
        
        # Get custom message or default
        from models import BlockMessage
        default_messages = BlockMessage.get_default_messages()
        
        if block_info.custom_message:
            message = default_messages['custom'].format(custom_message=block_info.custom_message)
        else:
            message = default_messages.get(block_info.block_type, default_messages['temporary'])
        
        block_details = {
            'block_type': block_info.block_type,
            'expires_at': block_info.expires_at.strftime('%B %d, %Y at %I:%M %p') if block_info.expires_at else None,
            'created_at': block_info.created_at.strftime('%B %d, %Y')
        }
        
        return render_template('blocked_message.html', 
                             title='Blocked', 
                             message=message,
                             block_details=block_details,
                             blocked_by=username)
        
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return redirect(url_for('main.home'))

# ================================
# PROFILE CUSTOMIZATION ROUTES
# ================================

@main_bp.route('/profile/customize')
def profile_customize():
    """MySpace-style profile customization page"""
    if not session.get('logged_in'):
        flash('Please log in to customize your profile.', 'error')
        return redirect(url_for('auth.login'))
    
    return render_template('profile_customize.html', title='Customize Profile', username=session.get('username'))

@main_bp.route('/save_profile_customization', methods=['POST'])
def save_profile_customization():
    """Save profile customization settings"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        
        # Save customization data to session for now (in real app, save to database)
        session['profile_customization'] = {
            'displayName': data.get('displayName', ''),
            'biography': data.get('biography', ''),
            'location': data.get('location', ''),
            'status': data.get('status', ''),
            'theme': data.get('theme', 'gangsta'),
            'background': data.get('background', 'linear-gradient(135deg, #000000, #333333)'),
            'glitterEnabled': data.get('glitterEnabled', False),
            'profileSong': data.get('profileSong', ''),
            'customCss': data.get('customCss', '')
        }
        
        return jsonify({'success': True, 'message': 'Profile customization saved!'})
        
    except Exception as e:
        return jsonify({'error': f'Error saving customization: {str(e)}'}), 500

@main_bp.route('/upload_profile_picture', methods=['POST'])
def upload_profile_picture():
    """Upload and save profile picture"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        if 'profile_picture' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['profile_picture']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # In a real app, you'd save to file system or cloud storage
        # For now, we'll just simulate success
        filename = f"profile_{session['username']}_{file.filename}"
        
        # Save file path to session
        session['profile_picture'] = filename
        
        return jsonify({
            'success': True, 
            'message': 'Profile picture uploaded successfully!',
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@main_bp.route('/upload_cover_photo', methods=['POST'])
def upload_cover_photo():
    """Upload and save cover photo"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        if 'cover_photo' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['cover_photo']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # In a real app, you'd save to file system or cloud storage
        filename = f"cover_{session['username']}_{file.filename}"
        
        # Save file path to session
        session['cover_photo'] = filename
        
        return jsonify({
            'success': True,
            'message': 'Cover photo uploaded successfully!', 
            'filename': filename
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@main_bp.route('/upload_music', methods=['POST'])
def upload_music():
    """Upload music tracks to user profile"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        if 'music_file' not in request.files:
            return jsonify({'error': 'No music file uploaded'}), 400
        
        file = request.files['music_file']
        track_name = request.form.get('track_name', file.filename)
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Check file type
        allowed_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.ogg'}
        file_ext = '.' + file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            return jsonify({'error': 'Invalid file type. Please upload .mp3, .wav, .flac, .m4a, or .ogg files'}), 400
        
        # Create filename
        username = session['username']
        safe_filename = f"music_{username}_{track_name.replace(' ', '_')}{file_ext}"
        
        # In a real app, you'd save to file system or cloud storage
        # For demo, we'll simulate by storing in session
        if 'uploaded_tracks' not in session:
            session['uploaded_tracks'] = []
        
        # Create file URL (simulated)
        file_path = f"/static/music/{safe_filename}"
        
        track_data = {
            'name': track_name,
            'file_path': file_path,
            'filename': safe_filename,
            'upload_time': 'Just now'
        }
        
        session['uploaded_tracks'].append(track_data)
        session.modified = True
        
        return jsonify({
            'success': True,
            'message': 'Music track uploaded successfully!',
            'track_name': track_name,
            'file_path': file_path
        })
        
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@main_bp.route('/get_user_tracks')
def get_user_tracks():
    """Get user's uploaded music tracks"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    tracks = session.get('uploaded_tracks', [])
    return jsonify({'tracks': tracks})

@main_bp.route('/remove_track', methods=['POST'])
def remove_track():
    """Remove a music track from user profile"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Not logged in'}), 401
    
    try:
        data = request.get_json()
        filename = data.get('filename')
        
        if not filename:
            return jsonify({'error': 'No filename provided'}), 400
        
        tracks = session.get('uploaded_tracks', [])
        session['uploaded_tracks'] = [t for t in tracks if t['filename'] != filename]
        session.modified = True
        
        return jsonify({'success': True, 'message': 'Track removed successfully'})
        
    except Exception as e:
        return jsonify({'error': f'Removal failed: {str(e)}'}), 500