"""TikTok upload placeholder."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def upload_tiktok(file_path: Path, title: str, description: str, schedule: Optional[str] = None) -> str:
    logger.info("Uploading to TikTok: %s", file_path)
    return f"tt_{file_path.stem}"
