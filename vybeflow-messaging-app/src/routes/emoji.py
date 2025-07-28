from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from ..models.emoji import Emoji
from .. import db

emoji_bp = Blueprint('emoji', __name__)

@emoji_bp.route('/customize_emoji', methods=['GET', 'POST'])
@login_required
def customize_emoji():
    if request.method == 'POST':
        emoji_name = request.form.get('emoji_name')
        emoji_unicode = request.form.get('emoji_unicode')
        
        if emoji_name and emoji_unicode:
            new_emoji = Emoji(name=emoji_name, unicode=emoji_unicode)
            db.session.add(new_emoji)
            db.session.commit()
            flash('Emoji added successfully!', 'success')
            return redirect(url_for('emoji.customize_emoji'))
        else:
            flash('Please provide both name and unicode for the emoji.', 'danger')

    emojis = Emoji.query.all()
    return render_template('customize_emoji.html', emojis=emojis)

@emoji_bp.route('/delete_emoji/<int:emoji_id>', methods=['POST'])
@login_required
def delete_emoji(emoji_id):
    emoji = Emoji.query.get(emoji_id)
    if emoji:
        db.session.delete(emoji)
        db.session.commit()
        flash('Emoji deleted successfully!', 'success')
    else:
        flash('Emoji not found.', 'danger')
    return redirect(url_for('emoji.customize_emoji'))