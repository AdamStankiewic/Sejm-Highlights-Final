"""Pipeline do usuwania muzyki chronionej prawem autorskim z krótkich klipów.

Działa defensywnie: jeśli AUDD/Demucs są niedostępne, zwraca mute fallback bez crasha.
"""
from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from moviepy.audio.io.AudioFileClip import AudioFileClip
from moviepy.editor import VideoFileClip

from .detector import CopyrightDetector

logger = logging.getLogger(__name__)


@dataclass
class CopyrightConfig:
    enabled: bool
    provider: str
    audd_api_key: str = ""
    keep_sfx: bool = True


class CopyrightProcessor:
    """Remove copyrighted music using AUDD detection + Demucs stems."""

    def __init__(self, config: CopyrightConfig):
        self.enabled = bool(config.enabled)
        self.detector = CopyrightDetector(config.provider, config.audd_api_key)
        self.keep_sfx = bool(config.keep_sfx)

    def _extract_audio_sample(self, video_path: Path, start: float, end: float) -> Optional[Path]:
        """Export 15s middle sample of a segment to temp wav."""
        mid = (start + end) / 2.0
        sample_start = max(start, mid - 7.5)
        sample_end = min(end, sample_start + 15.0)
        if sample_end <= sample_start:
            return None
        try:
            with VideoFileClip(str(video_path)) as clip:
                sub = clip.subclip(sample_start, sample_end)
                temp_file = Path(tempfile.mktemp(suffix="_sample.wav"))
                sub.audio.write_audiofile(str(temp_file), verbose=False, logger=None)
                return temp_file
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Audio sample extraction failed: %s", exc)
            return None

    def _apply_clean_audio(
        self, video_clip: VideoFileClip, clean_audio_path: Optional[Path], mute: bool
    ) -> VideoFileClip:
        if mute:
            return video_clip.set_audio(None)
        if clean_audio_path and clean_audio_path.exists():
            try:
                audio = AudioFileClip(str(clean_audio_path))
                return video_clip.set_audio(audio)
            except Exception as exc:  # pragma: no cover
                logger.warning("Failed to load clean audio: %s", exc)
                return video_clip.set_audio(None)
        return video_clip

    def process_segment(
        self,
        video_path: Path,
        start: float,
        end: float,
        segment_label: str = "segment",
    ) -> Tuple[Optional[Path], bool, Optional[str]]:
        """Return (clean_audio_path, mute_flag, detected_title)."""
        if not self.enabled:
            return None, False, None

        sample_path = self._extract_audio_sample(video_path, start, end)
        if not sample_path:
            logger.info("No sample extracted for %s – skipping copyright removal", segment_label)
            return None, False, None

        audd_result = {}
        detected_title = None
        if self.detector.provider == "audd":
            audd_result = self.detector.detect_with_audd(sample_path)
            if self.detector.has_copyright_match(audd_result):
                title = audd_result.get("title") or "muzyka"
                artist = audd_result.get("artist") or "unknown"
                detected_title = f"{title} – {artist}"
                logger.info("AUDD match: %s", detected_title)
            else:
                logger.info("AUDD: no copyrighted music detected")
                return None, False, None

        # Run Demucs for removal (either because provider=demucs or audd flagged)
        demucs_out = self.detector.separate_with_demucs(
            sample_path, Path(tempfile.mkdtemp()), keep_sfx=self.keep_sfx
        )
        if demucs_out:
            logger.info("Music removed for %s", segment_label)
            return demucs_out, False, detected_title

        logger.warning("Demucs unavailable/failed – muting audio for %s", segment_label)
        return None, True, detected_title

    def clean_clip_audio(
        self,
        video_clip: VideoFileClip,
        video_path: Path,
        start: float,
        end: float,
        segment_label: str = "segment",
    ) -> VideoFileClip:
        """Convenience helper to attach cleaned audio or mute."""
        clean_path, mute, detected = self.process_segment(video_path, start, end, segment_label)
        if detected:
            logger.info("Usunięto muzykę: %s", detected)
        return self._apply_clean_audio(video_clip, clean_path, mute)
