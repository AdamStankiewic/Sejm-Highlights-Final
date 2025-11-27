"""
Stage 11: Copyright Protection & Music Detection
Wykrywa muzykę i chroni przed copyright strikes na YouTube
"""

import numpy as np
import librosa
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import subprocess
import json


class CopyrightProtectionStage:
    """
    Detekcja muzyki i ochrona przed copyright

    Funkcje:
    1. Wykrywa segmenty z muzyką (music detection)
    2. Generuje raport o potencjalnych problemach
    3. Stosuje zabezpieczenia (pitch shift, speed change, muting)
    4. Ostrzega użytkownika przed uploadem
    """

    def __init__(self, config):
        self.config = config

        # Parametry detekcji muzyki
        self.music_detection_threshold = 0.7  # 70% pewności że to muzyka
        self.min_music_duration = 5.0  # Min 5s aby uznać za muzykę

        # Parametry ochrony
        self.protection_method = "pitch_shift"  # pitch_shift, speed_change, mute, filter
        self.pitch_shift_semitones = 0.5  # Subtelna zmiana (pół tonu)
        self.speed_change_factor = 1.02  # 2% przyspieszenie

    def detect_music_in_audio(self, audio_file: str) -> List[Dict]:
        """
        Wykrywa segmenty z muzyką w pliku audio

        Returns:
            Lista segmentów z muzyką: [
                {
                    'start': 10.5,
                    'end': 45.2,
                    'duration': 34.7,
                    'confidence': 0.85,
                    'features': {...}
                }
            ]
        """
        print(f"🎵 Analizuję audio pod kątem muzyki: {Path(audio_file).name}")

        # Load audio
        y, sr = librosa.load(audio_file, sr=22050)

        # Analiza w oknach 30-sekundowych
        window_duration = 30.0
        hop_duration = 10.0

        window_samples = int(window_duration * sr)
        hop_samples = int(hop_duration * sr)

        music_segments = []

        for i in range(0, len(y) - window_samples, hop_samples):
            window = y[i:i + window_samples]
            start_time = i / sr
            end_time = (i + window_samples) / sr

            # Cechy muzyczne
            music_score = self._calculate_music_score(window, sr)

            if music_score > self.music_detection_threshold:
                # Połącz z poprzednim segmentem jeśli są blisko
                if music_segments and (start_time - music_segments[-1]['end']) < 5.0:
                    music_segments[-1]['end'] = end_time
                    music_segments[-1]['duration'] = music_segments[-1]['end'] - music_segments[-1]['start']
                    music_segments[-1]['confidence'] = max(music_segments[-1]['confidence'], music_score)
                else:
                    music_segments.append({
                        'start': start_time,
                        'end': end_time,
                        'duration': end_time - start_time,
                        'confidence': music_score,
                        'type': 'music'
                    })

        # Filtruj krótkie segmenty
        music_segments = [seg for seg in music_segments if seg['duration'] >= self.min_music_duration]

        print(f"   🎵 Znaleziono {len(music_segments)} segmentów z muzyką")
        for seg in music_segments:
            print(f"      {seg['start']:.1f}s - {seg['end']:.1f}s (confidence: {seg['confidence']:.2f})")

        return music_segments

    def _calculate_music_score(self, audio: np.ndarray, sr: int) -> float:
        """
        Oblicza prawdopodobieństwo że segment zawiera muzykę

        Używa wielu cech:
        - Harmonic-Percussive Source Separation
        - Spectral centroid (jasność dźwięku)
        - Chroma (nuty muzyczne)
        - Tempo (regularny beat)
        - Zero crossing rate (szum vs muzyka)
        """
        try:
            # 1. Harmonic-Percussive Separation
            harmonic, percussive = librosa.effects.hpss(audio)
            harmonic_ratio = np.mean(np.abs(harmonic)) / (np.mean(np.abs(audio)) + 1e-8)

            # 2. Spectral centroid (muzyka ma wyższe częstotliwości niż mowa)
            spectral_centroid = librosa.feature.spectral_centroid(y=audio, sr=sr)
            centroid_mean = np.mean(spectral_centroid)
            centroid_score = min(centroid_mean / 3000.0, 1.0)  # Normalize

            # 3. Chroma features (nuty muzyczne)
            chroma = librosa.feature.chroma_stft(y=audio, sr=sr)
            chroma_var = np.var(chroma)
            chroma_score = min(chroma_var * 10, 1.0)

            # 4. Tempo detection (regularny beat = muzyka)
            tempo, beats = librosa.beat.beat_track(y=audio, sr=sr)
            tempo_score = 1.0 if 60 < tempo < 200 else 0.3  # Typical music tempo

            # 5. Zero crossing rate (speech ma więcej crossings niż muzyka)
            zcr = librosa.feature.zero_crossing_rate(audio)
            zcr_mean = np.mean(zcr)
            zcr_score = 1.0 - min(zcr_mean * 5, 1.0)  # Lower ZCR = more musical

            # Kombinacja cech (wagi empiryczne)
            music_score = (
                harmonic_ratio * 0.3 +
                centroid_score * 0.2 +
                chroma_score * 0.2 +
                tempo_score * 0.2 +
                zcr_score * 0.1
            )

            return float(music_score)

        except Exception as e:
            print(f"   ⚠️ Błąd analizy muzyki: {e}")
            return 0.0

    def apply_pitch_shift(self, input_file: str, output_file: str, semitones: float = 0.5) -> bool:
        """
        Zmienia tonację audio (pitch shift) używając FFmpeg

        Args:
            semitones: Zmiana w półtonach (0.5 = pół tonu wyżej, -0.5 = pół tonu niżej)
        """
        try:
            print(f"🎶 Stosuje pitch shift: {semitones:+.1f} semitones")

            # Oblicz shift ratio dla FFmpeg rubberband
            # ratio = 2^(semitones/12)
            ratio = 2 ** (semitones / 12)

            cmd = [
                'ffmpeg', '-i', input_file,
                '-af', f'rubberband=pitch={ratio}',
                '-c:v', 'copy',  # Kopiuj video bez zmian
                '-y', output_file
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"   ✅ Pitch shift zastosowany")
                return True
            else:
                print(f"   ❌ Błąd pitch shift: {result.stderr}")
                return False

        except Exception as e:
            print(f"   ❌ Błąd pitch shift: {e}")
            return False

    def apply_speed_change(self, input_file: str, output_file: str, speed_factor: float = 1.02) -> bool:
        """
        Zmienia prędkość video (2% = 1.02)

        Subtelna zmiana może pomóc uniknąć Content ID
        """
        try:
            print(f"⚡ Stosuje zmianę prędkości: {speed_factor}x")

            cmd = [
                'ffmpeg', '-i', input_file,
                '-filter_complex', f'[0:v]setpts={1/speed_factor}*PTS[v];[0:a]atempo={speed_factor}[a]',
                '-map', '[v]', '-map', '[a]',
                '-y', output_file
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"   ✅ Zmiana prędkości zastosowana")
                return True
            else:
                print(f"   ❌ Błąd zmiany prędkości: {result.stderr}")
                return False

        except Exception as e:
            print(f"   ❌ Błąd zmiany prędkości: {e}")
            return False

    def mute_music_segments(self, input_file: str, output_file: str, music_segments: List[Dict]) -> bool:
        """
        Wycisza segmenty z muzyką, zostawia tylko mowę
        """
        try:
            print(f"🔇 Wyciszam {len(music_segments)} segmentów z muzyką")

            if not music_segments:
                # Brak muzyki - kopiuj bez zmian
                subprocess.run(['ffmpeg', '-i', input_file, '-c', 'copy', '-y', output_file])
                return True

            # Buduj filter dla FFmpeg
            # Używamy volume filter dla każdego segmentu
            filters = []
            for seg in music_segments:
                start = seg['start']
                end = seg['end']
                # volume=0 między start-end (wyciszenie)
                filters.append(f"volume=enable='between(t,{start},{end})':volume=0")

            filter_str = ','.join(filters)

            cmd = [
                'ffmpeg', '-i', input_file,
                '-af', filter_str,
                '-c:v', 'copy',
                '-y', output_file
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                print(f"   ✅ Wyciszono segmenty z muzyką")
                return True
            else:
                print(f"   ❌ Błąd wyciszania: {result.stderr}")
                return False

        except Exception as e:
            print(f"   ❌ Błąd wyciszania: {e}")
            return False

    def generate_copyright_report(self, video_file: str, music_segments: List[Dict]) -> Dict:
        """
        Generuje raport o ryzyku copyright
        """
        total_duration = self._get_video_duration(video_file)
        music_duration = sum(seg['duration'] for seg in music_segments)
        music_percentage = (music_duration / total_duration * 100) if total_duration > 0 else 0

        # Ocena ryzyka
        if music_percentage > 30:
            risk_level = "HIGH"
            risk_color = "🔴"
        elif music_percentage > 10:
            risk_level = "MEDIUM"
            risk_color = "🟡"
        elif music_percentage > 0:
            risk_level = "LOW"
            risk_color = "🟢"
        else:
            risk_level = "NONE"
            risk_color = "✅"

        report = {
            'video_file': video_file,
            'total_duration': total_duration,
            'music_segments': music_segments,
            'music_duration': music_duration,
            'music_percentage': music_percentage,
            'risk_level': risk_level,
            'risk_color': risk_color,
            'recommendations': self._get_recommendations(risk_level, music_segments)
        }

        return report

    def _get_recommendations(self, risk_level: str, music_segments: List[Dict]) -> List[str]:
        """Rekomendacje na podstawie ryzyka"""
        recommendations = []

        if risk_level == "HIGH":
            recommendations.append("⚠️ WYSOKIE ryzyko copyright strike!")
            recommendations.append("🔧 Zalecana akcja: Usuń segmenty z muzyką lub zastosuj pitch shift")
            recommendations.append("🎵 Rozważ użycie muzyki royalty-free")
        elif risk_level == "MEDIUM":
            recommendations.append("⚠️ Średnie ryzyko copyright")
            recommendations.append("🔧 Rozważ: Pitch shift (+0.5 semitones) lub speed change (1.02x)")
        elif risk_level == "LOW":
            recommendations.append("✅ Niskie ryzyko copyright")
            recommendations.append("ℹ️ Opcjonalnie: Możesz zastosować subtelne zabezpieczenia")
        else:
            recommendations.append("✅ Brak wykrytej muzyki - bezpieczne do uploadu")

        return recommendations

    def _get_video_duration(self, video_file: str) -> float:
        """Pobiera długość video w sekundach"""
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'json',
                video_file
            ]
            result = subprocess.run(cmd, capture_output=True, text=True)
            data = json.loads(result.stdout)
            return float(data['format']['duration'])
        except:
            return 0.0

    def process(self, video_files: List[str], output_dir: Path,
                protection_mode: str = "report_only") -> Dict:
        """
        Główna metoda przetwarzania

        Args:
            video_files: Lista plików video do sprawdzenia
            output_dir: Katalog wyjściowy
            protection_mode:
                - "report_only": Tylko raport, bez modyfikacji
                - "pitch_shift": Zastosuj pitch shift
                - "speed_change": Zmień prędkość
                - "mute_music": Wycisz muzykę
                - "auto": Automatyczny wybór na podstawie ryzyka

        Returns:
            Dict z raportami i chronionymi plikami
        """
        results = {
            'reports': [],
            'protected_files': [],
            'total_risk': 'NONE'
        }

        for video_file in video_files:
            print(f"\n🔍 Analizuję: {Path(video_file).name}")

            # 1. Ekstrahuj audio
            audio_file = output_dir / f"{Path(video_file).stem}_audio.wav"
            self._extract_audio(video_file, str(audio_file))

            # 2. Wykryj muzykę
            music_segments = self.detect_music_in_audio(str(audio_file))

            # 3. Generuj raport
            report = self.generate_copyright_report(video_file, music_segments)
            results['reports'].append(report)

            # 4. Wyświetl raport
            self._print_report(report)

            # 5. Zastosuj ochronę jeśli nie report_only
            if protection_mode != "report_only":
                protected_file = self._apply_protection(
                    video_file, output_dir, music_segments,
                    protection_mode, report['risk_level']
                )
                if protected_file:
                    results['protected_files'].append(protected_file)

            # Cleanup
            if audio_file.exists():
                audio_file.unlink()

        # Określ całkowite ryzyko
        risk_levels = [r['risk_level'] for r in results['reports']]
        if 'HIGH' in risk_levels:
            results['total_risk'] = 'HIGH'
        elif 'MEDIUM' in risk_levels:
            results['total_risk'] = 'MEDIUM'
        elif 'LOW' in risk_levels:
            results['total_risk'] = 'LOW'

        return results

    def _extract_audio(self, video_file: str, audio_file: str):
        """Ekstrahuje audio z video"""
        cmd = [
            'ffmpeg', '-i', video_file,
            '-vn', '-acodec', 'pcm_s16le',
            '-ar', '22050', '-ac', '1',
            '-y', audio_file
        ]
        subprocess.run(cmd, capture_output=True)

    def _apply_protection(self, video_file: str, output_dir: Path,
                         music_segments: List[Dict], mode: str, risk_level: str) -> Optional[str]:
        """Stosuje ochronę na podstawie trybu"""
        output_file = output_dir / f"{Path(video_file).stem}_protected.mp4"

        if mode == "auto":
            # Automatyczny wybór na podstawie ryzyka
            if risk_level == "HIGH":
                mode = "mute_music"
            elif risk_level == "MEDIUM":
                mode = "pitch_shift"
            else:
                return None  # Brak potrzeby ochrony

        if mode == "pitch_shift":
            success = self.apply_pitch_shift(video_file, str(output_file), self.pitch_shift_semitones)
        elif mode == "speed_change":
            success = self.apply_speed_change(video_file, str(output_file), self.speed_change_factor)
        elif mode == "mute_music":
            success = self.mute_music_segments(video_file, str(output_file), music_segments)
        else:
            return None

        return str(output_file) if success else None

    def _print_report(self, report: Dict):
        """Wyświetla raport copyright"""
        print(f"\n{report['risk_color']} COPYRIGHT RISK REPORT")
        print(f"   Video: {Path(report['video_file']).name}")
        print(f"   Total duration: {report['total_duration']:.1f}s")
        print(f"   Music duration: {report['music_duration']:.1f}s ({report['music_percentage']:.1f}%)")
        print(f"   Risk level: {report['risk_level']}")
        print(f"\n   Recommendations:")
        for rec in report['recommendations']:
            print(f"   {rec}")
