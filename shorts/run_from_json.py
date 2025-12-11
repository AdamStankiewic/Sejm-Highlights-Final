"""Lightweight helper to render Shorts from shorts_candidates.json."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Iterable

from shorts import Segment, ShortsGenerator

logger = logging.getLogger(__name__)


def _load_segments(json_path: Path) -> list[Segment]:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    segments: list[Segment] = []
    for raw in data:
        start = float(raw.get("t0", raw.get("start", 0.0)))
        end = float(raw.get("t1", raw.get("end", start)))
        score = float(raw.get("final_score", raw.get("score", 0.0)))
        subtitles = raw.get("subtitles")

        segments.append(Segment(start=start, end=end, score=score, subtitles=subtitles))

    return segments


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Quickly render Shorts from a candidates JSON file.")
    parser.add_argument("--video", "-v", required=True, help="Path do pliku wideo (np. C:/Users/.../VOD.mp4)")
    parser.add_argument(
        "--candidates",
        "-c",
        default="shorts_candidates.json",
        help="Plik JSON z kandydatami Shorts (domyślnie shorts_candidates.json)",
    )
    parser.add_argument("--template", "-t", default="gaming", help="Szablon Shorts (gaming/universal)")
    parser.add_argument("--count", "-n", type=int, default=5, help="Maksymalna liczba shortów do wygenerowania")
    parser.add_argument("--output-dir", "-o", default="outputs/shorts/from_json", help="Katalog na wygenerowane shorty")
    parser.add_argument("--speedup", type=float, default=1.0, help="Przyspieszenie odtwarzania (np. 1.1)")
    parser.add_argument("--subtitles", action="store_true", help="Dodaj napisy jeśli dostępne w JSON")
    parser.add_argument("--subtitle-lang", default="pl", help="Język napisów (gdy subtitles=True)")
    return parser.parse_args()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args()

    json_path = Path(args.candidates)
    if not json_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku z kandydatami: {json_path}")

    video_path = Path(args.video)
    if not video_path.exists():
        raise FileNotFoundError(f"Nie znaleziono pliku wideo: {video_path}")

    segments = _load_segments(json_path)
    if not segments:
        logger.warning("Brak segmentów do przetworzenia w %s", json_path)
        return

    generator = ShortsGenerator(output_dir=Path(args.output_dir))
    results: Iterable[Path] = generator.generate(
        video_path,
        segments,
        template=args.template,
        count=args.count,
        speedup=args.speedup,
        add_subtitles=args.subtitles,
        subtitle_lang=args.subtitle_lang,
    )

    results = list(results)
    print(f"📱 Wygenerowano {len(results)} shortsów")
    for path in results:
        print(f" - {path}")


if __name__ == "__main__":
    main()
