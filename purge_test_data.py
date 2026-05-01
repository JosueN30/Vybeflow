"""
purge_test_data.py — VybeFlow Production Cleanup Utility
=========================================================
Permanently deletes all test / smoke-test / dummy / fake accounts and their
associated posts, comments, reactions, threads, and messages.

Usage:
    python purge_test_data.py           # dry-run (prints what WOULD be deleted)
    python purge_test_data.py --confirm # actually deletes (irreversible)

Patterns purged (case-insensitive, matched against username AND email):
    _smoketest_*  |  test_*  |  *_test  |  dummy*  |  fake*  |  *@vybeflow.local (guest accounts)
"""

from __future__ import annotations

import argparse
import re
import sys

# ── Patterns that identify test / bot accounts ─────────────────────────────
TEST_USERNAME_PATTERNS: list[re.Pattern] = [
    re.compile(r"^_smoketest", re.IGNORECASE),
    re.compile(r"^test[_\-]?", re.IGNORECASE),
    re.compile(r"[_\-]test$", re.IGNORECASE),
    re.compile(r"^dummy", re.IGNORECASE),
    re.compile(r"^fake", re.IGNORECASE),
    re.compile(r"^qa[_\-]", re.IGNORECASE),
    re.compile(r"^devtest", re.IGNORECASE),
    # DM / audit test accounts created by test scripts
    re.compile(r"^sender_\d{10,}", re.IGNORECASE),
    re.compile(r"^receiver_\d{10,}", re.IGNORECASE),
    re.compile(r"^audit_sender_", re.IGNORECASE),
    re.compile(r"^audit_recip_", re.IGNORECASE),
    re.compile(r"^vault_rl", re.IGNORECASE),
    re.compile(r"^vault_pepper", re.IGNORECASE),
    re.compile(r"^vault_serial", re.IGNORECASE),
    re.compile(r"^strike_log_", re.IGNORECASE),
]

TEST_EMAIL_PATTERNS: list[re.Pattern] = [
    re.compile(r"@vybeflow\.local$", re.IGNORECASE),  # auto-provisioned guest accounts
    re.compile(r"@test\.local$", re.IGNORECASE),       # DM send-block test accounts
    re.compile(r"@audit\.local$", re.IGNORECASE),      # security audit test accounts
    re.compile(r"^test.*@", re.IGNORECASE),
    re.compile(r"^dummy.*@", re.IGNORECASE),
    re.compile(r"^fake.*@", re.IGNORECASE),
]

TEST_CAPTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"\bsmoketest\b", re.IGNORECASE),
    re.compile(r"\bqa[_\-]?test\b", re.IGNORECASE),
    re.compile(r"full.armor qa test", re.IGNORECASE),
]


def _is_test_user(user) -> bool:
    """Return True if this user matches any test-account pattern."""
    uname = (user.username or "").strip()
    email = (user.email or "").strip()
    for pat in TEST_USERNAME_PATTERNS:
        if pat.search(uname):
            return True
    for pat in TEST_EMAIL_PATTERNS:
        if pat.search(email):
            return True
    return False


def _is_test_post(post) -> bool:
    """Return True if this post caption matches a test-content pattern."""
    caption = (post.caption or "")
    for pat in TEST_CAPTION_PATTERNS:
        if pat.search(caption):
            return True
    return False


def _get_user_fk_cols(db, table_name: str) -> list[str]:
    """Return column names in *table_name* that look like user foreign keys."""
    from sqlalchemy import inspect as _inspect
    try:
        inspector = _inspect(db.engine)
        cols = [c["name"] for c in inspector.get_columns(table_name)]
        fk_targets = {
            fk["referred_table"]
            for fk in inspector.get_foreign_keys(table_name)
        }
        # If the table has a FK to 'user', use those column names; otherwise
        # fall back to common naming conventions that every social-app table uses.
        if "user" in fk_targets:
            fk_cols = []
            for fk in inspector.get_foreign_keys(table_name):
                if fk["referred_table"] == "user":
                    fk_cols.extend(fk["constrained_columns"])
            return fk_cols or [c for c in cols if c.endswith("_id")]
        # No FK metadata available — guess by convention
        return [c for c in cols if c.endswith("_id") and "user" in c.lower()]
    except Exception:
        return []


