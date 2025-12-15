#!/usr/bin/env python3
"""Extract frame from VOD to analyze facecam placement and dimensions."""

import sys
from pathlib import Path
import cv2
import numpy as np
from moviepy.editor import VideoFileClip


def extract_frame(vod_path: str, timestamp: float = 60.0, output_path: str = "facecam_analysis.jpg"):
    """Extract a single frame from VOD for analysis."""
    print(f"📹 Loading VOD: {vod_path}")
    print(f"⏱️  Timestamp: {timestamp}s")

    clip = VideoFileClip(vod_path)
    frame = clip.get_frame(timestamp)
    clip.close()

    # Convert RGB to BGR for OpenCV
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    # Save frame
    cv2.imwrite(output_path, frame_bgr)
    print(f"✅ Frame saved to: {output_path}")
    print(f"📐 Frame size: {frame.shape[1]}x{frame.shape[0]}")

    return frame_bgr


def analyze_corners(frame, corner_size_percent=0.35):
    """Analyze all 4 corners to find facecam."""
    h, w = frame.shape[:2]
    corner_w = int(w * corner_size_percent)
    corner_h = int(h * 0.30)

    print(f"\n🔍 Analyzing corners (region: {corner_w}x{corner_h})")

    corners = {
        "right_top": frame[0:corner_h, w-corner_w:w],
        "right_bottom": frame[h-corner_h:h, w-corner_w:w],
        "left_top": frame[0:corner_h, 0:corner_w],
        "left_bottom": frame[h-corner_h:h, 0:corner_w],
    }

    # Save corner regions
    for name, region in corners.items():
        cv2.imwrite(f"corner_{name}.jpg", region)
        print(f"  ✓ Saved corner_{name}.jpg ({region.shape[1]}x{region.shape[0]})")

    return corners


def detect_edges(frame):
    """Detect edges to find facecam boundary."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)

    cv2.imwrite("edges.jpg", edges)
    print(f"✅ Edge detection saved to: edges.jpg")

    return edges


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python analyze_facecam.py <vod_path> [timestamp]")
        sys.exit(1)

    vod_path = sys.argv[1]
    timestamp = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0

    print("="*60)
    print("🎬 FACECAM ANALYSIS")
    print("="*60)

    frame = extract_frame(vod_path, timestamp)
    corners = analyze_corners(frame)
    edges = detect_edges(frame)

    print("\n" + "="*60)
    print("✅ ANALYSIS COMPLETE")
    print("="*60)
    print("📁 Generated files:")
    print("   - facecam_analysis.jpg (full frame)")
    print("   - corner_*.jpg (4 corner regions)")
    print("   - edges.jpg (edge detection)")
    print("\nCheck these files to see facecam placement!")
