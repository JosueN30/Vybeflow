from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_socketio import SocketIO, join_room, emit
import time
import uuid
import os
from pathlib import Path
from models import Post, User as DbUser
from utils.auth import get_session_username

# --- In-memory demo store (replace with DB) ---
STICKER_PACKS = [
    {
        "id": "vf-core",
        "name": "VybeFlow Core",
        "items": [
            {"id": "fire", "label": "🔥 Fire"},
            {"id": "vibe", "label": "✨ Vibe"},
            {"id": "wave", "label": "🌊 Wave"},
            {"id": "money", "label": "💸 Money"},
        ],
    },
    {
        "id": "memes",
        "name": "Memes + Roast",
        "items": [
            {"id": "cap", "label": "🧢 CAP"},
            {"id": "W", "label": "✅ W"},
            {"id": "L", "label": "❌ L"},
            {"id": "ratio", "label": "📉 ratio"},
        ],
    },
    {
        "id": "hype",
        "name": "Hype Pack",
        "items": [
            {"id": "heat", "label": "🔥"},
            {"id": "hundred", "label": "💯"},
            {"id": "spark", "label": "⚡"},
            {"id": "boom", "label": "💥"},
            {"id": "rocket", "label": "🚀"},
        ],
    },
    {
        "id": "vibes",
        "name": "Vibes",
        "items": [
            {"id": "stars", "label": "✨"},
            {"id": "moon", "label": "🌙"},
            {"id": "rainbow", "label": "🌈"},
            {"id": "sparkle", "label": "🪩"},
            {"id": "wave2", "label": "🌊"},
        ],
    },
    {
        "id": "love",
        "name": "Love",
        "items": [
            {"id": "heart", "label": "❤️"},
            {"id": "sparkheart", "label": "💖"},
            {"id": "kisses", "label": "😘"},
            {"id": "smile", "label": "🥰"},
            {"id": "eyes", "label": "😍"},
        ],
    },
    {
        "id": "street",
        "name": "Street",
        "items": [
            {"id": "ice", "label": "🧊"},
            {"id": "drip", "label": "💎"},
            {"id": "shades", "label": "🕶️"},
            {"id": "speaker", "label": "🔊"},
            {"id": "headphones", "label": "🎧"},
        ],
    },
    {
        "id": "animated",
        "name": "Animated",
        "items": [
            {"id": "fire", "label": "Fire", "type": "lottie", "src": "/static/lottie/fire.json"},
            {"id": "pulse", "label": "Pulse", "type": "lottie", "src": "/static/lottie/pulse.json"},
            {"id": "spin", "label": "Spin", "type": "lottie", "src": "/static/lottie/spin.json"},
            {"id": "bounce", "label": "Bounce", "type": "lottie", "src": "/static/lottie/bounce.json"},
            {"id": "spark", "label": "Spark", "type": "lottie", "src": "/static/lottie/spark.json"},
            {"id": "wave", "label": "Wave", "type": "lottie", "src": "/static/lottie/wave.json"},
            {"id": "glow", "label": "Glow", "type": "lottie", "src": "/static/lottie/glow.json"},
            {"id": "pop", "label": "Pop", "type": "lottie", "src": "/static/lottie/pop.json"},
            {"id": "heart", "label": "Heart", "type": "lottie", "src": "/static/lottie/heart.json"}
        ],
    },
]

# story_id -> state
STORY_STATE = {}  # { story_id: { "updated_at":..., "state": {...}} }


