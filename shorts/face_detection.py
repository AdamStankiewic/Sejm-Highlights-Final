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
        """Initialize MediaPipe Face Detection (supports both old and new API)"""
        try:
            import mediapipe as mp
            import cv2

            self.mp = mp
            self.cv2 = cv2

            # Try new API first (MediaPipe 0.10.30+)
            try:
                from mediapipe.tasks import python
                from mediapipe.tasks.python import vision

                # New API uses BaseOptions and vision.FaceDetector
                logger.info("Using MediaPipe new API (0.10.30+)")

                # Download model if needed
                model_path = self._download_face_detector_model()

                # Create FaceDetector with new API
                base_options = python.BaseOptions(model_asset_path=model_path)
                options = vision.FaceDetectorOptions(
                    base_options=base_options,
                    min_detection_confidence=self.confidence_threshold
                )
                self.face_detector = vision.FaceDetector.create_from_options(options)
                self._use_new_api = True
                logger.info("MediaPipe Face Detection (new API) initialized successfully")

            except (ImportError, AttributeError) as e:
                # Fallback to old API (MediaPipe < 0.10.30)
                logger.info(f"New API not available ({e}), trying old API...")

                if not hasattr(mp, 'solutions'):
                    raise ImportError("MediaPipe 'solutions' module not available - incompatible version")

                self.mp_face_detection = mp.solutions.face_detection
                self.face_detector = self.mp_face_detection.FaceDetection(
                    model_selection=0,  # 0 = short-range (< 2m), suitable for webcams
                    min_detection_confidence=self.confidence_threshold
                )
                self._use_new_api = False
                logger.info("MediaPipe Face Detection (old API) initialized successfully")

        except ImportError as e:
            logger.warning(
                "MediaPipe or OpenCV not available: %s. Face detection disabled.", e
            )
            self.face_detector = None
            self._use_new_api = False

    def _download_face_detector_model(self) -> str:
        """Download MediaPipe face detector model if not cached"""
        import urllib.request
        from pathlib import Path

        # Cache directory
        cache_dir = Path.home() / ".cache" / "mediapipe"
        cache_dir.mkdir(parents=True, exist_ok=True)

        model_filename = "blaze_face_short_range.tflite"
        model_path = cache_dir / model_filename

        # Download if not exists
        if not model_path.exists():
            logger.info("Downloading MediaPipe face detector model...")
            model_url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"

            try:
                urllib.request.urlretrieve(model_url, model_path)
                logger.info(f"Model downloaded to {model_path}")
            except Exception as e:
                logger.error(f"Failed to download model: {e}")
                raise
        else:
            logger.info(f"Using cached model from {model_path}")

        return str(model_path)

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

    def _detect_in_frame(
        self,
        video_path: Path,
        timestamp: float,
        search_regions_only: bool = True
    ) -> Optional[dict]:
        """Detect faces in a single frame at given timestamp.

        Args:
            video_path: Path to video file
            timestamp: Timestamp in seconds
            search_regions_only: If True, crop to corner regions before detection
                                (avoids detecting game character faces in center)

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
                logger.warning("Failed to load extracted frame at t=%.2fs from %s", timestamp, tmp_frame)
                return None

            frame_rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape

            logger.debug(
                "Loaded frame at t=%.2fs: %dx%d pixels, processing with MediaPipe (threshold=%.2f)",
                timestamp, w, h, self.confidence_threshold
            )

            # If search_regions_only, check only corner regions to avoid game character faces
            regions_to_check = []
            if search_regions_only:
                # Define 4 corner regions (30% width x 30% height each)
                region_w = int(w * 0.30)
                region_h = int(h * 0.30)

                regions_to_check = [
                    ("right_top", w - region_w, 0, w, region_h),
                    ("right_bottom", w - region_w, h - region_h, w, h),
                    ("left_top", 0, 0, region_w, region_h),
                    ("left_bottom", 0, h - region_h, region_w, h),
                ]
                logger.debug(
                    "Searching %d corner regions (30%%x30%% each) instead of full frame",
                    len(regions_to_check)
                )
            else:
                # Search full frame (original behavior)
                regions_to_check = [("full_frame", 0, 0, w, h)]

            # Check each region for faces
            best_detection = None
            best_confidence = 0.0

            for region_name, x1, y1, x2, y2 in regions_to_check:
                # Crop to region
                region_frame = frame_rgb[y1:y2, x1:x2]
                region_w = x2 - x1
                region_h = y2 - y1

                # Detect faces in this region (supports both old and new API)
                if self._use_new_api:
                    # New MediaPipe API (0.10.30+)
                    import mediapipe as mp
                    import numpy as np
                    # ✅ FIX: Make array contiguous for MediaPipe (it requires C-contiguous arrays)
                    region_frame = np.ascontiguousarray(region_frame)
                    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=region_frame)
                    detection_result = self.face_detector.detect(mp_image)
                    detections_list = detection_result.detections if detection_result else []
                else:
                    # Old MediaPipe API (< 0.10.30)
                    results = self.face_detector.process(region_frame)
                    detections_list = results.detections if results and results.detections else []

                if not detections_list:
                    logger.debug(
                        "  Region '%s': no faces detected",
                        region_name
                    )
                    continue

                logger.debug(
                    "  Region '%s': found %d face(s)",
                    region_name, len(detections_list)
                )

                # Extract faces from this region
                for detection in detections_list:
                    # Get bounding box and confidence (API-dependent)
                    if self._use_new_api:
                        # New API: bounding_box is in absolute pixels
                        bbox_abs = detection.bounding_box
                        confidence = detection.categories[0].score if detection.categories else 0.5

                        # Convert to relative coordinates (0-1)
                        face_x = x1 + int(bbox_abs.origin_x)
                        face_y = y1 + int(bbox_abs.origin_y)
                        face_w = int(bbox_abs.width)
                        face_h = int(bbox_abs.height)
                    else:
                        # Old API: relative_bounding_box is in relative coords (0-1)
                        bbox = detection.location_data.relative_bounding_box
                        confidence = detection.score[0]

                        # Convert bbox from region coordinates to full frame coordinates
                        face_x = x1 + max(int(bbox.xmin * region_w), 0)
                        face_y = y1 + max(int(bbox.ymin * region_h), 0)
                        face_w = int(bbox.width * region_w)
                        face_h = int(bbox.height * region_h)

                    logger.debug(
                        "    Face: confidence=%.3f, bbox=(%d,%d,%d,%d), size=%dx%d",
                        confidence, face_x, face_y, face_x + face_w, face_y + face_h,
                        face_w, face_h
                    )

                    # Keep track of best detection across all regions
                    if confidence > best_confidence:
                        best_confidence = confidence
                        best_detection = {
                            'x': face_x,
                            'y': face_y,
                            'w': face_w,
                            'h': face_h,
                            'confidence': confidence,
                            'area': max(face_w, 0) * max(face_h, 0),
                            'zone': region_name if search_regions_only else None
                        }

            if not best_detection:
                logger.debug("No faces detected in any region at t=%.2fs", timestamp)
                return None

            # Use pre-determined zone if we searched regions, otherwise classify
            if search_regions_only and best_detection['zone']:
                zone = best_detection['zone']
                logger.debug(
                    "Using face from region '%s' (conf=%.3f)",
                    zone, best_detection['confidence']
                )
            else:
                # Classify to zone (original behavior for full-frame search)
                zone = self._classify_to_zone(best_detection, w, h)
                if zone == "center_middle":
                    logger.debug(
                        "Face at t=%.2fs in center_middle (ignored) - conf=%.2f",
                        timestamp, best_detection['confidence']
                    )
                    return None  # Ignore center_middle faces (main gameplay area)

            logger.info(
                "Face detected at t=%.2fs in zone '%s' (conf=%.2f, size=%dx%d)",
                timestamp, zone, best_detection['confidence'],
                best_detection['w'], best_detection['h']
            )

            return {
                'zone': zone,
                'bbox': (best_detection['x'], best_detection['y'],
                        best_detection['w'], best_detection['h']),
                'confidence': best_detection['confidence'],
                'num_faces': 1  # Only keeping best detection
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
