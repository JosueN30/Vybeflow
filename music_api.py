import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode, urlparse
from flask import Blueprint, request, jsonify, Response, stream_with_context
from __init__ import db
from models import Track

bp = Blueprint("music", __name__, url_prefix="/api/music")

SESSION = requests.Session()
TIMEOUT = 4  # reduced — faster failure fallback to DB cache

# ── In-memory search result cache (5-min TTL) ─────────────────────────────
_search_cache: dict = {}  # cache_key → (timestamp, results)
_CACHE_TTL = 300  # seconds

def _cache_lookup(key: str):
    entry = _search_cache.get(key)
    if entry and time.time() - entry[0] < _CACHE_TTL:
        return entry[1]
    return None

def _cache_store(key: str, results: list):
    _search_cache[key] = (time.time(), results)
    # Evict expired entries when cache grows large
    if len(_search_cache) > 300:
        cutoff = time.time() - _CACHE_TTL
        expired = [k for k, v in list(_search_cache.items()) if v[0] < cutoff]
        for k in expired:
            _search_cache.pop(k, None)

def _itunes_search(q: str, limit: int = 25, country: str = "US"):
    params = {
        "term": q,
        "media": "music",
        "entity": "song",
        "limit": limit,
        "country": country,
    }
    url = "https://itunes.apple.com/search?" + urlencode(params)
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    out = []
    for item in data.get("results", []):
        preview = item.get("previewUrl")
        # Skip missing previews and DRM-protected Apple FairPlay content (.p.m4a suffix).
        # audio/x-m4p files require FairPlay DRM and cannot be decoded by browsers.
        if not preview or preview.endswith(".p.m4a"):
            continue
        out.append({
            "provider": "itunes",
            "provider_track_id": str(item.get("trackId")),
            "title": item.get("trackName") or "",
            "artist": item.get("artistName") or "",
            "album": item.get("collectionName"),
            "artwork_url": item.get("artworkUrl100"),
            "preview_url": preview,
            "duration_ms": item.get("trackTimeMillis"),
        })
    return out

def _deezer_search(q: str, limit: int = 25):
    # Deezer returns "preview" (30s) for many tracks
    url = "https://api.deezer.com/search?" + urlencode({"q": q, "limit": limit})
    r = SESSION.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()

    out = []
    for item in data.get("data", []):
        preview = item.get("preview")
        if not preview:
            continue
        album = (item.get("album") or {}).get("title")
        artist = (item.get("artist") or {}).get("name")
        artwork = (item.get("album") or {}).get("cover_medium")
        out.append({
            "provider": "deezer",
            "provider_track_id": str(item.get("id")),
            "title": item.get("title") or "",
            "artist": artist or "",
            "album": album,
            "artwork_url": artwork,
            "preview_url": preview,
            "duration_ms": (item.get("duration") or 0) * 1000,
        })
    return out

def _cache_tracks(results):
    cached = []
    now = time.time()
    for t in results:
        track = Track.query.filter_by(
            provider=t["provider"],
            provider_track_id=t["provider_track_id"]
        ).first()

        if track:
            track.title = t["title"]
            track.artist = t["artist"]
            track.album = t.get("album")
            track.artwork_url = t.get("artwork_url")
            track.preview_url = t.get("preview_url")
            track.duration_ms = t.get("duration_ms")
            track.last_seen_at = db.func.now()
        else:
            track = Track(**t)
            db.session.add(track)

        cached.append(track)

    db.session.commit()
    return cached

@bp.get("/list")
def list_tracks():
    """Return all cached/recently-seen tracks. Used by profile music picker."""
    limit = min(int(request.args.get("limit", 50)), 200)
    try:
        tracks = Track.query.order_by(Track.id.desc()).limit(limit).all()
        return jsonify({
            "tracks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "artist": t.artist,
                    "album": t.album,
                    "artwork_url": t.artwork_url,
                    "preview_url": t.preview_url,
                    "duration_ms": t.duration_ms,
                }
                for t in tracks
            ]
        })
    except Exception as e:
        return jsonify({"tracks": [], "error": str(e)}), 200


