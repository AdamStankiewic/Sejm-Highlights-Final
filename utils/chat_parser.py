"""Robust chat parser supporting multiple popular formats (Twitch/YouTube/Kick/Trovo/custom).

Zwraca mapę {sekunda: liczba_wiadomości} odporna na różne klucze timestampów
stosowane w 2025 r.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

logger = logging.getLogger(__name__)


def _load_raw(path: Path) -> Iterable:
    """Load JSON or JSONL content defensively."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as exc:  # pragma: no cover - defensive IO
        logger.error("Nie można odczytać chat.json (%s): %s", path, exc)
        return []

    # Try JSON first
    try:
        return json.loads(content)
    except Exception:
        # maybe JSONL
        lines: List = []
        for line in content.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                lines.append(json.loads(line))
            except Exception:
                continue
        if lines:
            return lines
        logger.warning("Nie udało się sparsować %s jako JSON/JSONL", path)
        return []


def _parse_time_value(raw_val) -> float | None:
    """Normalize different timestamp representations to seconds (float)."""
    # Direct numeric
    try:
        num = float(raw_val)
        if num > 1e12:  # ms or usec
            num /= 1000.0
        elif num > 1e6:  # likely microseconds
            num /= 1_000_000.0
        return max(0.0, num)
    except (TypeError, ValueError):
        pass

    if isinstance(raw_val, str):
        # HH:MM:SS or MM:SS
        if ":" in raw_val:
            parts = raw_val.split(":")
            try:
                parts = [float(p) for p in parts]
                seconds = 0.0
                for p in parts:
                    seconds = seconds * 60 + p
                return max(0.0, seconds)
            except ValueError:
                pass
        # ISO datetime
        try:
            iso_val = raw_val.replace("Z", "+00:00")
            dt = datetime.fromisoformat(iso_val)
            return max(0.0, dt.timestamp())
        except Exception:
            return None
    return None


_TIMESTAMP_KEYS = [
    "time_in_seconds",
    "time",
    "timestamp",
    "offset",
    "offset_seconds",
    "offsetSeconds",
    "content_offset_seconds",
    "contentOffsetSeconds",
    "offset_ms",
    "timestamp_ms",
    "timestamp_ms_usec",
    "timestamp_usec",
    "timestampUsec",
    "ts",
    "t",
    "seconds",
    "start",
    "start_time",
    "timeSeconds",
    "video_offset",
]


def _extract_timestamp(msg: dict) -> float | None:
    """Probe multiple keys and nested structures for timestamps."""
    for key in _TIMESTAMP_KEYS:
        if key in msg:
            ts = _parse_time_value(msg[key])
            if ts is not None:
                return ts

    # Twitch exports: comment.content_offset_seconds
    if "comment" in msg and isinstance(msg["comment"], dict):
        ts = _extract_timestamp(msg["comment"])
        if ts is not None:
            return ts

    # Nested payload/data
    for nested_key in ("payload", "data", "message"):
        nested = msg.get(nested_key)
        if isinstance(nested, dict):
            ts = _extract_timestamp(nested)
            if ts is not None:
                return ts
    return None


def _iter_messages(raw) -> Iterable[dict]:
    """Normalize different container shapes to a flat list of message dicts."""
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                yield item
    elif isinstance(raw, dict):
        for key in ("messages", "comments", "chat", "data", "items", "entries", "events"):
            val = raw.get(key)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        yield item
                return
        # Kick/Trovo sometimes embed messages directly in dict under numbered keys
        for val in raw.values():
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        yield item
                return
    # Fallback: nothing found
    return


def load_chat_robust(path: str) -> Dict[float, int]:
    """Spróbuj sparsować chat.json w kilku popularnych formatach.

    Obsługiwane formaty: Twitch, YouTube Live, Kick, Trovo, prosty custom
    (time_in_seconds/offset_ms + message). Zwraca mapę {sekunda: liczba}
    lub pusty dict, jeśli nie udało się nic odczytać.
    """

    chat_path = Path(path)
    if not chat_path.exists():
        logger.warning("Chat file not found: %s", chat_path)
        return {}

    raw = _load_raw(chat_path)
    counts: Dict[float, int] = {}

    for msg in _iter_messages(raw):
        ts = _extract_timestamp(msg)
        if ts is None:
            continue
        sec = int(ts)
        counts[sec] = counts.get(sec, 0) + 1

    if not counts:
        logger.warning("Nie rozpoznano formatu chat.json (%s) – zwracam pusty wynik", chat_path)
    else:
        logger.info("Załadowano %d sekund czatu z %s", len(counts), chat_path.name)

    return counts

