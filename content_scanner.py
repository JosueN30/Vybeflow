"""
content_scanner.py — VybeFlow Story Content Scanner
=====================================================
Analyses story uploads (image/video) and captions for policy violations.

Detection layers:
  1. Caption keyword analysis (violence, drugs, explicit, extreme)
     — normalises leet-speak / Unicode obfuscation before matching
  2. NudeNet image/video scan (nudity detection)
  3. Pillow colour heuristic for obvious blood/gore in static images

Returns a structured result dict with:
  label   → "clean" | "mature" | "extreme" | "blocked"
  flags   → list[str], e.g. ["nudity", "violence"]
  blocked → bool  (True means reject the upload entirely)
  details → human-readable summary
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata

log = logging.getLogger(__name__)


# ── Obfuscation normaliser ────────────────────────────────────────────────────
# Maps common leet-speak / Unicode substitutions to plain ASCII so regex
# patterns cannot be bypassed by e.g. "p0rn", "s3x", "childr€n", "b0mb".

_LEET_MAP = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's',
    '7': 't', '8': 'b', '9': 'g', '@': 'a', '$': 's',
    '!': 'i', '+': 't', '(': 'c', ')': 'o',
})

_UNICODE_SUBS = {
    '\u00e9': 'e', '\u00e8': 'e', '\u00ea': 'e',  # é è ê
    '\u00e0': 'a', '\u00e2': 'a', '\u00e4': 'a',  # à â ä
    '\u00f3': 'o', '\u00f4': 'o', '\u00f6': 'o',  # ó ô ö
    '\u00fa': 'u', '\u00fb': 'u', '\u00fc': 'u',  # ú û ü
    '\u00ed': 'i', '\u00ee': 'i', '\u00ef': 'i',  # í î ï
    '\u00e7': 'c',                                  # ç
    '\u20ac': 'e',                                  # €
}

def _normalize_text(text: str) -> str:
    """Return a leet-speak-normalised, ASCII-folded lowercase copy of text.
    Called before keyword regex matching to defeat obfuscation attempts.
    """
    # 1. Unicode normalise (decompose accented chars)
    t = unicodedata.normalize("NFKD", text)
    # 2. Map known Unicode substitutes to ASCII equivalents
    t = t.translate(str.maketrans(_UNICODE_SUBS))
    # 3. Drop remaining combining / non-ASCII characters
    t = t.encode("ascii", errors="ignore").decode("ascii")
    # 4. Leet-speak substitution
    t = t.translate(_LEET_MAP)
    # 5. Collapse repeated characters (e.g. "seeeex" → "sex") — max 2 repeats
    t = re.sub(r'(.)\1{2,}', r'\1\1', t)
    # 6. Strip zero-width / invisible characters sometimes used to split keywords
    t = re.sub(r'[\u200b-\u200f\u00ad\ufeff]', '', t)
    return t.lower()

# ── NudeNet label sets ────────────────────────────────────────────────────────

_EXPLICIT_NUDE_LABELS: frozenset[str] = frozenset({
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
})

_PARTIAL_NUDE_LABELS: frozenset[str] = frozenset({
    "BUTTOCKS_EXPOSED",
    "FEMALE_BREAST_COVERED",
    "FEMALE_GENITALIA_COVERED",
})

_NUDENET_CONFIDENCE = 0.60  # raised from 0.45 to cut false positives

# ── Caption keyword patterns ──────────────────────────────────────────────────

# Extreme content → blocked outright (no appeal, rejected at upload)
_RE_EXTREME = re.compile(
    r"\b("
    r"gore|snuff film|beheading|behead|decapit"
    r"|child porn|cp\b|csam|lolita|preteen sex|underage sex|minor sex|pedo"
    r"|methamphetamine lab|how to make meth|cook meth"
    r"|how to make a bomb|bomb making|ied recipe"
    r"|mass shooting|school shooting|suicide tutorial|how to self.harm"
    r")\b",
    re.IGNORECASE,
)

# Violence indicators → "mature" label
_RE_VIOLENCE = re.compile(
    r"\b("
    r"blood|bleeding|gore|kill|killed|murder|murdered|dead body|corpse|decapitat"
    r"|stab|stabbing|shoot|shot|gunshot|weapon|firearm|knife|blade|machete"
    r"|assault|attack|beat up|fight|punch|violence|brutal|brutal"
    r"|torture|chokehold|strangle"
    r")\b",
    re.IGNORECASE,
)

# Drug references → "mature" label
_RE_DRUGS = re.compile(
    r"\b("
    r"weed|marijuana|cannabis|blunt|joint|edible|thc|420|stoned|blazed"
    r"|cocaine|coke|crack|snow|snort"
    r"|heroin|smack|dope"
    r"|meth|crystal|ice\b|tweaking"
    r"|pill|pills|xanax|oxy|oxys|percs|vicodin|fentanyl|lean|promethazine"
    r"|mdma|ecstasy|molly|rolling|rave drug"
    r"|acid|lsd|shrooms|mushroom|trip|tripping|psychedelic"
    r"|drug|narco|dealer"
    r")\b",
    re.IGNORECASE,
)

# Explicit / sexual text → "mature" label
_RE_EXPLICIT = re.compile(
    r"\b("
    r"fuck|fucking|fucked|fuck\w*"
    r"|sex|sexy|sexual|sexting"
    r"|nude|naked|nudity|strip|stripper|stripping"
    r"|porn|pornography|xxx|adult content|18\+|onlyfans"
    r"|horny|aroused|orgasm|masturbat|handjob|blowjob|dick pic|cum"
    r")\b",
    re.IGNORECASE,
)


# ── Public API ────────────────────────────────────────────────────────────────

def scan_content(
    media_path: str | None = None,
    caption: str = "",
    media_type: str = "image",
) -> dict:
    """Return a content-scan result for the given media + caption.

    Args:
        media_path:  Absolute filesystem path to the uploaded file (or None).
        caption:     User-supplied caption text.
        media_type:  "image" | "video" | "audio" — controls scan strategy.

    Returns::
        {
          "label":   "clean" | "mature" | "extreme" | "blocked",
          "flags":   ["nudity", "violence", "drugs", "explicit", ...],
          "blocked": bool,
          "details": str,
        }
    """
    flags: set[str] = set()
    is_blocked = False
    text = (caption or "").strip()

    # ── 1. Caption / text analysis ────────────────────────────────────────────
    if text:
        # Normalise first to defeat leet-speak / Unicode obfuscation
        _norm = _normalize_text(text)
        if _RE_EXTREME.search(text) or _RE_EXTREME.search(_norm):
            flags.add("extreme")
            is_blocked = True
        if _RE_VIOLENCE.search(text) or _RE_VIOLENCE.search(_norm):
            flags.add("violence")
        if _RE_DRUGS.search(text) or _RE_DRUGS.search(_norm):
            flags.add("drugs")
        if _RE_EXPLICIT.search(text) or _RE_EXPLICIT.search(_norm):
            flags.add("explicit")

    # ── 2. Image/video nudity scan via NudeNet ────────────────────────────────
    if media_path and os.path.isfile(media_path) and media_type in ("image", "video"):
        _run_nudenet_scan(media_path, media_type, flags)

    # ── 3. Colour heuristic for potential blood / gore (images only) ──────────
    if (
        media_path
        and os.path.isfile(media_path)
        and media_type == "image"
        and "violence" not in flags
    ):
        _blood_colour_heuristic(media_path, flags)

    # ── 4. Compute final label ────────────────────────────────────────────────
    if is_blocked or "extreme" in flags:
        label = "blocked"
        is_blocked = True
    elif flags:
        label = "mature"
    else:
        label = "clean"

    flag_list = sorted(flags)
    details = (
        f"Detected: {', '.join(flag_list)}"
        if flag_list
        else "No policy violations detected"
    )

    log.info("[content_scanner] %s → label=%s flags=%s", media_path or "(text)", label, flag_list)
    return {
        "label": label,
        "flags": flag_list,
        "blocked": is_blocked,
        "details": details,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────

def _run_nudenet_scan(media_path: str, media_type: str, flags: set[str]) -> None:
    """Run NudeDetector on an image or sampled video frames."""
    try:
        from nudenet import NudeDetector  # type: ignore
        detector = NudeDetector()

        if media_type == "image":
            detections = detector.detect(media_path)
            found = {d.get("class", "") for d in detections if d.get("score", 0) >= _NUDENET_CONFIDENCE}
            if found & _EXPLICIT_NUDE_LABELS:
                flags.add("nudity")
            elif found & _PARTIAL_NUDE_LABELS:
                flags.add("partial_nudity")
            return

        # Video — sample frames and scan each
        _scan_video_frames(media_path, detector, flags)

    except ImportError:
        log.debug("nudenet not installed — nudity scan skipped")
        # ── Fallback: skin-tone heuristic when NudeNet is unavailable ──
        _skin_tone_heuristic(media_path, flags)
    except Exception as exc:
        log.warning("NudeNet scan error: %s", exc)


def _scan_video_frames(video_path: str, detector, flags: set[str]) -> None:
    """Sample up to 12 evenly-spaced frames from a video and run NudeDetector."""
    try:
        import cv2  # type: ignore
        import tempfile

        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_count = min(12, max(1, total_frames))
        step = max(1, total_frames // sample_count)

        for i in range(sample_count):
            cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
            ret, frame = cap.read()
            if not ret:
                continue

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                cv2.imwrite(tmp_path, frame)
                detections = detector.detect(tmp_path)
                found = {
                    d.get("class", "")
                    for d in detections
                    if d.get("score", 0) >= _NUDENET_CONFIDENCE
                }
                if found & _EXPLICIT_NUDE_LABELS:
                    flags.add("nudity")
                    break  # one explicit frame is enough
                if found & _PARTIAL_NUDE_LABELS:
                    flags.add("partial_nudity")
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

        cap.release()

    except ImportError:
        log.debug("opencv not installed — video frame scan skipped")
    except Exception as exc:
        log.warning("Video frame scan error: %s", exc)


def _skin_tone_heuristic(image_path: str, flags: set[str]) -> None:
    """Pillow-based skin-tone heuristic.
    If a large proportion of pixels match typical human skin tones, flag as
    partial_nudity so the post is held for review even without NudeNet.
    Thresholds are conservative to minimise false positives on portraits.
    """
    if not image_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return
    try:
        from PIL import Image  # type: ignore

        img = Image.open(image_path).convert("RGB")
        img.thumbnail((256, 256))  # fast downscale
        pixels = list(img.getdata())
        total = len(pixels)
        if total == 0:
            return

        skin_count = 0
        for r, g, b in pixels:
            # Classic skin-tone HSV-derived RGB range (covers light→dark skin)
            # Rule: R ≥ 80, G ≥ 40, B ≥ 20; R > G > B; R-G < 50; R-B > 15
            if (
                r >= 80 and g >= 40 and b >= 20
                and r > g and g > b * 0.75
                and (r - g) < 50
                and (r - b) > 15
            ):
                skin_count += 1

        skin_ratio = skin_count / total
        if skin_ratio > 0.65:
            # More than 65 % skin-tone pixels → highly likely significant nudity
            flags.add("nudity")
            log.info("[skin_heuristic] HIGH skin ratio %.1f%% → nudity", skin_ratio * 100)
        elif skin_ratio > 0.50:
            # 50–65 % → possible partial nudity / swimwear
            flags.add("partial_nudity")
            log.info("[skin_heuristic] MODERATE skin ratio %.1f%% → partial_nudity", skin_ratio * 100)

    except ImportError:
        pass  # Pillow not installed
    except Exception as exc:
        log.debug("skin heuristic error: %s", exc)


def _blood_colour_heuristic(image_path: str, flags: set[str]) -> None:
    """
    Quick Pillow colour heuristic: if >12 % of pixels are dark-red (possible
    blood), add a 'violence' flag.  Only fires on common image formats.
    """
    if not image_path.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
        return
    try:
        from PIL import Image  # type: ignore

        img = Image.open(image_path).convert("RGB")
        img.thumbnail((200, 200))  # fast downscale
        pixels = list(img.getdata())
        dark_red = sum(
            1
            for r, g, b in pixels
            if r > 100 and r < 210 and r > g * 2.2 and r > b * 2.2
        )
        if dark_red / max(len(pixels), 1) > 0.20:  # raised from 0.12 to reduce false positives on warm/sunset photos
            flags.add("violence")
    except ImportError:
        pass
    except Exception:
        pass


def flags_to_json(flags: list[str]) -> str:
    """Serialise a flag list to a compact JSON string for DB storage."""
    return json.dumps(sorted(set(flags)))


def json_to_flags(json_str: str | None) -> list[str]:
    """Deserialise flags from DB column value."""
    if not json_str:
        return []
    try:
        return json.loads(json_str)
    except Exception:
        return []
