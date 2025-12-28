"""
Streamer Auto-Detection - Determines which streamer profile to use.
"""
import re
from pathlib import Path
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class StreamerDetector:
    """
    Auto-detect streamer from video filename, directory, or metadata.

    Detection strategies (in order):
    1. Explicit --streamer-id flag (highest priority)
    2. Filename patterns (e.g., "asmongold_2024_12_23.mp4")
    3. Directory name (e.g., "vods/zackrawrr/video.mp4")
    4. Video metadata (if available)
    5. Default fallback (configurable)
    """

    def __init__(self, streamer_manager, default_streamer: str = "sejm"):
        """
        Args:
            streamer_manager: StreamerManager instance
            default_streamer: Fallback streamer_id if detection fails
        """
        self.streamer_manager = streamer_manager
        self.default_streamer = default_streamer

    def detect(
        self,
        video_path: str,
        explicit_id: Optional[str] = None
    ) -> str:
        """
        Detect streamer from video path and context.

        Args:
            video_path: Path to video file
            explicit_id: Explicitly provided streamer_id (highest priority)

        Returns:
            streamer_id: Detected or default streamer ID
        """
        # Strategy 1: Explicit ID (from --streamer-id flag)
        if explicit_id:
            profile = self.streamer_manager.get(explicit_id)
            if profile:
                logger.info(f"✅ Using explicit streamer: {explicit_id}")
                return explicit_id
            else:
                logger.warning(f"⚠️  Explicit streamer '{explicit_id}' not found, trying auto-detect...")

        # Strategy 2: Filename patterns
        detected = self._detect_from_filename(video_path)
        if detected:
            logger.info(f"✅ Detected from filename: {detected}")
            return detected

        # Strategy 3: Directory name
        detected = self._detect_from_directory(video_path)
        if detected:
            logger.info(f"✅ Detected from directory: {detected}")
            return detected

        # Strategy 4: Default fallback
        logger.warning(f"⚠️  Could not auto-detect streamer, using default: {self.default_streamer}")
        return self.default_streamer

    def _detect_from_filename(self, video_path: str) -> Optional[str]:
        """
        Detect streamer from filename patterns.

        Supported patterns:
        - asmongold_2024_12_23.mp4
        - zackrawrr-reaction-drama.mp4
        - sejm_posiedzenie_123.mp4
        - [Asmongold] React to Drama.mp4
        """
        filename = Path(video_path).stem.lower()

        # Get all known streamers
        profiles = self.streamer_manager.list_all()

        for profile in profiles:
            streamer_id = profile.streamer_id.lower()
            aliases = [alias.lower() for alias in profile.aliases]

            # Check if streamer_id or alias appears in filename
            all_names = [streamer_id] + aliases

            for name in all_names:
                # Pattern 1: name_date.mp4 or name-title.mp4
                if re.search(rf'\b{re.escape(name)}[_-]', filename):
                    return profile.streamer_id

                # Pattern 2: [Name] Title.mp4
                if re.search(rf'\[{re.escape(name)}\]', filename):
                    return profile.streamer_id

                # Pattern 3: name at start of filename
                if filename.startswith(name):
                    return profile.streamer_id

        return None

    def _detect_from_directory(self, video_path: str) -> Optional[str]:
        """
        Detect streamer from parent directory names.

        Supported patterns:
        - vods/asmongold/video.mp4
        - downloads/zackrawrr/2024-12-23/stream.mp4
        - content/sejm/posiedzenie_123.mp4
        """
        path_parts = Path(video_path).parts
        path_lower = [part.lower() for part in path_parts]

        # Get all known streamers
        profiles = self.streamer_manager.list_all()

        for profile in profiles:
            streamer_id = profile.streamer_id.lower()
            aliases = [alias.lower() for alias in profile.aliases]

            all_names = [streamer_id] + aliases

            # Check if any directory in path matches streamer
            for name in all_names:
                if name in path_lower:
                    return profile.streamer_id

        return None


def detect_streamer(
    video_path: str,
    explicit_id: Optional[str] = None,
    default: str = "sejm"
) -> str:
    """
    Convenience function: Auto-detect streamer.

    Args:
        video_path: Path to video file
        explicit_id: Explicitly provided streamer_id (highest priority)
        default: Fallback if detection fails

    Returns:
        streamer_id: Detected or default streamer ID

    Examples:
        >>> detect_streamer("vods/asmongold/2024_12_23.mp4")
        'asmongold'

        >>> detect_streamer("sejm_posiedzenie_123.mp4")
        'sejm'

        >>> detect_streamer("video.mp4", explicit_id="asmongold")
        'asmongold'
    """
    from pipeline.streamers import get_manager

    manager = get_manager()
    detector = StreamerDetector(manager, default_streamer=default)

    return detector.detect(video_path, explicit_id)
