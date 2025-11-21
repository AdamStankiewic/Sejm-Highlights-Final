"""
Voice Activity Detection using Silero VAD
Part of Highlights AI Platform - Core Engine
"""
import torch
import torchaudio
import numpy as np
from pathlib import Path
from typing import Dict, Any, List


class VADDetector:
    """Detect speech segments in audio using Silero VAD"""

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_duration: float = 0.5,
        min_silence_duration: float = 0.3,
        max_segment_duration: float = 180.0,
        use_gpu: bool = True
    ):
        self.threshold = threshold
        self.min_speech_duration = min_speech_duration
        self.min_silence_duration = min_silence_duration
        self.max_segment_duration = max_segment_duration
        self.use_gpu = use_gpu and torch.cuda.is_available()

        self.model = None
        self.utils = None
        self._load_model()

    def _load_model(self):
        """Load Silero VAD model"""
        try:
            torch.hub._validate_not_a_forked_repo = lambda a, b, c: True

            self.model, self.utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False,
                trust_repo=True
            )

            self.model.eval()

            if self.use_gpu:
                self.model = self.model.cuda()

        except Exception as e:
            # Try alternative loading method
            try:
                self.model, self.utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=True,
                    onnx=False,
                    trust_repo=True
                )
                self.model.eval()

                if self.use_gpu:
                    self.model = self.model.cuda()

            except Exception as e2:
                raise RuntimeError(f"Failed to load Silero VAD: {e2}")

    def detect_speech(self, audio_path: str) -> List[Dict[str, Any]]:
        """
        Detect speech segments in audio file

        Args:
            audio_path: Path to audio file (WAV, 16kHz recommended)

        Returns:
            List of segment dicts with t0, t1, duration
        """
        audio_path = Path(audio_path)

        # Load audio
        waveform, sample_rate = self._load_audio(audio_path)

        # Run VAD
        try:
            raw_segments = self._run_vad(waveform, sample_rate)
        except Exception:
            # Fallback to energy-based detection
            raw_segments = self._detect_speech_fallback(waveform, sample_rate)

        # Post-process
        processed_segments = self._post_process_segments(raw_segments)

        return processed_segments

    def _load_audio(self, audio_path: Path) -> tuple:
        """Load and prepare audio"""
        waveform, sample_rate = torchaudio.load(str(audio_path))

        # Convert to mono
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        # Resample to 16kHz if needed
        if sample_rate != 16000:
            resampler = torchaudio.transforms.Resample(sample_rate, 16000)
            waveform = resampler(waveform)
            sample_rate = 16000

        return waveform, sample_rate

    def _run_vad(self, waveform: torch.Tensor, sample_rate: int) -> List[Dict]:
        """Run Silero VAD"""
        (get_speech_timestamps, *_) = self.utils

        audio_tensor = waveform.squeeze()

        if self.use_gpu:
            audio_tensor = audio_tensor.cuda()
        else:
            audio_tensor = audio_tensor.cpu()

        vad_params = {
            'threshold': self.threshold,
            'min_speech_duration_ms': int(self.min_speech_duration * 1000),
            'min_silence_duration_ms': int(self.min_silence_duration * 1000),
            'sampling_rate': sample_rate
        }

        with torch.no_grad():
            speech_timestamps = get_speech_timestamps(
                audio_tensor,
                self.model,
                **vad_params
            )

        # Convert to seconds
        segments = []
        for i, ts in enumerate(speech_timestamps):
            start_sec = ts['start'] / sample_rate
            end_sec = ts['end'] / sample_rate

            segments.append({
                'id': f"seg_{i:04d}",
                't0': start_sec,
                't1': end_sec,
                'duration': end_sec - start_sec
            })

        return segments

    def _detect_speech_fallback(self, waveform: torch.Tensor, sample_rate: int) -> List[Dict]:
        """Fallback energy-based VAD"""
        audio_np = waveform.squeeze().cpu().numpy()

        frame_length = int(0.02 * sample_rate)
        hop_length = int(0.01 * sample_rate)

        # Calculate energy
        energy = []
        for i in range(0, len(audio_np) - frame_length, hop_length):
            frame = audio_np[i:i+frame_length]
            frame_energy = np.sum(frame ** 2) / len(frame)
            energy.append(frame_energy)

        energy = np.array(energy)
        threshold = np.percentile(energy, 30)
        is_speech = energy > threshold

        # Find segments
        segments = []
        in_speech = False
        start_idx = 0

        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                start_idx = i
                in_speech = True
            elif not speech and in_speech:
                start_time = start_idx * hop_length / sample_rate
                end_time = i * hop_length / sample_rate
                duration = end_time - start_time

                if duration >= self.min_speech_duration:
                    segments.append({
                        'id': f"seg_{len(segments):04d}",
                        't0': start_time,
                        't1': end_time,
                        'duration': duration
                    })

                in_speech = False

        return segments

    def _post_process_segments(self, segments: List[Dict]) -> List[Dict]:
        """Merge gaps and split long segments"""
        if not segments:
            return []

        # Merge close segments
        merged = self._merge_close_segments(segments)

        # Split long segments
        processed = []
        for seg in merged:
            if seg['duration'] > self.max_segment_duration:
                splits = self._split_long_segment(seg)
                processed.extend(splits)
            else:
                processed.append(seg)

        # Re-index
        for i, seg in enumerate(processed):
            seg['id'] = f"seg_{i:04d}"

        return processed

    def _merge_close_segments(self, segments: List[Dict]) -> List[Dict]:
        """Merge segments with small gaps"""
        if len(segments) < 2:
            return segments

        merged = []
        current = segments[0].copy()

        for next_seg in segments[1:]:
            gap = next_seg['t0'] - current['t1']

            if gap < self.min_silence_duration:
                current['t1'] = next_seg['t1']
                current['duration'] = current['t1'] - current['t0']
            else:
                merged.append(current)
                current = next_seg.copy()

        merged.append(current)
        return merged

    def _split_long_segment(self, segment: Dict) -> List[Dict]:
        """Split long segment into smaller chunks"""
        splits = []

        t0 = segment['t0']
        t1 = segment['t1']
        duration = segment['duration']

        num_splits = int(np.ceil(duration / self.max_segment_duration))
        split_duration = duration / num_splits

        for i in range(num_splits):
            split_t0 = t0 + i * split_duration
            split_t1 = min(t0 + (i + 1) * split_duration, t1)

            splits.append({
                'id': f"{segment['id']}_split{i}",
                't0': split_t0,
                't1': split_t1,
                'duration': split_t1 - split_t0
            })

        return splits
