"""Utility helpers for shorts processing (speedup, subtitles, crops).

Funkcje współdzielone przez szablony shortsów i generator.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Iterable, Optional, Tuple

# Support both MoviePy 1.x and 2.x
try:
    # MoviePy 2.x
    from moviepy.audio.AudioClip import AudioClip
    import moviepy.audio.fx as afx
    from moviepy import CompositeVideoClip, VideoFileClip
    from moviepy.video.fx import Resize, Crop
    MOVIEPY_V2 = True
except ImportError:
    # MoviePy 1.x
    from moviepy.audio.AudioClip import AudioClip
    from moviepy.audio.fx import all as afx
    from moviepy.editor import CompositeVideoClip, VideoFileClip
    from moviepy.video.fx import resize, crop
    Resize = None
    Crop = None
    MOVIEPY_V2 = False

logger = logging.getLogger(__name__)


class FpsFixedCompositeVideoClip(CompositeVideoClip):
    """CompositeVideoClip with forced fps property.

    MoviePy's CompositeVideoClip.fps property can return None even when
    fps is explicitly provided to the constructor. This subclass overrides
    the fps property to always return our forced fps value.
    """
    def __init__(self, clips, size=None, bg_color=None, use_bgclip=False, fps=30, **kwargs):
        """Initialize with forced fps value.

        Args:
            clips: List of clips to compose
            size: Output size (width, height)
            bg_color: Background color
            use_bgclip: Whether to use first clip as background
            fps: Forced fps value (default: 30)
            **kwargs: Additional arguments for CompositeVideoClip
        """
        super().__init__(clips, size=size, bg_color=bg_color, use_bgclip=use_bgclip, **kwargs)
        self._forced_fps = fps
        logger.debug("FpsFixedCompositeVideoClip initialized with forced fps=%s", fps)

    @property
    def fps(self):
        """Always return forced fps value."""
        return self._forced_fps

    @fps.setter
    def fps(self, value):
        """Update forced fps value."""
        self._forced_fps = value
        logger.debug("FpsFixedCompositeVideoClip fps set to %s", value)


def ensure_fps(clip: VideoFileClip, fallback: int = 30) -> VideoFileClip:
    """THE ONLY fps enforcement function - ensures clip has valid, non-None fps.

    This function handles MoviePy's unreliable fps metadata by:
    1. Checking if current fps is valid (numeric, positive)
    2. Setting to fallback if invalid
    3. Force-assigning the attribute (MoviePy sometimes ignores set_fps)
    4. Logging for debugging

    Args:
        clip: VideoFileClip or any clip object
        fallback: FPS to use if current is invalid (default: 30)

    Returns:
        Clip with guaranteed valid fps attribute
    """
    # Determine target fps
    current_fps = getattr(clip, "fps", None)
    if not isinstance(current_fps, (int, float)) or current_fps <= 0:
        target_fps = fallback
        logger.debug("ensure_fps: Invalid fps=%s, using fallback=%s", current_fps, fallback)
    else:
        target_fps = current_fps
        logger.debug("ensure_fps: Current fps=%s is valid", current_fps)

    # ✅ FIX: Check if clip has set_fps method (ColorClip doesn't have it)
    if hasattr(clip, 'set_fps') and callable(getattr(clip, 'set_fps')):
        # Set fps using MoviePy API
        clip = clip.set_fps(target_fps)
    else:
        logger.debug("ensure_fps: Clip type %s has no set_fps method, using direct assignment only", type(clip).__name__)

    # Force attribute assignment (MoviePy workaround for some clip types)
    try:
        clip.fps = target_fps
        logger.debug("ensure_fps: Direct fps attribute assignment successful")
    except (AttributeError, TypeError) as e:
        logger.warning("ensure_fps: Unable to assign fps attribute directly: %s", e)

    # Verify fps was actually set
    final_fps = getattr(clip, "fps", None)
    if final_fps is None or final_fps != target_fps:
        logger.error(
            "ensure_fps: FAILED to set fps! target=%s, final=%s, clip_type=%s",
            target_fps, final_fps, type(clip).__name__
        )
    else:
        logger.debug("ensure_fps: SUCCESS - fps=%s", final_fps)

    return clip


def center_crop_9_16(clip: VideoFileClip, scale: float = 1.0) -> VideoFileClip:
    """Crop clip to 9:16 keeping center, optional scale (zoom out).

    ✅ FIX: Handle ColorClip which doesn't have fx() method
    """
    # ✅ FIX: Check if clip is ColorClip (has no fx method)
    if not hasattr(clip, 'fx') and not hasattr(clip, 'resized'):
        # ColorClip - just return as is (already 9:16 from template)
        logger.debug("center_crop_9_16: Skipping resize for ColorClip")
        return ensure_fps(clip)

    target_ratio = 9 / 16

    # ✅ DEBUG: Log scale parameter to verify it's being used
    logger.info("🔍 center_crop_9_16: scale=%.2f (1.0=normal, >1.0=zoom OUT to show MORE content)", scale)

    # Resize with scale factor
    if MOVIEPY_V2:
        # MoviePy 2.x: use Resize class - calculate new size from scale
        w, h = clip.size
        new_w, new_h = int(w * scale), int(h * scale)
        logger.info("   Resizing: %dx%d → %dx%d (scale=%.2f)", w, h, new_w, new_h, scale)
        clip = ensure_fps(Resize(width=new_w, height=new_h).apply(clip))
    else:
        # MoviePy 1.x: use .fx(resize, scale)
        clip = ensure_fps(clip.fx(resize.resize, scale))
    logger.debug("Clip FPS after resize: %s", clip.fps)
    w, h = clip.size
    current_ratio = w / h
    if abs(current_ratio - target_ratio) < 0.01:
        return ensure_fps(clip)
    if current_ratio > target_ratio:
        new_w = int(h * target_ratio)
        x1 = int((w - new_w) / 2)
        if MOVIEPY_V2:
            # MoviePy 2.x: Use Crop class with .apply() method
            cropped = Crop(x1=x1, y1=0, x2=x1+new_w, y2=h).apply(clip)
        else:
            cropped = crop.crop(clip, x1=x1, y1=0, width=new_w, height=h)
        cropped = ensure_fps(cropped)
        logger.debug("Clip FPS after center_crop_9_16 width crop: %s", cropped.fps)
        return cropped
    new_h = int(w / target_ratio)
    y1 = int((h - new_h) / 2)
    if MOVIEPY_V2:
        # MoviePy 2.x: Use Crop class with .apply() method
        cropped = Crop(x1=0, y1=y1, x2=w, y2=y1+new_h).apply(clip)
    else:
        cropped = crop.crop(clip, x1=0, y1=y1, width=w, height=new_h)
    cropped = ensure_fps(cropped)
    logger.debug("Clip FPS after center_crop_9_16 height crop: %s", cropped.fps)
    return cropped


def apply_speedup(clip: AudioClip | None, factor: float | None) -> AudioClip | None:
    """Przyspiesz klip audio w sposób defensywny."""

    if clip is None:
        return None

    if factor is None or factor == 1.0:
        return clip

    original_clip = clip
    try:
        if hasattr(afx, "audio_speedx"):
            return clip.fx(afx.audio_speedx, factor)
        if hasattr(afx, "speedx"):
            return clip.fx(afx.speedx, factor)
        logger.warning(
            "Audio speedup unavailable – no audio_speedx/speedx in moviepy.afx, using original audio"
        )
        return clip
    except Exception:
        logger.error("Audio speedup failed — using original audio", exc_info=True)
        return clip


def write_srt(subtitles: Iterable[Tuple[str, float, float]], srt_path: Path) -> Path:
    """Serialize subtitles to SRT file."""
    ensure_output_path(Path(srt_path))
    lines = []
    for idx, (text, start, end) in enumerate(subtitles, 1):
        lines.append(str(idx))
        lines.append(f"{_format_ts(start)} --> {_format_ts(end)}")
        lines.append(_wrap_subtitle_line(text))
        lines.append("")
    Path(srt_path).write_text("\n".join(lines), encoding="utf-8")
    return Path(srt_path)


def burn_subtitles_ffmpeg(
    input_video: str,
    srt_path: str,
    output_video: str,
    font_size: Optional[int] = None,
    margin_v: Optional[int] = None,
):
    """Render subtitles using ffmpeg's subtitles filter (Windows-safe)."""

    if not Path(srt_path).exists():
        logger.warning("Subtitles file missing (%s) – copying video without subtitles", srt_path)
        ensure_output_path(Path(output_video))
        shutil.copyfile(input_video, output_video)
        return

    # Log SRT file size to verify it has content
    srt_size = Path(srt_path).stat().st_size
    logger.info("Subtitles file: %s (size: %d bytes)", srt_path, srt_size)
    if srt_size == 0:
        logger.warning("Subtitles file is EMPTY - no subtitles will be rendered")

    # Dynamically scale subtitle styling based on video height (Shorts vs 16:9)
    video_height = _probe_video_height(input_video)
    # For Shorts (1920px height): readable font (36) and positioned WELL ABOVE facecam area (800px margin)
    # Facecam bar: 1536-1920px (bottom 20%, 384px)
    # MarginV=800 → subtitles at Y=1120px (center of lower gameplay area, safe from facecam)
    default_font, default_margin = (36, 800) if video_height and video_height >= 1600 else (46, 84)
    font_size = font_size or default_font
    margin_v = margin_v or default_margin

    # Escape Windows paths for the subtitles filter
    escaped = Path(srt_path).as_posix().replace(":", r"\:").replace("'", r"\'")
    force_style = ",".join(
        [
            f"Fontsize={font_size}",
            "Bold=1",
            "PrimaryColour=&HFFFFFF&",
            "OutlineColour=&H000000&",
            "BorderStyle=3",
            "Outline=2",
            "Shadow=1",
            f"MarginV={margin_v}",
        ]
    )
    vf_filter = f"subtitles='{escaped}':force_style='{force_style}'"

    logger.info("Subtitle parameters: font_size=%d, margin_v=%d, video_height=%s",
                font_size, margin_v, video_height)
    logger.debug("FFmpeg subtitle filter: %s", vf_filter)

    ensure_output_path(Path(output_video))

    # Try NVENC first for 5-10x faster subtitle rendering, fallback to CPU
    try:
        # Test if NVENC is available
        test_cmd = ["ffmpeg", "-hide_banner", "-encoders"]
        result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=5)
        has_nvenc = "h264_nvenc" in result.stdout
    except:
        has_nvenc = False

    if has_nvenc:
        cmd = [
            "ffmpeg",
            "-y",
            "-hwaccel", "cuda",  # GPU hardware acceleration
            "-i",
            str(input_video),
            "-vf",
            vf_filter,
            "-c:v",
            "h264_nvenc",  # NVENC GPU encoding
            "-preset", "p4",  # NVENC preset
            "-rc", "vbr",
            "-cq", "23",
            "-b:v", "5000k",
            "-c:a",
            "copy",
            str(output_video),
        ]
        logger.info("Burning subtitles with NVENC GPU encoding → %s", output_video)
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(input_video),
            "-vf",
            vf_filter,
            "-c:v",
            "libx264",
            "-preset", "ultrafast",  # Faster CPU encoding
            "-threads", "4",
            "-c:a",
            "copy",
            str(output_video),
        ]
        logger.info("Burning subtitles with CPU encoding (NVENC unavailable) → %s", output_video)

    subprocess.run(cmd, check=True, capture_output=True)


