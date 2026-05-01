from datetime import datetime, timezone
from typing import Optional

from models import (
    db,
    Challenge,
    ChallengeEntry,
    Post,
    PostCoAuthor,
    Room,
    Tip,
)


def create_duet_or_stitch_post(
    author_id: int,
    parent_post_id: int,
    duet_layout: str = "split",
    clip_start: Optional[int] = None,
    clip_end: Optional[int] = None,
    caption: Optional[str] = None,
    media_type: Optional[str] = None,
    media_url: Optional[str] = None,
    thumbnail_url: Optional[str] = None,
) -> Post:
    post = Post(
        author_id=author_id,
        parent_post_id=parent_post_id,
        duet_layout=duet_layout,
        clip_start=clip_start,
        clip_end=clip_end,
        caption=caption,
        media_type=media_type,
        media_url=media_url,
        thumbnail_url=thumbnail_url,
    )
    db.session.add(post)
    db.session.commit()
    return post


def add_post_co_author(post_id: int, user_id: int, role: str = "collaborator") -> PostCoAuthor:
    existing = PostCoAuthor.query.filter_by(post_id=post_id, user_id=user_id).first()
    if existing:
        return existing

    co_author = PostCoAuthor(post_id=post_id, user_id=user_id, role=role)
    db.session.add(co_author)
    db.session.commit()
    return co_author


def create_room(host_id: int, title: str, topic: Optional[str] = None, is_live: bool = True) -> Room:
    room = Room(
        host_id=host_id,
        title=title,
        topic=topic,
        is_live=is_live,
        started_at=datetime.now(timezone.utc),
    )
    db.session.add(room)
    db.session.commit()
    return room


def send_tip(
    sender_id: int,
    receiver_id: int,
    amount_cents: int,
    currency: str = "USD",
    post_id: Optional[int] = None,
    note: Optional[str] = None,
) -> Tip:
    if amount_cents <= 0:
        raise ValueError("amount_cents must be greater than zero")
    if sender_id == receiver_id:
        raise ValueError("sender and receiver must be different")

    tip = Tip(
        sender_id=sender_id,
        receiver_id=receiver_id,
        post_id=post_id,
        amount_cents=amount_cents,
        currency=currency,
        note=note,
    )
    db.session.add(tip)
    db.session.commit()
    return tip


def create_challenge(
    creator_id: int,
    title: str,
    description: Optional[str] = None,
    hashtag: Optional[str] = None,
    starts_at: Optional[datetime] = None,
    ends_at: Optional[datetime] = None,
    status: str = "active",
) -> Challenge:
    challenge = Challenge(
        creator_id=creator_id,
        title=title,
        description=description,
        hashtag=hashtag,
        starts_at=starts_at or datetime.now(timezone.utc),
        ends_at=ends_at,
        status=status,
    )
    db.session.add(challenge)
    db.session.commit()
    return challenge


def enter_challenge(
    challenge_id: int,
    user_id: int,
    post_id: int,
    caption: Optional[str] = None,
    score: int = 0,
) -> ChallengeEntry:
    existing = ChallengeEntry.query.filter_by(
        challenge_id=challenge_id,
        user_id=user_id,
        post_id=post_id,
    ).first()
    if existing:
        return existing

    entry = ChallengeEntry(
        challenge_id=challenge_id,
        user_id=user_id,
        post_id=post_id,
        caption=caption,
        score=score,
    )
    db.session.add(entry)
    db.session.commit()
    return entry
