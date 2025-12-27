#!/usr/bin/env python3
"""
Diagnostic Script - Check what content is actually in your clips.json file.

This helps debug content type detection issues by showing:
1. First 3 clip transcripts
2. Detected language
3. Detected keywords (sejm vs gaming vs irl)
4. Recommended streamer_id

Usage:
    python scripts/diagnose_clips.py "path/to/selected_clips.json"
"""
import sys
import json
from pathlib import Path
from collections import Counter

def detect_language(text):
    """Simple language detection based on common words"""
    polish_words = ["i", "w", "na", "z", "to", "się", "że", "jest", "nie", "do", "jak", "ale", "co", "był"]
    english_words = ["the", "is", "and", "to", "a", "of", "that", "in", "it", "for", "on", "with", "was", "this"]

    text_lower = text.lower()

    polish_count = sum(1 for word in polish_words if f" {word} " in text_lower)
    english_count = sum(1 for word in english_words if f" {word} " in text_lower)

    if polish_count > english_count * 1.5:
        return "pl", polish_count
    elif english_count > polish_count * 1.5:
        return "en", english_count
    else:
        return "unknown", max(polish_count, english_count)

def detect_content_type(text):
    """Detect content type from text"""
    text_lower = text.lower()

    scores = {
        "sejm": 0,
        "gaming": 0,
        "irl": 0,
        "react": 0
    }

    # Sejm keywords (Polish)
    sejm_keywords = ["sejm", "posiedzenie", "obrady", "poseł", "posłanka", "komisja", "pis", "po", "koalicja",
                     "ustawa", "głosowanie", "marszałek", "parlament", "premier", "minister", "rząd"]
    for kw in sejm_keywords:
        if kw in text_lower:
            scores["sejm"] += 1

    # Gaming keywords (EN + PL)
    gaming_keywords = ["game", "gaming", "play", "playing", "boss", "level", "quest", "rpg", "mmo", "pvp",
                      "gra", "granie", "grać", "poziom", "misja"]
    for kw in gaming_keywords:
        if kw in text_lower:
            scores["gaming"] += 1

    # IRL keywords (EN + PL)
    irl_keywords = ["irl", "just chatting", "talking", "chat", "czat", "rozmowa"]
    for kw in irl_keywords:
        if kw in text_lower:
            scores["irl"] += 1

    # React keywords (EN + PL)
    react_keywords = ["react", "reacts", "reacting", "reaction", "reaguje", "reakcja"]
    for kw in react_keywords:
        if kw in text_lower:
            scores["react"] += 1

    return scores

def diagnose_clips(clips_path):
    """Diagnose clips.json content"""
    print(f"\n{'='*70}")
    print(f"🔍 CLIPS DIAGNOSTIC REPORT")
    print(f"{'='*70}")
    print(f"File: {clips_path}\n")

    # Load clips
    path = Path(clips_path)
    if not path.exists():
        print(f"❌ File not found!")
        return

    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    # Handle different formats
    if isinstance(data, dict):
        clips = data.get('clips', [])
    elif isinstance(data, list):
        clips = data
    else:
        print(f"❌ Invalid clips format")
        return

    if not clips:
        print(f"❌ No clips found")
        return

    print(f"📊 Total clips: {len(clips)}\n")

    # Analyze first 3 clips (same as auto-detection does)
    print(f"{'='*70}")
    print(f"📝 FIRST 3 CLIPS ANALYSIS (used for auto-detection)")
    print(f"{'='*70}\n")

    all_text = ""
    for i, clip in enumerate(clips[:3], 1):
        title = clip.get("title", "N/A")
        transcript = clip.get("transcript", "")

        print(f"--- Clip {i} ---")
        print(f"Title: {title}")
        print(f"Transcript ({len(transcript)} chars):")
        print(f"{transcript[:400]}...")
        print()

        all_text += " " + title.lower()
        all_text += " " + transcript[:200].lower()

    # Language detection
    print(f"{'='*70}")
    print(f"🌍 LANGUAGE DETECTION")
    print(f"{'='*70}")
    lang, score = detect_language(all_text)
    print(f"Detected language: {lang.upper()} (confidence: {score} markers)")
    print()

    # Content type detection
    print(f"{'='*70}")
    print(f"🎯 CONTENT TYPE DETECTION")
    print(f"{'='*70}")
    scores = detect_content_type(all_text)

    for content_type, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
        bar = "█" * score + "░" * (20 - score)
        print(f"{content_type:12} [{bar}] {score} keywords")

    # Recommendation
    print()
    print(f"{'='*70}")
    print(f"💡 RECOMMENDATION")
    print(f"{'='*70}")

    max_score = max(scores.values())
    if max_score == 0:
        print("⚠️  No clear content type detected")
        print("   This might be generic content or unknown format")
    else:
        detected_type = max(scores, key=scores.get)

        if detected_type == "sejm":
            print("🏛️  This looks like SEJM (Polish Parliament) content")
            print("   Recommended: --streamer sejm")
            print("   Language: Polish (pl)")
        elif detected_type == "gaming":
            print("🎮 This looks like GAMING content")
            print("   Recommended: --streamer [streamer_name] (e.g., asmongold)")
            print(f"   Language: {lang}")
        elif detected_type in ["irl", "react"]:
            print("🗣️  This looks like IRL/REACT content")
            print("   Recommended: --streamer [streamer_name] (e.g., asmongold)")
            print(f"   Language: {lang}")

    # Warning if mismatch
    if "sejm" in str(path).lower() and scores["sejm"] < 3:
        print("\n⚠️  WARNING: Path contains 'sejm' but content doesn't look like parliament!")
        print("   You might be using the wrong file.")

    if any(name in str(path).lower() for name in ["asmongold", "zackrawrr", "asmon"]):
        if scores["sejm"] > scores["gaming"] + scores["irl"] + scores["react"]:
            print("\n⚠️  WARNING: Path suggests Asmongold but content looks like SEJM!")
            print("   You might be using the wrong file.")

    print(f"\n{'='*70}\n")

def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/diagnose_clips.py <path_to_clips.json>")
        print("\nExample:")
        print('  python scripts/diagnose_clips.py "output/session_123/selected_clips.json"')
        sys.exit(1)

    clips_path = sys.argv[1]
    diagnose_clips(clips_path)

if __name__ == "__main__":
    main()
