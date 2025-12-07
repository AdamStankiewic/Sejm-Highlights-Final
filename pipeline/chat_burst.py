"""
Analiza czatu: wykrywanie burstów i finalny scoring.

Zawiera narzędzia do parsowania plików chat.json (Twitch/YouTube)
oraz obliczania burstów aktywności czatu w oknach sekundowych.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, Iterable

from .config import CompositeWeights

logger = logging.getLogger(__name__)


def parse_chat_json(path: str) -> Dict[int, int]:
    """Wczytaj plik chat.json i zwróć mapę {sekunda: liczba_wiadomości}.

    The function is defensive and supports multiple common export formats
    from Twitch/YouTube chat archivers. Missing or malformed files return
    an empty dictionary so the pipeline can gracefully fall back to 0.0 chat
    influence.
    """

    chat_path = Path(path)
    if not chat_path.exists():
        logger.warning("Chat file not found: %s", chat_path)
        return {}

    try:
        with open(chat_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Failed to read chat file %s: %s", chat_path, exc)
        return {}

    messages: Iterable = []
    if isinstance(raw, list):
        messages = raw
    elif isinstance(raw, dict):
        if isinstance(raw.get("messages"), list):
            messages = raw.get("messages", [])
        elif isinstance(raw.get("comments"), list):
            messages = raw.get("comments", [])
        elif isinstance(raw.get("data"), list):
            messages = raw.get("data", [])
        elif isinstance(raw.get("chat"), list):
            messages = raw.get("chat", [])

    counts: Dict[int, int] = {}

    def _extract_ts(msg: dict) -> int | None:
        """Try multiple keys and normalize to integer seconds."""

        for key in ("timestamp", "time", "offset", "offsetSeconds", "timestamp_ms"):
            if key in msg:
                ts_val = msg[key]
                try:
                    ts_float = float(ts_val)
                except (TypeError, ValueError):
                    continue

                if ts_float > 1e12:  # probably milliseconds
                    ts_float /= 1000.0
                return max(0, int(ts_float))
        return None

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        ts = _extract_ts(msg)
        if ts is None:
            continue
        counts[ts] = counts.get(ts, 0) + 1

    logger.info("Parsed %d chat seconds from %s", len(counts), chat_path.name)
    return counts


def calculate_chat_burst_score(
    segment_start: float,
    segment_end: float,
    chat_data: Dict[int, int],
    baseline_window: int = 180,
    peak_extension: int = 10,
) -> float:
    """Oblicz burst score czatu dla danego segmentu.

    - baseline: średnia liczba wiadomości/s z ostatnich 2-3 minut (domyślnie 180s)
    - peak: maksymalna liczba wiadomości/s w trakcie segmentu + 10s po nim
    - burst_multiplier = peak / max(baseline, 1)
    - Zwraca score 0.0-1.0 zgodnie z progiem z instrukcji.
    """

    if not chat_data:
        return 0.0

    seg_start = max(0, int(segment_start))
    seg_end = max(seg_start, int(segment_end))

    baseline_start = max(0, seg_start - baseline_window)
    baseline_seconds = range(baseline_start, seg_start)
    baseline_total = sum(chat_data.get(sec, 0) for sec in baseline_seconds)
    baseline_duration = max(seg_start - baseline_start, 1)
    baseline_rate = baseline_total / baseline_duration

    peak_window = range(seg_start, seg_end + peak_extension + 1)
    peak_msgs_per_sec = max((chat_data.get(sec, 0) for sec in peak_window), default=0)

    burst_multiplier = peak_msgs_per_sec / max(baseline_rate, 1)

    if burst_multiplier >= 15:
        score = 1.00
    elif burst_multiplier >= 10:
        score = 0.95
    elif burst_multiplier >= 7:
        score = 0.85
    elif burst_multiplier >= 5:
        score = 0.70
    elif burst_multiplier >= 3:
        score = 0.50
    elif burst_multiplier >= 2:
        score = 0.30
    else:
        score = 0.10

    return float(score)


def calculate_final_score(
    chat_burst_score: float,
    acoustic_score: float,
    semantic_score: float,
    prompt_similarity_score: float,
    weights: CompositeWeights,
) -> float:
    """Połącz cztery składowe w finalny score 0.0-1.0.

    All partial scores are expected to be in 0.0-1.0 range already.
    """

    final_score = (
        chat_burst_score * weights.chat_burst_weight
        + acoustic_score * weights.acoustic_weight
        + semantic_score * weights.semantic_weight
        + prompt_similarity_score * weights.prompt_boost_weight
    )

    return max(0.0, min(1.0, float(final_score)))

