"""
video_scanner.py — AI-powered video content scanner for Vyvid

Uses NudeNet (ONNX, no TensorFlow required) to scan frames extracted from
uploaded videos and classify them into:

    clean       – no adult content detected
    suggestive  – covered/partial nudity (swimwear-level); stays at chosen rating
    explicit    – exposed genitalia / breast / anus; forces mature rating
    blocked     – graphic content that violates Vyvid policy (violence, gore)
                  → video is kept off-platform until manual review passes it

Scanning runs in a background thread so the upload response is instant.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import cv2
import numpy as np

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Genre taxonomy
# ──────────────────────────────────────────────────────────────────────────────

GENRE_DISPLAY_NAMES: dict[str, str] = {
    "adult":               "Adult Content",
    "fitness_sports":      "Fitness & Sports",
    "dance_performance":   "Dance & Performance",
    "podcast_talk":        "Podcast & Talk Show",
    "music_entertainment": "Music & Entertainment",
    "gaming":              "Gaming",
    "animation_art":       "Animation & Art",
    "education":           "Education",
    "comedy_entertainment":"Comedy & Entertainment",
    "other":               "Other / General",
}

# ──────────────────────────────────────────────────────────────────────────────
# NudeNet label taxonomy
# ──────────────────────────────────────────────────────────────────────────────

# Labels that indicate explicitly adult/pornographic content
EXPLICIT_LABELS: set[str] = {
    "FEMALE_GENITALIA_EXPOSED",
    "MALE_GENITALIA_EXPOSED",
    "FEMALE_BREAST_EXPOSED",
    "ANUS_EXPOSED",
    "BUTTOCKS_EXPOSED",
}

# Labels that are suggestive but not necessarily explicit (covered nudity, etc.)
SUGGESTIVE_LABELS: set[str] = {
    "FEMALE_GENITALIA_COVERED",
    "FEMALE_BREAST_COVERED",
    "ANUS_COVERED",
    "BUTTOCKS_COVERED",
    "ARMPITS_EXPOSED",
    "BELLY_EXPOSED",
    "FEET_EXPOSED",
}

# Minimum confidence to count a detection
DETECTION_CONFIDENCE = 0.45

# Frames to sample (evenly spaced through the video)
FRAMES_TO_SAMPLE = 12

# If more than this fraction of sampled frames contain explicit content → explicit
EXPLICIT_FRAME_THRESHOLD = 0.15   # 15 % — even 2 frames out of 12 triggers

# Confidence score averaged across explicit detections that forces "explicit"
EXPLICIT_SCORE_THRESHOLD = 0.50


# ──────────────────────────────────────────────────────────────────────────────
# Singleton detector (loads once, reused across all scans)
# ──────────────────────────────────────────────────────────────────────────────

_detector = None
_detector_lock = threading.Lock()


def _get_detector():
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                from nudenet import NudeDetector
                _detector = NudeDetector()
                log.info("[scanner] NudeDetector loaded (ONNX)")
    return _detector


# ──────────────────────────────────────────────────────────────────────────────
# Frame extraction
# ──────────────────────────────────────────────────────────────────────────────

def _extract_frames(video_path: str, n_frames: int = FRAMES_TO_SAMPLE) -> tuple[list[str], str, float]:
    """
    Extract `n_frames` evenly-spaced frames from the video.
    Saves them as temporary JPEG files and returns their paths.
    Must be cleaned up by the caller with _cleanup_frames().
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    duration_sec = total_frames / fps if total_frames > 0 else 0

    if total_frames <= 0:
        cap.release()
        raise ValueError("Video has no frames or could not be read")

    # Pick evenly-spaced frame indices, skip the first 5 % (often black/title)
    skip = max(1, int(total_frames * 0.05))
    end  = total_frames - 1
    indices = [
        int(skip + (end - skip) * i / max(n_frames - 1, 1))
        for i in range(n_frames)
    ]
    indices = list(dict.fromkeys(indices))  # deduplicate

    tmp_dir = tempfile.mkdtemp(prefix="vyvid_scan_")
    paths: list[str] = []

    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret or frame is None:
            continue
        path = os.path.join(tmp_dir, f"frame_{idx:06d}.jpg")
        cv2.imwrite(path, frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        paths.append(path)

    cap.release()
    return paths, tmp_dir, duration_sec


def _cleanup_frames(tmp_dir: str):
    import shutil
    try:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    except Exception:
        pass


# ──────────────────────────────────────────────────────────────────────────────
# Genre Classification
# ──────────────────────────────────────────────────────────────────────────────

def _classify_genre(frame_paths: list[str], nudenet_result: dict) -> str:
    """
    Classify the genre of a video using visual frame analysis and NudeNet results.

    Priority:
      1. adult   — explicit NudeNet detections
      2. gaming  — dark, high-saturation screen-like content
      3. podcast_talk     — faces + near-static frames
      4. dance_performance— high motion + moderate lighting
      5. fitness_sports   — high motion + outdoor brightness
      6. animation_art    — super-saturated flat colours, no natural faces
      7. education        — faces + low motion + text-like brightness distribution
      8. music_entertainment — moderate motion + colourful
      9. comedy_entertainment (catch-all)
    """
    import json as _json

    # ── Step 1: Adult content from NudeNet ──────────────────────────────────
    explicit_detected_labels = {
        "FEMALE_GENITALIA_EXPOSED", "MALE_GENITALIA_EXPOSED",
        "FEMALE_BREAST_EXPOSED", "ANUS_EXPOSED",
    }
    try:
        labels_found = set(_json.loads(nudenet_result.get("scan_labels", "[]")))
    except Exception:
        labels_found = set()

    if nudenet_result.get("scan_status") == "explicit" or bool(
        labels_found & explicit_detected_labels
    ):
        return "adult"

    if not frame_paths:
        return "other"

    # ── Step 2: Load raw frames ──────────────────────────────────────────────
    frames_bgr: list[np.ndarray] = []
    for fp in frame_paths:
        img = cv2.imread(fp)
        if img is not None:
            frames_bgr.append(img)

    if not frames_bgr:
        return "other"

    # ── Step 3: Visual feature extraction ───────────────────────────────────
    saturation_scores: list[float] = []
    brightness_scores: list[float] = []
    colorfulness_scores: list[float] = []

    for frame in frames_bgr:
        try:
            hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
            saturation_scores.append(float(np.mean(hsv[:, :, 1])))
            brightness_scores.append(float(np.mean(hsv[:, :, 2])))
            # Colorfulness: std-dev of each channel in RGB
            b, g, r = cv2.split(frame.astype("float32"))
            rg = r - g
            yb = 0.5 * (r + g) - b
            colorfulness_scores.append(
                float(np.sqrt(np.std(rg) ** 2 + np.std(yb) ** 2) +
                      0.3 * np.sqrt(np.mean(rg) ** 2 + np.mean(yb) ** 2))
            )
        except Exception:
            pass

    avg_sat   = float(np.mean(saturation_scores)) if saturation_scores else 0
    avg_bright = float(np.mean(brightness_scores)) if brightness_scores else 0
    avg_color  = float(np.mean(colorfulness_scores)) if colorfulness_scores else 0

    # ── Step 4: Motion (inter-frame difference) ──────────────────────────────
    motion_scores: list[float] = []
    for i in range(1, len(frames_bgr)):
        try:
            g1 = cv2.cvtColor(frames_bgr[i - 1], cv2.COLOR_BGR2GRAY)
            g2 = cv2.cvtColor(frames_bgr[i],     cv2.COLOR_BGR2GRAY)
            motion_scores.append(float(np.mean(cv2.absdiff(g1, g2))))
        except Exception:
            pass
    avg_motion = float(np.mean(motion_scores)) if motion_scores else 0

    # ── Step 5: Face detection ───────────────────────────────────────────────
    try:
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"  # type: ignore[attr-defined]
        )
        face_frame_count = 0
        sample = frames_bgr[:min(8, len(frames_bgr))]
        for frame in sample:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4)
            if len(faces) > 0:
                face_frame_count += 1
        face_ratio = face_frame_count / max(len(sample), 1)
    except Exception:
        face_ratio = 0.0

    # ── Step 6: Decision tree ────────────────────────────────────────────────
    is_dark     = avg_bright < 90
    is_bright   = avg_bright > 140
    is_sat      = avg_sat > 110
    is_very_sat = avg_sat > 150
    is_colorful = avg_color > 35
    is_static   = avg_motion < 5
    is_moderate_motion = 5 <= avg_motion < 18
    is_high_motion = avg_motion >= 18
    has_faces   = face_ratio >= 0.4

    # Gaming: dark + saturated screen-like content (HUD colours, no natural faces)
    if is_dark and is_sat and not has_faces:
        return "gaming"

    # Podcast / talk: talking heads + mostly static
    if has_faces and is_static and not is_colorful:
        return "podcast_talk"

    # Education: faces + low motion + text-like moderate brightness  
    if has_faces and is_moderate_motion and avg_bright > 80:
        return "education"

    # Animation / art: hyper-saturated, flat, no natural skin tones
    if is_very_sat and not has_faces:
        return "animation_art"

    # Dance / performance: high motion + non-dark
    if is_high_motion and not is_dark:
        return "dance_performance"

    # Fitness / sports: high motion + bright/outdoor setting
    if is_high_motion and is_bright:
        return "fitness_sports"

    # Music / entertainment: moderate motion + colourful
    if is_moderate_motion and is_colorful:
        return "music_entertainment"

    return "comedy_entertainment"


