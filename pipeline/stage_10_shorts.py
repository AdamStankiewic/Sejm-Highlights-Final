"""
Stage 10: YouTube Shorts Generator (ENHANCED)
- Format pionowy 9:16 (1080x1920)
- Żółte napisy z safe zones
- AI-generowane viralne tytuły
- Stały opis zoptymalizowany pod Shorts
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime
import os

from .config import Config


class ShortsStage:
    """Stage 10: YouTube Shorts Generation"""
    
    def __init__(self, config: Config):
        self.config = config
        self._check_ffmpeg()
        
        # Initialize GPT for title generation
        self._init_gpt()
    
    def _init_gpt(self):
        """Inicjalizacja GPT dla generowania tytułów"""
        try:
            from openai import OpenAI
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                print("   ⚠️ Brak OPENAI_API_KEY - tytuły będą generowane bez AI")
                self.gpt_client = None
            else:
                self.gpt_client = OpenAI(api_key=api_key)
                print("   ✓ GPT-4o-mini gotowy do generowania tytułów")
        except ImportError:
            print("   ⚠️ Brak biblioteki openai - zainstaluj: pip install openai")
            self.gpt_client = None
    
    def _check_ffmpeg(self):
        """Sprawdź czy ffmpeg jest dostępny"""
        try:
            subprocess.run(['ffmpeg', '-version'], 
                         stdout=subprocess.PIPE, 
                         stderr=subprocess.PIPE, 
                         check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffmpeg nie jest zainstalowany lub niedostępny w PATH")
    
    def process(
        self,
        input_file: str,
        shorts_clips: List[Dict],
        segments: List[Dict],
        output_dir: Path,
        session_dir: Path
    ) -> Dict[str, Any]:
        """
        Główna metoda generowania Shorts
        
        Args:
            shorts_clips: Już wybrane klipy dla Shorts (z Stage 6)
            
        Returns:
            Dict zawierający listę wygenerowanych Shorts
        """
        print(f"\n🎬 YouTube Shorts Generator (ENHANCED)")
        print(f"📱 Generowanie {len(shorts_clips)} Shorts...")
        
        if not shorts_clips:
            print("   ⚠️ Brak kandydatów na Shorts")
            return {
                'shorts': [],
                'shorts_dir': '',
                'count': 0
            }
        
        input_path = Path(input_file)
        
        # Create subdirs
        shorts_dir = session_dir / "shorts"
        shorts_dir.mkdir(exist_ok=True)
        
        # Generate each Short
        generated_shorts = []
        
        for i, clip in enumerate(shorts_clips, 1):
            print(f"\n   📱 Short {i}/{len(shorts_clips)}")
            
            try:
                short_result = self._generate_single_short(
                    input_path,
                    clip,
                    segments,
                    shorts_dir,
                    i
                )
                generated_shorts.append(short_result)
                
                print(f"      ✅ Zapisano: {short_result['filename']}")
                print(f"      📝 Tytuł: {short_result['title']}")
                
            except Exception as e:
                print(f"      ❌ Błąd: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # Save metadata
        metadata_file = shorts_dir / "shorts_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(generated_shorts, f, indent=2, ensure_ascii=False)
        
        print(f"\n✅ Wygenerowano {len(generated_shorts)} Shorts!")
        print(f"📁 Lokalizacja: {shorts_dir}")
        
        return {
            'shorts': generated_shorts,
            'shorts_dir': str(shorts_dir),
            'metadata_file': str(metadata_file),
            'count': len(generated_shorts)
        }
    
    def _generate_single_short(
        self,
        input_file: Path,
        clip: Dict,
        segments: List[Dict],
        output_dir: Path,
        index: int
    ) -> Dict:
        """Generuj pojedynczy Short z napisami"""

        # Extract clip times
        t0 = max(0, clip['t0'] - self.config.shorts.pre_roll)
        t1 = clip['t1'] + self.config.shorts.post_roll
        duration = t1 - t0

        # Output files
        output_file = output_dir / f"short_{index:02d}.mp4"
        srt_file = output_dir / f"short_{index:02d}.srt"
        ass_file = output_dir / f"short_{index:02d}.ass"

        # Shorts format: 1080x1920 (9:16)
        width = self.config.shorts.width
        height = self.config.shorts.height

        print(f"      🎬 Renderowanie video...")

        # Generate AI title BEFORE subtitles (need it for first frame)
        title = self._generate_ai_short_title(clip, segments)

        # STEP 1: Generuj ASS napisy (żółte, safe zone) + tytuł na pierwszej klatce
        self._generate_shorts_subtitles(clip, segments, t0, t1, ass_file, title)
        
        # STEP 2: Renderuj video z napisami
        # Filter complex:
        # 1. Scale + crop do 9:16
        # 2. Dodaj napisy z ASS (żółte, centered, safe zone)
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[v];"
            f"[v]ass='{str(ass_file).replace('\\', '/')}'"
        )
        
        cmd = [
            'ffmpeg',
            '-ss', str(t0),
            '-to', str(t1),
            '-i', str(input_file),
            '-filter_complex', filter_complex,
            '-map', '0:a',
            '-c:v', 'libx264',
            '-preset', 'medium',
            '-crf', '23',
            '-c:a', 'aac',
            '-b:a', '128k',
            '-movflags', '+faststart',
            '-y',
            str(output_file)
        ]
        
        try:
            result = subprocess.run(
                cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                check=True,
                encoding='utf-8'
            )
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            print(f"      ⚠️ FFmpeg error: {error_msg[:200]}")
            raise

        # Generate description (title already generated above)
        description = self._generate_short_description_fixed()
        
        return {
            'file': str(output_file),
            'filename': output_file.name,
            'srt_file': str(srt_file),
            'ass_file': str(ass_file),
            'title': title,
            'description': description,
            'tags': self._generate_short_tags(clip),
            'duration': duration,
            'clip_id': clip.get('id'),
            'score': clip.get('final_score', 0),
            'source_timestamp': f"{t0:.1f}-{t1:.1f}s"
        }
    
    def _generate_shorts_subtitles(
        self,
        clip: Dict,
        segments: List[Dict],
        clip_start: float,
        clip_end: float,
        ass_file: Path,
        title: str = None
    ):
        """
        Generuj napisy w formacie ASS dla Shorts + tytuł na pierwszej klatce

        Żółte napisy z czarnym outline, positioned w safe zone
        YouTube Shorts UI:
        - Góra (0-200px): nazwa kanału, czas
        - Dół (1620-1920px): przyciski like/comment/share
        - Safe zone: 300-1500px (środek)
        """

        # Znajdź segment odpowiadający clipowi
        segment = None
        for seg in segments:
            if abs(seg['t0'] - clip['t0']) < 1.0:  # Dopasowanie z tolerancją
                segment = seg
                break

        if not segment or 'words' not in segment:
            # Brak transkrypcji - użyj prostego napisu
            self._generate_simple_subtitle(clip, ass_file, clip_start, clip_end, title)
            return

        # Pobierz ustawienia z konfiguracji
        title_fontsize = self.config.shorts.title_fontsize
        title_color = self.config.shorts.title_color
        title_y = self.config.shorts.title_position_y
        title_outline = self.config.shorts.title_outline
        title_shadow = self.config.shorts.title_shadow
        title_bold = -1 if self.config.shorts.title_bold else 0

        # ASS Header - optymalizowany dla Shorts (9:16)
        # Dwa style: Title (duży, żółty, góra) i Default (napisy, dół)
        ass_content = f"""[Script Info]
