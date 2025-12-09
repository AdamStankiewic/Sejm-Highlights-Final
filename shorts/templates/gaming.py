"""Gaming template with more robust facecam detection and fallbacks."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, Tuple

import cv2
from moviepy.editor import (
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    VideoFileClip,
)

from utils.video import (
    center_crop_9_16,
    apply_speedup,
    add_subtitles,
    ensure_fps,
    ensure_output_path,
    load_subclip,
)
from .base import TemplateBase

logger = logging.getLogger(__name__)

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


class GamingTemplate(TemplateBase):
    name = "gaming"

    def __init__(self, face_regions: Iterable[str] | None = None):
        self.face_regions = face_regions or [
            "top_right",
            "mid_right",
            "bottom_right",
            "top_left",
            "bottom_left",
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
        segment_duration = max(0.1, end - start)
        clip = load_subclip(video_path, start, end)

        if clip is None or clip.duration is None or clip.duration <= 0:
            logger.warning("[GamingTemplate] Invalid clip — using fallback segment")
            clip = ensure_fps(
                ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=segment_duration)
            )
            clip.audio = CompositeAudioClip([])

        clip = clip.set_duration(segment_duration)
        logger.debug("Clip FPS after load and duration set: %s", clip.fps)

        subtitles_data = list(subtitles or [])
        face_snapshot = self._detect_face(video_path, start, end)

        try:
            clip = center_crop_9_16(clip, scale=0.9)
            logger.debug("Clip FPS after center crop: %s", clip.fps)
            if speedup and speedup > 1.0:
                clip = apply_speedup(clip, speedup)
                clip = ensure_fps(clip)
                logger.debug("Clip FPS after speedup: %s", clip.fps)
            if add_subtitles and subtitles_data:
                clip = add_subtitles(clip, subtitles_data)
                logger.debug("Clip FPS after subtitles: %s", clip.fps)

            if copyright_processor:
                clip = copyright_processor.clean_clip_audio(
                    clip, video_path, start, end, output_path.stem
                )

            clip = ensure_fps(clip)
            if clip.audio is None:
                clip.audio = CompositeAudioClip([])
            logger.debug("Clip FPS before composition: %s", clip.fps)

            final = (
                self._compose_with_face(clip, face_snapshot)
                if face_snapshot
                else self._compose_gameplay_only(clip)
            )

            if final.fps is None:
                logger.warning("Final composite had no fps – forcing 30fps")
                final = final.set_fps(30)
            final = ensure_fps(final)
            logger.debug("Clip FPS before render: %s", final.fps)

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
        except Exception:
            logger.exception(
                "[GamingTemplate] Failed rendering segment %.2f-%.2f", start, end
            )
            try:
                fallback = ensure_fps(
                    ColorClip(
                        size=(1080, 1920), color=(0, 0, 0), duration=segment_duration
                    )
                )
                fallback.audio = CompositeAudioClip([])
                fallback = fallback.set_duration(segment_duration)
                fallback.write_videofile(
                    str(output_path),
                    codec="libx264",
                    audio_codec="aac",
                    threads=2,
                    verbose=False,
                    logger=None,
                )
                fallback.close()
            except Exception:
                logger.exception("[GamingTemplate] Failed to render fallback clip")
            try:
                clip.close()
            except Exception:
                pass
            return output_path

    def _detect_face(self, video_path: Path, start: float, end: float):
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.exception("Cannot open video for face detection: %s", video_path)
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
            for region_name in self.face_regions:
                if region_name not in regions:
                    continue
                x1, y1, x2, y2 = regions[region_name]
                region_gray = gray[y1:y2, x1:x2]
                if region_gray.size == 0:
                    continue
                faces = FACE_CASCADE.detectMultiScale(region_gray, 1.1, 4)
                for (fx, fy, fw, fh) in faces:
                    gx, gy = x1 + fx, y1 + fy
                    crop = frame[gy : gy + fh, gx : gx + fw]
                    cap.release()
                    return crop[:, :, ::-1], (gx, gy, fw, fh)  # convert BGR to RGB
            frame_idx += step_frames
        cap.release()
        return found

    def _regions_from_config(self, cap):
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        regions = {
            "top_left": (0, 0, int(w * 0.5), int(h * 0.5)),
            "top_right": (int(w * 0.5), 0, int(w), int(h * 0.5)),
            "bottom_left": (0, int(h * 0.5), int(w * 0.5), int(h)),
            "bottom_right": (int(w * 0.5), int(h * 0.5), int(w), int(h)),
            "mid_right": (int(w * 0.6), 0, int(w), int(h)),
        }
        return regions

    def _in_allowed_region(self, x, y, w, h, regions):
        cx = x + w / 2
        cy = y + h / 2
        for name in self.face_regions:
            if name not in regions:
                continue
            x1, y1, x2, y2 = regions[name]
            if x1 <= cx <= x2 and y1 <= cy <= y2:
                return True
        return False

    def _compose_with_face(self, clip, face_snapshot):
        face_img, bbox = face_snapshot
        target_w, target_h = 1080, 1920

        gameplay = center_crop_9_16(clip).resize(height=int(target_h * 0.65))
        gameplay = ensure_fps(gameplay.set_duration(clip.duration))
        logger.debug("Clip FPS after gameplay resize: %s", gameplay.fps)

        face_clip = ImageClip(face_img).set_duration(clip.duration)
        margin = 0.2
        exp_h = int(bbox[3] * (1 + margin))
        face_clip = face_clip.resize(height=min(int(target_h * 0.35), int(exp_h)))
        face_clip = face_clip.set_position(("center", target_h - face_clip.h - 40))
        face_clip = ensure_fps(face_clip.set_duration(clip.duration))
        logger.debug("Clip FPS after face clip prep: %s", face_clip.fps)

        final = CompositeVideoClip(
            [
                gameplay.set_position(("center", 0)),
                face_clip,
            ],
            size=(target_w, target_h),
        ).set_duration(clip.duration)
        final = ensure_fps(final)
        logger.debug("Clip FPS after compose_with_face: %s", final.fps)
        logger.info("[GamingTemplate] Using gameplay+face layout")
        return final

    def _compose_gameplay_only(self, clip):
        logger.warning("[GamingTemplate] No face detected — using gameplay-only layout")
        target_w, target_h = 1080, 1920
        gameplay = center_crop_9_16(clip).resize((target_w, target_h))
        gameplay = ensure_fps(gameplay.set_duration(clip.duration))
        logger.debug("Clip FPS after gameplay-only resize: %s", gameplay.fps)
        return gameplay