def register_story_routes(app):
    """Register story creation and collaboration routes"""

    # /story/create/<story_id>, /api/stickers/packs, /api/story/load,
    # /api/story/save, /api/captions/transcribe, /api/media/recents
    # are all registered by the story_routes Blueprint (routes/story_routes.py).
    # Only register the /stories/new redirect here since the Blueprint lacks it.

    @app.route("/stories/new")
    def stories_new():
        """Entry point used by the feed sidebar link.

        Creates a new story_id and redirects to the story editor so
        /stories/new is always a valid URL instead of 404.
        """
        story_id = uuid.uuid4().hex
        return redirect(url_for("story_routes.story_create", story_id=story_id))

    # ═══════════════════════════════════════════════════════════
    #  VYBEFLOW EXCLUSIVE STORY FEATURES
    # ═══════════════════════════════════════════════════════════

    # 1. Voice Commentary 🎤
    @app.route("/api/story/<int:story_id>/voice-commentary", methods=["POST"])
    def api_voice_commentary(story_id):
        """Record and attach voice commentary to a story."""
        from models import Story, VoiceCommentary
        from __init__ import db

        audio_file = request.files.get("audio")
        if not audio_file:
            return jsonify({"error": "Missing audio file"}), 400

        _ALLOWED_AUDIO_EXT = {"webm", "mp3", "ogg", "wav", "m4a", "aac"}
        _orig_ext = os.path.splitext(audio_file.filename or "")[1].lstrip(".").lower()
        if _orig_ext not in _ALLOWED_AUDIO_EXT:
            return jsonify({"error": "Unsupported audio format"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        story = db.session.get(Story, story_id)
        if not story:
            return jsonify({"error": "Story not found"}), 404

        upload_dir = os.path.join(app.root_path, "static", "uploads", "voice")
        os.makedirs(upload_dir, exist_ok=True)
        fname = f"voice_{story_id}_{uuid.uuid4().hex[:8]}.{_orig_ext}"
        fpath = os.path.join(upload_dir, fname)
        audio_file.save(fpath)
        audio_url = f"/static/uploads/voice/{fname}"

        try:
            duration = int(request.form.get("duration", 10))
        except (ValueError, TypeError):
            duration = 10
        vc = VoiceCommentary(story_id=story_id, author_id=user.id, audio_url=audio_url, duration_sec=min(duration, 30))
        db.session.add(vc)

        story.voice_commentary_url = audio_url
        story.voice_duration_sec = min(duration, 30)
        db.session.commit()

        return jsonify({"ok": True, "audio_url": audio_url}), 201

    @app.route("/api/story/<int:story_id>/voice-commentary", methods=["GET"])
    def api_get_voice_commentary(story_id):
        """Get voice commentaries for a story."""
        from models import VoiceCommentary
        vcs = VoiceCommentary.query.filter_by(story_id=story_id).all()
        return jsonify({"ok": True, "commentaries": [
            {"id": v.id, "audio_url": v.audio_url, "duration_sec": v.duration_sec,
             "author_id": v.author_id, "created_at": v.created_at.isoformat() if v.created_at else ""}
            for v in vcs
        ]})

    # 2. React With a Question ❓
    @app.route("/api/story/<int:story_id>/question", methods=["POST"])
    def api_story_question(story_id):
        """Post a question reaction to a story."""
        from models import Story, StoryQuestion
        from __init__ import db

        data = request.get_json(force=True) or {}
        question_text = (data.get("question") or "").strip()
        if not question_text or len(question_text) > 300:
            return jsonify({"error": "Question required (max 300 chars)"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        story = db.session.get(Story, story_id)
        if not story:
            return jsonify({"error": "Story not found"}), 404

        q = StoryQuestion(story_id=story_id, asker_id=user.id, question_text=question_text)
        db.session.add(q)
        db.session.commit()

        return jsonify({"ok": True, "question_id": q.id}), 201

    @app.route("/api/story/<int:story_id>/questions", methods=["GET"])
    def api_get_story_questions(story_id):
        """Get all questions asked on a story."""
        from models import StoryQuestion
        qs = StoryQuestion.query.filter_by(story_id=story_id).order_by(StoryQuestion.created_at.desc()).all()
        return jsonify({"ok": True, "questions": [
            {"id": q.id, "question": q.question_text, "asker_id": q.asker_id,
             "answer_story_id": q.answer_story_id, "created_at": q.created_at.isoformat() if q.created_at else ""}
            for q in qs
        ]})

    # 3. Decision Polls 🗳️
    @app.route("/api/story/<int:story_id>/poll", methods=["POST"])
    def api_create_decision_poll(story_id):
        """Create a decision poll on a story."""
        from models import Story, DecisionPoll
        from __init__ import db

        data = request.get_json(force=True) or {}
        question = (data.get("question") or "").strip()
        option_a = (data.get("option_a") or "").strip()
        option_b = (data.get("option_b") or "").strip()

        if not question or not option_a or not option_b:
            return jsonify({"error": "Question and both options required"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        story = db.session.get(Story, story_id)
        if not story:
            return jsonify({"error": "Story not found"}), 404

        poll = DecisionPoll(story_id=story_id, question=question, option_a=option_a, option_b=option_b)
        db.session.add(poll)
        db.session.commit()

        return jsonify({"ok": True, "poll_id": poll.id}), 201

    @app.route("/api/poll/<int:poll_id>/vote", methods=["POST"])
    def api_vote_decision_poll(poll_id):
        """Vote on a decision poll."""
        from models import DecisionPoll, DecisionPollVote
        from __init__ import db

        data = request.get_json(force=True) or {}
        choice = (data.get("choice") or "").strip().lower()
        if choice not in ("a", "b"):
            return jsonify({"error": "Choice must be 'a' or 'b'"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        poll = db.session.get(DecisionPoll, poll_id)
        if not poll:
            return jsonify({"error": "Poll not found"}), 404

        existing = DecisionPollVote.query.filter_by(poll_id=poll_id, voter_id=user.id).first()
        if existing:
            return jsonify({"error": "Already voted"}), 409

        vote = DecisionPollVote(poll_id=poll_id, voter_id=user.id, choice=choice)
        db.session.add(vote)
        if choice == "a":
            poll.votes_a += 1
        else:
            poll.votes_b += 1
        db.session.commit()

        return jsonify({"ok": True, "votes_a": poll.votes_a, "votes_b": poll.votes_b})

    @app.route("/api/story/<int:story_id>/poll", methods=["GET"])
    def api_get_decision_poll(story_id):
        """Get the decision poll for a story."""
        from models import DecisionPoll
        poll = DecisionPoll.query.filter_by(story_id=story_id).first()
        if not poll:
            return jsonify({"ok": True, "poll": None})
        return jsonify({"ok": True, "poll": {
            "id": poll.id, "question": poll.question, "option_a": poll.option_a, "option_b": poll.option_b,
            "votes_a": poll.votes_a, "votes_b": poll.votes_b
        }})

    # 4. Anonymous Confession Stories 🤫
    @app.route("/api/confessions", methods=["POST"])
    def api_create_confession():
        """Post an anonymous confession."""
        from models import AnonymousConfession
        from __init__ import db

        data = request.get_json(force=True) or {}
        text = (data.get("text") or "").strip()
        category = (data.get("category") or "general").strip().lower()
        if not text:
            return jsonify({"error": "Confession text required"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        # AI moderation on confession text
        try:
            from moderation_engine import moderate_text
            mod = moderate_text(text)
            if mod.decision in ("block",):
                return jsonify({"error": "Content violates community guidelines"}), 403
        except Exception:
            pass

        confession = AnonymousConfession(author_id=user.id, confession_text=text, category=category)
        db.session.add(confession)
        db.session.commit()

        return jsonify({"ok": True, "confession_id": confession.id}), 201

    @app.route("/api/confessions", methods=["GET"])
    def api_get_confessions():
        """Get recent anonymous confessions."""
        from models import AnonymousConfession
        try:
            limit = int(request.args.get("limit", 20))
        except (ValueError, TypeError):
            limit = 20
        confessions = AnonymousConfession.query.order_by(AnonymousConfession.created_at.desc()).limit(limit).all()
        return jsonify({"ok": True, "confessions": [
            {"id": c.id, "text": c.confession_text, "category": c.category,
             "likes": c.likes_count, "created_at": c.created_at.isoformat() if c.created_at else ""}
            for c in confessions
        ]})

    # 5. Location Mood Stories 🌎
    @app.route("/api/story/<int:story_id>/mood", methods=["POST"])
    def api_set_story_mood(story_id):
        """Tag a story with a mood/vibe instead of a location."""
        from models import Story, LocationMood
        from __init__ import db

        data = request.get_json(force=True) or {}
        mood = (data.get("mood") or "").strip()
        if not mood or len(mood) > 100:
            return jsonify({"error": "Mood required (max 100 chars)"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        story = db.session.get(Story, story_id)
        if not story:
            return jsonify({"error": "Story not found"}), 404

        story.mood_tag = mood
        lm = LocationMood(story_id=story_id, mood=mood)
        db.session.add(lm)
        db.session.commit()

        return jsonify({"ok": True})

    @app.route("/api/stories/by-mood", methods=["GET"])
    def api_stories_by_mood():
        """Browse stories by vibe/mood."""
        from models import LocationMood, Story
        from __init__ import db
        mood = (request.args.get("mood") or "").strip()
        if not mood:
            # Return distinct moods
            moods = db.session.query(LocationMood.mood).distinct().limit(50).all()
            return jsonify({"ok": True, "moods": [m[0] for m in moods]})
        mood_entries = LocationMood.query.filter(LocationMood.mood.ilike(f"%{mood}%")).limit(30).all()
        story_ids = [m.story_id for m in mood_entries]
        return jsonify({"ok": True, "story_ids": story_ids, "mood": mood})

    # 6. Story Debates ⚖️
    @app.route("/api/debates", methods=["POST"])
    def api_create_debate():
        """Start a story debate."""
        from models import StoryDebate
        from __init__ import db

        data = request.get_json(force=True) or {}
        topic = (data.get("topic") or "").strip()
        side_a_text = (data.get("side_a") or "").strip()

        if not topic or not side_a_text:
            return jsonify({"error": "Topic and your side required"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        debate = StoryDebate(topic=topic, side_a_user_id=user.id, side_a_text=side_a_text)
        db.session.add(debate)
        db.session.commit()

        return jsonify({"ok": True, "debate_id": debate.id}), 201

    @app.route("/api/debates/<int:debate_id>/join", methods=["POST"])
    def api_join_debate(debate_id):
        """Join the opposing side of a debate."""
        from models import StoryDebate
        from __init__ import db

        data = request.get_json(force=True) or {}
        side_b_text = (data.get("side_b") or "").strip()
        if not side_b_text:
            return jsonify({"error": "Your opposing argument required"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        debate = db.session.get(StoryDebate, debate_id)
        if not debate:
            return jsonify({"error": "Debate not found"}), 404
        if debate.side_b_user_id:
            return jsonify({"error": "Debate already has two sides"}), 409

        debate.side_b_user_id = user.id
        debate.side_b_text = side_b_text
        debate.status = "matched"
        db.session.commit()

        return jsonify({"ok": True})

    @app.route("/api/debates/<int:debate_id>/vote", methods=["POST"])
    def api_vote_debate(debate_id):
        """Vote on a side in a debate."""
        from models import StoryDebate
        from __init__ import db

        data = request.get_json(force=True) or {}
        side = (data.get("side") or "").strip().lower()
        if side not in ("a", "b"):
            return jsonify({"error": "Side must be 'a' or 'b'"}), 400

        debate = db.session.get(StoryDebate, debate_id)
        if not debate:
            return jsonify({"error": "Debate not found"}), 404

        if side == "a":
            debate.votes_a += 1
        else:
            debate.votes_b += 1
        db.session.commit()

        return jsonify({"ok": True, "votes_a": debate.votes_a, "votes_b": debate.votes_b})

    @app.route("/api/debates", methods=["GET"])
    def api_get_debates():
        """List open or matched debates."""
        from models import StoryDebate
        status = (request.args.get("status") or "open").strip()
        debates = StoryDebate.query.filter_by(status=status).order_by(StoryDebate.created_at.desc()).limit(20).all()
        return jsonify({"ok": True, "debates": [
            {"id": d.id, "topic": d.topic, "side_a": d.side_a_text, "side_b": d.side_b_text,
             "votes_a": d.votes_a, "votes_b": d.votes_b, "status": d.status}
            for d in debates
        ]})

    # 7. Reality Check Stories ✔️
    @app.route("/api/story/<int:story_id>/reality-check", methods=["POST"])
    def api_reality_check(story_id):
        """Mark a story with a reality check label."""
        from models import Story, RealityCheck
        from __init__ import db

        data = request.get_json(force=True) or {}
        label = (data.get("label") or "").strip().lower()
        if label not in ("verified", "opinion", "joke", "rumor"):
            return jsonify({"error": "Label must be: verified, opinion, joke, or rumor"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        story = db.session.get(Story, story_id)
        if not story:
            return jsonify({"error": "Story not found"}), 404

        existing = RealityCheck.query.filter_by(story_id=story_id, set_by_id=user.id).first()
        if existing:
            existing.label = label
        else:
            rc = RealityCheck(story_id=story_id, label=label, set_by_id=user.id)
            db.session.add(rc)

        story.reality_label = label
        db.session.commit()

        return jsonify({"ok": True})

    @app.route("/api/story/<int:story_id>/reality-check", methods=["GET"])
    def api_get_reality_check(story_id):
        """Get reality check labels for a story."""
        from models import RealityCheck
        checks = RealityCheck.query.filter_by(story_id=story_id).all()
        label_counts = {}
        for c in checks:
            label_counts[c.label] = label_counts.get(c.label, 0) + 1
        return jsonify({"ok": True, "labels": label_counts})

    # 8. Continue the Story 📖
    @app.route("/api/story/<int:story_id>/continue", methods=["POST"])
    def api_continue_story(story_id):
        """Add a chapter to continue a collaborative story."""
        from models import Story, StoryChapter
        from __init__ import db
        import hashlib

        data = request.get_json(force=True) or {}
        caption = (data.get("caption") or "").strip()
        if not caption:
            return jsonify({"error": "Chapter text required"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        parent = db.session.get(Story, story_id)
        if not parent:
            return jsonify({"error": "Parent story not found"}), 404

        parent.is_collab_chain = True

        last_chapter = StoryChapter.query.filter_by(parent_story_id=story_id).order_by(StoryChapter.chapter_number.desc()).first()
        next_num = (last_chapter.chapter_number + 1) if last_chapter else 2

        new_story = Story(author_id=user.id, user_id=user.id, caption=caption, visibility="Public", is_collab_chain=True)
        db.session.add(new_story)
        db.session.flush()

        chapter = StoryChapter(parent_story_id=story_id, chapter_story_id=new_story.id, author_id=user.id, chapter_number=next_num)
        db.session.add(chapter)
        db.session.commit()

        return jsonify({"ok": True, "chapter_number": next_num, "chapter_story_id": new_story.id}), 201

    @app.route("/api/story/<int:story_id>/chapters", methods=["GET"])
    def api_get_story_chapters(story_id):
        """Get all chapters of a collaborative story."""
        from models import StoryChapter, Story
        from __init__ import db
        chapters = StoryChapter.query.filter_by(parent_story_id=story_id).order_by(StoryChapter.chapter_number).all()
        result = []
        for ch in chapters:
            s = db.session.get(Story, ch.chapter_story_id)
            result.append({
                "chapter_number": ch.chapter_number,
                "story_id": ch.chapter_story_id,
                "author_id": ch.author_id,
                "caption": s.caption if s else "",
                "created_at": ch.created_at.isoformat() if ch.created_at else ""
            })
        return jsonify({"ok": True, "chapters": result})

    # 9. Micro Challenges 🏆
    @app.route("/api/challenges", methods=["GET"])
    def api_get_challenges():
        """Get active micro challenges."""
        from models import MicroChallenge
        challenges = MicroChallenge.query.filter_by(active=True).order_by(MicroChallenge.created_at.desc()).limit(10).all()
        return jsonify({"ok": True, "challenges": [
            {"id": c.id, "prompt": c.prompt, "emoji": c.emoji,
             "created_at": c.created_at.isoformat() if c.created_at else ""}
            for c in challenges
        ]})

    @app.route("/api/challenges", methods=["POST"])
    def api_create_challenge():
        """Create a micro challenge (admin or any user)."""
        from models import MicroChallenge
        from __init__ import db

        data = request.get_json(force=True) or {}
        prompt = (data.get("prompt") or "").strip()
        emoji = (data.get("emoji") or "🏆").strip()
        if not prompt:
            return jsonify({"error": "Prompt required"}), 400

        challenge = MicroChallenge(prompt=prompt, emoji=emoji)
        db.session.add(challenge)
        db.session.commit()

        return jsonify({"ok": True, "challenge_id": challenge.id}), 201

    @app.route("/api/challenges/<int:challenge_id>/enter", methods=["POST"])
    def api_enter_challenge(challenge_id):
        """Enter a micro challenge."""
        from models import MicroChallenge, MicroChallengeEntry
        from __init__ import db

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        challenge = db.session.get(MicroChallenge, challenge_id)
        if not challenge or not challenge.active:
            return jsonify({"error": "Challenge not found or inactive"}), 404

        existing = MicroChallengeEntry.query.filter_by(challenge_id=challenge_id, user_id=user.id).first()
        if existing:
            return jsonify({"error": "Already entered"}), 409

        data = request.get_json(force=True) or {}
        entry = MicroChallengeEntry(challenge_id=challenge_id, user_id=user.id,
                               story_id=data.get("story_id"), media_url=data.get("media_url"))
        db.session.add(entry)
        db.session.commit()

        return jsonify({"ok": True, "entry_id": entry.id}), 201

    # 10. Truth Meter 🔎
    @app.route("/api/story/<int:story_id>/truth-meter", methods=["POST"])
    def api_truth_meter_vote(story_id):
        """Rate how believable a story is."""
        from models import Story, TruthMeter
        from __init__ import db

        data = request.get_json(force=True) or {}
        rating = (data.get("rating") or "").strip()
        if rating not in ("100_true", "sounds_fake", "probably_exaggerated"):
            return jsonify({"error": "Rating must be: 100_true, sounds_fake, or probably_exaggerated"}), 400

        username = get_session_username()
        user = DbUser.query.filter_by(username=username).first() if username else None
        if not user:
            return jsonify({"error": "Not logged in"}), 401

        story = db.session.get(Story, story_id)
        if not story:
            return jsonify({"error": "Story not found"}), 404

        existing = TruthMeter.query.filter_by(story_id=story_id, voter_id=user.id).first()
        if existing:
            existing.rating = rating
        else:
            tm = TruthMeter(story_id=story_id, voter_id=user.id, rating=rating)
            db.session.add(tm)
        db.session.commit()

        return jsonify({"ok": True})

    @app.route("/api/story/<int:story_id>/truth-meter", methods=["GET"])
    def api_get_truth_meter(story_id):
        """Get truth meter results for a story."""
        from models import TruthMeter
        votes = TruthMeter.query.filter_by(story_id=story_id).all()
        results = {"100_true": 0, "sounds_fake": 0, "probably_exaggerated": 0}
        for v in votes:
            if v.rating in results:
                results[v.rating] += 1
        total = sum(results.values())
        return jsonify({"ok": True, "results": results, "total": total})


def register_story_socketio(socketio):
    """Register Socket.IO events for real-time story collaboration"""

    @socketio.on("join")
    def on_join(data):
        story_id = data.get("story_id")
        user = data.get("user") or {"id": str(uuid.uuid4())[:8], "name": "Anon"}
        if not story_id:
            return
        join_room(story_id)
        emit("presence", {"type": "join", "user": user}, room=story_id)

    @socketio.on("patch")
    def on_patch(data):
        """
        data: { story_id, patch, user }
        patch is a small update the clients apply.
        """
        story_id = data.get("story_id")
        patch = data.get("patch")
        user = data.get("user")
        if not story_id or not patch:
            return
        emit("patch", {"patch": patch, "user": user}, room=story_id, include_self=False)
