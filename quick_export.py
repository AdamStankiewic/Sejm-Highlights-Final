# quick_export.py
from pathlib import Path
from pipeline.stage_07_export import ExportStage
from pipeline.config import Config
import json

# Wczytaj dane
temp_dir = Path("temp/nazwa_twojej_sesji")  # Znajdź folder z datą
clips_file = temp_dir / "selected_clips.json"
segments_file = temp_dir / "scored_segments.json"

if clips_file.exists():
    with open(clips_file) as f:
        clips = json.load(f)
    with open(segments_file) as f:
        segments = json.load(f)
    
    config = Config.load_default()
    stage = ExportStage(config)
    
    result = stage.process(
        input_file="twoj_plik.mp4",
        clips=clips,
        segments=segments,
        output_dir=Path("output"),
        session_dir=temp_dir
    )
    
    print(f"✅ Gotowe! {result['output_file']}")
else:
    print("❌ Brak pliku selected_clips.json")