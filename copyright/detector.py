"""Detection backends for copyrighted music (AUDD + Demucs).

Moduł defensywny: wszystkie zależności opcjonalne, błędy logowane zamiast crasha.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class CopyrightDetector:
    """Handle remote (AUDD) and local (Demucs) music detection."""

    def __init__(self, provider: str = "demucs", audd_api_key: str | None = None):
        self.provider = (provider or "demucs").lower()
        self.audd_api_key = audd_api_key or ""

    # --- AUDD ---
    def detect_with_audd(self, sample_path: Path) -> Dict:
        """Call AUDD.io API for song recognition; returns dict or {} on failure."""
        if not self.audd_api_key:
            logger.info("AUDD API key missing – skipping cloud detection")
            return {}
        try:
            import requests  # type: ignore
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.warning("requests missing for AUDD detection: %s", exc)
            return {}

        try:
            data = {"api_token": self.audd_api_key, "return": "apple_music,spotify"}
            with open(sample_path, "rb") as fh:
                resp = requests.post("https://api.audd.io/", data=data, files={"file": fh}, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            logger.debug("AUDD response: %s", json.dumps(payload)[:500])
            result = payload.get("result") or {}
            return result or {}
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("AUDD detection failed: %s", exc)
            return {}

    def has_copyright_match(self, audd_result: Dict) -> bool:
        """Check if AUDD result points to a copyrighted track."""
        if not audd_result:
            return False
        links = audd_result.get("spotify") or audd_result.get("apple_music") or {}
        return bool(links)

    # --- DEMUCS ---
    def separate_with_demucs(self, audio_path: Path, output_dir: Path, keep_sfx: bool = True) -> Optional[Path]:
        """Run Demucs V4 if available. Returns path to cleaned mix or None."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Prefer demucs CLI if available
        demucs_bin = shutil.which("demucs")
        if demucs_bin:
            try:
                cmd = [
                    demucs_bin,
                    "--two-stems",
                    "vocals",
                    "--mp3",
                    "--out",
                    str(output_dir),
                    str(audio_path),
                ]
                logger.info("Running Demucs: %s", " ".join(cmd))
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            except subprocess.TimeoutExpired:
                logger.warning("Demucs timeout – skipping separation")
                return None
            except subprocess.CalledProcessError as exc:
                logger.warning("Demucs failed (%s): %s", exc.returncode, exc)
                return None
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Demucs error: %s", exc)
                return None
        else:
            logger.info("Demucs binary not found – skipping separation")
            return None

        # Locate separated stems
        vocals = self._find_first(output_dir, "vocals")
        drums = self._find_first(output_dir, "drums")
        bass = self._find_first(output_dir, "bass")

        if keep_sfx and vocals and (drums or bass):
            mixed = output_dir / "clean_mix.wav"
            cmd = ["ffmpeg", "-y", "-i", str(vocals)]
            filters = ["[0:a]"]
            input_idx = 1
            if drums:
                cmd += ["-i", str(drums)]
                filters.append(f"[{input_idx}:a]")
                input_idx += 1
            if bass:
                cmd += ["-i", str(bass)]
                filters.append(f"[{input_idx}:a]")
                input_idx += 1
            inputs = len(filters)
            filter_expr = "".join(filters) + f"amix=inputs={inputs}:normalize=0"
            cmd += ["-filter_complex", filter_expr, str(mixed)]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                return mixed
            except Exception as exc:  # pragma: no cover
                logger.warning("Mixing stems failed: %s", exc)

        if vocals:
            return vocals
        logger.warning("Demucs output missing vocals stem")
        return None

    @staticmethod
    def _find_first(base: Path, stem: str) -> Optional[Path]:
        candidates = list(base.rglob(f"*{stem}.mp3")) + list(base.rglob(f"*{stem}.wav"))
        return candidates[0] if candidates else None
