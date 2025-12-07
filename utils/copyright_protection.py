"""Lightweight copyright protection for audio tracks.

This module scans audio for potential copyrighted music using a local
music/non‑music classifier and optional AudD.io lookup. If suspicious
content is detected, the audio is muted in short regions or replaced with
royalty‑free music.
"""

from __future__ import annotations

import logging
import random
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Tuple

import requests
from moviepy.audio.AudioClip import AudioClip
from moviepy.audio.fx import all as afx
from moviepy.editor import AudioFileClip, VideoFileClip
from transformers import pipeline

LOG_PATH = Path("logs") / "copyright.log"


def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("copyright")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_PATH, encoding="utf-8")
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    return logger


@dataclass
class CopyrightSettings:
    enable_protection: bool = True
    audd_api_key: str = ""
    music_detection_threshold: float = 0.7
    royalty_free_folder: Path = Path("assets/royalty_free")


class CopyrightProtector:
    """Detects and fixes copyrighted music in clips.

    The detector first uses a lightweight music/non‑music classifier from
    HuggingFace (audeering/wav2-music-1.0). If music likelihood exceeds the
    threshold, it optionally queries AudD.io for track identification and
    mutes/replaces the detected regions.
    """

    def __init__(self, settings: CopyrightSettings):
        self.settings = settings
        self.logger = _setup_logger()
        self._music_classifier = None

    def _load_model(self):
        if self._music_classifier is not None:
            return self._music_classifier
        try:
            self._music_classifier = pipeline("audio-classification", model="audeering/wav2-music-1.0")
        except Exception as exc:  # pragma: no cover - safety
            self.logger.warning("Music classifier unavailable: %s", exc)
            self._music_classifier = None
        return self._music_classifier

    def _sample_audio(self, video: VideoFileClip, start: float, duration: float, tmp_dir: Path) -> Path:
        sample = video.audio.subclip(start, min(video.duration, start + duration))
        sample_path = tmp_dir / f"sample_{int(start)}.wav"
        sample.write_audiofile(sample_path.as_posix(), fps=video.audio.fps, verbose=False, logger=None)
        sample.close()
        return sample_path

    def _detect_music_segments(self, video_path: Path) -> List[Tuple[float, float]]:
        classifier = self._load_model()
        if classifier is None:
            return []
        try:
            video = VideoFileClip(video_path.as_posix())
        except Exception as exc:  # pragma: no cover - io failure
            self.logger.warning("Cannot open video for copyright scan: %s", exc)
            return []

        detections: List[Tuple[float, float]] = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            step = 30.0
            sample_len = 15.0 if video.duration > 30 else max(5.0, video.duration * 0.3)
            t = 0.0
            while t < video.duration:
                sample_path = self._sample_audio(video, t, sample_len, tmp_dir)
                try:
                    result = classifier(sample_path.as_posix())
                except Exception as exc:  # pragma: no cover - runtime failure
                    self.logger.warning("Classifier failed on sample %.2fs: %s", t, exc)
                    t += step
                    continue
                best = result[0] if result else None
                if best and best.get("score", 0.0) >= self.settings.music_detection_threshold:
                    detections.append((t, min(video.duration, t + sample_len)))
                t += step
        video.close()
        return detections

    def _query_audd(self, audio_path: Path) -> dict | None:
        if not self.settings.audd_api_key:
            return None
        try:
            with open(audio_path, "rb") as f:
                resp = requests.post(
                    "https://api.audd.io/",
                    data={"api_token": self.settings.audd_api_key, "return": "apple_music,spotify"},
                    files={"file": f},
                    timeout=10,
                )
            if resp.status_code != 200:
                return None
            data = resp.json()
            return data.get("result")
        except Exception as exc:  # pragma: no cover - network errors
            self.logger.warning("AudD lookup failed: %s", exc)
            return None

    def _mute_intervals(self, audio: AudioClip, intervals: Iterable[Tuple[float, float]]) -> AudioClip:
        intervals = list(intervals)

        def volume_at(t: float) -> float:
            for s, e in intervals:
                if s <= t <= e:
                    return 0.0
            return 1.0

        return audio.fx(afx.volumex, volume_at)

    def _replace_with_royalty_free(self, duration: float) -> AudioFileClip | None:
        folder = Path(self.settings.royalty_free_folder)
        if not folder.exists():
            return None
        tracks = list(folder.glob("*.mp3")) + list(folder.glob("*.wav"))
        if not tracks:
            return None
        track = random.choice(tracks)
        clip = AudioFileClip(track.as_posix())
        return clip.set_duration(duration)

    def scan_and_fix(self, video_path: str) -> tuple[str, str]:
        """Scan the file and return (path, status)."""

        if not self.settings.enable_protection:
            return video_path, "skipped"

        path = Path(video_path)
        if not path.exists():
            return video_path, "failed"

        intervals = self._detect_music_segments(path)
        if not intervals:
            return video_path, "clean"

        try:
            video = VideoFileClip(path.as_posix())
        except Exception as exc:  # pragma: no cover - io failure
            self.logger.error("Cannot open video for audio fix: %s", exc)
            return video_path, "failed"

        try:
            # Refine with AudD on first detection
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                refined_intervals: List[Tuple[float, float]] = []
                for (s, e) in intervals:
                    sample_path = self._sample_audio(video, s, min(20.0, e - s), tmp_dir)
                    audd_result = self._query_audd(sample_path)
                    if audd_result and audd_result.get("artist"):
                        title = audd_result.get("title", "?")
                        artist = audd_result.get("artist", "?")
                        self.logger.info("Detected copyrighted track %s – %s at %.2fs", title, artist, s)
                        refined_intervals.append((max(0, s - 5), min(video.duration, e + 5)))
                    else:
                        refined_intervals.append((s, e))

                total_mute = sum(e - s for s, e in refined_intervals)
                status = "muted_fragment"
                if total_mute / max(video.duration, 1) > 0.45:
                    rf = self._replace_with_royalty_free(video.duration)
                    if rf:
                        fixed_audio = rf
                        status = "replaced_audio"
                    else:
                        fixed_audio = self._mute_intervals(video.audio, refined_intervals)
                else:
                    fixed_audio = self._mute_intervals(video.audio, refined_intervals)

                # Optional crop of 10s if detection at edges for long videos
                cropped = False
                if video.duration > 300 and any(s < 5 or e > video.duration - 5 for s, e in refined_intervals):
                    video = video.subclip(10, max(10, video.duration - 10))
                    cropped = True

                video = video.set_audio(fixed_audio)
                fixed_path = path.with_name(f"{path.stem}_fixed{path.suffix}")
                video.write_videofile(
                    fixed_path.as_posix(),
                    codec="libx264",
                    audio_codec="aac",
                    threads=2,
                    verbose=False,
                    logger=None,
                )
                video.close()
                final_status = "cropped" if cropped else status
                return fixed_path.as_posix(), final_status
        except Exception as exc:  # pragma: no cover - robustness
            self.logger.error("Copyright fix failed for %s: %s", path, exc)
            return video_path, "failed"

    # --- Integration helper for already-open clips (shorts) ---
    def clean_clip_audio(
        self,
        clip: VideoFileClip,
        source_path: Path,
        start: float,
        end: float,
        stem: str,
    ) -> VideoFileClip:
        """Inspect a clip segment and mute/replace audio inline.

        Used by shorts templates to avoid an extra render pass. This keeps the
        same duration and returns a clip with sanitized audio.
        """

        if not self.settings.enable_protection:
            return clip

        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_dir = Path(tmp)
                sample_path = self._sample_audio(clip, 0, min(clip.duration, 15.0), tmp_dir)
                classifier = self._load_model()
                if classifier is None:
                    return clip
                result = classifier(sample_path.as_posix())
                best = result[0] if result else None
                if not best or best.get("score", 0.0) < self.settings.music_detection_threshold:
                    return clip
                audd_result = self._query_audd(sample_path)
                if audd_result:
                    self.logger.info(
                        "Short clip %s flagged as copyrighted: %s - %s", stem, audd_result.get("artist"), audd_result.get("title")
                    )
                muted_audio = self._mute_intervals(clip.audio, [(0, clip.duration)])
                return clip.set_audio(muted_audio)
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Inline copyright cleaning failed: %s", exc)
            return clip

