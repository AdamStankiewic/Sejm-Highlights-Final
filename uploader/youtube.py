"""Lightweight YouTube upload placeholder."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def upload_video(file_path: Path, title: str, description: str, schedule: Optional[str] = None) -> str:
    logger.info("Uploading to YouTube: %s", file_path)
    # Placeholder: return fake video id
    return f"yt_{file_path.stem}"