def purge(confirm: bool = False) -> None:
    from app import create_app

    app, _ = create_app()
    with app.app_context():
        from __init__ import db
        from models import (
            User, Post, Comment, Reaction, Message,
            Thread, ThreadMember,
        )

        # ── 1. Identify test users ────────────────────────────────────────────
        all_users: list = User.query.all()
        test_users = [u for u in all_users if _is_test_user(u)]
        test_user_ids = {u.id for u in test_users}

        # ── 2. Identify orphaned test posts (by caption, regardless of author) ─
        all_posts: list = Post.query.all()
        test_posts_by_caption = [
            p for p in all_posts
            if _is_test_post(p) and p.author_id not in test_user_ids
        ]

        # All posts by test users
        test_posts_by_author = Post.query.filter(Post.author_id.in_(test_user_ids)).all() if test_user_ids else []

        all_test_posts = list({p.id: p for p in test_posts_by_author + test_posts_by_caption}.values())
        test_post_ids = {p.id for p in all_test_posts}

        # ── 3. Identify threads involving test users ──────────────────────────
        test_thread_ids: set = set()
        if test_user_ids:
            thread_member_rows = ThreadMember.query.filter(
                ThreadMember.user_id.in_(test_user_ids)
            ).all()
            test_thread_ids = {r.thread_id for r in thread_member_rows}
            # Only purge threads where ALL members are test accounts
            for tid in list(test_thread_ids):
                members = ThreadMember.query.filter_by(thread_id=tid).all()
                if any(m.user_id not in test_user_ids for m in members):
                    test_thread_ids.discard(tid)

        # ── 4. Print summary ─────────────────────────────────────────────────
        print("=" * 64)
        print("VybeFlow Test Data Purge — %s" % ("DRY RUN" if not confirm else "LIVE DELETE"))
        print("=" * 64)
        print(f"Test users ({len(test_users)}):")
        for u in test_users:
            print(f"  id={u.id}  username={u.username!r}  email={u.email!r}")
        print(f"\nTest posts ({len(all_test_posts)}):")
        for p in all_test_posts[:20]:
            print(f"  id={p.id}  caption={str(p.caption or '')[:60]!r}")
        if len(all_test_posts) > 20:
            print(f"  …and {len(all_test_posts) - 20} more")
        print(f"\nPure-test threads to purge: {len(test_thread_ids)}")
        print()

        if not confirm:
            print("DRY RUN complete. No data was deleted.")
            print("Re-run with --confirm to permanently delete the above records.")
            return

        # ── 5. Execute deletions ─────────────────────────────────────────────
        deleted = {"users": 0, "posts": 0, "comments": 0, "reactions": 0,
                   "messages": 0, "threads": 0}

        # Comments + reactions on test posts
        if test_post_ids:
            c = Comment.query.filter(Comment.post_id.in_(test_post_ids)).delete(
                synchronize_session=False
            )
            deleted["comments"] += c
            r = Reaction.query.filter(Reaction.post_id.in_(test_post_ids)).delete(
                synchronize_session=False
            )
            deleted["reactions"] += r

        # Also delete all comments/reactions BY test users on other posts
        if test_user_ids:
            c2 = Comment.query.filter(Comment.author_id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
            deleted["comments"] += c2
            r2 = Reaction.query.filter(Reaction.user_id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
            deleted["reactions"] += r2

        # Posts
        for p in all_test_posts:
            db.session.delete(p)
            deleted["posts"] += 1

        # Test-only threads
        for tid in test_thread_ids:
            msgs = Message.query.filter_by(thread_id=tid).delete(synchronize_session=False)
            deleted["messages"] += msgs
            ThreadMember.query.filter_by(thread_id=tid).delete(synchronize_session=False)
            thread = Thread.query.get(tid)
            if thread:
                db.session.delete(thread)
            deleted["threads"] += 1

        # Messages sent BY test users in mixed threads (leave thread intact)
        if test_user_ids:
            m2 = Message.query.filter(Message.sender_id.in_(test_user_ids)).delete(
                synchronize_session=False
            )
            deleted["messages"] += m2

        # Delete all rows in FK-constrained tables that reference test users.
        # Done with raw SQL BEFORE ORM touches user rows, and users are also
        # deleted via raw SQL to bypass SQLAlchemy's relationship cascade which
        # would try to SET blocker_id/etc = NULL (violating NOT NULL constraints).
        if test_user_ids:
            from sqlalchemy import text as _sql
            ids = list(test_user_ids)
            # Use proper SQLAlchemy parameterized binds — never interpolate IDs into SQL
            placeholder = ",".join([f":id{i}" for i in range(len(ids))])
            bind_params = {f"id{i}": v for i, v in enumerate(ids)}
            _fk_cleanups = [
                # (table, [col, ...])
                ("user_block",    ["blocker_id",  "blocked_id"]),
                ("follow",        ["follower_id", "following_id"]),
                ("story",         ["user_id"]),
                ("notification",  ["user_id",     "actor_id"]),
                ("poll_vote",     ["user_id"]),
                ("circle_member", ["user_id"]),
                ("report",        ["reporter_id", "reported_user_id"]),
                ("appeal",        ["user_id"]),
                ("stalker_pattern_log", ["user_id", "stalker_id"]),
                ("device_fingerprint",  ["user_id"]),
                ("strike",              ["user_id"]),
            ]
            for tbl, cols in _fk_cleanups:
                for col in cols:
                    try:
                        db.session.execute(
                            _sql(f"DELETE FROM {tbl} WHERE {col} IN ({placeholder})"),
                            bind_params,
                        )
                    except Exception:
                        db.session.rollback()
            # Delete the users themselves with raw SQL (skip ORM cascade)
            try:
                db.session.execute(
                    _sql(f"DELETE FROM user WHERE id IN ({placeholder})"),
                    bind_params,
                )
                deleted["users"] += len(test_user_ids)
            except Exception as _ue:
                db.session.rollback()
                print(f"[WARN] Could not delete users via raw SQL: {_ue}")
                # Fall back to ORM (may fail on some setups)
                db.session.expunge_all()
                for u in User.query.filter(User.id.in_(test_user_ids)).all():
                    db.session.delete(u)
                    deleted["users"] += 1

        try:
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"[ERROR] Transaction rolled back: {exc}")
            sys.exit(1)

        print("Deleted successfully:")
        for k, v in deleted.items():
            print(f"  {k}: {v}")
        print("\nPurge complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Purge VybeFlow test data")
    parser.add_argument("--confirm", action="store_true",
                        help="Actually delete records (default is dry-run)")
    args = parser.parse_args()
    purge(confirm=args.confirm)
