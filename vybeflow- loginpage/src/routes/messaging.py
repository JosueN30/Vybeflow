from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from ..models.user import User
from .. import db

messaging_bp = Blueprint('messaging', __name__)

@messaging_bp.route('/messages', methods=['GET', 'POST'])
@login_required
def messages():
    if request.method == 'POST':
        # Logic to send a message
        content = request.form.get('content')
        receiver_id = request.form.get('receiver_id')
        if content and receiver_id:
            new_message = Message(sender_id=current_user.id, receiver_id=receiver_id, content=content)
            db.session.add(new_message)
            db.session.commit()
            flash('Message sent!', 'success')
        else:
            flash('Message content and receiver are required.', 'danger')
        return redirect(url_for('messaging.messages'))

    # Logic to retrieve messages for the current user
    received_messages = Message.query.filter_by(receiver_id=current_user.id).all()
    return render_template('chat.html', messages=received_messages)