def _imagemagick_available() -> bool:
    """Best-effort check for ImageMagick binary presence."""
    binary = os.environ.get("IMAGEMAGICK_BINARY")
    if binary:
        return Path(binary).expanduser().exists()

    # Common names across platforms
    for candidate in ("magick", "convert"):  # pragma: no cover - simple availability check
        if shutil.which(candidate):
            return True
    return False


def ensure_output_path(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _format_ts(value: float) -> str:
    total_ms = max(0, int(round(value * 1000)))
    hours, remainder = divmod(total_ms, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def _wrap_subtitle_line(text: str, width: int = 38) -> str:
    """Wrap long subtitle sentences for better readability in Shorts."""

    if not text:
        return ""

    if "\n" in text:
        return text

    return textwrap.fill(text, width=width, break_long_words=False, break_on_hyphens=False)


def _probe_video_height(input_video: str) -> Optional[int]:
    """Return video height using ffprobe; best-effort fallback to None."""

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=height",
                "-of",
                "csv=p=0",
                input_video,
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        output = result.stdout.strip().splitlines()
        return int(output[-1]) if output else None
    except Exception:
        logger.debug("Unable to probe video height, using defaults", exc_info=True)
        return None


def load_subclip(video_path: Path, start: float, end: float) -> VideoFileClip | None:
    """Load a subclip with basic sanity checks, returning None if unusable.

    Falls back to FFmpeg extraction if MoviePy fails (e.g., on videos with chapters metadata).
    """

    try:
        clip = VideoFileClip(str(video_path)).subclip(start, end)
        clip = ensure_fps(clip)
        logger.debug("Clip FPS after load_subclip: %s", clip.fps)
    except Exception as e:
        logger.warning(
            "[Shorts] MoviePy failed to load subclip %s %.2f-%.2f: %s",
            video_path, start, end, str(e)
        )

        # ✅ FIX: Fallback to FFmpeg direct extraction (handles videos with chapters)
        logger.info("[Shorts] Attempting FFmpeg fallback for subclip extraction...")
        try:
            clip = _extract_subclip_with_ffmpeg(video_path, start, end)
            if clip:
                logger.info("[Shorts] ✓ FFmpeg fallback successful")
            else:
                return None
        except Exception as ffmpeg_error:
            logger.exception("[Shorts] FFmpeg fallback also failed: %s", ffmpeg_error)
            return None

    if clip.duration is None or clip.duration <= 0:
        logger.warning(f"[Shorts] Skipping invalid clip: duration={clip.duration}, segment {start}-{end}")
        clip.close()
        return None

    if clip.audio is None:
        logger.warning(f"[Shorts] Clip {start}-{end} has no audio – speedup disabled")

    logger.debug("Clip FPS after load_subclip validation: %s", clip.fps)

    return clip


def _extract_subclip_with_ffmpeg(video_path: Path, start: float, end: float) -> VideoFileClip | None:
    """Extract subclip using FFmpeg directly (bypasses MoviePy metadata parsing issues).

    Creates a temporary file with the extracted segment, then loads it with MoviePy.
    The temporary file won't have problematic metadata like chapters.
    """
    import tempfile
    import subprocess

    duration = end - start

    # Create temporary file for extracted segment
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file:
        tmp_path = tmp_file.name

    try:
        # Extract segment with FFmpeg (fast seek + re-encode to avoid keyframe issues)
        cmd = [
            'ffmpeg',
            '-y',  # Overwrite output
            '-ss', str(start),  # Start time
            '-i', str(video_path),  # Input file
            '-t', str(duration),  # Duration
            '-map', '0:v:0',  # ✅ FIX: Map only first video stream (exclude data/chapter tracks)
            '-map', '0:a:0',  # ✅ FIX: Map only first audio stream
            '-c:v', 'libx264',  # Re-encode video (ensures clean keyframes)
            '-preset', 'ultrafast',  # Fast encoding
            '-crf', '23',  # Good quality
            '-c:a', 'aac',  # Re-encode audio
            '-b:a', '192k',  # Good audio quality
            '-map_metadata', '-1',  # ✅ FIX: Strip ALL metadata (including chapters)
            '-avoid_negative_ts', 'make_zero',  # Fix timestamp issues
            tmp_path
        ]

        logger.debug("[Shorts] FFmpeg command: %s", ' '.join(cmd))

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=60,  # 1 minute timeout
            check=True
        )

        # ✅ FIX: Second pass to FORCE remove chapters metadata (FFmpeg keeps adding them)
        # Create second temp file for cleaned output
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_file2:
            tmp_path_clean = tmp_file2.name

        try:
            # Second pass: copy with explicit metadata/chapter removal
            cmd_clean = [
                'ffmpeg',
                '-y',
                '-i', tmp_path,  # Input: first pass output
                '-c', 'copy',  # Stream copy (no re-encoding)
                '-map', '0:v:0',  # Map only video
                '-map', '0:a:0',  # Map only audio
                '-map_metadata', '-1',  # Strip all metadata
                '-map_chapters', '-1',  # Strip chapters
                '-fflags', '+bitexact',  # Bitexact mode (no metadata)
                tmp_path_clean
            ]

            logger.debug("[Shorts] FFmpeg cleanup command: %s", ' '.join(cmd_clean))

            result_clean = subprocess.run(
                cmd_clean,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=True
            )

            # Remove first temp file, keep only cleaned one
            Path(tmp_path).unlink(missing_ok=True)
            tmp_path = tmp_path_clean

        except Exception as e:
            logger.warning("[Shorts] Second-pass cleanup failed, using first-pass output: %s", e)
            # Cleanup failed temp file
            try:
                Path(tmp_path_clean).unlink(missing_ok=True)
            except:
                pass
            # Continue with first-pass output (tmp_path)

        # Load extracted file with MoviePy (should work since it has no chapters)
        clip = VideoFileClip(tmp_path)
        clip = ensure_fps(clip)

        # Store temp file path so it can be cleaned up later
        clip._temp_file_path = tmp_path

        logger.debug("[Shorts] FFmpeg extracted subclip duration: %.2fs", clip.duration)

        return clip

    except subprocess.TimeoutExpired:
        logger.error("[Shorts] FFmpeg extraction timed out")
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except:
            pass
        return None

    except Exception as e:
        logger.error("[Shorts] FFmpeg extraction failed: %s", e)
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except:
            pass
        return None