@bp.get("/search")
def search_music():
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"results": []})

    try:
        limit = min(int(request.args.get("limit", 25)), 50)
    except (ValueError, TypeError):
        limit = 25
    country = (request.args.get("country") or "US").strip().upper()

    # ── 1. Check in-memory cache first (instant) ─────────────────────────
    cache_key = f"{q.lower()}:{limit}"
    cached_results = _cache_lookup(cache_key)
    if cached_results is not None:
        return jsonify({"results": cached_results})

    # ── 2. Check DB cache before hitting external APIs ───────────────────
    try:
        from sqlalchemy import or_
        db_cached = Track.query.filter(
            or_(
                Track.title.ilike(f"%{q}%"),
                Track.artist.ilike(f"%{q}%"),
            )
        ).order_by(Track.id.desc()).limit(limit).all()
        if db_cached:
            db_rows = [{
                "id": t.id, "title": t.title, "artist": t.artist,
                "album": t.album, "artwork_url": t.artwork_url,
                "preview_url": t.preview_url, "duration_ms": t.duration_ms,
            } for t in db_cached if t.preview_url]  # only tracks with playable previews
            if len(db_rows) >= 5:  # enough local results — return immediately
                _cache_store(cache_key, db_rows)
                return jsonify({"results": db_rows})
    except Exception:
        pass

    # ── 3. Fetch from iTunes + Deezer concurrently ───────────────────────
    itunes_results = []
    deezer_results = []
    with ThreadPoolExecutor(max_workers=2) as _pool:
        _fut_itunes = _pool.submit(_itunes_search, q, limit, country)
        _fut_deezer = _pool.submit(_deezer_search, q, limit)
        for fut in as_completed([_fut_itunes, _fut_deezer]):
            try:
                res = fut.result()
            except Exception as _provider_err:
                _src = "iTunes" if fut is _fut_itunes else "Deezer"
                print(f"[VybeFlow MUSIC] {_src} search failed: {_provider_err}")
                res = []
            if fut is _fut_itunes:
                itunes_results = res
            else:
                deezer_results = res

    # Merge results — Deezer first (plain MP3, always browser-playable),
    # then iTunes as supplemental (only non-DRM previews are included above).
    results = deezer_results + itunes_results

    # ── Fallback: if both providers returned nothing, search the local DB cache ──
    if not results:
        try:
            from sqlalchemy import or_
            cached = Track.query.filter(
                or_(
                    Track.title.ilike(f"%{q}%"),
                    Track.artist.ilike(f"%{q}%"),
                    Track.album.ilike(f"%{q}%"),
                )
            ).order_by(Track.id.desc()).limit(limit).all()
            if cached:
                fallback_rows = [{
                    "id": t.id, "title": t.title, "artist": t.artist,
                    "album": t.album, "artwork_url": t.artwork_url,
                    "preview_url": t.preview_url, "duration_ms": t.duration_ms,
                } for t in cached]
                _cache_store(cache_key, fallback_rows)
                return jsonify({"results": fallback_rows})
        except Exception:
            pass

    # Try to cache in DB, but return results even if DB caching fails
    try:
        tracks = _cache_tracks(results)
        final_rows = [{
            "id": t.id, "provider": t.provider, "provider_track_id": t.provider_track_id,
            "title": t.title, "artist": t.artist, "album": t.album,
            "artwork_url": t.artwork_url, "preview_url": t.preview_url,
            "duration_ms": t.duration_ms
        } for t in tracks]
        _cache_store(cache_key, final_rows)
        return jsonify({"results": final_rows})
    except Exception:
        # DB caching failed — return raw API results directly
        raw_rows = [{
            "id": idx, "provider": r.get("provider", ""),
            "provider_track_id": r.get("provider_track_id", ""),
            "title": r.get("title", ""), "artist": r.get("artist", ""),
            "album": r.get("album"), "artwork_url": r.get("artwork_url"),
            "preview_url": r.get("preview_url"), "duration_ms": r.get("duration_ms")
        } for idx, r in enumerate(results)]
        _cache_store(cache_key, raw_rows)
        return jsonify({"results": raw_rows})


