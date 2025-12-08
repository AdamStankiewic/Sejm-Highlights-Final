"""Konfiguracja shortsów (bezpieczne domyślne wartości).

Zapewnia komplet pól wymaganych przez generator oraz GUI
i dodaje aliasy kompatybilności (count/speedup/subtitles),
aby uniknąć błędów typu AttributeError podczas migracji.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class ShortsConfig:
    enabled: bool = True
    generate_shorts: bool = False
    template: str = "gaming"  # lub "universal"
    face_regions: List[str] = field(
        default_factory=lambda: ["bottom_right", "bottom_left", "top_right", "top_left"]
    )
    speedup_factor: float = 1.0
    add_subtitles: bool = False
    subtitle_lang: str = "pl"
    min_duration: int = 8
    max_duration: int = 58
    num_shorts: int = 5
    gameplay_scale: float = 0.88
    universal_scale: float = 0.90
    face_resize_width: int = 250
    face_detection: bool = False

    # Aliasy kompatybilności (nie inicjalizowane w konstruktorze)
    count: int = field(init=False, default=5)
    speedup: float = field(init=False, default=1.0)
    subtitles: bool = field(init=False, default=False)

    def __post_init__(self) -> None:
        """Ustandaryzuj i zaklamruj wartości, zachowując aliasy."""

        # Alias speedup -> speedup_factor
        if hasattr(self, "speedup") and self.speedup is not None:
            try:
                self.speedup_factor = float(getattr(self, "speedup"))
            except Exception:
                self.speedup_factor = 1.0

        # Alias subtitles -> add_subtitles
        if hasattr(self, "subtitles") and self.subtitles is not None:
            try:
                self.add_subtitles = bool(getattr(self, "subtitles"))
            except Exception:
                self.add_subtitles = False

        try:
            self.face_detection = bool(self.face_detection)
        except Exception:
            self.face_detection = False

        # Num shorts (alias count)
        provided_count = getattr(self, "count", None)
        try:
            base_num = int(self.num_shorts if self.num_shorts is not None else provided_count or 5)
        except Exception:
            base_num = 5
        base_num = max(1, min(50, base_num))
        self.num_shorts = base_num
        self.count = base_num

        # Bezpieczne limity długości
        try:
            self.min_duration = int(self.min_duration)
        except Exception:
            self.min_duration = 8
        if self.min_duration < 8:
            self.min_duration = 8

        try:
            self.max_duration = int(self.max_duration)
        except Exception:
            self.max_duration = 58
        self.max_duration = max(self.min_duration + 1, self.max_duration)

        # Skale gameplay/universal
        try:
            self.gameplay_scale = float(self.gameplay_scale)
        except Exception:
            self.gameplay_scale = 0.88

        try:
            self.universal_scale = float(self.universal_scale)
        except Exception:
            self.universal_scale = 0.90

        # Regiony twarzy – fallback na domyślne, gdy lista pusta/None
        if not self.face_regions:
            self.face_regions = ["bottom_right", "bottom_left", "top_right", "top_left"]
