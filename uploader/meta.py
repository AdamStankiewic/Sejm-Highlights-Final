"""Meta (Facebook/Instagram) upload placeholder."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def upload_reel(file_path: Path, title: str, description: str, schedule: Optional[str] = None) -> str:
    logger.info("Uploading reel to Meta: %s", file_path)
    return f"meta_{file_path.stem}"