# ── AI Wallpaper Generation ──
@bp.get("/ai-wallpaper")
def generate_ai_wallpaper():
    """
    Generate an AI wallpaper image based on user prompt.
    Uses free image generation APIs as fallback chain.
    Returns the image URL or base64 data.
    """
    prompt = (request.args.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "missing prompt"}), 400

    try:
        width = min(int(request.args.get("width", 960)), 1920)
        height = min(int(request.args.get("height", 540)), 1080)
    except (ValueError, TypeError):
        width, height = 960, 540

    # Try multiple free services as fallback chain
    # 1. Try DreamStudio free tier alternative - Craiyon (takes longer but works)
    # 2. Fallback to themed random images
    
    # For now, use a hybrid approach: generate themed gradient + text overlay
    # This gives users something visual while we implement full AI generation
    
    import base64
    from io import BytesIO
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return jsonify({"error": "PIL not installed"}), 500

    # Create a themed image based on keywords
    img = Image.new('RGB', (width, height), color='#0a0810')
    draw = ImageDraw.Draw(img)
    
    # Parse prompt for colors and themes
    words = prompt.lower().split()
    bg_colors = {
        'fire': [(10, 5, 0), (42, 10, 0), (255, 68, 0)],
        'ocean': [(0, 1, 17), (0, 17, 51), (0, 136, 204)],
        'neon': [(10, 0, 26), (51, 0, 102), (255, 0, 255)],
        'gold': [(42, 31, 0), (170, 136, 0), (255, 204, 0)],
        'street': [(10, 10, 10), (26, 21, 0), (255, 68, 0)],
        'hiphop': [(10, 10, 32), (42, 21, 53), (255, 51, 102)],
        'space': [(0, 0, 17), (0, 0, 51), (51, 0, 170)],
        'nature': [(0, 17, 0), (0, 51, 0), (0, 170, 0)],
    }
    
    theme = 'street'  # default
    for keyword, colors in bg_colors.items():
        if any(keyword in w for w in words):
            theme = keyword
            break
    
    colors = bg_colors[theme]
    
    # Draw gradient background
    for y in range(height):
        ratio = y / height
        if ratio < 0.5:
            r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * ratio * 2)
            g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * ratio * 2)
            b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * ratio * 2)
        else:
            r = int(colors[1][0] + (colors[2][0] - colors[1][0]) * (ratio - 0.5) * 2)
            g = int(colors[1][1] + (colors[2][1] - colors[1][1]) * (ratio - 0.5) * 2)
            b = int(colors[1][2] + (colors[2][2] - colors[1][2]) * (ratio - 0.5) * 2)
        draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))
    
    # Add abstract shapes for visual interest
    import random
    random.seed(hash(prompt) % 10000)
    for _ in range(30):
        x = random.randint(0, width)
        y = random.randint(0, height)
        r = random.randint(30, 150)
        color_idx = random.randint(0, 2)
        c = colors[color_idx]
        overlay_color = (c[0], c[1], c[2], 60)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=overlay_color)
    
    # Convert to base64
    buffered = BytesIO()
    img.save(buffered, format="JPEG", quality=85)
    img_data = base64.b64encode(buffered.getvalue()).decode()
    
    return jsonify({
        "success": True,
        "image": f"data:image/jpeg;base64,{img_data}",
        "prompt": prompt,
        "note": "AI wallpaper generated with themed gradients. Full AI image generation coming soon!"
    })


# ── Audio proxy: stream iTunes / Deezer previews through our server ──
ALLOWED_AUDIO_HOSTS = {
    "audio-ssl.itunes.apple.com",
    "audio.itunes.apple.com",
    # Deezer CDN — "cdns-preview-X" (legacy) and "cdnt-preview" (2024+ format)
    "cdnt-preview.dzcdn.net",
    "cdns-preview-a.dzcdn.net",
    "cdns-preview-b.dzcdn.net",
    "cdns-preview-c.dzcdn.net",
    "cdns-preview-d.dzcdn.net",
    "cdns-preview-e.dzcdn.net",
    "cdns-preview-f.dzcdn.net",
    "cdns-preview-0.dzcdn.net",
    "cdns-preview-1.dzcdn.net",
    "cdns-preview-2.dzcdn.net",
    "cdns-preview-3.dzcdn.net",
    "cdns-preview-4.dzcdn.net",
    "cdns-preview-5.dzcdn.net",
    "cdns-preview-6.dzcdn.net",
    "cdns-preview-7.dzcdn.net",
    "cdns-preview-8.dzcdn.net",
    "cdns-preview-9.dzcdn.net",
}

