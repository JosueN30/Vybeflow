from flask import Blueprint, request, jsonify, render_template, redirect, url_for
from flask_login import login_required, current_user
from ..models.message import Message
from ..models.emoji import Emoji

messaging_bp = Blueprint('messaging', __name__)

@messaging_bp.route('/messages', methods=['GET'])
@login_required
def get_messages():
    messages = Message.query.filter((Message.sender_id == current_user.id) | (Message.recipient_id == current_user.id)).all()
    return jsonify([message.to_dict() for message in messages])

@messaging_bp.route('/messages', methods=['POST'])
@login_required
def send_message():
    data = request.get_json()
    new_message = Message(sender_id=current_user.id, recipient_id=data['recipient_id'], content=data['content'])
    new_message.save()
    return jsonify(new_message.to_dict()), 201

@messaging_bp.route('/customize_emoji', methods=['GET', 'POST'])
@login_required
def customize_emoji():
    if request.method == 'POST':
        emoji_data = request.form
        new_emoji = Emoji(name=emoji_data['name'], unicode=emoji_data['unicode'])
        new_emoji.save()
        return redirect(url_for('messaging.customize_emoji'))
    return render_template('customize_emoji.html')

# --- Signal Integration (stub) ---
@messaging_bp.route('/send_signal', methods=['POST'])
@login_required
def send_signal_message():
    data = request.get_json()
    # Integrate with Signal API here
    # Example: signal_send(data['recipient'], data['content'])
    return jsonify({"status": "Signal message sent"}), 200

# --- Telegram Integration (stub) ---
@messaging_bp.route('/send_telegram', methods=['POST'])
@login_required
def send_telegram_message():
    data = request.get_json()
    # Integrate with Telegram Bot API here
    # Example: telegram_send(data['recipient'], data['content'])
    return jsonify({"status": "Telegram message sent"}), 200

# --- Live Stream Feature (stub) ---
@messaging_bp.route('/live_stream', methods=['GET', 'POST'])
@login_required
def live_stream():
    if request.method == 'POST':
        # Start or interact with live stream
        return jsonify({"status": "Live stream started"}), 200
    return render_template('live_stream.html')
