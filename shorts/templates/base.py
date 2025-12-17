"""Base template for shorts rendering."""
from __future__ import annotations

import abc
from pathlib import Path
from typing import Iterable, Tuple, Optional


class TemplateBase(abc.ABC):
    """Abstrakcyjna baza szablonów.

    Każdy szablon powinien implementować apply() i zwracać Path do wygenerowanego shortsa.
    """

    name: str = "base"

    @abc.abstractmethod
    def apply(
        self,
        video_path: Path,
        start: float,
        end: float,
        output_path: Path,
        speedup: float = 1.0,
        enable_subtitles: bool = False,
        subtitles: Iterable[Tuple[str, float, float]] | None = None,
        subtitle_lang: str = "pl",
        copyright_processor: Optional[object] = None,
    ) -> Path:
        raise NotImplementedError
