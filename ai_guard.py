"""
ai_guard.py — VybeFlow AI Bodyguard Middleware
================================================

Multi-layer toxicity / threat detection pipeline used by Inbox Shield Mode.

Layers (tried in order; first decisive verdict wins):
  1. Hard-block keyword phrases  (always active, zero deps)
  2. Regex threat patterns       (always active, zero deps)
  3. Scam / social-engineering signals
  4. NLTK-based sentiment        (optional; skipped if NLTK not installed)
  5. transformers Detoxify        (optional; skipped if not installed)

Returns a BodyguardResult named-tuple:
  verdict  : 'clean' | 'flagged' | 'blocked'
  reason   : short code string (None when clean)
  score    : float 0-1 toxicity estimate (0 = safe, 1 = worst)
  layer    : which detection layer fired
"""

from __future__ import annotations

import logging
import re
from typing import NamedTuple

_log = logging.getLogger("vybeflow.ai_guard")

# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

class BodyguardResult(NamedTuple):
    verdict: str          # 'clean' | 'flagged' | 'blocked'
    reason:  str | None   # machine-readable code
    score:   float        # 0.0 – 1.0
    layer:   str          # detection layer that fired


_CLEAN = BodyguardResult("clean", None, 0.0, "none")


# ─────────────────────────────────────────────────────────────────────────────
# Layer 1 — Hard-block phrases (zero tolerance, instant block)
# ─────────────────────────────────────────────────────────────────────────────

_HARD_BLOCK: list[str] = [
    # Physical threats
    "i will kill you", "i'm going to kill you", "gonna kill you",
    "i'll hurt you", "i know where you live", "i have your address",
    "i know where you sleep", "you won't be safe",
    # Blackmail / extortion
    "leak your nudes", "i'll expose you", "i'll ruin your life",
    "send nudes or", "leak your pics", "i'll post your pictures",
    "pay me or i'll", "give me money or",
    # Child safety (zero tolerance)
    "i want to meet your kids", "send me photos of your child",
    "are you under 18", "how old are you really",
]

def _layer1_hard_block(text: str) -> BodyguardResult | None:
    lower = text.lower()
    for phrase in _HARD_BLOCK:
        if phrase in lower:
            return BodyguardResult("blocked", "hard_block_phrase", 1.0, "layer1_keywords")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 2 — Regex threat patterns
# ─────────────────────────────────────────────────────────────────────────────

_THREAT_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    # (compiled_pattern, reason_code, verdict)
    (re.compile(r"\bi('?ll|'?m going to|'?m gonna)\s+\w*\s*(kill|murder|shoot|stab|beat)\b", re.I),
     "credible_threat", "blocked"),
    (re.compile(r"\b(your|ur)\s+(address|location|ip|home)\b.*(know|found|got|leaked)\b", re.I),
     "dox_threat", "blocked"),
    (re.compile(r"\b(gonna|will|going to)\s+(destroy|ruin|expose|humiliate)\s+you\b", re.I),
     "harassment_threat", "flagged"),
    (re.compile(r"\b(die|kys|kill\s+yourself|end\s+your\s+life)\b", re.I),
     "self_harm_encouragement", "blocked"),
    (re.compile(r"\b(n[i1!]gg[aoe]r|ch[i1!]nk|sp[i1!]c|f[a4@]gg[o0]t|k[i1!]ke)\b", re.I),
     "slur", "blocked"),
    (re.compile(r"\bwh[o0]re|b[i1!]tch|c[u0]nt|sl[u0]t\b", re.I),
     "sexual_harassment", "flagged"),
]

def _layer2_regex(text: str) -> BodyguardResult | None:
    for pattern, reason, verdict in _THREAT_PATTERNS:
        if pattern.search(text):
            score = 1.0 if verdict == "blocked" else 0.7
            return BodyguardResult(verdict, reason, score, "layer2_regex")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 3 — Scam & social-engineering signals
# ─────────────────────────────────────────────────────────────────────────────

_SCAM_SIGNALS: list[re.Pattern] = [
    re.compile(r"\b(crypto|bitcoin|btc|eth)\s+(investment|profit|guaranteed)\b", re.I),
    re.compile(r"\b(click\s+this\s+link|verify\s+your\s+account|confirm\s+your\s+password)\b", re.I),
    re.compile(r"\byou\s+(won|have\s+won|are\s+selected)\b.{0,60}\b(prize|reward|gift|cash)\b", re.I),
    re.compile(r"\bsend\s+me\s+(cash|money|\$|£|€|₹|your\s+card)\b", re.I),
    re.compile(r"\b(western\s+union|moneygram|gift\s+card\s+code)\b", re.I),
    # URLs from untrusted external domains combined with other suspicious context
    re.compile(r"\bhttp[s]?://(?!(?:[\w.-]*\.)?(youtu\.be|youtube\.com|spotify\.com|soundcloud\.com|vybeflow\.app|twitter\.com|x\.com|instagram\.com|tiktok\.com|apple\.com|google\.com))\S+\b.{0,200}\b(click|verify|confirm|invest|profit|prize|free|won|gift)\b", re.I),
]

