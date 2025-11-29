"""
Shorts Templates - FFmpeg filter_complex generators for different layouts
Part of stage_10_shorts.py - extracted for clarity
"""

from typing import Dict, Any, Tuple


def template_simple(width: int = 1080, height: int = 1920) -> str:
    """
    Simple template - original behavior (backward compatibility)
    Just scale and crop to 9:16

    Returns:
        FFmpeg filter_complex string
    """
    return (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}[v]"
    )


def template_classic_gaming(
    width: int = 1080,
    height: int = 1920,
    webcam_region: Dict[str, Any] = None
) -> str:
    """
    Classic Gaming template:
    - Webcam at bottom (full width, ~30-35% height)
    - Gameplay at top (scaled, max 12-15% horizontal crop)

    Layout:
    ┌─────────────┐
    │  Gameplay   │  60-65% height
    │  (scaled)   │
    ├─────────────┤
    │   Webcam    │  30-35% height
    └─────────────┘

    Returns:
        FFmpeg filter_complex string
    """
    # Heights
    webcam_height = int(height * 0.33)  # 33% for webcam
    gameplay_height = height - webcam_height  # 67% for gameplay

    # Webcam region (bottom of original video)
    # Assume webcam is bottom 35% of original 1920x1080 stream
    if webcam_region and webcam_region.get('type') == 'bottom_bar':
        # Use detected webcam region
        webcam_y_start = webcam_region['y']
    else:
        # Default: assume 1920x1080 input with webcam at bottom
        webcam_y_start = int(1080 * 0.65)  # Bottom 35%

    filter_complex = (
        # GAMEPLAY: top section (crop sides slightly, scale to fit)
        f"[0:v]crop=iw:ih-{webcam_y_start}:0:0,"  # Crop out webcam
        f"scale={width}:{gameplay_height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{gameplay_height}:(ow-iw)/2:(oh-ih)/2:black[gameplay];"

        # WEBCAM: bottom section (full width)
        f"[0:v]crop=iw:{webcam_y_start}:0:{webcam_y_start},"  # Extract webcam area
        f"scale={width}:{webcam_height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{webcam_height}[webcam];"

        # Stack vertically: gameplay on top, webcam on bottom
        f"[gameplay][webcam]vstack=inputs=2[v]"
    )

    return filter_complex


def template_pip_modern(
    width: int = 1080,
    height: int = 1920,
    webcam_region: Dict[str, Any] = None,
    pip_size: float = 0.25  # PIP size as fraction of width
) -> str:
    """
    PIP Modern template:
    - Full stream scaled to 9:16 (max 15% horizontal crop)
    - Small webcam PIP in bottom-right corner
    - Rounded corners and drop shadow on PIP

    Returns:
        FFmpeg filter_complex string
    """
    pip_w = int(width * pip_size)  # 270px for 0.25
    pip_h = int(pip_w * 0.75)  # 3:4 aspect ratio for PIP

    # Position: 30px from right, 30px from bottom
    pip_x = width - pip_w - 30
    pip_y = height - pip_h - 30

    # If webcam region detected, extract that specific area
    if webcam_region and webcam_region.get('type') in ['corner', 'bottom_bar']:
        # Extract detected webcam region
        wc_x = webcam_region['x']
        wc_y = webcam_region['y']
        wc_w = webcam_region['w']
        wc_h = webcam_region['h']

        webcam_crop = f"crop={wc_w}:{wc_h}:{wc_x}:{wc_y},"
    else:
        # Fallback: crop bottom-right corner
        webcam_crop = f"crop=iw/3:ih/3:iw*2/3:ih*2/3,"

    filter_complex = (
        # BACKGROUND: scale main stream to 9:16
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}[bg];"

        # PIP: extract webcam, scale, add rounded corners
        f"[0:v]{webcam_crop}"  # Extract webcam region
        f"scale={pip_w}:{pip_h}:force_original_aspect_ratio=increase,"
        f"crop={pip_w}:{pip_h},"
        # Rounded corners using geq filter
        f"format=yuva420p,geq="
        f"lum='p(X,Y)':a='"
        f"if(lt(X,20)*lt(Y,20),if(lt(hypot(20-X,20-Y),20),255,0),"  # Top-left
        f"if(gt(X,W-20)*lt(Y,20),if(lt(hypot(X-(W-20),20-Y),20),255,0),"  # Top-right
        f"if(lt(X,20)*gt(Y,H-20),if(lt(hypot(20-X,Y-(H-20)),20),255,0),"  # Bottom-left
        f"if(gt(X,W-20)*gt(Y,H-20),if(lt(hypot(X-(W-20),Y-(H-20)),20),255,0),255))))'[pip];"  # Bottom-right

        # Overlay PIP on background
        f"[bg][pip]overlay={pip_x}:{pip_y}[v]"
    )

    return filter_complex


def template_irl_fullface(
    width: int = 1080,
    height: int = 1920,
    zoom: float = 1.2  # Zoom factor (1.15-1.25)
) -> str:
    """
    IRL Full-face template:
    - Detect that there's no separate webcam (full face stream)
    - Zoom in slightly (1.15-1.25x) for more engaging framing
    - Crop 10-12% from sides
    - Optional: subtle gradient overlay at top/bottom

    Returns:
        FFmpeg filter_complex string
    """
    # Calculate zoomed dimensions
    zoomed_w = int(width * zoom)
    zoomed_h = int(height * zoom)

    filter_complex = (
        # Scale with zoom
        f"[0:v]scale={zoomed_w}:{zoomed_h}:force_original_aspect_ratio=decrease,"
        # Crop to final size (centered)
        f"crop={width}:{height},"
        # Optional: add subtle vignette/gradient overlay
        # (skipped for simplicity - can add later with drawbox)
        f"format=yuv420p[v]"
    )

    return filter_complex


def select_template_auto(webcam_detection: Dict[str, Any]) -> str:
    """
    Auto-select best template based on webcam detection

    Args:
        webcam_detection: Result from _detect_webcam_region()

    Returns:
        Template name: "classic_gaming", "pip_modern", "irl_fullface", or "simple"
    """
    webcam_type = webcam_detection.get('type', 'none')
    confidence = webcam_detection.get('confidence', 0.0)

    if confidence < 0.4:
        # Low confidence - use simple fallback
        return "simple"

    if webcam_type == "full_face":
        return "irl_fullface"
    elif webcam_type == "bottom_bar":
        return "classic_gaming"
    elif webcam_type == "corner":
        return "pip_modern"
    else:
        return "simple"