def _is_deezer_host(hostname: str) -> bool:
    return hostname is not None and hostname.endswith(".dzcdn.net")


def _refresh_itunes_preview(stale_url: str) -> str | None:
    """When an Apple CDN preview URL has expired, search Deezer (stable CDN) then iTunes
    for the same track title+artist and return a fresh preview URL, updating the DB."""
    try:
        from models import User as _User
        from datetime import datetime as _dt

        owner = _User.query.filter_by(profile_music_preview=stale_url).first()
        if not owner or not owner.profile_music_title:
            return None

        query = owner.profile_music_title
        if owner.profile_music_artist:
            query = f"{owner.profile_music_title} {owner.profile_music_artist}"

        # Try Deezer first — its CDN is open and doesn't expire like Apple's
        try:
            deezer_hits = _deezer_search(query, limit=5)
            if deezer_hits:
                fresh = deezer_hits[0].get("preview_url")
                if fresh:
                    owner.profile_music_preview = fresh
                    # update artwork if Deezer has one
                    if deezer_hits[0].get("artwork_url"):
                        owner.profile_music_artwork = deezer_hits[0]["artwork_url"]
                    db.session.commit()
                    return fresh
        except Exception:
            db.session.rollback()

        # Fallback: try iTunes fresh search
        try:
            itunes_hits = _itunes_search(query, limit=5)
            if itunes_hits:
                fresh = itunes_hits[0].get("preview_url")
                if fresh:
                    owner.profile_music_preview = fresh
                    db.session.commit()
                    return fresh
        except Exception:
            db.session.rollback()

    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    return None


def _refresh_deezer_preview(stale_url: str) -> str | None:
    """Try to obtain a fresh Deezer preview URL for an expired CDN link.

    Strategy 1: look up the Track cache by URL path / hash — if it has a
    provider_track_id, call /track/{id} directly for a fresh URL.
    Strategy 2: if Track not found, look up the User whose profile_music_preview
    matches this URL, then search Deezer by their saved title+artist.
    Returns None if all strategies fail.
    """
    try:
        import re
        from models import Track as _Track
        from datetime import datetime as _dt

        # ── Strategy 1: Track cache lookup ────────────────────────────────
        base_path = stale_url.split("?")[0]  # strip query params
        cached = _Track.query.filter(
            _Track.provider == "deezer",
            _Track.preview_url.like(f"{base_path}%"),
        ).first()
        if not cached:
            m = re.search(r'/([0-9a-f]{32})\.mp3', stale_url)
            if m:
                cached = _Track.query.filter(
                    _Track.provider == "deezer",
                    _Track.preview_url.contains(m.group(1)),
                ).first()

        if cached and cached.provider_track_id:
            resp = SESSION.get(
                f"https://api.deezer.com/track/{cached.provider_track_id}",
                timeout=TIMEOUT,
            )
            if resp.ok:
                data = resp.json()
                fresh = data.get("preview")
                if fresh:
                    cached.preview_url = fresh
                    cached.last_seen_at = _dt.utcnow()
                    db.session.commit()
                    return fresh

        # ── Strategy 2: User-record fallback (for profile music not in Track table) ──
        try:
            from models import User as _User
            owner = _User.query.filter_by(profile_music_preview=stale_url).first()
            if owner and owner.profile_music_title:
                query = owner.profile_music_title
                if owner.profile_music_artist:
                    query = f"{owner.profile_music_title} {owner.profile_music_artist}"
                hits = _deezer_search(query, limit=3)
                if hits:
                    fresh = hits[0].get("preview_url")
                    track_id = hits[0].get("provider_track_id") or None
                    if fresh:
                        # Update the user's stored preview URL so it stays fresh
                        owner.profile_music_preview = fresh
                        # Also upsert a Track record so future refreshes succeed
                        if track_id:
                            existing = _Track.query.filter_by(
                                provider="deezer", provider_track_id=track_id
                            ).first()
                            if existing:
                                existing.preview_url = fresh
                                existing.last_seen_at = _dt.utcnow()
                            else:
                                new_track = _Track(
                                    title=owner.profile_music_title,
                                    artist=owner.profile_music_artist or "",
                                    provider="deezer",
                                    provider_track_id=track_id,
                                    preview_url=fresh,
                                    artwork_url=hits[0].get("artwork_url") or hits[0].get("album_cover") or "",
                                )
                                db.session.add(new_track)
                        db.session.commit()
                        return fresh
        except Exception:
            db.session.rollback()

    except Exception:
        try:
            db.session.rollback()
        except Exception:
            pass
    return None


