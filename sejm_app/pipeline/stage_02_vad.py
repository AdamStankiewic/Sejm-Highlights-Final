"""
Stage 2: Voice Activity Detection (VAD)
- Używa Silero VAD do wykrycia gdzie jest mowa
- Segmentuje audio na fragmenty z mową
- Post-processing: merge gaps, split długich segmentów
"""

import torch
import torchaudio
import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np

from .config import Config


class VADStage:
    """Stage 2: Voice Activity Detection"""
    
    def __init__(self, config: Config):
        self.config = config
        self.model = None
        self.utils = None
        self._load_model()
    
    def _load_model(self):
        """Załaduj Silero VAD model"""
        print("📥 Ładowanie Silero VAD model...")
        
        try:
            # Force reload to avoid cached corrupted models
            torch.hub._validate_not_a_forked_repo = lambda a, b, c: True
            
            # Pobierz model z torch hub
            self.model, self.utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False,
                trust_repo=True
            )
            
            # Set to eval mode
            self.model.eval()
            
            # Przenieś na GPU jeśli dostępne
            if self.config.use_gpu and torch.cuda.is_available():
                self.model = self.model.cuda()
                print("   ✓ Model załadowany na GPU")
            else:
                print("   ✓ Model załadowany na CPU")
            
        except Exception as e:
            print(f"   ⚠️ Błąd ładowania Silero VAD: {e}")
            print("   Próba alternatywnej metody...")
            
            try:
                # Alternative: load without JIT compilation
                self.model, self.utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=True,
                    onnx=False,
                    trust_repo=True
                )
                self.model.eval()
                
                if self.config.use_gpu and torch.cuda.is_available():
                    self.model = self.model.cuda()
                
                print("   ✓ Model załadowany (alternatywna metoda)")
                
            except Exception as e2:
                raise RuntimeError(f"Nie udało się załadować Silero VAD: {e2}")
    
    def process(self, audio_file: str, output_dir: Path) -> Dict[str, Any]:
        """
        Główna metoda przetwarzania
        
        Returns:
            Dict zawierający:
                - segments: Lista segmentów z mową
                - total_speech_duration: Całkowity czas mowy (sekundy)
        """
        audio_path = Path(audio_file)
        
        # 1. Wczytaj audio
        print(f"🎵 Wczytywanie audio: {audio_path.name}")
        waveform, sample_rate = self._load_audio(audio_path)
        
        # 2. Uruchom VAD
        print("🔍 Wykrywanie aktywności głosowej...")
        try:
            raw_segments = self._detect_speech(waveform, sample_rate)
        except Exception as e:
            print(f"   ⚠️ Błąd VAD, używam fallback metody: {e}")
            raw_segments = self._detect_speech_fallback(waveform, sample_rate)
        
        print(f"   Znaleziono {len(raw_segments)} surowych segmentów")
        
        # 3. Post-processing
        print("⚙️ Post-processing segmentów...")
        processed_segments = self._post_process_segments(raw_segments)
        
        print(f"   Po przetworzeniu: {len(processed_segments)} segmentów")
        
        # 4. Statystyki
        total_speech = sum(seg['duration'] for seg in processed_segments)
        print(f"   Całkowity czas mowy: {total_speech/3600:.2f}h")
        
        # 5. Zapisz wyniki
        output_file = output_dir / "vad_segments.json"
        self._save_segments(processed_segments, output_file)
        
        print("✅ Stage 2 zakończony")
        
        return {
            'segments': processed_segments,
            'total_speech_duration': total_speech,
            'num_segments': len(processed_segments),
            'output_file': str(output_file)
        }
    
    def _load_audio(self, audio_path: Path) -> tuple:
        """Wczytaj audio file"""
        try:
            waveform, sample_rate = torchaudio.load(str(audio_path))
            
            # Konwertuj na mono jeśli stereo
            if waveform.shape[0] > 1:
                waveform = torch.mean(waveform, dim=0, keepdim=True)
            
            # Resample jeśli potrzeba (Silero wymaga 16kHz)
            if sample_rate != 16000:
                resampler = torchaudio.transforms.Resample(sample_rate, 16000)
                waveform = resampler(waveform)
                sample_rate = 16000
            
            return waveform, sample_rate
            
        except Exception as e:
            raise RuntimeError(f"Błąd wczytywania audio: {e}")
    
    def _detect_speech(self, waveform: torch.Tensor, sample_rate: int) -> List[Dict]:
        """
        Wykryj segmenty mowy używając Silero VAD
        """
        # Get utilities
        (get_speech_timestamps, _, read_audio, *_) = self.utils
        
        # Prepare audio tensor (move to same device as model)
        audio_tensor = waveform.squeeze()
        
        if self.config.use_gpu and torch.cuda.is_available():
            audio_tensor = audio_tensor.cuda()
        else:
            audio_tensor = audio_tensor.cpu()
        
        # Parametry VAD z config
        vad_params = {
            'threshold': self.config.vad.threshold,
            'min_speech_duration_ms': int(self.config.vad.min_speech_duration * 1000),
            'min_silence_duration_ms': int(self.config.vad.min_silence_duration * 1000),
            'sampling_rate': sample_rate
        }
        
        # Uruchom VAD with error handling
        with torch.no_grad():
            speech_timestamps = get_speech_timestamps(
                audio_tensor,
                self.model,
                **vad_params
            )
        
        # Konwertuj timestamps na sekundy i format dict
        segments = []
        for i, ts in enumerate(speech_timestamps):
            start_sec = ts['start'] / sample_rate
            end_sec = ts['end'] / sample_rate
            duration = end_sec - start_sec
            
            segments.append({
                'id': f"seg_{i:04d}",
                't0': start_sec,
                't1': end_sec,
                'duration': duration
            })
        
        return segments
    
    def _detect_speech_fallback(self, waveform: torch.Tensor, sample_rate: int) -> List[Dict]:
        """
        Fallback VAD using simple energy-based detection
        """
        print("   Używam prostej detekcji opartej na energii...")
        
        audio_np = waveform.squeeze().cpu().numpy()
        
        # Parametry
        frame_length = int(0.02 * sample_rate)  # 20ms frames
        hop_length = int(0.01 * sample_rate)  # 10ms hop
        
        # Oblicz energię w każdym oknie
        energy = []
        for i in range(0, len(audio_np) - frame_length, hop_length):
            frame = audio_np[i:i+frame_length]
            frame_energy = np.sum(frame ** 2) / len(frame)
            energy.append(frame_energy)
        
        energy = np.array(energy)
        
        # Threshold (percentyl 30 - poniżej tego to cisza)
        threshold = np.percentile(energy, 30)
        
        # Znajdź segmenty z mową
        is_speech = energy > threshold
        
        # Znajdź początki i końce segmentów
        segments = []
        in_speech = False
        start_idx = 0
        
        for i, speech in enumerate(is_speech):
            if speech and not in_speech:
                # Początek segmentu
                start_idx = i
                in_speech = True
            elif not speech and in_speech:
                # Koniec segmentu
                start_time = start_idx * hop_length / sample_rate
                end_time = i * hop_length / sample_rate
                duration = end_time - start_time
                
                # Tylko segmenty dłuższe niż min_duration
                if duration >= self.config.vad.min_speech_duration:
                    segments.append({
                        'id': f"seg_{len(segments):04d}",
                        't0': start_time,
                        't1': end_time,
                        'duration': duration
                    })
                
                in_speech = False
        
        # Ostatni segment jeśli jest otwarty
        if in_speech:
            start_time = start_idx * hop_length / sample_rate
            end_time = len(is_speech) * hop_length / sample_rate
            duration = end_time - start_time
            
            if duration >= self.config.vad.min_speech_duration:
                segments.append({
                    'id': f"seg_{len(segments):04d}",
                    't0': start_time,
                    't1': end_time,
                    'duration': duration
                })
        
        return segments
    
    def _post_process_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Post-processing segmentów:
        1. Merge gaps < min_silence_duration
        2. Split segmentów > max_segment_duration
        3. Trim silence na brzegach
        """
        if not segments:
            return []
        
        processed = []
        
        # 1. Merge bliskich segmentów
        merged = self._merge_close_segments(segments)
        
        # 2. Split długich segmentów
        for seg in merged:
            if seg['duration'] > self.config.vad.max_segment_duration:
                # Split na kawałki max_segment_duration
                splits = self._split_long_segment(seg)
                processed.extend(splits)
            else:
                processed.append(seg)
        
        # 3. Re-index
        for i, seg in enumerate(processed):
            seg['id'] = f"seg_{i:04d}"
        
        return processed
    
    def _merge_close_segments(self, segments: List[Dict]) -> List[Dict]:
        """Merge segmentów z małymi przerwami"""
        if len(segments) < 2:
            return segments
        
        min_gap = self.config.vad.min_silence_duration
        merged = []
        current = segments[0].copy()
        
        for next_seg in segments[1:]:
            gap = next_seg['t0'] - current['t1']
            
            if gap < min_gap:
                # Merge: rozszerz current do końca next
                current['t1'] = next_seg['t1']
                current['duration'] = current['t1'] - current['t0']
            else:
                # Gap za duży, zapisz current i zacznij nowy
                merged.append(current)
                current = next_seg.copy()
        
        # Dodaj ostatni
        merged.append(current)
        
        return merged
    
    def _split_long_segment(self, segment: Dict) -> List[Dict]:
        """Split długiego segmentu na mniejsze kawałki"""
        max_dur = self.config.vad.max_segment_duration
        splits = []
        
        t0 = segment['t0']
        t1 = segment['t1']
        duration = segment['duration']
        
        # Ile splitów potrzeba?
        num_splits = int(np.ceil(duration / max_dur))
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
    
    def _save_segments(self, segments: List[Dict], output_file: Path):
        """Zapisz segmenty do JSON"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        
        print(f"   💾 Segmenty zapisane: {output_file.name}")
    
    def cancel(self):
        """Anuluj operację"""
        pass


if __name__ == "__main__":
    # Test
    from .config import Config
    
    config = Config.load_default()
    stage = VADStage(config)
    
    # Test na przykładowym audio
    test_audio = "temp_test/audio_normalized.wav"
    test_output = Path("temp_test")
    
    try:
        result = stage.process(test_audio, test_output)
        print("\n✅ Test passed!")
        print(f"Znaleziono {result['num_segments']} segmentów")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")