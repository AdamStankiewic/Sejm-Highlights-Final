"""Gaming template with facecam detection in corners."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple

import cv2
from moviepy.editor import ImageClip, VideoFileClip, CompositeVideoClip

from utils.video import center_crop_9_16, apply_speedup, add_subtitles, ensure_output_path, load_subclip
from .base import TemplateBase
from .universal import UniversalTemplate

logger = logging.getLogger(__name__)

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


class GamingTemplate(TemplateBase):
    name = "gaming"

    def __init__(self, face_regions: Iterable[str] | None = None):
        self.face_regions = face_regions or [
            "bottom_right",
            "bottom_left",
            "top_right",
            "top_left",
        ]

    def apply(
        self,
        video_path: Path,
        start: float,
        end: float,
        output_path: Path,
        speedup: float = 1.0,
        add_subtitles: bool = False,
        subtitles: Iterable[Tuple[str, float, float]] | None = None,
        subtitle_lang: str = "pl",
        copyright_processor=None,
    ) -> Path | None:
        logger.info("[GamingTemplate] Rendering segment %.2f-%.2f", start, end)
        output_path = ensure_output_path(Path(output_path))
        face_snapshot = self._detect_face(video_path, start, end)
        if face_snapshot is None:
            logger.warning("No face detected in regions; falling back to universal template")
            return UniversalTemplate().apply(
                video_path,
                start,
                end,
                output_path,
                speedup,
                add_subtitles,
                subtitles,
                subtitle_lang,
                copyright_processor,
            )
        clip = load_subclip(video_path, start, end)
        if clip is None:
            logger.warning("[GamingTemplate] Invalid clip — skipping segment")
            return None
        clip = center_crop_9_16(clip, scale=0.88)
        if add_subtitles and subtitles:
            clip = add_subtitles(clip, subtitles)
        if speedup > 1.0:
            try:
                clip = apply_speedup(clip, speedup)
            except Exception as exc:  # pragma: no cover - defensywnie
                logger.error("Speedup failed, keeping original speed: %s", exc)
        if copyright_processor:
            clip = copyright_processor.clean_clip_audio(clip, video_path, start, end, output_path.stem)
        face_img, (x, y, w, h) = face_snapshot
        face_clip = ImageClip(face_img).set_duration(clip.duration)
        face_clip = face_clip.resize(height=250)
        face_clip = face_clip.set_position(("center", clip.h - face_clip.h - 40))
        final = CompositeVideoClip([clip, face_clip]).set_duration(clip.duration)
        final.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            threads=2,
            verbose=False,
            logger=None,
        )
        final.close()
        clip.close()
        return output_path

    def _detect_face(self, video_path: Path, start: float, end: float):
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error("Cannot open video for face detection: %s", video_path)
            return None
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        step_frames = int(fps * 5)
        start_frame = int(max(0, start) * fps)
        end_frame = int(end * fps)
        regions = self._regions_from_config(cap)
        frame_idx = start_frame
        found = None
        while frame_idx <= end_frame:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = FACE_CASCADE.detectMultiScale(gray, 1.1, 4)
            for (x, y, w, h) in faces:
                if self._in_allowed_region(x, y, w, h, regions):
                    crop = frame[y : y + h, x : x + w]
                    cap.release()
                    return crop[:, :, ::-1], (x, y, w, h)  # convert BGR to RGB
            frame_idx += step_frames
        cap.release()
        return found

    def _regions_from_config(self, cap):
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        regions = {}
        regions["bottom_right"] = (w * 0.7, h * 0.7, w * 0.3, h * 0.3)
        regions["bottom_left"] = (0, h * 0.7, w * 0.3, h * 0.3)
        regions["top_right"] = (w * 0.7, 0, w * 0.3, h * 0.3)
        regions["top_left"] = (0, 0, w * 0.3, h * 0.3)
        return regions

    def _in_allowed_region(self, x, y, w, h, regions):
        cx = x + w / 2
        cy = y + h / 2
        for name in self.face_regions:
            if name not in regions:
                continue
            rx, ry, rw, rh = regions[name]
            if rx <= cx <= rx + rw and ry <= cy <= ry + rh:
                return True
        return False
