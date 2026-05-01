import os
import mimetypes
from flask import Blueprint, current_app, request, Response, abort

media_bp = Blueprint("media", __name__)

def _range_response(path, mimetype):
    file_size = os.path.getsize(path)
    range_header = request.headers.get("Range", None)

    if not range_header:
        # Normal full response
        with open(path, "rb") as f:
            data = f.read()
        return Response(
            data,
            status=200,
            mimetype=mimetype,
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=31536000",
            },
        )

    # Example: "bytes=0-"
    units, rng = range_header.split("=", 1)
    if units.strip() != "bytes":
        abort(416)

    start_str, end_str = (rng.split("-", 1) + [""])[:2]
    try:
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except ValueError:
        abort(416)

    start = max(0, start)
    end = min(end, file_size - 1)
    if start > end:
        abort(416)

    length = end - start + 1
    with open(path, "rb") as f:
        f.seek(start)
        chunk = f.read(length)

    return Response(
        chunk,
        status=206,
        mimetype=mimetype,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Cache-Control": "public, max-age=31536000",
        },
    )

@media_bp.get("/media/<path:filename>")
def serve_media(filename):
    upload_dir = current_app.config.get("UPLOAD_FOLDER", "uploads")
    path = os.path.join(upload_dir, filename)

    # prevent path traversal
    path = os.path.abspath(path)
    if not path.startswith(os.path.abspath(upload_dir) + os.sep):
        abort(403)

    if not os.path.exists(path):
        abort(404)

    guessed, _ = mimetypes.guess_type(path)
    mimetype = guessed or "application/octet-stream"
    return _range_response(path, mimetype)
