"""
vision_scanner.py — Cloud Vision AI scanner for story uploads
=============================================================
Scans uploaded images/videos for Adult or Suggestive content using either
Google Cloud Vision SafeSearch or AWS Rekognition.

Provider is selected via the VISION_PROVIDER environment variable:

  VISION_PROVIDER=gcv          → Google Cloud Vision SafeSearch
  VISION_PROVIDER=rekognition  → AWS Rekognition DetectModerationLabels

If the variable is unset, empty, or credentials are missing the scanner
returns is_sensitive=False so uploads are never blocked by a missing config.

Required credentials
────────────────────
GCV:
  GOOGLE_APPLICATION_CREDENTIALS  path to your service-account JSON key

Rekognition:
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_DEFAULT_REGION               (default: us-east-1)

Required packages (install whichever provider you use):
  pip install google-cloud-vision      # GCV
  pip install boto3                    # Rekognition

Sensitive-content threshold: 75 % confidence (SENSITIVE_THRESHOLD = 0.75).

Return value of scan_story_media()
───────────────────────────────────
{
    "is_sensitive": bool,   # True if AI confidence >= SENSITIVE_THRESHOLD
    "score":        float,  # Highest confidence found (0.0–1.0)
    "labels":       list,   # Human-readable label names that tripped the threshold
}
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile

log = logging.getLogger(__name__)

# ── Configurable threshold (75 %) ────────────────────────────────────────────
SENSITIVE_THRESHOLD: float = 0.75


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def scan_story_media(media_path: str, media_type: str) -> dict:
    """Scan a story upload for Adult/Suggestive content.

    Args:
        media_path:  Absolute filesystem path to the saved file.
        media_type:  ``'image'`` or ``'video'`` (audio is skipped).

    Returns a dict with keys ``is_sensitive``, ``score``, and ``labels``.
    Always succeeds — any internal error returns ``is_sensitive=False`` so the
    upload is never blocked due to a configuration or network issue.
    """
    provider = os.environ.get("VISION_PROVIDER", "").strip().lower()

    if not provider:
        return _no_op()

    if not media_path or not os.path.isfile(media_path):
        log.warning("vision_scanner: file not found: %s", media_path)
        return _no_op()

    tmp_frame: str | None = None

    try:
        # For videos, extract the first frame as a scannable image.
        if media_type == "video":
            tmp_frame = _extract_video_frame(media_path)
            if not tmp_frame:
                log.info("vision_scanner: video frame extraction skipped for %s", media_path)
                return _no_op()
            scan_path = tmp_frame
        elif media_type == "image":
            scan_path = media_path
        else:
            # Audio or unknown — skip silently.
            return _no_op()

        if provider == "gcv":
            return _scan_gcv(scan_path)
        elif provider == "rekognition":
            return _scan_rekognition(scan_path)
        else:
            log.warning("vision_scanner: unknown VISION_PROVIDER=%r", provider)
            return _no_op()

    except Exception:
        log.exception("vision_scanner: scan failed for %s — upload allowed", media_path)
        return _no_op()

    finally:
        # Always clean up any temp frame file.
        if tmp_frame and os.path.isfile(tmp_frame):
            try:
                os.unlink(tmp_frame)
            except OSError:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _no_op() -> dict:
    return {"is_sensitive": False, "score": 0.0, "labels": []}


def _extract_video_frame(video_path: str) -> str | None:
    """Use ffmpeg to extract the first frame of a video into a temp PNG.

    Returns the temp file path on success, or None if ffmpeg is unavailable
    or extraction fails.
    """
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    out_path = tmp.name
    tmp.close()

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", video_path,
                "-vframes", "1",
                "-q:v", "2",
                out_path,
            ],
            capture_output=True,
            timeout=30,
        )
        if result.returncode == 0 and os.path.getsize(out_path) > 0:
            return out_path
        log.debug("ffmpeg returned %d for %s", result.returncode, video_path)
    except FileNotFoundError:
        log.debug("ffmpeg not installed; video frame scan unavailable")
    except subprocess.TimeoutExpired:
        log.warning("ffmpeg timed out extracting frame from %s", video_path)
    except Exception:
        log.exception("Unexpected error extracting video frame")

    try:
        os.unlink(out_path)
    except OSError:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Google Cloud Vision
# ─────────────────────────────────────────────────────────────────────────────

# Map GCV Likelihood enum names to numeric confidence values.
_GCV_LIKELIHOOD: dict[str, float] = {
    "UNKNOWN":       0.00,
    "VERY_UNLIKELY": 0.05,
    "UNLIKELY":      0.20,
    "POSSIBLE":      0.50,
    "LIKELY":        0.80,
    "VERY_LIKELY":   0.95,
}


def _scan_gcv(image_path: str) -> dict:
    """Call Google Cloud Vision SafeSearch on the given image file."""
    try:
        from google.cloud import vision  # type: ignore[import]
    except ImportError:
        log.error(
            "google-cloud-vision is not installed. "
            "Run: pip install google-cloud-vision"
        )
        return _no_op()

    client = vision.ImageAnnotatorClient()
    with open(image_path, "rb") as fh:
        content = fh.read()

    image = vision.Image(content=content)
    response = client.safe_search_detection(image=image)

    if response.error.message:
        raise RuntimeError(
            f"GCV SafeSearch error: {response.error.message}"
        )

    ann = response.safe_search_annotation

    # ``adult`` covers explicit nudity; ``racy`` covers suggestive/swimwear/etc.
    adult_score = _GCV_LIKELIHOOD.get(ann.adult.name, 0.0)
    racy_score  = _GCV_LIKELIHOOD.get(ann.racy.name, 0.0)
    top_score   = max(adult_score, racy_score)

    labels: list[str] = []
    if adult_score >= SENSITIVE_THRESHOLD:
        labels.append("Adult")
    if racy_score >= SENSITIVE_THRESHOLD:
        labels.append("Suggestive")

    log.debug(
        "GCV scan: adult=%.2f racy=%.2f sensitive=%s labels=%s",
        adult_score, racy_score, top_score >= SENSITIVE_THRESHOLD, labels,
    )
    return {
        "is_sensitive": top_score >= SENSITIVE_THRESHOLD,
        "score":        round(top_score, 4),
        "labels":       labels,
    }


# ─────────────────────────────────────────────────────────────────────────────
# AWS Rekognition
# ─────────────────────────────────────────────────────────────────────────────

# Parent/top-level category names that count as sensitive.
# Rekognition returns hierarchical labels; we check both parent and child.
_REKOG_SENSITIVE: frozenset[str] = frozenset({
    "Explicit Nudity",
    "Nudity",
    "Graphic Nudity",
    "Sexual Activity",
    "Illustrated Explicit Nudity",
    "Adult Toys",
    "Partial Nudity",
    "Suggestive",
    "Sexual Situations",
    "Revealing Clothes",
})


def _scan_rekognition(image_path: str) -> dict:
    """Call AWS Rekognition DetectModerationLabels on the given image file."""
    try:
        import boto3  # type: ignore[import]
    except ImportError:
        log.error("boto3 is not installed. Run: pip install boto3")
        return _no_op()

    with open(image_path, "rb") as fh:
        image_bytes = fh.read()

    client = boto3.client(
        "rekognition",
        region_name=os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
    )

    # MinConfidence=40 fetches all labels; we filter by SENSITIVE_THRESHOLD below.
    response = client.detect_moderation_labels(
        Image={"Bytes": image_bytes},
        MinConfidence=40.0,
    )

    labels: list[str] = []
    top_score: float = 0.0

    for item in response.get("ModerationLabels", []):
        name       = item.get("Name", "")
        parent     = item.get("ParentName", "")
        confidence = item.get("Confidence", 0.0) / 100.0  # normalise to 0–1

        # Match on both the label itself and its parent category.
        if (name in _REKOG_SENSITIVE or parent in _REKOG_SENSITIVE) and confidence >= SENSITIVE_THRESHOLD:
            labels.append(name)
            if confidence > top_score:
                top_score = confidence

    log.debug(
        "Rekognition scan: sensitive=%s score=%.4f labels=%s",
        len(labels) > 0, top_score, labels,
    )
    return {
        "is_sensitive": len(labels) > 0,
        "score":        round(top_score, 4),
        "labels":       labels,
    }