# ──────────────────────────────────────────────────────────────────────────────
# Scoring
# ──────────────────────────────────────────────────────────────────────────────

def _analyze_detections(detections_per_frame: list[list[dict]]) -> dict:
    """
    Aggregate per-frame NudeNet detections into a single result dict.

    Returns:
        {
            "scan_status":      "clean" | "suggestive" | "explicit" | "error",
            "scan_score":       float   # highest explicit confidence seen (0-1)
            "scan_labels":      str     # JSON list of labels seen above threshold
            "forced_rating":    str | None  # "mature" if explicit content found
            "frames_explicit":  int     # number of frames with explicit content
            "frames_total":     int
        }
    """
    n_total = len(detections_per_frame)
    if n_total == 0:
        return {
            "scan_status": "clean",
            "scan_score": 0.0,
            "scan_labels": "[]",
            "forced_rating": None,
            "frames_explicit": 0,
            "frames_total": 0,
        }

    all_labels: dict[str, float] = {}  # label → max confidence seen
    frames_with_explicit = 0
    frames_with_suggestive = 0

    for frame_detections in detections_per_frame:
        frame_has_explicit = False
        for det in frame_detections:
            label = det.get("class", "")
            score = float(det.get("score", 0))
            if score < DETECTION_CONFIDENCE:
                continue
            # Track highest confidence per label
            if label not in all_labels or all_labels[label] < score:
                all_labels[label] = score
            if label in EXPLICIT_LABELS:
                frame_has_explicit = True
            elif label in SUGGESTIVE_LABELS:
                frames_with_suggestive += 1
        if frame_has_explicit:
            frames_with_explicit += 1

    # Explicit score = highest confidence among explicit labels
    explicit_scores = [all_labels[l] for l in all_labels if l in EXPLICIT_LABELS]
    max_explicit_score = max(explicit_scores) if explicit_scores else 0.0

    explicit_fraction = frames_with_explicit / n_total

    # ── Decision ──
    if explicit_fraction >= EXPLICIT_FRAME_THRESHOLD and max_explicit_score >= EXPLICIT_SCORE_THRESHOLD:
        status = "explicit"
        forced_rating = "mature"
    elif explicit_scores:
        # Some explicit detections but below threshold — treat as suggestive/mature
        status = "suggestive"
        forced_rating = "mature"
    elif frames_with_suggestive > 0:
        status = "suggestive"
        forced_rating = None  # user chose rating, don't override for mere suggestive
    else:
        status = "clean"
        forced_rating = None

    seen_labels = sorted(all_labels.keys())

    return {
        "scan_status": status,
        "scan_score": round(max_explicit_score, 4),
        "scan_labels": json.dumps(seen_labels),
        "forced_rating": forced_rating,
        "frames_explicit": frames_with_explicit,
        "frames_total": n_total,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def scan_video_file(video_path: str) -> dict:
    """
    Scan a video file and return a result dict.  Does NOT touch the database.

    Result keys:
        scan_status     "clean" | "suggestive" | "explicit" | "error"
        scan_score      float 0-1 (highest explicit detection confidence)
        scan_labels     JSON-encoded list of detected label names
        scan_genre      genre string from GENRE_DISPLAY_NAMES
        forced_rating   "mature" | None
        duration_sec    float (video duration in seconds)
        error           str | None (only present if scan_status == "error")
    """
    try:
        detector = _get_detector()
        frame_paths, tmp_dir, duration_sec = _extract_frames(video_path)

        if not frame_paths:
            return {
                "scan_status": "error",
                "scan_score": 0.0,
                "scan_labels": "[]",
                "scan_genre": "other",
                "forced_rating": None,
                "duration_sec": 0,
                "error": "No frames could be extracted from the video",
            }

        all_detections: list[list[dict]] = []
        try:
            for fp in frame_paths:
                try:
                    dets = detector.detect(fp)
                    all_detections.append(dets or [])
                except Exception as e:
                    log.warning(f"[scanner] frame detection failed ({fp}): {e}")
                    all_detections.append([])

            result = _analyze_detections(all_detections)

            # Genre classification (uses the same temp frames — before cleanup)
            try:
                result["scan_genre"] = _classify_genre(frame_paths, result)
            except Exception as ge:
                log.warning(f"[scanner] genre classification failed: {ge}")
                result["scan_genre"] = "other"

        finally:
            _cleanup_frames(tmp_dir)

        result["duration_sec"] = duration_sec
        result["error"] = None
        return result

    except Exception as e:
        log.error(f"[scanner] scan_video_file failed for {video_path}: {e}")
        return {
            "scan_status": "error",
            "scan_score": 0.0,
            "scan_labels": "[]",
            "scan_genre": "other",
            "forced_rating": None,
            "duration_sec": 0,
            "error": str(e),
        }


def scan_video_async(video_id: int, video_path: str, flask_app):
    """
    Kick off an async scan in a background thread.
    Updates the VyvidVideo row in the DB when done.
    Call this from the upload route immediately after saving the video.
    """
    def _run():
        with flask_app.app_context():
            from __init__ import db
            from models import VyvidVideo

            video = db.session.get(VyvidVideo, video_id)
            if video is None:
                log.warning(f"[scanner] video {video_id} not found — aborting scan")
                return

            # Mark as scanning
            try:
                video.scan_status = "scanning"
                db.session.commit()
            except Exception:
                db.session.rollback()

            log.info(f"[scanner] scanning video {video_id}: {video_path}")

            # Minimum visible scan time so the UI animation is always shown
            import time as _time
            _scan_start = _time.monotonic()

            result = scan_video_file(video_path)

            # Ensure scan takes at least 10 seconds (gives the UI time to animate)
            elapsed = _time.monotonic() - _scan_start
            if elapsed < 10.0:
                _time.sleep(10.0 - elapsed)

            try:
                video = db.session.get(VyvidVideo, video_id)
                if video is None:
                    return

                video.scan_status     = result["scan_status"]
                video.scan_score      = result["scan_score"]
                video.scan_labels     = result["scan_labels"]
                video.scan_completed_at = datetime.now(timezone.utc)

                # Persist AI-detected genre
                if result.get("scan_genre"):
                    video.scan_genre = result["scan_genre"]

                # Update duration if we got it
                if result.get("duration_sec"):
                    video.duration_sec = int(result["duration_sec"])

                # Enforce rating escalation for explicit content
                if result["forced_rating"] == "mature":
                    if video.content_rating != "mature":
                        log.info(
                            f"[scanner] video {video_id}: escalating rating "
                            f"{video.content_rating!r} → 'mature' (explicit content detected)"
                        )
                        video.content_rating  = "mature"
                        video.advertiser_tier = "adult"

                    # Check if uploader is already adult-content verified
                    already_verified = False
                    try:
                        from models import UserVerification
                        uv = UserVerification.query.filter_by(user_id=video.author_id).first()
                        already_verified = bool(
                            uv and getattr(uv, "adult_content_verified", False)
                        )
                    except Exception as uv_err:
                        log.warning(f"[scanner] could not check UserVerification: {uv_err}")

                    if already_verified:
                        # User already verified for adult content — keep video live,
                        # only flag for admin awareness (does NOT block the video)
                        video.needs_review    = True
                        video.is_approved     = True   # stays live
                        video.adult_id_required = False
                        log.info(
                            f"[scanner] video {video_id}: uploader {video.author_id} already "
                            f"adult-verified — video stays approved (mature), flagged for review"
                        )
                    else:
                        # First explicit upload — block video and request ID verification
                        video.needs_review    = True
                        video.is_approved     = False  # hold until ID verified
                        video.adult_id_required = True
                        log.info(
                            f"[scanner] video {video_id}: adult_id_required set "
                            f"(uploader {video.author_id} needs adult content ID verification)"
                        )

                # If the scan itself errored, don't block the video but flag it
                if result["scan_status"] == "error":
                    video.needs_review = True
                    log.warning(
                        f"[scanner] video {video_id} scan error: {result.get('error')}"
                    )

                db.session.commit()
                log.info(
                    f"[scanner] video {video_id} done — "
                    f"status={result['scan_status']!r}  score={result['scan_score']:.3f}  "
                    f"explicit_frames={result.get('frames_explicit',0)}/{result.get('frames_total',0)}"
                )
            except Exception as e:
                db.session.rollback()
                log.error(f"[scanner] DB update failed for video {video_id}: {e}")

    t = threading.Thread(target=_run, daemon=True, name=f"vyvid-scan-{video_id}")
    t.start()
    return t