@bp.get("/stream")
def stream_audio():
    """Proxy an external preview URL so the browser plays it same-origin."""
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"error": "missing url"}), 400

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return jsonify({"error": "invalid url scheme"}), 400
    # Reject DRM-protected Apple FairPlay content before even proxying —
    # audio/x-m4p cannot be decoded by any browser without DRM infrastructure.
    if url.endswith(".p.m4a"):
        return jsonify({"error": "drm protected content not supported"}), 400
    # Allow any *.dzcdn.net host (Deezer rotates CDN hostnames) + explicit whitelist
    if parsed.hostname not in ALLOWED_AUDIO_HOSTS and not _is_deezer_host(parsed.hostname):
        return jsonify({"error": "host not allowed"}), 403

    # Forward Range header so browsers can seek and resume audio
    upstream_headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        upstream_headers["Range"] = range_header

    try:
        upstream = SESSION.get(url, stream=True, timeout=TIMEOUT,
                               headers=upstream_headers)
        upstream.raise_for_status()
    except Exception:
        # ── Deezer CDN tokens expire — try to fetch a fresh preview URL ──
        if _is_deezer_host(parsed.hostname):
            fresh_url = _refresh_deezer_preview(url)
            if fresh_url:
                try:
                    upstream = SESSION.get(fresh_url, stream=True, timeout=TIMEOUT,
                                           headers=upstream_headers)
                    upstream.raise_for_status()
                    url = fresh_url  # fall through to the normal response
                except Exception:
                    return jsonify({"error": "upstream fetch failed"}), 502
            else:
                return jsonify({"error": "upstream fetch failed"}), 502
        else:
            # iTunes CDN tokens expire too — try to refresh via Deezer/iTunes search
            if parsed.hostname in ALLOWED_AUDIO_HOSTS:
                fresh_url = _refresh_itunes_preview(url)
                if fresh_url:
                    try:
                        upstream = SESSION.get(fresh_url, stream=True, timeout=TIMEOUT,
                                               headers=upstream_headers)
                        upstream.raise_for_status()
                        url = fresh_url  # fall through to the normal response
                    except Exception:
                        return jsonify({"error": "upstream fetch failed"}), 502
                else:
                    return jsonify({"error": "upstream fetch failed"}), 502
            else:
                return jsonify({"error": "upstream fetch failed"}), 502

    content_type = upstream.headers.get("Content-Type", "audio/mp4")
    # Normalise the oddball iTunes MIME type so browsers accept it
    if content_type in ("audio/x-m4p",):
        content_type = "audio/mp4"

    headers = {
        "Content-Type": content_type,
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=86400",
        # Required for crossorigin="anonymous" + Web Audio API analyser
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
        "Access-Control-Allow-Headers": "Range",
        "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
    }
    cl = upstream.headers.get("Content-Length")
    if cl:
        headers["Content-Length"] = cl
    cr = upstream.headers.get("Content-Range")
    if cr:
        headers["Content-Range"] = cr

    return Response(
        stream_with_context(upstream.iter_content(chunk_size=16384)),
        status=upstream.status_code,
        headers=headers,
    )


@bp.route("/stream", methods=["OPTIONS"])
def stream_audio_options():
    """CORS preflight handler for the audio stream proxy."""
    return Response(
        status=204,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range",
            "Access-Control-Max-Age": "86400",
        },
    )
