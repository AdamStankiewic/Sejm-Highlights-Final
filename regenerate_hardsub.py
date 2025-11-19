# regenerate_hardsub.py
from pathlib import Path
from pipeline.stage_07_export import ExportStage
from pipeline.config import Config
import json

TEMP_DIR = Path("temp/43. posiedzenie Sejmu - dzień 3. 17 października 2025r. - Sejm RP (720p, h264, youtube) (1)_20251020_222521")
OUTPUT_DIR = Path("output")
VIDEO_FILE = OUTPUT_DIR / "SEJM_HIGHLIGHTS_43. posiedzenie Sejmu - dzień 3. 17 października 2025r. - Sejm RP (720p, h264, youtube) (1)_2025-10-21.mp4"

# Load data - FIXED: add encoding
with open(TEMP_DIR / "selected_clips.json", encoding='utf-8') as f:
    clips = json.load(f)
with open(TEMP_DIR / "scored_segments.json", encoding='utf-8') as f:
    segments = json.load(f)

config = Config.load_default()
stage = ExportStage(config)

print("🎬 Regeneruję hardsub z poprawionymi napisami...")
hardsub_file = stage._generate_hardsub(
    VIDEO_FILE,
    clips,
    segments,
    OUTPUT_DIR
)

print(f"✅ Gotowe! {hardsub_file}")