"""
Dokończenie przetwarzania - Stage 6 i 7 - AUTO DETECT
"""
from pathlib import Path
from pipeline.stage_06_selection import SelectionStage
from pipeline.stage_07_export import ExportStage
from pipeline.config import Config
import json

# === KONFIGURACJA ===
# ZMIEŃ tę ścieżkę na swoją!
INPUT_VIDEO = r"C:\Users\adams\Downloads\43. posiedzenie Sejmu - dzień 3. 17 października 2025r. - Sejm RP (720p, h264, youtube) (1).mp4"
OUTPUT_DIR = Path("output")

# === AUTO DETECT najnowszy folder ===
temp_folders = []
for folder in Path("temp").iterdir():
    if folder.is_dir() and (folder / "scored_segments.json").exists():
        temp_folders.append(folder)

if not temp_folders:
    print("❌ Brak folderu z scored_segments.json!")
    exit(1)

TEMP_DIR = sorted(temp_folders, key=lambda x: x.stat().st_mtime, reverse=True)[0]
print(f"📂 Znaleziono najnowszy folder: {TEMP_DIR.name}")

# === Wczytaj dane ===
print("📂 Wczytywanie danych...")
with open(TEMP_DIR / "scored_segments.json", "r", encoding="utf-8") as f:
    segments = json.load(f)

print(f"✓ Załadowano {len(segments)} segmentów")

# === Stage 6: Selection ===
print("\n🎯 Stage 6: Selekcja klipów...")
config = Config.load_default()

config.selection.min_clip_duration = 60.0
config.selection.max_clip_duration = 180.0
config.selection.target_total_duration = 1800.0
config.selection.max_clips = 12
config.selection.min_clips = 6
config.selection.enable_trimming = False

selection_stage = SelectionStage(config)

try:
    selection_result = selection_stage.process(
        segments=segments,
        total_duration=19296.0,
        output_dir=TEMP_DIR
    )
    
    clips = selection_result['clips']
    print(f"✅ Wybrano {len(clips)} klipów")
    print(f"   Całkowity czas: {selection_result['total_duration']/60:.1f} min")
    
    with open(TEMP_DIR / "selected_clips.json", "w", encoding="utf-8") as f:
        json.dump(clips, f, indent=2, ensure_ascii=False)
    
except Exception as e:
    print(f"❌ Błąd Stage 6: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

# === Stage 7: Export ===
print("\n🎬 Stage 7: Export video...")

config.export.generate_hardsub = True
config.export.add_transitions = False

export_stage = ExportStage(config)

try:
    export_result = export_stage.process(
        input_file=INPUT_VIDEO,
        clips=clips,
        segments=segments,
        output_dir=OUTPUT_DIR,
        session_dir=TEMP_DIR
    )
    
    print(f"\n✅ GOTOWE!")
    print(f"📹 Film: {export_result['output_file']}")
    if export_result.get('output_file_hardsub'):
        print(f"📝 Hardsub: {export_result['output_file_hardsub']}")
    
except Exception as e:
    print(f"❌ Błąd Stage 7: {e}")
    import traceback
    traceback.print_exc()
    exit(1)