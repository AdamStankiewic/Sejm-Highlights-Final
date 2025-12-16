"""
Cache Manager
Zarządza cache dla kosztownych etapów pipeline'u (VAD, Transcribe, Scoring)

Cache key = hash(input_video) + hash(config_for_stage)
- Jeśli input i config się nie zmieniły → cache hit → pomiń stage
- Jeśli coś się zmieniło → cache miss → wykonaj stage i zapisz do cache
"""

import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import asdict


class CacheManager:
    """
    Zarządza cache dla pipeline stages.

    Cache structure:
        cache/
            {input_hash}_{config_hash}/
                vad_segments.json           # Stage 2
                segments_with_transcript.json  # Stage 3
                scored_segments.json        # Stage 5
    """

    def __init__(self, cache_dir: Path, enabled: bool = True, force_recompute: bool = False):
        """
        Args:
            cache_dir: Katalog cache (np. cache/)
            enabled: Czy cache jest włączony
            force_recompute: Wymuszenie pełnego przeliczenia (--force flag)
        """
        self.cache_dir = Path(cache_dir)
        self.enabled = enabled and not force_recompute
        self.force_recompute = force_recompute

        if self.enabled:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Current cache key dla tej sesji
        self.current_cache_key: Optional[str] = None
        self.current_cache_path: Optional[Path] = None

    def calculate_input_hash(self, file_path: str, chunk_size: int = 8192) -> str:
        """
        Oblicz hash pliku wideo (używa pierwszych i ostatnich 10MB + size dla szybkości)

        Args:
            file_path: Ścieżka do pliku wideo
            chunk_size: Rozmiar chunka do czytania

        Returns:
            SHA256 hash jako hex string
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        hasher = hashlib.sha256()
        file_size = path.stat().st_size

        # Hash zawiera: file_size + first 10MB + last 10MB (dla szybkości)
        hasher.update(str(file_size).encode())

        with open(path, 'rb') as f:
            # First 10MB
            chunk_limit = 10 * 1024 * 1024  # 10MB
            read_bytes = 0
            while read_bytes < chunk_limit:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
                read_bytes += len(chunk)

            # Last 10MB (jeśli plik > 20MB)
            if file_size > 20 * 1024 * 1024:
                f.seek(-chunk_limit, 2)  # Seek from end
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    hasher.update(chunk)

        return hasher.hexdigest()[:16]  # First 16 chars (64 bits)

    def calculate_config_hash(self, config: Any, stage: str) -> str:
        """
        Oblicz hash konfiguracji dla danego stage.

        Args:
            config: Config object
            stage: Nazwa stage ('vad', 'transcribe', 'scoring')

        Returns:
            SHA256 hash jako hex string
        """
        hasher = hashlib.sha256()

        # Config parameters wpływające na dany stage
        if stage == 'vad':
            params = {
                'model': config.vad.model,
                'threshold': config.vad.threshold,
                'min_speech_duration': config.vad.min_speech_duration,
                'min_silence_duration': config.vad.min_silence_duration,
                'max_segment_duration': config.vad.max_segment_duration,
                'sample_rate': config.audio.sample_rate,
            }
        elif stage == 'transcribe':
            params = {
                'model': config.asr.model,
                'language': config.asr.language,
                'initial_prompt': config.asr.initial_prompt,
                'temperature': config.asr.temperature,
                'beam_size': config.asr.beam_size,
                'compute_type': config.asr.compute_type,
                'condition_on_previous_text': config.asr.condition_on_previous_text,
                'global_language': config.language,  # Include global language for cache invalidation
            }
        elif stage == 'scoring':
            params = {
                'nli_model': config.scoring.nli_model,
                'interest_labels': config.scoring.interest_labels,
                'weight_acoustic': config.scoring.weight_acoustic,
                'weight_keyword': config.scoring.weight_keyword,
                'weight_semantic': config.scoring.weight_semantic,
                'weight_speaker_change': config.scoring.weight_speaker_change,
                'position_diversity_bonus': config.scoring.position_diversity_bonus,
                'global_language': config.language,  # Include global language for cache invalidation (affects prompts)
            }
        else:
            raise ValueError(f"Unknown stage for cache: {stage}")

        # Sortuj dict dla konsystentności
        params_json = json.dumps(params, sort_keys=True)
        hasher.update(params_json.encode())

        return hasher.hexdigest()[:16]  # First 16 chars (64 bits)

    def initialize_cache_key(self, input_file: str, config: Any):
        """
        Inicjalizuj cache key dla tej sesji przetwarzania.

        Args:
            input_file: Ścieżka do pliku wideo
            config: Config object
        """
        if not self.enabled:
            return

        # Oblicz hash inputu
        input_hash = self.calculate_input_hash(input_file)

        # Oblicz combined config hash (wszystkie stages)
        vad_hash = self.calculate_config_hash(config, 'vad')
        transcribe_hash = self.calculate_config_hash(config, 'transcribe')
        scoring_hash = self.calculate_config_hash(config, 'scoring')

        combined_config_hash = hashlib.sha256(
            f"{vad_hash}{transcribe_hash}{scoring_hash}".encode()
        ).hexdigest()[:16]

        # Cache key
        self.current_cache_key = f"{input_hash}_{combined_config_hash}"
        self.current_cache_path = self.cache_dir / self.current_cache_key

        # Utwórz katalog cache dla tej sesji
        self.current_cache_path.mkdir(parents=True, exist_ok=True)

        print(f"💾 Cache initialized: {self.current_cache_key}")
        print(f"   Cache dir: {self.current_cache_path}")

    def get_cache_file_path(self, stage: str) -> Path:
        """
        Pobierz ścieżkę do pliku cache dla danego stage.

        Args:
            stage: Nazwa stage ('vad', 'transcribe', 'scoring')

        Returns:
            Path do pliku cache
        """
        if not self.current_cache_path:
            raise RuntimeError("Cache key not initialized. Call initialize_cache_key() first.")

        filename_map = {
            'vad': 'vad_segments.json',
            'transcribe': 'segments_with_transcript.json',
            'scoring': 'scored_segments.json'
        }

        if stage not in filename_map:
            raise ValueError(f"Unknown stage for cache: {stage}")

        return self.current_cache_path / filename_map[stage]

    def is_cache_valid(self, stage: str) -> bool:
        """
        Sprawdź czy cache istnieje i jest aktualny dla danego stage.

        Args:
            stage: Nazwa stage ('vad', 'transcribe', 'scoring')

        Returns:
            True jeśli cache jest valid, False w przeciwnym razie
        """
        if not self.enabled:
            return False

        cache_file = self.get_cache_file_path(stage)
        return cache_file.exists() and cache_file.stat().st_size > 0

    def load_from_cache(self, stage: str) -> Dict[str, Any]:
        """
        Załaduj dane z cache dla danego stage.

        Args:
            stage: Nazwa stage ('vad', 'transcribe', 'scoring')

        Returns:
            Dict z danymi z cache

        Raises:
            FileNotFoundError: Jeśli cache nie istnieje
        """
        cache_file = self.get_cache_file_path(stage)

        if not cache_file.exists():
            raise FileNotFoundError(f"Cache file not found: {cache_file}")

        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def save_to_cache(self, data: Dict[str, Any], stage: str):
        """
        Zapisz dane do cache dla danego stage.

        Args:
            data: Dict z danymi do zapisania
            stage: Nazwa stage ('vad', 'transcribe', 'scoring')
        """
        if not self.enabled:
            return

        cache_file = self.get_cache_file_path(stage)

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        print(f"💾 Saved to cache: {cache_file.name}")

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Pobierz statystyki cache (ile stages ma cache hit).

        Returns:
            Dict ze statystykami
        """
        if not self.enabled:
            return {
                'enabled': False,
                'reason': 'force_recompute' if self.force_recompute else 'disabled'
            }

        stats = {
            'enabled': True,
            'cache_key': self.current_cache_key,
            'cache_path': str(self.current_cache_path),
            'stages': {}
        }

        for stage in ['vad', 'transcribe', 'scoring']:
            is_valid = self.is_cache_valid(stage)
            stats['stages'][stage] = {
                'cached': is_valid,
                'file': self.get_cache_file_path(stage).name if is_valid else None
            }

        return stats


