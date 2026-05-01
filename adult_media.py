"""adult_media — stub blueprint.

Adult content PIN verification and media gating is handled in app.py
(/api/posts/<id>/set-pin and /api/posts/<id>/verify-pin) and in
routes/messaging.py (/api/dm/messages/<id>/unlock).
This stub exists so app.py can import adult_media_bp without error.
"""
from flask import Blueprint

adult_media_bp = Blueprint("adult_media", __name__)
