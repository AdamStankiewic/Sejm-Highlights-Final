"""Unified face detection for facecam region identification in gaming streams.

This module provides a clean abstraction for detecting webcam/facecam regions
in video files using MediaPipe Face Detection with multi-frame consensus.

DETECTION STRATEGY:
    The detector uses a 3x3 grid covering all areas of the frame.
    Only center_middle is ignored (main gameplay area).
    Facecams can appear anywhere: corners, edges, center_top, center_bottom, etc.

    Visual layout (16:9 video):
    ┌──────────┬──────────┬──────────┐
    │   LEFT   │  CENTER  │  RIGHT   │
    │   TOP    │   TOP    │   TOP    │
    ├──────────┼──────────┼──────────┤
    │   LEFT   │ CENTER   │  RIGHT   │
    │  MIDDLE  │(GAMEPLAY)│  MIDDLE  │
    ├──────────┼──────────┼──────────┤
    │   LEFT   │  CENTER  │  RIGHT   │
    │  BOTTOM  │  BOTTOM  │  BOTTOM  │
    └──────────┴──────────┴──────────┘

    This prevents false positives from faces in gameplay content.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np

logger = logging.getLogger(__name__)


# Zone definitions: (x%, y%, w%, h%) of frame
# NOTE: Center column (33%-67% width) is NEVER checked - reserved for gameplay
ZONE_DEFINITIONS = {
    # Left edge zones (0-33% width)
    "left_top": (0.00, 0.00, 0.33, 0.33),
    "left_middle": (0.00, 0.33, 0.33, 0.34),
    "left_bottom": (0.00, 0.67, 0.33, 0.33),
    # Right edge zones (67-100% width)
    "right_top": (0.67, 0.00, 0.33, 0.33),
    "right_middle": (0.67, 0.33, 0.33, 0.34),
    "right_bottom": (0.67, 0.67, 0.33, 0.33),
}


@dataclass
class FaceRegion:
    """Detected face region with metadata"""
    zone: str  # "left_bottom", "right_top", etc.
    bbox: Tuple[int, int, int, int]  # (x, y, w, h) in pixels
    confidence: float  # Detection confidence (0-1)
    detection_rate: float  # % of frames where face was detected
    num_faces: int  # Number of faces detected in region


class FaceDetector:
    """MediaPipe-based face detector with multi-frame consensus.

    Analyzes multiple frames across a video segment to reliably detect
    facecam regions even with occasional occlusions or poor lighting.

    Example:
        detector = FaceDetector(confidence_threshold=0.5)
        region = detector.detect(video_path, start=10.0, end=20.0)
        if region:
            print(f"Facecam found in {region.zone}: {region.bbox}")
    """

    def __init__(
        self,
        confidence_threshold: float = 0.5,
        consensus_threshold: float = 0.3,
        num_samples: int = 5
    ):
        """Initialize face detector

        Args:
            confidence_threshold: Minimum confidence for face detection (0-1)
            consensus_threshold: Minimum detection rate to confirm region (0-1)
            num_samples: Number of frames to sample across segment
        """
        self.confidence_threshold = confidence_threshold
        self.consensus_threshold = consensus_threshold
        self.num_samples = num_samples
        self._init_mediapipe()

    def _init_mediapipe(self):
        """Initialize MediaPipe Face Detection"""
        try:
            import mediapipe as mp
            import cv2

            self.mp = mp
            self.cv2 = cv2
            self.mp_face_detection = mp.solutions.face_detection
            self.face_detector = self.mp_face_detection.FaceDetection(
                model_selection=0,  # 0 = short-range (< 2m), suitable for webcams
                min_detection_confidence=self.confidence_threshold
            )
            logger.info("MediaPipe Face Detection initialized successfully")

        except ImportError as e:
            logger.warning(
                "MediaPipe or OpenCV not available: %s. Face detection disabled.", e
            )
            self.face_detector = None

    def detect(
        self,
        video_path: Path,
        start: float,
        end: float
    ) -> Optional[FaceRegion]:
        """Detect facecam region in video segment using multi-frame sampling

        Args:
            video_path: Path to video file
            start: Start time in seconds
            end: End time in seconds

        Returns:
            FaceRegion if detected, None otherwise
        """
        if not self.face_detector:
            logger.debug("Face detector not available")
            return None

        try:
            duration = end - start
            sample_times = np.linspace(start, end, self.num_samples)

            logger.info(
                "Face detection: sampling %d frames from %.2f-%.2fs (duration=%.1fs)",
                self.num_samples, start, end, duration
            )

            detections: List[dict] = []
            all_zones: List[str] = []

            for t in sample_times:
                frame_detection = self._detect_in_frame(video_path, t)
                if frame_detection:
                    detections.append(frame_detection)
                    all_zones.append(frame_detection['zone'])

            if not all_zones:
                logger.info(
                    "No faces detected in any of %d sampled frames (%.2f-%.2fs)",
                    self.num_samples, start, end
                )
                return None

            logger.info(
                "Detected faces in %d/%d frames - zones: %s",
                len(all_zones), self.num_samples, dict(Counter(all_zones))
            )

            # Find dominant zone through voting
            zone_counts = Counter(all_zones)
            dominant_zone, dominant_count = zone_counts.most_common(1)[0]
            detection_rate = dominant_count / self.num_samples

            # Check for ambiguous detections (tie in votes)
            if len(zone_counts) > 1:
                _, second_count = zone_counts.most_common(2)[1]
                if second_count == dominant_count:
                    logger.warning(
                        "Ambiguous face detection: tie between zones %s",
                        zone_counts.most_common(2)
                    )
                    return None

            # Require minimum detection rate
            if detection_rate < self.consensus_threshold:
                logger.debug(
                    "Detection rate %.2f below threshold %.2f",
                    detection_rate,
                    self.consensus_threshold
                )
                return None

            # Get representative bbox from dominant zone (use most recent)
            dominant_detection = next(
                (d for d in reversed(detections) if d['zone'] == dominant_zone),
                detections[-1]
            )

            logger.info(
                "Face detected in %s (rate: %.2f, conf: %.2f)",
                dominant_zone,
                detection_rate,
                dominant_detection['confidence']
            )

            return FaceRegion(
                zone=dominant_zone,
                bbox=dominant_detection['bbox'],
                confidence=dominant_detection['confidence'],
                detection_rate=detection_rate,
                num_faces=dominant_detection['num_faces']
            )

        except Exception as e:
            logger.exception("Face detection failed: %s", e)
            return None

    def _detect_in_frame(self, video_path: Path, timestamp: float) -> Optional[dict]:
        """Detect faces in a single frame at given timestamp

        Returns:
            Dict with {zone, bbox, confidence, num_faces} or None
        """
        tmp_frame = None
        try:
            # Extract frame using ffmpeg
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_frame = tmp.name

            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),
                '-i', str(video_path),
                '-vframes', '1',
                '-q:v', '5',
                '-y',
                tmp_frame,
            ]
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            # Load and process frame
            frame = self.cv2.imread(tmp_frame)
            if frame is None:
                return None

            frame_rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape

            # Detect faces
            results = self.face_detector.process(frame_rgb)
            if not results or not results.detections:
                logger.debug("No faces detected at t=%.2fs", timestamp)
                return None

            # Extract all face bboxes
            faces = []
            for detection in results.detections:
                bbox = detection.location_data.relative_bounding_box
                confidence = detection.score[0]

                x = max(int(bbox.xmin * w), 0)
                y = max(int(bbox.ymin * h), 0)
                fw = int(bbox.width * w)
                fh = int(bbox.height * h)

                faces.append({
                    'x': x,
                    'y': y,
                    'w': fw,
                    'h': fh,
                    'confidence': confidence,
                    'area': max(fw, 0) * max(fh, 0),
                })

            if not faces:
                return None

            # Take largest face (main streamer)
            main_face = max(faces, key=lambda f: f['area'])

            # Classify to zone
            zone = self._classify_to_zone(main_face, w, h)
            if zone == "center_middle":
                logger.debug(
                    "Face at t=%.2fs in center_middle (ignored) - conf=%.2f",
                    timestamp, main_face['confidence']
                )
                return None  # Ignore center_middle faces (main gameplay area)

            logger.info(
                "Face detected at t=%.2fs in zone '%s' (conf=%.2f, size=%dx%d)",
                timestamp, zone, main_face['confidence'], main_face['w'], main_face['h']
            )

            return {
                'zone': zone,
                'bbox': (main_face['x'], main_face['y'], main_face['w'], main_face['h']),
                'confidence': main_face['confidence'],
                'num_faces': len(faces)
            }

        finally:
            if tmp_frame and os.path.exists(tmp_frame):
                try:
                    os.unlink(tmp_frame)
                except Exception:
                    pass

    def _classify_to_zone(
        self,
        face_bbox: dict,
        frame_w: int,
        frame_h: int
    ) -> str:
        """Classify face center to one of 9 zones (3x3 grid).

        Grid layout:
            Horizontal: LEFT (0-33%) | CENTER (33-67%) | RIGHT (67-100%)
            Vertical:   TOP (0-33%)  | MIDDLE (33-67%) | BOTTOM (67-100%)

        All 9 zones are valid except center_middle (gameplay area).
        Facecams can appear in center_top, center_bottom, left/right edges, etc.

        Args:
            face_bbox: Dict with {x, y, w, h}
            frame_w: Frame width in pixels
            frame_h: Frame height in pixels

        Returns:
            Zone name (e.g., "left_bottom", "center_top", "right_middle") or "center_middle" (ignored)
        """
        # Calculate face center point
        center_x = face_bbox['x'] + face_bbox['w'] / 2
        center_y = face_bbox['y'] + face_bbox['h'] / 2

        # Convert to relative ratios (0.0 - 1.0)
        col_ratio = center_x / frame_w
        row_ratio = center_y / frame_h

        # Determine column (left, center, or right)
        if col_ratio < 1/3:
            col = "left"
        elif col_ratio <= 2/3:
            col = "center"
        else:
            col = "right"

        # Determine row (top, middle, or bottom)
        if row_ratio < 1/3:
            row = "top"
        elif row_ratio < 2/3:
            row = "middle"
        else:
            row = "bottom"

        zone_name = f"{col}_{row}"

        # Only ignore center_middle (main gameplay area)
        if zone_name == "center_middle":
            logger.debug(
                "Face detected in center_middle (%.2f, %.2f) - ignored (gameplay area)",
                col_ratio, row_ratio
            )
            return "center_middle"

        logger.debug(
            "Face classified to zone: %s (col_ratio=%.2f, row_ratio=%.2f)",
            zone_name, col_ratio, row_ratio
        )
        return zone_name
