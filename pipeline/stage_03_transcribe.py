"""
Stage 3: Transkrypcja Audio → Tekst
- Używa Faster-Whisper (optimized dla GPU)
- TYLKO szybka metoda (wycinanie segmentów)
"""

# Suppress pkg_resources deprecation warning from ctranslate2
# See: https://github.com/OpenNMT/CTranslate2/pull/1911
import warnings
warnings.filterwarnings("ignore", message="pkg_resources is deprecated", category=UserWarning)

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable

try:
    from faster_whisper import WhisperModel
except ImportError:
    print("⚠️ faster-whisper nie zainstalowany. Instaluję...")
    import subprocess
    subprocess.check_call(["pip", "install", "faster-whisper"])
    from faster_whisper import WhisperModel

from .config import Config


class TranscribeStage:
    """Stage 3: Automatic Speech Recognition z Whisper"""
    
    def __init__(self, config: Config):
        self.config = config
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """Załaduj Faster-Whisper model"""
        print(f"📥 Ładowanie Whisper model: {self.config.asr.model}")
        
        device = "cuda" if self.config.use_gpu else "cpu"
        compute_type = self.config.asr.compute_type if device == "cuda" else "int8"
        
        try:
            self.model = WhisperModel(
                self.config.asr.model,
                device=device,
                compute_type=compute_type,
                download_root=None
            )
            
            print(f"   ✓ Model załadowany na {device.upper()}")
            
        except Exception as e:
            raise RuntimeError(f"Nie udało się załadować Whisper: {e}")
    
    def process(
        self, 
        audio_file: str, 
        vad_segments: List[Dict],
        output_dir: Path,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Główna metoda przetwarzania"""
        audio_path = Path(audio_file)
        
        print(f"🎤 Transkrypcja {len(vad_segments)} segmentów...")
        
        transcribed_segments = []
        total_segments = len(vad_segments)
        batch_size = self.config.asr.batch_size
        
        for batch_idx in range(0, total_segments, batch_size):
            batch = vad_segments[batch_idx:batch_idx + batch_size]
            
            progress_pct = (batch_idx / total_segments) * 100
            if progress_callback:
                progress_callback(
                    progress_pct / 100,
                    f"Transkrypcja batch {batch_idx//batch_size + 1}/{(total_segments + batch_size - 1)//batch_size}"
                )
            
            print(f"   Batch {batch_idx//batch_size + 1}: segmenty {batch_idx}-{batch_idx+len(batch)}")
            
            for seg in batch:
                transcribed = self._transcribe_segment(audio_path, seg)
                transcribed_segments.append(transcribed)
        
        total_words = sum(len(seg.get('words', [])) for seg in transcribed_segments)
        
        print(f"   ✓ Transkrybowano {total_words} słów")
        
        output_file = output_dir / "segments_with_transcript.json"
        self._save_segments(transcribed_segments, output_file)
        
        print("✅ Stage 3 zakończony")
        
        return {
            'segments': transcribed_segments,
            'total_words': total_words,
            'num_segments': len(transcribed_segments),
            'output_file': str(output_file)
        }
    
    def _transcribe_segment(self, audio_path: Path, segment: Dict) -> Dict:
        """Transkrybuj segment - TYLKO szybka metoda"""
        print(f"      → Segment {segment['id']} ({segment['duration']:.1f}s)...")
        
        try:
            return self._transcribe_segment_alternative(audio_path, segment)
        except Exception as e:
            print(f"      ❌ Błąd: {e}")
            return {
                **segment,
                'transcript': "",
                'words': [],
                'confidence': 0.0,
                'error': str(e),
                'num_words': 0
            }
    
    def _transcribe_segment_alternative(self, audio_path: Path, segment: Dict) -> Dict:
        """Szybka metoda: wytnij segment → transkrybuj"""
        import subprocess
        import tempfile
        import os
        import time

        t0 = float(segment['t0'])
        t1 = float(segment['t1'])
        duration = t1 - t0

        temp_fd, temp_audio = tempfile.mkstemp(suffix='.wav', prefix='whisper_')
        os.close(temp_fd)

        try:
            # Extract segment
            cmd = [
                'ffmpeg', '-ss', str(t0), '-t', str(duration),
                '-i', str(audio_path), '-ar', '16000', '-ac', '1',
                '-y', temp_audio
            ]

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         check=True, timeout=60)

            # Transcribe
            segments_iter, info = self.model.transcribe(
                temp_audio,
                language=self.config.asr.language,
                beam_size=self.config.asr.beam_size,
                temperature=self.config.asr.temperature,
                condition_on_previous_text=self.config.asr.condition_on_previous_text,
                initial_prompt=self.config.asr.initial_prompt.strip(),
                word_timestamps=True,
                vad_filter=False
            )

            full_text = []
            all_words = []
            confidence_scores = []

            # ZABEZPIECZENIE: Limit iteracji + timeout
            # Normalny segment (~3 min audio) powinien dać max ~30 Whisper segments
            # Dodajemy 10x buffer = 300 max iterations
            max_iterations = 300
            iteration_start_time = time.time()
            iteration_timeout = 120  # 2 minuty timeout na całą iterację
            iteration_count = 0

            for whisper_seg in segments_iter:
                # Check iteration limit
                iteration_count += 1
                if iteration_count > max_iterations:
                    print(f"      ⚠️ OSTRZEŻENIE: Przekroczono max iteracji ({max_iterations}) - przerywam transkrypcję")
                    break

                # Check timeout
                elapsed = time.time() - iteration_start_time
                if elapsed > iteration_timeout:
                    print(f"      ⚠️ OSTRZEŻENIE: Timeout iteracji ({iteration_timeout}s) - przerywam transkrypcję")
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

            # Debug info jeśli była bliska przekroczenia
            if iteration_count > max_iterations * 0.8:
                print(f"      ℹ️ Info: Segment wygenerował {iteration_count} Whisper segments (limit: {max_iterations})")

            transcript = " ".join(full_text)
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0
            
            return {
                **segment,
                'transcript': transcript,
                'words': all_words,
                'confidence': float(avg_confidence),
                'language': info.language if hasattr(info, 'language') else self.config.asr.language,
                'num_words': len(all_words)
            }
            
        finally:
            try:
                if os.path.exists(temp_audio):
                    os.unlink(temp_audio)
            except:
                pass
    
    def _save_segments(self, segments: List[Dict], output_file: Path):
        """Zapisz segmenty"""
        serializable = []
        
        for seg in segments:
            seg_copy = seg.copy()
            if 'confidence' in seg_copy:
                seg_copy['confidence'] = float(seg_copy['confidence'])
            serializable.append(seg_copy)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        
        print(f"   💾 Transkrypcja zapisana: {output_file.name}")
    
    def cancel(self):
        """Anuluj operację"""
        pass