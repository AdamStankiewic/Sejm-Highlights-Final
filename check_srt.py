# check_srt.py
from pathlib import Path

srt_file = Path("output/full_subtitles.srt")

print("📄 Sprawdzam SRT file...\n")

with open(srt_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Pokaż pierwsze 50 linii
print("Pierwsze 15 napisów:")
print(''.join(lines[:60]))

# Pokaż ostatnie napisy
print("\n\nOstatnie 5 napisów:")
print(''.join(lines[-20:]))

# Statystyki
num_subtitles = len([l for l in lines if l.strip().isdigit()])
print(f"\n📊 Łącznie napisów: {num_subtitles}")