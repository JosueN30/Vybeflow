from flask import Blueprint, request, jsonify
from src.models.emoji import Emoji
from src import db
from flask_login import login_required, current_user

emoji_bp = Blueprint('emoji', __name__)

@emoji_bp.route('/emojis', methods=['GET'])
@login_required
def get_emojis():
    emojis = Emoji.query.filter_by(user_id=current_user.id).all()
    return jsonify([{'id': emoji.id, 'emoji_character': emoji.emoji_character} for emoji in emojis])

@emoji_bp.route('/emojis', methods=['POST'])
@login_required
def add_emoji():
    data = request.get_json()
    new_emoji = Emoji(user_id=current_user.id, emoji_character=data['emoji_character'])
    db.session.add(new_emoji)
    db.session.commit()
    return jsonify({'id': new_emoji.id, 'emoji_character': new_emoji.emoji_character}), 201

@emoji_bp.route('/emojis/<int:emoji_id>', methods=['PUT'])
@login_required
def edit_emoji(emoji_id):
    data = request.get_json()
    emoji = Emoji.query.get_or_404(emoji_id)
    if emoji.user_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403
    emoji.emoji_character = data['emoji_character']
    db.session.commit()
    return jsonify({'id': emoji.id, 'emoji_character': emoji.emoji_character})

@emoji_bp.route('/emojis/<int:emoji_id>', methods=['DELETE'])
@login_required
def delete_emoji(emoji_id):
    emoji = Emoji.query.get_or_404(emoji_id)
    if emoji.user_id != current_user.id:
        return jsonify({'message': 'Unauthorized'}), 403
    db.session.delete(emoji)
    db.session.commit()
    return jsonify({'message': 'Emoji deleted successfully'})