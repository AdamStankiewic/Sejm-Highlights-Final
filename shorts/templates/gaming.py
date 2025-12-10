"""Gaming template with robust facecam detection and stable 9:16 layout."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Tuple

import cv2
from moviepy.editor import ColorClip, CompositeVideoClip, VideoClip, VideoFileClip
from moviepy.video.fx.all import speedx as vfx_speedx

from utils.video import (
    add_subtitles,
    apply_speedup,
    center_crop_9_16,
    ensure_fps,
    ensure_output_path,
    load_subclip,
)
from .base import TemplateBase

logger = logging.getLogger(__name__)

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


REGION_DEFS = {
    "right_top": (0.60, 0.00, 0.38, 0.40),
    "right_middle": (0.60, 0.30, 0.38, 0.40),
    "right_bottom": (0.60, 0.60, 0.38, 0.40),
    "left_top": (0.02, 0.00, 0.38, 0.40),
    "left_middle": (0.02, 0.30, 0.38, 0.40),
    "left_bottom": (0.02, 0.60, 0.38, 0.40),
}


@dataclass
class FacecamDetection:
    region: str
    bbox: Tuple[int, int, int, int]


class GamingTemplate(TemplateBase):
    name = "gaming"

    def __init__(self, face_regions: Iterable[str] | None = None):
        self.face_regions = list(face_regions) if face_regions else list(REGION_DEFS.keys())

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
    ) -> Path:
        logger.info("[GamingTemplate] Rendering segment %.2f-%.2f", start, end)
        output_path = ensure_output_path(Path(output_path))
        segment_duration = max(0.1, end - start)

        clip = load_subclip(video_path, start, end)
        if clip is None or clip.duration is None or clip.duration <= 0:
            logger.warning("[GamingTemplate] Hard failure loading clip — using black fallback")
            clip = ensure_fps(
                ColorClip(size=(1080, 1920), color=(0, 0, 0), duration=segment_duration)
            )

        clip = ensure_fps(clip.set_duration(segment_duration))
        logger.debug("Clip FPS after load and duration set: %s", clip.fps)

        subtitles_data = list(subtitles or [])

        detection = self._detect_facecam_region(video_path, start, end)
        logger.debug("[GamingTemplate] Detection result: %s", detection)

        try:
            gameplay_clip = center_crop_9_16(clip)
            logger.debug("Clip FPS after gameplay crop: %s", gameplay_clip.fps)
            if speedup and speedup > 1.0:
                try:
                    gameplay_clip = ensure_fps(gameplay_clip.fx(vfx_speedx, speedup))
                    logger.debug("Clip FPS after video speedup: %s", gameplay_clip.fps)
                    if gameplay_clip.audio:
                        new_audio = apply_speedup(gameplay_clip.audio, speedup)
                        gameplay_clip = gameplay_clip.set_audio(new_audio)
                except Exception:
                    logger.exception("[GamingTemplate] Speedup failed — using original speed")

            if add_subtitles and subtitles_data:
                gameplay_clip = add_subtitles(gameplay_clip, subtitles_data)
                logger.debug("Clip FPS after subtitles: %s", gameplay_clip.fps)

            if copyright_processor:
                gameplay_clip = copyright_processor.clean_clip_audio(
                    gameplay_clip, video_path, start, end, output_path.stem
                )

            gameplay_clip = ensure_fps(gameplay_clip.set_duration(segment_duration))
            logger.debug("Clip FPS before layout: %s", gameplay_clip.fps)

            if detection:
                final = self._build_layout_with_face(
                    clip, gameplay_clip, detection.region, detection.bbox
                )
            else:
                logger.warning("[GamingTemplate] No face detected, using gameplay-only layout")
                final = self._build_layout_gameplay_only(gameplay_clip)

            final = ensure_fps(final.set_duration(segment_duration))
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
            logger.exception("[GamingTemplate] Hard failure during render")
            try:
                clip.close()
            except Exception:
                pass
            return None

    def _detect_facecam_region(
        self, video_path: Path, start: float, end: float, samples: int = 6
    ) -> FacecamDetection | None:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.exception("[GamingTemplate] Cannot open video for face detection: %s", video_path)
            return None

        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            start_frame = int(max(0, start) * fps)
            end_frame = int(max(start, end) * fps)
            total_frames = max(end_frame - start_frame, 1)

            frame_idxs = [start_frame + int(i * total_frames / max(samples - 1, 1)) for i in range(samples)]
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            regions_px = self._region_pixels(width, height)

            matches: dict[str, list[Tuple[int, int, int, int]]] = {name: [] for name in regions_px}

            for frame_idx in frame_idxs:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                if not ret:
                    continue

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = FACE_CASCADE.detectMultiScale(gray, 1.1, 4)
                for (fx, fy, fw, fh) in faces:
                    cx, cy = fx + fw / 2, fy + fh / 2
                    for region_name in self.face_regions:
                        region = regions_px.get(region_name)
                        if not region:
                            continue
                        x1, y1, x2, y2 = region
                        if x1 <= cx <= x2 and y1 <= cy <= y2:
                            matches[region_name].append((fx, fy, fw, fh))

            best_region = None
            best_count = 0
            best_area = 0
            for region_name, bboxes in matches.items():
                if not bboxes:
                    continue
                count = len(bboxes)
                area_sum = sum(w * h for (_, _, w, h) in bboxes)
                if count > best_count or (count == best_count and area_sum > best_area):
                    best_region = region_name
                    best_count = count
                    best_area = area_sum

            if not best_region:
                return None

            bbox_list = matches[best_region]
            avg = [int(sum(vals) / len(bbox_list)) for vals in zip(*bbox_list)]
            logger.info(
                "[GamingTemplate] Facecam detected in region %s, bbox=%s", best_region, tuple(avg)
            )
            return FacecamDetection(region=best_region, bbox=tuple(avg))
        finally:
            cap.release()

    def _region_pixels(self, width: int, height: int) -> dict[str, Tuple[int, int, int, int]]:
        regions = {}
        for name in self.face_regions:
            if name not in REGION_DEFS:
                continue
            rx, ry, rw, rh = REGION_DEFS[name]
            x1 = int(width * rx)
            y1 = int(height * ry)
            x2 = int(width * (rx + rw))
            y2 = int(height * (ry + rh))
            regions[name] = (x1, y1, x2, y2)
        return regions

    def _build_layout_with_face(
        self,
        source_clip: VideoFileClip,
        gameplay_clip: VideoFileClip,
        region_name: str,
        bbox: Tuple[int, int, int, int],
    ) -> VideoClip:
        target_w, target_h = 1080, 1920
        x, y, w, h = bbox
        margin = 1.2
        x1 = max(0, int(x - (margin - 1) * w / 2))
        y1 = max(0, int(y - (margin - 1) * h / 2))
        x2 = int(min(source_clip.w, x + w * margin))
        y2 = int(min(source_clip.h, y + h * margin))

        face_clip = source_clip.crop(x1=x1, y1=y1, x2=x2, y2=y2)
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))
        face_clip = face_clip.resize(width=int(target_w * 0.45))
        logger.debug("Clip FPS after face crop: %s", face_clip.fps)

        gameplay_full = center_crop_9_16(gameplay_clip)
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, target_h)).set_duration(source_clip.duration))
        logger.debug("Clip FPS after gameplay resize: %s", gameplay_full.fps)

        side = "left" if region_name.startswith("left_") else "right"
        if region_name.endswith("top"):
            vertical = "top"
        elif region_name.endswith("middle"):
            vertical = "middle"
        else:
            vertical = "bottom"

        margin_px = 40
        face_x = margin_px if side == "left" else target_w - face_clip.w - margin_px
        if vertical == "top":
            face_y = margin_px
        elif vertical == "middle":
            face_y = (target_h - face_clip.h) // 2
        else:
            face_y = target_h - face_clip.h - margin_px

        face_clip = face_clip.set_position((face_x, face_y))
        face_clip = ensure_fps(face_clip.set_duration(source_clip.duration))
        logger.debug("Clip FPS after face positioning: %s", face_clip.fps)

        final = CompositeVideoClip(
            [gameplay_full, face_clip],
            size=(target_w, target_h),
        ).set_duration(source_clip.duration)
        final = ensure_fps(final)
        logger.info("[GamingTemplate] Using gameplay+face layout (%s, %s)", side, vertical)
        return final

    def _build_layout_gameplay_only(self, gameplay_clip: VideoFileClip) -> VideoClip:
        target_w, target_h = 1080, 1920
        gameplay_full = center_crop_9_16(gameplay_clip, scale=1.05)
        gameplay_full = ensure_fps(gameplay_full.resize((target_w, target_h)).set_duration(gameplay_clip.duration))
        logger.debug("Clip FPS after gameplay-only layout: %s", gameplay_full.fps)
        return gameplay_full