if __name__ == "__main__":
    # Test
    import tempfile
    from pathlib import Path

    # Mock config
    class MockConfig:
        class VAD:
            model = "silero_v4"
            threshold = 0.5
            min_speech_duration = 3.0
            min_silence_duration = 1.5
            max_segment_duration = 180.0

        class Audio:
            sample_rate = 16000

        class ASR:
            model = "large-v3"
            language = "pl"
            initial_prompt = "Test prompt"
            temperature = [0.0, 0.2]
            beam_size = 3
            compute_type = "float16"
            condition_on_previous_text = True

        class Scoring:
            nli_model = "clarin-pl/roberta-large-nli"
            interest_labels = {"label1": 1.0}
            weight_acoustic = 0.25
            weight_keyword = 0.15
            weight_semantic = 0.50
            weight_speaker_change = 0.10
            position_diversity_bonus = 0.1

        vad = VAD()
        audio = Audio()
        asr = ASR()
        scoring = Scoring()

    config = MockConfig()

    # Test cache manager
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_manager = CacheManager(cache_dir=Path(tmpdir) / "cache")

        # Create test video file
        test_video = Path(tmpdir) / "test.mp4"
        test_video.write_text("fake video content")

        # Initialize cache
        cache_manager.initialize_cache_key(str(test_video), config)

        print(f"\nCache stats:")
        print(json.dumps(cache_manager.get_cache_stats(), indent=2))

        # Test save/load
        test_data = {"segments": [{"id": 1, "text": "test"}]}
        cache_manager.save_to_cache(test_data, 'vad')

        print(f"\nCache valid for VAD: {cache_manager.is_cache_valid('vad')}")

        loaded = cache_manager.load_from_cache('vad')
        print(f"Loaded from cache: {loaded}")

        print("\n✅ CacheManager test passed!")
