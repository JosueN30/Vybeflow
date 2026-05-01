"""Quick diagnostic — run: python _diag.py"""
import sys, os
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from app import create_app
app, _socketio = create_app()
with app.app_context():
    from models import db, Post, User, Story
    pc = Post.query.count()
    uc = User.query.count()
    sc = Story.query.count()
    print(f"Users: {uc}  Posts: {pc}  Stories: {sc}")
    if pc:
        p = Post.query.order_by(Post.id.desc()).first()
        print(f"  Latest post id={p.id} vis={p.visibility!r} author_id={p.author_id} media_type={p.media_type!r}")
        u = User.query.get(p.author_id) if p.author_id else None
        print(f"  Author: {getattr(u,'username',None)!r}  avatar_url={getattr(u,'avatar_url',None)!r}")
    if uc:
        u = User.query.first()
        print(f"  First user: {u.username!r} avatar={u.avatar_url!r}")
    print("DONE")
