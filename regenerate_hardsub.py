# regenerate_hardsub.py
from pathlib import Path
"""Przykład użycia ShortsGenerator / regeneracji napisów.

Zostawiamy hardsub regenerację oraz nowy przykład generowania shortów
z modularnym generatorem (gaming/universal).
"""

import json
import logging
from pipeline.stage_07_export import ExportStage
from pipeline.config import Config
from shorts import Segment, ShortsGenerator

TEMP_DIR = Path("temp/43. posiedzenie Sejmu - dzień 3. 17 października 2025r. - Sejm RP (720p, h264, youtube) (1)_20251020_222521")
OUTPUT_DIR = Path("output")
VIDEO_FILE = OUTPUT_DIR / "SEJM_HIGHLIGHTS_43. posiedzenie Sejmu - dzień 3. 17 października 2025r. - Sejm RP (720p, h264, youtube) (1)_2025-10-21.mp4"


def regenerate_hardsub() -> None:
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


def generate_shorts_example() -> None:
    """Lekki przykład jak wywołać nowy ShortsGenerator z gotowymi kandydatami."""

    config = Config.load_default()
    config.shorts.enabled = True
    generator = ShortsGenerator(output_dir=OUTPUT_DIR / "manual_shorts")

    shorts_candidates = [
        Segment(start=30, end=55, score=1.0),
        Segment(start=120, end=160, score=0.9),
    ]
    result = generator.generate(
        VIDEO_FILE,
        shorts_candidates,
        template=config.shorts.template,
        count=getattr(config.shorts, "num_shorts", getattr(config.shorts, "count", 5)),
        speedup=getattr(config.shorts, "speedup_factor", getattr(config.shorts, "speedup", 1.0)),
        enable_subtitles=getattr(
            config.shorts, "enable_subtitles", getattr(config.shorts, "add_subtitles", getattr(config.shorts, "subtitles", False))
        ),
        subtitle_lang=config.shorts.subtitle_lang,
    )
    print(f"📱 Wygenerowano {len(result)} shortsów → {result}")


if __name__ == "__main__":
    regenerate_hardsub()
    # Opcjonalnie odkomentuj aby wygenerować manualne shortsy
    # generate_shorts_example()