"""
Whisper ASR transcription using faster-whisper
Part of Highlights AI Platform - Core Engine
"""
import subprocess
import tempfile
import os
import time
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

try:
    from faster_whisper import WhisperModel
except ImportError:
    WhisperModel = None


class WhisperTranscriber:
    """Transcribe audio using Faster-Whisper"""

    def __init__(
        self,
        model: str = "small",
        language: str = "pl",
        use_gpu: bool = True,
        beam_size: int = 5,
        temperature: float = 0.0,
        initial_prompt: str = "",
        batch_size: int = 10
    ):
        self.model_name = model
        self.language = language
        self.use_gpu = use_gpu
        self.beam_size = beam_size
        self.temperature = temperature
        self.initial_prompt = initial_prompt
        self.batch_size = batch_size

        self.model = None
        self._load_model()

    def _load_model(self):
        """Load Whisper model"""
        if WhisperModel is None:
            raise ImportError("faster-whisper not installed. Run: pip install faster-whisper")

        device = "cuda" if self.use_gpu else "cpu"
        compute_type = "float16" if device == "cuda" else "int8"

        try:
            self.model = WhisperModel(
                self.model_name,
                device=device,
                compute_type=compute_type,
                download_root=None
            )
        except Exception as e:
            raise RuntimeError(f"Failed to load Whisper model: {e}")

    def transcribe_segments(
        self,
        audio_path: str,
        segments: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Transcribe VAD segments

        Args:
            audio_path: Path to audio file
            segments: List of segment dicts from VAD
            progress_callback: Optional callback(progress, message)

        Returns:
            Segments with added transcript, words, confidence
        """
        audio_path = Path(audio_path)
        transcribed = []
        total = len(segments)

        for batch_idx in range(0, total, self.batch_size):
            batch = segments[batch_idx:batch_idx + self.batch_size]

            if progress_callback:
                progress = batch_idx / total
                progress_callback(progress, f"Batch {batch_idx // self.batch_size + 1}")

            for seg in batch:
                result = self._transcribe_segment(audio_path, seg)
                transcribed.append(result)

        return transcribed

    def _transcribe_segment(self, audio_path: Path, segment: Dict) -> Dict:
        """Transcribe single segment"""
        t0 = float(segment['t0'])
        t1 = float(segment['t1'])
        duration = t1 - t0

        # Create temp file for segment
        temp_fd, temp_audio = tempfile.mkstemp(suffix='.wav', prefix='whisper_')
        os.close(temp_fd)

        try:
            # Extract segment using ffmpeg
            cmd = [
                'ffmpeg', '-ss', str(t0), '-t', str(duration),
                '-i', str(audio_path), '-ar', '16000', '-ac', '1',
                '-y', temp_audio
            ]

            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                timeout=60
            )

            # Transcribe
            segments_iter, info = self.model.transcribe(
                temp_audio,
                language=self.language,
                beam_size=self.beam_size,
                temperature=self.temperature,
                condition_on_previous_text=False,
                initial_prompt=self.initial_prompt,
                word_timestamps=True,
                vad_filter=False
            )

            full_text = []
            all_words = []
            confidence_scores = []

            # Safety limits
            max_iterations = 300
            iteration_timeout = 120
            iteration_start = time.time()
            iteration_count = 0

            for whisper_seg in segments_iter:
                iteration_count += 1

                if iteration_count > max_iterations:
                    break

                if time.time() - iteration_start > iteration_timeout:
                    break

                full_text.append(whisper_seg.text.strip())

                if whisper_seg.words:
                    for word_info in whisper_seg.words:
                        all_words.append({
                            'word': word_info.word.strip(),
                            'start': float(word_info.start) + t0,
                            'end': float(word_info.end) + t0,
                            'probability': float(word_info.probability)
                        })

                if hasattr(whisper_seg, 'avg_logprob'):
                    confidence_scores.append(whisper_seg.avg_logprob)

            transcript = " ".join(full_text)
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

            return {
                **segment,
                'transcript': transcript,
                'words': all_words,
                'confidence': float(avg_confidence),
                'language': info.language if hasattr(info, 'language') else self.language,
                'num_words': len(all_words)
            }

        except Exception as e:
            return {
                **segment,
                'transcript': "",
                'words': [],
                'confidence': 0.0,
                'error': str(e),
                'num_words': 0
            }

        finally:
            try:
                if os.path.exists(temp_audio):
                    os.unlink(temp_audio)
            except:
                pass

    def transcribe_full_audio(self, audio_path: str) -> Dict[str, Any]:
        """
        Transcribe entire audio file (no VAD segments)

        Args:
            audio_path: Path to audio file

        Returns:
            Dict with transcript, words, language
        """
        segments_iter, info = self.model.transcribe(
            audio_path,
            language=self.language,
            beam_size=self.beam_size,
            word_timestamps=True
        )

        full_text = []
        all_words = []

        for seg in segments_iter:
            full_text.append(seg.text.strip())

            if seg.words:
                for w in seg.words:
                    all_words.append({
                        'word': w.word.strip(),
                        'start': float(w.start),
                        'end': float(w.end),
                        'probability': float(w.probability)
                    })

        return {
            'transcript': " ".join(full_text),
            'words': all_words,
            'language': info.language,
            'num_words': len(all_words)
        }
