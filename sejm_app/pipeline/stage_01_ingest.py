"""
Stage 1: Ingest & Preprocessing
- Ekstrakcja audio z video
- Normalizacja głośności (EBU R128)
- Walidacja plików
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any

from .config import Config


class IngestStage:
    """Stage 1: Audio extraction i preprocessing"""
    
    def __init__(self, config: Config):
        self.config = config
        self._check_ffmpeg()
    
    def _check_ffmpeg(self):
        """Sprawdź czy ffmpeg jest dostępny"""
        try:
            subprocess.run(
                ['ffmpeg', '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "❌ ffmpeg nie jest zainstalowany!\n"
                "Pobierz z: https://ffmpeg.org/download.html\n"
                "Lub zainstaluj: choco install ffmpeg (Windows)"
            )
    
    def process(self, input_file: str, output_dir: Path) -> Dict[str, Any]:
        """
        Główna metoda przetwarzania
        
        Returns:
            Dict zawierający:
                - audio_raw: Path do surowego audio
                - audio_normalized: Path do znormalizowanego audio
                - metadata: Dict z metadanymi video
        """
        input_path = Path(input_file)
        
        # 1. Walidacja pliku wejściowego
        print("📋 Walidacja pliku wejściowego...")
        metadata = self._validate_and_get_metadata(input_path)
        
        # 2. Ekstrakcja audio
        print("🎵 Ekstrakcja audio...")
        audio_raw = output_dir / "audio_raw.wav"
        self._extract_audio(input_path, audio_raw)
        
        # 3. Normalizacja głośności
        print("🔊 Normalizacja głośności (EBU R128)...")
        audio_normalized = output_dir / "audio_normalized.wav"
        self._normalize_audio(audio_raw, audio_normalized)
        
        print("✅ Stage 1 zakończony")
        
        return {
            'audio_raw': str(audio_raw),
            'audio_normalized': str(audio_normalized),
            'metadata': metadata
        }
    
    def _validate_and_get_metadata(self, input_file: Path) -> Dict[str, Any]:
        """Waliduj plik i wyciągnij metadata za pomocą ffprobe"""
        if not input_file.exists():
            raise FileNotFoundError(f"Plik nie istnieje: {input_file}")
        
        # Uruchom ffprobe
        cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(input_file)
        ]
        
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                text=True
            )
            
            probe_data = json.loads(result.stdout)
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffprobe error: {e.stderr}")
        except json.JSONDecodeError:
            raise RuntimeError("Nie udało się sparsować ffprobe output")
        
        # Wyciągnij metadata
        format_data = probe_data.get('format', {})
        video_stream = None
        audio_stream = None
        
        for stream in probe_data.get('streams', []):
            if stream['codec_type'] == 'video' and not video_stream:
                video_stream = stream
            elif stream['codec_type'] == 'audio' and not audio_stream:
                audio_stream = stream
        
        if not video_stream:
            raise ValueError("Brak video stream w pliku")
        
        if not audio_stream:
            raise ValueError("Brak audio stream w pliku")
        
        # Parse duration
        duration = float(format_data.get('duration', 0))
        
        # Parse resolution
        width = int(video_stream.get('width', 0))
        height = int(video_stream.get('height', 0))
        
        # Parse FPS
        fps_str = video_stream.get('r_frame_rate', '25/1')
        try:
            num, den = map(int, fps_str.split('/'))
            fps = num / den
        except:
            fps = 25.0
        
        metadata = {
            'duration': duration,
            'width': width,
            'height': height,
            'fps': fps,
            'video_codec': video_stream.get('codec_name', 'unknown'),
            'audio_codec': audio_stream.get('codec_name', 'unknown'),
            'file_size_mb': input_file.stat().st_size / (1024**2)
        }
        
        print(f"   Czas trwania: {duration/3600:.2f}h")
        print(f"   Rozdzielczość: {width}x{height}")
        print(f"   FPS: {fps:.2f}")
        print(f"   Rozmiar: {metadata['file_size_mb']:.1f} MB")
        
        return metadata
    
    def _extract_audio(self, input_file: Path, output_file: Path):
        """
        Ekstrakcja audio z video
        Output: 16kHz mono WAV (wymóg Whisper)
        """
        cmd = [
            'ffmpeg',
            '-i', str(input_file),
            '-vn',  # No video
            '-ac', str(self.config.audio.channels),  # Mono
            '-ar', str(self.config.audio.sample_rate),  # 16kHz
            '-y',  # Overwrite
            str(output_file)
        ]
        
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            
            print(f"   ✓ Audio zapisane: {output_file.name}")
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg extraction error: {e.stderr.decode()}")
    
    def _normalize_audio(self, input_file: Path, output_file: Path):
        """
        Normalizacja głośności używając EBU R128
        
        Sejm ma bardzo nierówną głośność (mikrofony różne, oklaski itp)
        EBU R128 to broadcast standard dla normalizacji
        """
        target_loudness = self.config.audio.target_loudness
        
        # Dwu-przebiegowa normalizacja:
        # Pass 1: Analiza
        # Pass 2: Aplikacja
        
        cmd = [
            'ffmpeg',
            '-i', str(input_file),
            '-af', f'loudnorm=I={target_loudness}:LRA=11:TP=-1.5',
            '-ar', str(self.config.audio.sample_rate),
            '-ac', str(self.config.audio.channels),
            '-y',
            str(output_file)
        ]
        
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )
            
            print(f"   ✓ Audio znormalizowane: {output_file.name}")
            print(f"   Target loudness: {target_loudness} LUFS")
            
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"ffmpeg normalization error: {e.stderr.decode()}")
    
    def cancel(self):
        """Anuluj operację (placeholder dla future)"""
        # TODO: Implement process termination
        pass


if __name__ == "__main__":
    # Test
    from .config import Config
    
    config = Config.load_default()
    stage = IngestStage(config)
    
    # Test na przykładowym pliku
    test_input = "test_video.mp4"
    test_output = Path("temp_test")
    test_output.mkdir(exist_ok=True)
    
    try:
        result = stage.process(test_input, test_output)
        print("\n✅ Test passed!")
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"\n❌ Test failed: {e}")