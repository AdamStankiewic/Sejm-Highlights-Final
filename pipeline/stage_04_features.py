"""
Stage 4: Feature Engineering
- Acoustic features (RMS, spectral, prosodic)
- Lexical features (keywords, entities)
- Contextual features (speaker change, position)

GPU-accelerated version using torchaudio + CUDA
"""

import json
import csv
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import torch
import torchaudio
import torchaudio.transforms as T
from collections import defaultdict

try:
    import spacy
except ImportError:
    print("⚠️ spaCy nie zainstalowany. Instaluję...")
    import subprocess
    subprocess.check_call(["pip", "install", "spacy"])
    import spacy

from .config import Config


class FeaturesStage:
    """Stage 4: Feature extraction"""
    
    def __init__(self, config: Config):
        self.config = config
        self.keywords_db = {}
        self.nlp = None
        
        self._load_keywords()
        self._load_spacy()
    
    def _load_keywords(self):
        """Załaduj bazę słów kluczowych"""
        keywords_path = Path(self.config.features.keywords_file)
        
        if not keywords_path.exists():
            print(f"⚠️ Brak pliku keywords: {keywords_path}")
            return
        
        print(f"📚 Ładowanie keywords z {keywords_path.name}")
        
        with open(keywords_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Skip comments
                if row['token'].startswith('#'):
                    continue
                
                token = row['token'].lower().strip()
                weight = float(row['weight'])
                category = row['category'].strip()
                
                self.keywords_db[token] = {
                    'weight': weight,
                    'category': category
                }
        
        print(f"   ✓ Załadowano {len(self.keywords_db)} keywords")
    
    def _load_spacy(self):
        """Załaduj model spaCy dla NLP"""
        if not self.config.features.compute_entity_density:
            return
        
        model_name = self.config.features.spacy_model
        
        try:
            print(f"📥 Ładowanie spaCy model: {model_name}")
            self.nlp = spacy.load(model_name)
            print("   ✓ spaCy załadowany")
        except OSError:
            print(f"⚠️ Model spaCy '{model_name}' nie zainstalowany")
            print(f"   Instaluję: python -m spacy download {model_name}")
            import subprocess
            subprocess.check_call([
                "python", "-m", "spacy", "download", model_name
            ])
            self.nlp = spacy.load(model_name)
    
    def process(
        self, 
        audio_file: str,
        segments: List[Dict],
        output_dir: Path
    ) -> Dict[str, Any]:
        """
        Główna metoda przetwarzania
        
        Returns:
            Dict zawierający segments wzbogacone o features
        """
        audio_path = Path(audio_file)
        
        print(f"🔍 Ekstrakcja cech dla {len(segments)} segmentów...")

        # Wczytaj audio raz (dla wszystkich segmentów) - GPU accelerated
        waveform, sr = torchaudio.load(str(audio_path))

        # Convert to mono if stereo
        if waveform.shape[0] > 1:
            waveform = torch.mean(waveform, dim=0, keepdim=True)

        # Move to GPU if available
        device = torch.device('cuda' if (self.config.use_gpu and torch.cuda.is_available()) else 'cpu')
        waveform = waveform.to(device)

        if device.type == 'cuda':
            print(f"   ✓ Audio załadowane na GPU ({waveform.shape[1]/sr/3600:.2f}h, {sr}Hz)")
        else:
            print(f"   ✓ Audio załadowane na CPU")

        # Przetworz każdy segment (TODO: batch processing for even better speed)
        enriched_segments = []

        for i, seg in enumerate(segments):
            if i % 20 == 0:
                print(f"   Przetwarzanie segmentu {i+1}/{len(segments)}")

            # Extract features (GPU accelerated)
            features = self._extract_segment_features(seg, waveform, sr, len(segments), device)

            # Merge z oryginalnym segmentem
            enriched = {**seg, 'features': features}
            enriched_segments.append(enriched)
        
        # Normalizacja features (Z-score w obrębie nagrania)
        enriched_segments = self._normalize_features(enriched_segments)
        
        # Zapisz
        output_file = output_dir / "segments_with_features.json"
        self._save_segments(enriched_segments, output_file)
        
        print("✅ Stage 4 zakończony")
        
        return {
            'segments': enriched_segments,
            'num_segments': len(enriched_segments),
            'output_file': str(output_file)
        }
    
    def _extract_segment_features(
        self,
        segment: Dict,
        audio: torch.Tensor,  # Changed from np.ndarray to torch.Tensor
        sr: int,
        total_segments: int,
        device: torch.device
    ) -> Dict[str, Any]:
        """Ekstrakcja wszystkich cech dla segmentu - GPU accelerated"""

        features = {}

        # 1. ACOUSTIC FEATURES (GPU accelerated)
        if self.config.features.compute_rms:
            features.update(self._extract_acoustic_features_gpu(segment, audio, sr, device))

        # 2. PROSODIC FEATURES (CPU - lightweight)
        if self.config.features.compute_speech_rate:
            features.update(self._extract_prosodic_features(segment))

        # 3. LEXICAL FEATURES (CPU - NLP)
        features.update(self._extract_lexical_features(segment))

        # 4. CONTEXTUAL FEATURES (CPU - simple calc)
        features.update(self._extract_contextual_features(segment, total_segments))

        return features

    def _extract_acoustic_features_gpu(
        self,
        segment: Dict,
        audio: torch.Tensor,
        sr: int,
        device: torch.device
    ) -> Dict[str, float]:
        """Ekstrakcja cech akustycznych - GPU accelerated using torch"""

        # Wytnij audio dla tego segmentu
        t0 = int(segment['t0'] * sr)
        t1 = int(segment['t1'] * sr)
        seg_audio = audio[:, t0:t1]  # [1, samples]

        if seg_audio.shape[1] == 0:
            return {
                'rms': 0.0,
                'spectral_centroid': 0.0,
                'spectral_flux': 0.0,
                'zcr': 0.0
            }

        # RMS Energy (głośność) - GPU
        with torch.no_grad():
            rms = torch.sqrt(torch.mean(seg_audio ** 2)).item()

            # STFT for spectral features - GPU
            n_fft = min(2048, seg_audio.shape[1])
            hop_length = n_fft // 4

            if n_fft < 32:  # Too short for STFT
                return {
                    'rms': rms,
                    'spectral_centroid': 0.0,
                    'spectral_flux': 0.0,
                    'zcr': 0.0
                }

            # Compute STFT on GPU
            stft = torch.stft(
                seg_audio.squeeze(0),
                n_fft=n_fft,
                hop_length=hop_length,
                window=torch.hann_window(n_fft, device=device),
                return_complex=True
            )

            # Magnitude spectrum
            spec = torch.abs(stft)  # [freq_bins, time_frames]

            # Spectral Centroid - GPU
            freqs = torch.linspace(0, sr / 2, spec.shape[0], device=device)
            freqs = freqs.unsqueeze(1)  # [freq_bins, 1]
            centroid = torch.sum(freqs * spec, dim=0) / (torch.sum(spec, dim=0) + 1e-10)
            spectral_centroid = torch.mean(centroid).item()

            # Spectral Flux - GPU
            if spec.shape[1] > 1:
                spec_diff = spec[:, 1:] - spec[:, :-1]
                flux = torch.sqrt(torch.sum(spec_diff ** 2, dim=0))
                spectral_flux = torch.mean(flux).item()
            else:
                spectral_flux = 0.0

            # Zero Crossing Rate - GPU
            # Count sign changes
            signs = torch.sign(seg_audio.squeeze(0))
            sign_changes = torch.abs(signs[1:] - signs[:-1])
            zcr = torch.sum(sign_changes > 0).item() / (2.0 * seg_audio.shape[1])

        return {
            'rms': rms,
            'spectral_centroid': spectral_centroid,
            'spectral_flux': spectral_flux,
            'zcr': zcr
        }
    
    def _extract_prosodic_features(self, segment: Dict) -> Dict[str, float]:
        """Ekstrakcja cech prozodycznych (z word timings)"""
        
        words = segment.get('words', [])
        duration = segment['duration']
        
        if not words or duration == 0:
            return {
                'speech_rate_wpm': 0.0,
                'num_pauses': 0,
                'avg_pause_duration': 0.0,
                'dramatic_pauses': 0
            }
        
        # Speech rate (words per minute)
        speech_rate_wpm = (len(words) / duration) * 60
        
        # Analiza pauz (z word timestamps)
        pauses = []
        for i in range(len(words) - 1):
            gap = words[i+1]['start'] - words[i]['end']
            if gap > 0.3:  # Pauza > 300ms
                pauses.append(gap)
        
        num_pauses = len(pauses)
        avg_pause = float(np.mean(pauses)) if pauses else 0.0
        dramatic_pauses = sum(1 for p in pauses if p > 2.0)  # >2s
        
        return {
            'speech_rate_wpm': float(speech_rate_wpm),
            'num_pauses': num_pauses,
            'avg_pause_duration': avg_pause,
            'dramatic_pauses': dramatic_pauses
        }
    
    def _extract_lexical_features(self, segment: Dict) -> Dict[str, Any]:
        """Ekstrakcja cech leksykalnych (keywords, entities)"""
        
        transcript = segment.get('transcript', '').lower()
        
        if not transcript:
            return {
                'keyword_score': 0.0,
                'matched_keywords': [],
                'entity_density': 0.0,
                'has_question': False
            }
        
        # 1. Keyword matching
        keyword_score = 0.0
        matched_keywords = []
        
        for token, data in self.keywords_db.items():
            if token in transcript:
                keyword_score += data['weight']
                matched_keywords.append({
                    'token': token,
                    'weight': data['weight'],
                    'category': data['category']
                })
        
        # 2. Entity density (jeśli spaCy available)
        entity_density = 0.0
        entities = []
        
        if self.nlp and self.config.features.compute_entity_density:
            doc = self.nlp(segment.get('transcript', ''))
            entities = [
                {'text': ent.text, 'label': ent.label_}
                for ent in doc.ents
                if ent.label_ in ['PER', 'ORG', 'LOC', 'GPE']
            ]
            entity_density = len(entities) / len(doc) if len(doc) > 0 else 0.0
        
        # 3. Question detection
        has_question = '?' in segment.get('transcript', '')
        
        return {
            'keyword_score': float(keyword_score),
            'matched_keywords': matched_keywords[:5],  # Top 5
            'entity_density': float(entity_density),
            'entities': entities[:3],  # Top 3
            'has_question': has_question
        }
    
    def _extract_contextual_features(
        self, 
        segment: Dict,
        total_segments: int
    ) -> Dict[str, float]:
        """Ekstrakcja cech kontekstowych"""
        
        # Position in video (0.0 - 1.0)
        # Zakładamy że segmenty są posortowane chronologicznie
        position = segment['t0'] / (segment['t1'] + 1)  # Approx
        
        # Speaker change likelihood (heurystyka)
        # W przyszłości możemy dodać prawdziwy speaker diarization
        # Na razie: jeśli długa przerwa przed segmentem = prawdopodobna zmiana
        speaker_change_prob = 0.5  # Default
        
        return {
            'position_in_video': float(position),
            'speaker_change_prob': speaker_change_prob
        }
    
    def _normalize_features(self, segments: List[Dict]) -> List[Dict]:
        """Z-score normalizacja features w obrębie nagrania"""
        
        # Zbierz wszystkie wartości dla każdej cechy
        feature_values = defaultdict(list)
        
        for seg in segments:
            features = seg.get('features', {})
            for key, value in features.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    feature_values[key].append(value)
        
        # Oblicz mean i std dla każdej cechy
        stats = {}
        for key, values in feature_values.items():
            if len(values) > 1:
                mean = np.mean(values)
                std = np.std(values)
                stats[key] = {'mean': mean, 'std': std if std > 0 else 1.0}
        
        # Normalizuj
        for seg in segments:
            features = seg['features']
            normalized = {}
            
            for key, value in features.items():
                if key in stats and isinstance(value, (int, float)) and not isinstance(value, bool):
                    mean = stats[key]['mean']
                    std = stats[key]['std']
                    normalized[f"{key}_z"] = (value - mean) / std
                
                # Zachowaj oryginał
                normalized[key] = value
            
            seg['features'] = normalized
        
        return segments
    
    def _save_segments(self, segments: List[Dict], output_file: Path):
        """Zapisz segmenty"""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(segments, f, indent=2, ensure_ascii=False)
        
        print(f"   💾 Features zapisane: {output_file.name}")
    
    def cancel(self):
        """Anuluj operację"""
        pass


if __name__ == "__main__":
    # Test
    from .config import Config
    import json as js
    
    config = Config.load_default()
    stage = FeaturesStage(config)
    
    # Load test segments
    test_file = "temp_test/segments_with_transcript.json"
    
    try:
        with open(test_file, 'r') as f:
            segments = js.load(f)
        
        result = stage.process(
            audio_file="temp_test/audio_normalized.wav",
            segments=segments[:5],  # Test na 5 segmentach
            output_dir=Path("temp_test")
        )
        
        print("\n✅ Test passed!")
        print(f"Extracted features for {result['num_segments']} segments")
        
        # Show example
        if result['segments']:
            example = result['segments'][0]
            print(f"\nExample features:")
            print(json.dumps(example['features'], indent=2))
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")