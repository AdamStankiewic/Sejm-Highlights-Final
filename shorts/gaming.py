"""Szablony Shorts (gaming/universal/IRL placeholder).

Minimalna, ale stabilna implementacja:
- TemplateBase: kontrakt apply()
- GamingTemplate: detekcja twarzy w narożnikach (Haar cascade) + crop 9:16
- UniversalTemplate: prosty crop 9:16 z lekkim zoom-out
- IRLTemplatePlaceholder: przekierowanie do uniwersalnego cropu

Komentarze PL/EN zgodnie z wytycznymi.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

try:
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - środowisko bez OpenCV
    cv2 = None  # type: ignore

try:
    from moviepy.editor import ImageClip, VideoFileClip
    from moviepy.video.fx import all as vfx
except ImportError:  # pragma: no cover - środowisko testowe
    ImageClip = None  # type: ignore
    VideoFileClip = None  # type: ignore
    vfx = None  # type: ignore


@dataclass
class DetectionResult:
    """Prosty wynik detekcji twarzy."""

    bbox: Optional[Tuple[int, int, int, int]]
    confidence: float
    method: str


class TemplateBase:
    """Bazowa klasa dla szablonów Shorts."""

    name: str = "base"

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def apply(self, clip: "VideoFileClip", output_path: Path, **kwargs) -> Path:
        """Zastosuj szablon. Must be overridden."""

        raise NotImplementedError


class UniversalTemplate(TemplateBase):
    """Uniwersalny crop 9:16 z delikatnym zoom out."""

    name = "universal"

    def apply(self, clip: "VideoFileClip", output_path: Path, zoom: float = 0.9, **_: object) -> Path:
        if VideoFileClip is None:
            raise RuntimeError("MoviePy niedostępny - nie mogę wygenerować shorta")

        self.logger.info("[UniversalTemplate] Center crop 9:16")
        w, h = clip.size
        target_ratio = 9 / 16
        new_w = min(w, int(h * target_ratio))
        x1 = int((w - new_w) / 2)
        x2 = x1 + new_w

        cropped = clip.crop(x1=x1, x2=x2)
        if zoom != 1.0:
            cropped = cropped.fx(vfx.resize, zoom)

        cropped.write_videofile(str(output_path), codec="libx264", audio_codec="aac", threads=2, verbose=False, logger=None)
        return output_path


class GamingTemplate(TemplateBase):
    """Gamingowy szablon z detekcją kamerki w rogach."""

    name = "gaming"

    def __init__(self, logger: logging.Logger, use_ai_fallback: bool = False):
        super().__init__(logger)
        self.use_ai_fallback = use_ai_fallback
        self._face_cascade = None
        if cv2 is not None:
            try:
                self._face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
            except Exception as exc:  # pragma: no cover - środowisko bez modeli
                self.logger.warning("[GamingTemplate] Nie udało się zainicjalizować Haar cascade: %s", exc)

    def _detect_face(self, frame: np.ndarray) -> DetectionResult:
        if cv2 is None or self._face_cascade is None:
            return DetectionResult(None, 0.0, "none")

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces) == 0:
            return DetectionResult(None, 0.0, "haar")
        x, y, w, h = faces[0]
        return DetectionResult((int(x), int(y), int(w), int(h)), 0.9, "haar")

    def _detect_face_ai(self, frame_path: Path) -> DetectionResult:
        """Opcjonalny fallback z GPT-4o-vision (mock-friendly)."""

        if not self.use_ai_fallback:
            return DetectionResult(None, 0.0, "off")

        try:
            from openai import OpenAI

            client = OpenAI()
            with open(frame_path, "rb") as f:
                img_bytes = f.read()

            prompt = "Locate streamer facecam position in gaming stream, return bbox x,y,w,h in JSON"
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": [{"type": "text", "text": prompt}, {"type": "image", "image": img_bytes}]}],
                max_tokens=150,
            )
            content = resp.choices[0].message.content if resp and resp.choices else ""
            # Parsowanie defensywne
            import json as _json

            coords = _json.loads(content) if content else {}
            bbox = (int(coords.get("x", 0)), int(coords.get("y", 0)), int(coords.get("w", 0)), int(coords.get("h", 0)))
            if sum(bbox) == 0:
                return DetectionResult(None, 0.0, "vision")
            return DetectionResult(bbox, 0.5, "vision")
        except Exception as exc:  # pragma: no cover - środowisko offline
            self.logger.warning("[GamingTemplate] Vision fallback failed: %s", exc)
            return DetectionResult(None, 0.0, "vision_error")

    def _find_face_in_clip(self, clip: "VideoFileClip", tmp_frame: Path) -> DetectionResult:
        start = time.perf_counter()
        step = 5.0
        if VideoFileClip is None:
            return DetectionResult(None, 0.0, "none")
        for t in np.arange(0, max(0.1, clip.duration), step):
            if time.perf_counter() - start > 5.0:
                self.logger.warning("[GamingTemplate] Timeout 5s podczas detekcji twarzy")
                break
            frame = clip.get_frame(min(t, clip.duration - 0.05))
            result = self._detect_face(frame)
            if result.bbox:
                return result
        # AI fallback na ostatnim kadrze
        if self.use_ai_fallback:
            clip.save_frame(str(tmp_frame), t=min(clip.duration / 2, clip.duration - 0.1))
            return self._detect_face_ai(tmp_frame)
        return DetectionResult(None, 0.0, "none")

    def apply(self, clip: "VideoFileClip", output_path: Path, **kwargs) -> Path:
        if VideoFileClip is None:
            raise RuntimeError("MoviePy niedostępny - nie mogę wygenerować shorta")

        face_result = self._find_face_in_clip(clip, output_path.with_suffix(".jpg"))
        w, h = clip.size
        target_ratio = 9 / 16
        new_w = min(w, int(h * target_ratio * 0.95))
        x1 = int((w - new_w) / 2)
        x2 = x1 + new_w
        base = clip.crop(x1=x1, x2=x2)

        if face_result.bbox:
            x, y, fw, fh = face_result.bbox
            self.logger.info("[GamingTemplate] Face detected via %s at (%s,%s,%s,%s)", face_result.method, x, y, fw, fh)
            face_clip = clip.crop(x1=x, y1=y, x2=x + fw, y2=y + fh).fx(vfx.resize, (200, 200))
            face_clip = face_clip.set_position((base.w / 2 - 100, base.h - 220))
            composed = ImageClip(np.zeros((base.h, base.w, 3), dtype=np.uint8)).set_duration(base.duration)
            composed = composed.set_audio(base.audio)
            composed = composed.set_fps(base.fps)
            composed = composed.set_mask(None)
            composed = composed.set_position((0, 0))
            composed = composed.set_duration(base.duration)
            composed = composed.set_audio(base.audio)
            composed = composed.set_fps(base.fps)
            composed = composed.overlay(base)
            composed = composed.overlay(face_clip)
            final_clip = composed
        else:
            self.logger.info("[GamingTemplate] Brak twarzy - używam tylko crop 9:16")
            final_clip = base

        final_clip.write_videofile(
            str(output_path),
            codec="libx264",
            audio_codec="aac",
            threads=2,
            verbose=False,
            logger=None,
        )
        return output_path


class IRLTemplatePlaceholder(TemplateBase):
    """Placeholder dla przyszłych szablonów IRL."""

    name = "irl"

    def apply(self, clip: "VideoFileClip", output_path: Path, **kwargs) -> Path:
        self.logger.info("[IRLTemplatePlaceholder] Używam uniwersalnego cropu (placeholder)")
        universal = UniversalTemplate(self.logger)
        return universal.apply(clip, output_path, **kwargs)