def _layer3_scam(text: str) -> BodyguardResult | None:
    hits = sum(1 for p in _SCAM_SIGNALS if p.search(text))
    if hits >= 2:
        return BodyguardResult("blocked", "scam_multiple_signals", 0.9, "layer3_scam")
    if hits == 1:
        return BodyguardResult("flagged", "scam_signal", 0.55, "layer3_scam")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 4 — NLTK Vader sentiment (optional)
# ─────────────────────────────────────────────────────────────────────────────

_vader_analyzer = None
_vader_attempted = False

def _get_vader():
    global _vader_analyzer, _vader_attempted
    if _vader_attempted:
        return _vader_analyzer
    _vader_attempted = True
    try:
        from nltk.sentiment.vader import SentimentIntensityAnalyzer  # type: ignore
        import nltk  # type: ignore
        try:
            nltk.data.find("sentiment/vader_lexicon.zip")
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
        _vader_analyzer = SentimentIntensityAnalyzer()
        _log.debug("ai_guard: NLTK Vader loaded")
    except Exception as exc:
        _log.debug("ai_guard: NLTK Vader unavailable (%s)", exc)
    return _vader_analyzer


def _layer4_vader(text: str) -> BodyguardResult | None:
    analyzer = _get_vader()
    if analyzer is None:
        return None
    try:
        scores = analyzer.polarity_scores(text)
        neg = scores.get("neg", 0.0)
        compound = scores.get("compound", 0.0)
        if compound <= -0.75 and neg >= 0.5:
            return BodyguardResult("flagged", "high_negativity", abs(compound), "layer4_vader")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Layer 5 — Detoxify transformers model (optional, GPU-optional)
# ─────────────────────────────────────────────────────────────────────────────

_detoxify_model = None
_detoxify_attempted = False

_DETOX_THRESHOLDS = {
    "toxicity":            0.70,
    "severe_toxicity":     0.40,
    "obscene":             0.75,
    "threat":              0.50,
    "insult":              0.75,
    "identity_attack":     0.55,
    "sexual_explicit":     0.70,
}

def _get_detoxify():
    global _detoxify_model, _detoxify_attempted
    if _detoxify_attempted:
        return _detoxify_model
    _detoxify_attempted = True
    try:
        from detoxify import Detoxify  # type: ignore
        _detoxify_model = Detoxify("original")
        _log.info("ai_guard: Detoxify transformers model loaded")
    except Exception as exc:
        _log.debug("ai_guard: Detoxify unavailable (%s)", exc)
    return _detoxify_model


def _layer5_detoxify(text: str) -> BodyguardResult | None:
    model = _get_detoxify()
    if model is None:
        return None
    try:
        results = model.predict(text)   # returns dict of label → float score
        for label, threshold in _DETOX_THRESHOLDS.items():
            score = float(results.get(label, 0.0))
            if score >= threshold:
                verdict = "blocked" if label in ("severe_toxicity", "threat", "identity_attack") else "flagged"
                return BodyguardResult(verdict, f"detoxify_{label}", score, "layer5_detoxify")
    except Exception as exc:
        _log.debug("ai_guard: Detoxify predict failed: %s", exc)
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def scan(text: str) -> BodyguardResult:
    """
    Scan *text* through all available detection layers and return a
    BodyguardResult.  Layers are applied in order; the first decisive
    result (flagged or blocked) is returned immediately.

    Usage:
        from ai_guard import scan, BodyguardResult

        result = scan(message_body)
        if result.verdict == "blocked":
            return jsonify({"error": "Message blocked", "reason": result.reason}), 403
        elif result.verdict == "flagged":
            issue_strike(...)

    Always returns BodyguardResult('clean', None, 0.0, 'none') on a safe msg.
    """
    if not text or not text.strip():
        return _CLEAN

    # If the text is suspiciously long (wall-of-text spam), flag it
    if len(text) > 5000:
        return BodyguardResult("flagged", "message_too_long", 0.6, "layer0_length")

    for layer_fn in (
        _layer1_hard_block,
        _layer2_regex,
        _layer3_scam,
        _layer4_vader,
        _layer5_detoxify,
    ):
        try:
            result = layer_fn(text)
            if result is not None:
                _log.info("ai_guard scan: %s [%s] score=%.2f via %s",
                          result.verdict, result.reason, result.score, result.layer)
                return result
        except Exception as exc:
            _log.error("ai_guard layer %s raised: %s", layer_fn.__name__, exc)

    return _CLEAN


def scan_bulk(texts: list[str]) -> list[BodyguardResult]:
    """Scan multiple messages. Useful for moderator batch review."""
    return [scan(t) for t in texts]