Title: YouTube Short Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,{title_fontsize},{title_color},&H000000FF,&H00000000,&H80000000,{title_bold},0,0,0,100,100,0,0,1,{title_outline},{title_shadow},8,60,60,{title_y},1
Style: Default,Arial,68,&H00FFFF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,30,30,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Dodaj tytuł przez cały czas trwania Shorta
        if title:
            # Zawijanie długiego tytułu - dziel na linie co ~20 znaków (mniej bo większa czcionka 90px)
            wrapped_title = self._wrap_title(title, max_chars=20)
            # Wyświetlaj tytuł przez cały czas: od 0 do końca klipu
            ass_content += f"Dialogue: 1,{self._format_ass_time(0)},{self._format_ass_time(clip_end - clip_start)},Title,,0,0,0,,{wrapped_title}\n"

        # Generuj linie napisów z word-level timing
        words = segment.get('words', [])
        
        if not words:
            # Fallback - użyj całego tekstu
            text = segment.get('text', '').strip()
            if text:
                ass_content += f"Dialogue: 0,{self._format_ass_time(0)},{self._format_ass_time(clip_end - clip_start)},Default,,0,0,0,,{text}\n"
        else:
            # Grupuj słowa w krótkie frazy (3-4 słowa) dla lepszej czytelności
            # Krótsze frazy bo większa czcionka (68px)
            phrase_length = 4
            i = 0
            
            while i < len(words):
                # Zbierz 4-6 słów
                phrase_words = words[i:i+phrase_length]
                
                if not phrase_words:
                    break
                
                # Oblicz timing względem początku clipu
                start_time = phrase_words[0]['start'] - clip['t0']
                end_time = phrase_words[-1]['end'] - clip['t0']
                
                # Zabezpieczenie przed ujemnymi czasami
                start_time = max(0, start_time)
                end_time = max(start_time + 0.5, end_time)
                
                # Złącz słowa
                text = ' '.join(w['word'] for w in phrase_words)
                
                # Dodaj linię ASS
                ass_content += (
                    f"Dialogue: 0,"
                    f"{self._format_ass_time(start_time)},"
                    f"{self._format_ass_time(end_time)},"
                    f"Default,,0,0,0,,{text}\n"
                )
                
                i += phrase_length
        
        # Zapisz ASS
        with open(ass_file, 'w', encoding='utf-8') as f:
            f.write(ass_content)
        
        print(f"      📝 Napisy ASS: {ass_file.name}")
    
    def _generate_simple_subtitle(
        self,
        clip: Dict,
        ass_file: Path,
        clip_start: float,
        clip_end: float,
        title: str = None
    ):
        """Fallback - prosty napis gdy brak transkrypcji"""

        duration = clip_end - clip_start
        text = clip.get('title', 'Gorący moment z Sejmu! 🔥')

        # Pobierz ustawienia z konfiguracji
        title_fontsize = self.config.shorts.title_fontsize
        title_color = self.config.shorts.title_color
        title_y = self.config.shorts.title_position_y
        title_outline = self.config.shorts.title_outline
        title_shadow = self.config.shorts.title_shadow
        title_bold = -1 if self.config.shorts.title_bold else 0

        ass_content = f"""[Script Info]
Title: YouTube Short Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,{title_fontsize},{title_color},&H000000FF,&H00000000,&H80000000,{title_bold},0,0,0,100,100,0,0,1,{title_outline},{title_shadow},8,60,60,{title_y},1
Style: Default,Arial,68,&H00FFFF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,3,2,30,30,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Dodaj tytuł przez cały czas trwania
        if title:
            wrapped_title = self._wrap_title(title, max_chars=20)
            ass_content += f"Dialogue: 1,{self._format_ass_time(0)},{self._format_ass_time(duration)},Title,,0,0,0,,{wrapped_title}\n"

        # Dodaj główny tekst
        ass_content += f"Dialogue: 0,{self._format_ass_time(0)},{self._format_ass_time(duration)},Default,,0,0,0,,{text}\n"

        with open(ass_file, 'w', encoding='utf-8') as f:
            f.write(ass_content)
    
    def _wrap_title(self, title: str, max_chars: int = 25) -> str:
        """
        Zawijanie długiego tytułu do wielu linii dla lepszej czytelności

        Args:
            title: Tytuł do zawinięcia
            max_chars: Maksymalna liczba znaków na linię

        Returns:
            Tytuł z `\\N` jako separatorami linii (ASS format)
        """
        words = title.split()
        lines = []
        current_line = []
        current_length = 0

        for word in words:
            word_length = len(word)

            # Jeśli dodanie słowa przekroczy limit, zakończ obecną linię
            if current_length + word_length + len(current_line) > max_chars and current_line:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_length = word_length
            else:
                current_line.append(word)
                current_length += word_length

        # Dodaj ostatnią linię
        if current_line:
            lines.append(' '.join(current_line))

        # Złącz linie używając \\N (ASS line break)
        return '\\N'.join(lines)

    def _format_ass_time(self, seconds: float) -> str:
        """Format time for ASS: 0:00:00.00"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        centisecs = int((seconds % 1) * 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centisecs:02d}"
    
    def _generate_ai_short_title(self, clip: Dict, segments: List[Dict]) -> str:
        """
        Generuj viralny tytuł dla Shorta używając GPT-4o-mini
        
        Tytuły w stylu:
        - "GRZESIU ODLECIAŁ! 🔥"
        - "Tusk ZMIAŻDŻYŁ Kaczyńskiego!"
        - "Ta wymiana doprowadziła salę do SZAŁU!"
        """
        
        if not self.gpt_client:
            # Fallback gdy brak GPT
            return self._generate_fallback_title(clip)
        
        # Pobierz transkrypcję dla kontekstu
        segment = None
        for seg in segments:
            if abs(seg['t0'] - clip['t0']) < 1.0:
                segment = seg
                break
        
        transcript = segment.get('transcript', '...') if segment else '...'
        keywords = ', '.join(clip.get('keywords', [])[:3])
        
        # Prompt dla GPT
        prompt = f"""Jesteś ekspertem od viralowych tytułów YouTube Shorts dla polskiej polityki.

TRANSKRYPCJA MOMENTU:
{transcript[:300]}

SŁOWA KLUCZOWE: {keywords}

Wygeneruj JEDEN chwytliwy tytuł dla YouTube Short (max 60 znaków):
- Krótki, dynamiczny, emocjonalny
- Polskie litery (ą, ę, ć, etc.)
- Może zawierać emoji (🔥, 💥, 😱, ⚡)
- W stylu: "Tusk DEMOLUJE Kaczyńskiego! 💥", "Ta wymiana ZMIAŻDŻYŁA salę 🔥"
- NIE używaj [TOP], [HOT], etc.
- Kapitalizacja dla EFEKTU

Tylko tytuł, bez cudzysłowów, bez wyjaśnień:"""

        try:
            response = self.gpt_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od viralowych tytułów YouTube Shorts."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.9,  # Wyższa kreatywność
                max_tokens=50
            )
            
            title = response.choices[0].message.content.strip()
            
            # Cleanup
            title = title.strip('"').strip("'")
            
            # Limit długości
            if len(title) > 70:
                title = title[:67] + "..."
            
            return title
            
        except Exception as e:
            print(f"      ⚠️ GPT error: {e}")
            return self._generate_fallback_title(clip)
    
    def _generate_fallback_title(self, clip: Dict) -> str:
        """Fallback tytuł gdy GPT nie działa"""
        keywords = clip.get('keywords', [])
        score = clip.get('final_score', 0)
        
        if keywords:
            main_keyword = keywords[0]
            
            # Różne templates
            templates = [
                f"{main_keyword.upper()} w Sejmie! 🔥",
                f"GORĄCA debata o {main_keyword}! 💥",
                f"Ta wymiana o {main_keyword}! 😱",
                f"{main_keyword} - moment prawdy! ⚡"
            ]
            
            # Wybierz na podstawie score
            idx = min(int(score * len(templates)), len(templates) - 1)
            return templates[idx]
        else:
            return "Gorący moment z Sejmu! 🔥"
    
    def _generate_short_description_fixed(self) -> str:
        """
        Stały opis dla wszystkich Shorts
        Zoptymalizowany pod YouTube Shorts
        """
        return """Najgorętsze momenty z Sejmu w skrócie! Emocje, konflikty i polityczne bomby. Subskrybuj 'Sejm na Pełnej' po więcej! 💥

#Sejm #Polityka #DebataSejmowa #Shorts #PolskaPolityka"""
    
    def _generate_short_tags(self, clip: Dict) -> List[str]:
        """Generuj tagi dla Short"""
        tags = [
            'Sejm',
            'Polska', 
            'Polityka',
            'Shorts',
            'PolskaPolityka',
            'DebataSejmowa',
            'Parlament'
        ]
        
        # Dodaj keywords z clipu
        keywords = clip.get('keywords', [])
        for kw in keywords[:3]:  # Max 3 dodatkowe
            if kw not in tags:
                tags.append(kw)
        
        return tags[:15]  # YouTube limit