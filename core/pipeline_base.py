"""
Abstract base class for all pipelines
Part of Highlights AI Platform - Core Engine

Each domain module (Politics, Streaming, etc.) extends this base class
and implements its own scoring and selection logic.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Callable
from pathlib import Path

from .audio.extraction import AudioExtractor
from .audio.normalization import AudioNormalizer
from .audio.vad import VADDetector
from .transcription.whisper import WhisperTranscriber
from .features.acoustic import AcousticFeatureExtractor
from .features.prosodic import ProsodicFeatureExtractor
from .features.lexical import LexicalFeatureExtractor


class BasePipeline(ABC):
    """
    Base pipeline that all domain modules must implement.

    The pipeline flow:
    1. Ingest (audio extraction + normalization) - SHARED
    2. VAD (speech detection) - SHARED
    3. Transcription - SHARED
    4. Feature extraction - SHARED
    5. Scoring - MODULE-SPECIFIC (abstract)
    6. Selection - MODULE-SPECIFIC (abstract)
    7. Export - SHARED
    """

    def __init__(self, config):
        self.config = config
        self.progress_callback: Optional[Callable] = None
        self._cancelled = False

        # Initialize core components
        self._init_core_components()

    def _init_core_components(self):
        """Initialize shared core components"""
        # Audio processing
        self.audio_extractor = AudioExtractor(
            sample_rate=getattr(self.config, 'sample_rate', 16000),
            channels=getattr(self.config, 'channels', 1)
        )

        self.audio_normalizer = AudioNormalizer(
            target_loudness=getattr(self.config, 'target_loudness', -16.0),
            sample_rate=getattr(self.config, 'sample_rate', 16000)
        )

        # VAD
        self.vad_detector = VADDetector(
            threshold=getattr(self.config, 'vad_threshold', 0.5),
            min_speech_duration=getattr(self.config, 'min_speech_duration', 0.5),
            use_gpu=getattr(self.config, 'use_gpu', True)
        )

        # Transcription
        self.transcriber = WhisperTranscriber(
            model=getattr(self.config, 'whisper_model', 'small'),
            language=getattr(self.config, 'language', 'pl'),
            use_gpu=getattr(self.config, 'use_gpu', True)
        )

        # Feature extractors
        self.acoustic_extractor = AcousticFeatureExtractor()
        self.prosodic_extractor = ProsodicFeatureExtractor()

    def set_progress_callback(self, callback: Callable):
        """Set progress callback for UI updates"""
        self.progress_callback = callback

    def cancel(self):
        """Cancel pipeline execution"""
        self._cancelled = True

    def _update_progress(self, progress: float, message: str):
        """Update progress if callback is set"""
        if self.progress_callback:
            self.progress_callback(progress, message)

    @abstractmethod
    def score_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Domain-specific scoring logic.
        Each module implements its own scoring strategy.

        Args:
            segments: List of segments with features

        Returns:
            Segments with added 'score' field
        """
        pass

    @abstractmethod
    def select_clips(self, segments: List[Dict]) -> List[Dict]:
        """
        Domain-specific clip selection logic.

        Args:
            segments: Scored segments

        Returns:
            Selected clips for final video
        """
        pass

    def process(self, input_file: str, output_dir: str) -> Dict[str, Any]:
        """
        Main processing pipeline - SHARED across all modules

        Args:
            input_file: Path to input video
            output_dir: Path to output directory

        Returns:
            Dict with processing results
        """
        input_path = Path(input_file)
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        results = {}

        # Stage 1: Ingest (Audio Extraction + Normalization)
        self._update_progress(0.1, "Extracting audio...")

        audio_raw = output_path / "audio_raw.wav"
        audio_normalized = output_path / "audio_normalized.wav"

        self.audio_extractor.extract(str(input_path), str(audio_raw))
        self.audio_normalizer.normalize(str(audio_raw), str(audio_normalized))

        metadata = self.audio_extractor.get_metadata(str(input_path))
        results['metadata'] = metadata

        if self._cancelled:
            return {'cancelled': True}

        # Stage 2: VAD
        self._update_progress(0.2, "Detecting speech...")

        segments = self.vad_detector.detect_speech(str(audio_normalized))
        results['vad_segments'] = len(segments)

        if self._cancelled:
            return {'cancelled': True}

        # Stage 3: Transcription
        self._update_progress(0.4, "Transcribing...")

        segments = self.transcriber.transcribe_segments(
            str(audio_normalized),
            segments,
            progress_callback=lambda p, m: self._update_progress(0.4 + p * 0.2, m)
        )

        if self._cancelled:
            return {'cancelled': True}

        # Stage 4: Feature Extraction
        self._update_progress(0.6, "Extracting features...")

        segments = self.acoustic_extractor.extract_for_segments(
            str(audio_normalized),
            segments
        )
        segments = self.prosodic_extractor.extract_for_segments(segments)

        if self._cancelled:
            return {'cancelled': True}

        # Stage 5: Scoring (MODULE-SPECIFIC)
        self._update_progress(0.7, "Scoring segments...")

        segments = self.score_segments(segments)

        if self._cancelled:
            return {'cancelled': True}

        # Stage 6: Selection (MODULE-SPECIFIC)
        self._update_progress(0.8, "Selecting clips...")

        selected_clips = self.select_clips(segments)
        results['selected_clips'] = selected_clips

        if self._cancelled:
            return {'cancelled': True}

        # Stage 7: Export (to be implemented per module if needed)
        self._update_progress(0.9, "Preparing export...")

        results['segments'] = segments
        results['num_clips'] = len(selected_clips)

        self._update_progress(1.0, "Done!")

        return results

    def get_module_name(self) -> str:
        """Return module name for display"""
        return self.__class__.__name__.replace('Pipeline', '')
