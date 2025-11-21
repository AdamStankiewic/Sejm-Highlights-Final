"""
Stage 10: YouTube Shorts Generator (ENHANCED v2.0)
- Format pionowy 9:16 (1080x1920)
- Żółte napisy z safe zones
- AI-generowane viralne tytuły
- INTRO OVERLAY: Ultra-clickable first frame z GPT titles
- Stały opis zoptymalizowany pod Shorts
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import os
import random

# PIL dla intro overlay
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ PIL nie zainstalowany - intro overlay wyłączony")

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
        
        # STEP 1: Generuj ASS napisy (żółte, safe zone)
        self._generate_shorts_subtitles(clip, segments, t0, t1, ass_file)
        
        # STEP 2: Renderuj video z napisami
        # Filter complex:
        # 1. Scale + crop do 9:16
        # 2. Dodaj napisy z ASS (żółte, centered, safe zone)
        # Output: [vout] = video z napisami
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"ass='{str(ass_file).replace('\\', '/')}' [vout]"
        )

        cmd = [
            'ffmpeg',
            '-ss', str(t0),
            '-to', str(t1),
            '-i', str(input_file),
            '-filter_complex', filter_complex,
            '-map', '[vout]',  # ✅ Video z filtra (z napisami!)
            '-map', '0:a',     # ✅ Audio z oryginału
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

        # Generate AI title and metadata
        title = self._generate_ai_short_title(clip, segments)
        description = self._generate_short_description_fixed()

        # === INTRO TITLE SYSTEM (drawtext zamiast PNG overlay) ===
        intro_enabled = getattr(self.config.shorts.intro, 'enabled', False)

        if intro_enabled:
            print(f"      📝 Napisy ASS: {ass_file.name}")
            try:
                # Generuj clickbait dwu-liniowy title (FAZA 1!)
                line1, line2, emoji_list = self._generate_ultra_short_title_gpt(clip, segments)

                # Dodaj FAZA 1 overlay: 2 linie + emoji + ramka (pierwsze 3 sekundy)
                success = self._add_intro_drawtext_to_video(
                    output_file,
                    line1,
                    line2,
                    emoji_list,
                    output_dir,
                    index
                )

                if success:
                    print(f"      ✅ FAZA 1 intro dodany! (2 linie tekstu + czerwona ramka)")
                else:
                    print(f"      ⚠️ Intro failed, Short bez intro")

            except Exception as e:
                print(f"      ⚠️ Intro error: {e}")
                # Video bez intro nadal działa
        else:
            print(f"      📝 Napisy ASS: {ass_file.name}")

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
        ass_file: Path
    ):
        """
        Generuj napisy w formacie ASS dla Shorts
        
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
            self._generate_simple_subtitle(clip, ass_file, clip_start, clip_end)
            return
        
        # ASS Header - optymalizowany dla Shorts (9:16)
        # Ustawienia napisów:
        # - Fontsize: 68px (duży, łatwy do czytania)
        # - MarginL/R: 30px (szersze napisy)
        # - MarginV: 600px (niżej, ale w safe zone)
        ass_content = f"""[Script Info]
Title: YouTube Short Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,68,&H00FFFF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,30,30,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
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
        clip_end: float
    ):
        """Fallback - prosty napis gdy brak transkrypcji"""
        
        duration = clip_end - clip_start
        text = clip.get('title', 'Gorący moment z Sejmu! 🔥')
        
        ass_content = f"""[Script Info]
Title: YouTube Short Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,68,&H00FFFF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,3,2,30,30,600,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{self._format_ass_time(0)},{self._format_ass_time(duration)},Default,,0,0,0,,{text}
"""
        
        with open(ass_file, 'w', encoding='utf-8') as f:
            f.write(ass_content)
    
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

    # ==========================================
    # INTRO OVERLAY SYSTEM (v2.0)
    # ==========================================

    def _generate_ultra_short_title_gpt(self, clip: Dict, segments: List[Dict]) -> Tuple[str, str, List[str]]:
        """
        Generuj dwu-liniowy clickbait title dla Shorts miniaturki (FAZA 1 upgrade!)

        Returns:
            (line1_hook, line2_subtext, [emoji1, emoji2, emoji3, emoji4])
        """
        if not self.gpt_client or not getattr(self.config.shorts.intro, 'use_gpt_titles', True):
            return self._generate_ultra_short_fallback(clip)

        # Context
        segment = None
        for seg in segments:
            if abs(seg['t0'] - clip['t0']) < 1.0:
                segment = seg
                break

        transcript = segment.get('transcript', '')[:200] if segment else ''
        keywords = ', '.join(clip.get('keywords', [])[:3])

        prompt = f"""Wygeneruj DWU-LINIOWY clickbait title dla YouTube Shorts miniaturki (polska polityka):

KONTEKST:
- Fragment: "{transcript}"
- Keywords: {keywords}
- To jest MINIATURKA Shorts (pierwsza klatka) - musi być ULTRA clickbait jak Onet/WP!

WYMAGANIA:
- 2 LINIE tekstu
- LINE 1 (hook): 3-7 słów, ALL CAPS, krzykliwy (jak nagłówki Onetu)
- LINE 2 (subtext): 2-5 słów, doprecyzowanie

PRZYKŁADY (IDEALNE dla polskiej polityki):
Line 1: "KŁAMSTWO STULECIA W SEJMIE!"
Line 2: "Tusk w szoku"

Line 1: "POSEŁ OSZALAŁ!"
Line 2: "Nikt tego nie widział"

Line 1: "TO KONIEC PIS-u?!"
Line 2: "Kaczyński milczy"

Line 1: "AWANTURA! BIJATYKA!"
Line 2: "Zamknęli Sejm"

EMOJI: Daj 4 emoji (polityczne shock value)
Najlepsze: 🔥😱💥🚨⚡🤯💀👀

Format JSON:
{{
  "line1": "SZOK W SEJMIE!",
  "line2": "Posłowie oszaleli",
  "emoji": ["🔥", "😱", "💥", "🚨"]
}}"""

        try:
            response = self.gpt_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od clickbaitowych miniaturek YouTube w polskiej niszy politycznej. Znasz styl Onetu, WP, Super Expressu."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=getattr(self.config.shorts.intro, 'gpt_temperature', 0.9),
                max_tokens=100
            )

            result = json.loads(response.choices[0].message.content)
            line1 = result.get('line1', 'SZOK W SEJMIE!').strip().upper()
            line2 = result.get('line2', 'Posłowie oszaleli').strip()
            emoji = result.get('emoji', ['🔥', '😱', '💥', '🚨'])

            print(f"      🎨 GPT Clickbait:")
            print(f"         Line 1: '{line1}'")
            print(f"         Line 2: '{line2}'")
            print(f"         Emoji: {emoji[:4]}")

            return line1, line2, emoji[:4]  # Max 4 emoji dla 4 rogów

        except Exception as e:
            print(f"      ⚠️ GPT clickbait error: {e}")
            return self._generate_ultra_short_fallback(clip)

    def _generate_ultra_short_fallback(self, clip: Dict) -> Tuple[str, str, List[str]]:
        """Fallback dwu-liniowy title"""
        keywords = clip.get('keywords', [])

        templates = [
            ("SZOK W SEJMIE!", "Posłowie oszaleli", ['🔥', '😱', '💥', '🚨']),
            ("AWANTURA!", "Nikt tego nie widział", ['😱', '🤯', '💥', '🔥']),
            ("TO KONIEC?!", "Politycy w szoku", ['💥', '😱', '⚡', '🚨']),
            ("SKANDAL!", "Zamknęli Sejm", ['🚨', '😱', '🔥', '💀']),
        ]

        if keywords:
            kw = keywords[0].upper()[:15]
            return (f"{kw}!", "Zobacz co się stało", ['🔥', '😱', '💥', '⚡'])

        # Random z templates
        return random.choice(templates)

    def _create_intro_overlay_image(
        self,
        title: str,
        emoji_list: List[str],
        output_path: Path
    ) -> bool:
        """
        Stwórz PNG overlay z tytułem i emoji (transparent background)

        Layout (1080x1920):
        ┌─────────────────────┐
        │        🔥💥         │  ← Top emoji (y=200)
        │                     │
        │                     │
        │                     │
        │   (transparent)     │  ← Middle: przezroczysty (video widoczny)
        │                     │
        │                     │
        │     SZOK! 😱        │  ← Bottom title (y=1600)
        └─────────────────────┘
        """
        if not PIL_AVAILABLE:
            print("      ⚠️ PIL niedostępny, pomijam intro overlay")
            return False

        try:
            width = self.config.shorts.width
            height = self.config.shorts.height

            # Create transparent image
            overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Config
            intro_config = self.config.shorts.intro

            # === TOP EMOJI ===
            if getattr(intro_config.text.emoji_top, 'enabled', True) and emoji_list:
                try:
                    emoji_size = getattr(intro_config.text.emoji_top, 'size', 140)
                    emoji_y = getattr(intro_config.text.emoji_top, 'position_y', 200)
                    emoji_font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", emoji_size)

                    # Center emoji(s)
                    emoji_text = ' '.join(emoji_list[:2])  # Max 2
                    bbox = draw.textbbox((0, 0), emoji_text, font=emoji_font)
                    emoji_width = bbox[2] - bbox[0]
                    emoji_x = (width - emoji_width) // 2

                    draw.text((emoji_x, emoji_y), emoji_text, font=emoji_font, fill=(255, 255, 255, 255))
                except Exception as e:
                    print(f"      ⚠️ Emoji error: {e}")

            # === BOTTOM TITLE ===
            try:
                title_y = getattr(intro_config.text.title_bottom, 'position_y', 1600)
                title_size = getattr(intro_config.text.title_bottom, 'font_size', 90)
                title_font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", title_size)

                # Colors
                text_color = getattr(intro_config.colors, 'text', '#FFFF00')
                outline_color = getattr(intro_config.colors, 'outline', '#000000')
                outline_width = getattr(intro_config.colors, 'outline_width', 10)

                # Parse colors
                if text_color.startswith('#'):
                    r, g, b = int(text_color[1:3], 16), int(text_color[3:5], 16), int(text_color[5:7], 16)
                    text_color_rgb = (r, g, b, 255)
                else:
                    text_color_rgb = (255, 255, 0, 255)

                if outline_color.startswith('#'):
                    r, g, b = int(outline_color[1:3], 16), int(outline_color[3:5], 16), int(outline_color[5:7], 16)
                    outline_color_rgb = (r, g, b, 255)
                else:
                    outline_color_rgb = (0, 0, 0, 255)

                # Center title
                bbox = draw.textbbox((0, 0), title, font=title_font)
                title_width = bbox[2] - bbox[0]
                title_x = (width - title_width) // 2

                # Draw outline
                for adj_x in range(-outline_width, outline_width + 1):
                    for adj_y in range(-outline_width, outline_width + 1):
                        if adj_x != 0 or adj_y != 0:
                            draw.text((title_x + adj_x, title_y + adj_y), title, font=title_font, fill=outline_color_rgb)

                # Draw text
                draw.text((title_x, title_y), title, font=title_font, fill=text_color_rgb)

            except Exception as e:
                print(f"      ⚠️ Title text error: {e}")
                return False

            # Save overlay
            overlay.save(output_path, 'PNG')
            print(f"      💾 Overlay PNG: {output_path.name}")
            return True

        except Exception as e:
            print(f"      ❌ Overlay creation error: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _add_intro_drawtext_to_video(
        self,
        video_file: Path,
        line1: str,
        line2: str,
        emoji_list: List[str],
        output_dir: Path,
        index: int
    ) -> bool:
        """
        FAZA 1: Dodaj clickbait intro (pierwsze 3s) - PROSTY i DZIAŁAJĄCY!

        Layout (9:16, 1080x1920):
        ┌─────────────────────┐
        │                     │
        │                     │
        │  SZOK W SEJMIE!     │  ← Line 1 (duży, żółty, 140px)
        │                     │
        │  Posłowie oszaleli  │  ← Line 2 (mniejszy, biały, 80px)
        │                     │
        │                     │
        └─────────────────────┘
        └───── Czerwona ─────┘  ← Czerwona ramka (10px)

        enable='between(t,0,3)' - wszystko widoczne tylko pierwsze 3s
        Pierwsza klatka (t=0) = pełny clickbait = IDEALNA miniaturka! ✅
        """
        temp_video = None
        try:
            # Escape text dla ffmpeg (polskie znaki wymagają text_shaping!)
            safe_line1 = line1.replace("'", "'\\''").replace(":", "\\:").replace("ł", "l").replace("ą", "a").replace("ę", "e").replace("ć", "c").replace("ź", "z").replace("ż", "z").replace("ń", "n").replace("ó", "o").replace("ś", "s")
            safe_line2 = line2.replace("'", "'\\''").replace(":", "\\:").replace("ł", "l").replace("ą", "a").replace("ę", "e").replace("ć", "c").replace("ź", "z").replace("ż", "z").replace("ń", "n").replace("ó", "o").replace("ś", "s")

            # ffmpeg complex filter chain (UPROSZCZONY - najpierw sprawdźmy czy działa):
            # TYLKO Line 1 + czerwona ramka (bez Line 2 na razie)
            filter_complex = (
                # Czerwona ramka (10px thick)
                f"drawbox=x=10:y=10:w=iw-20:h=ih-20:color=red:t=10:enable='between(t,0,3)',"

                # Line 1 - DUŻY hook (środek, Arial dla lepszego UTF-8)
                f"drawtext="
                f"text='{safe_line1}':"
                f"fontfile=C\\:/Windows/Fonts/arial.ttf:"
                f"fontsize=140:"
                f"fontcolor=yellow:"
                f"borderw=10:"
                f"bordercolor=black:"
                f"x=(w-text_w)/2:"
                f"y=(h-text_h)/2:"
                f"enable='between(t,0,3)'"
            )

            print(f"      🔧 DEBUG filter: {filter_complex[:200]}...")

            # Temp files
            temp_video = output_dir / f"short_{index:02d}_temp.mp4"
            video_file.rename(temp_video)

            cmd = [
                'ffmpeg',
                '-i', str(temp_video),
                '-vf', filter_complex,
                '-c:a', 'copy',  # Copy audio (szybsze)
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-y',
                str(video_file)
            ]

            print(f"      🔧 FAZA 1 filter: 2 linie tekstu + czerwona ramka")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding='utf-8'
            )

            # Cleanup temp
            temp_video.unlink()

            return True

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            # Pokaż TYLKO faktyczny błąd (ostatnie linie stderr zawierają prawdziwy error)
            if error_msg:
                lines = error_msg.split('\n')
                # Ostatnie 5 linii zwykle zawierają error
                relevant_lines = [l.strip() for l in lines[-5:] if l.strip()]
                print(f"      ❌ ffmpeg error:")
                for line in relevant_lines:
                    print(f"         {line}")
            # Restore original if failed
            if temp_video and temp_video.exists():
                temp_video.rename(video_file)
            return False
        except Exception as e:
            print(f"      ❌ FAZA 1 error: {e}")
            # Restore original if failed
            if temp_video and temp_video.exists():
                temp_video.rename(video_file)
            return False

    def _add_intro_overlay_to_video_OLD(
        self,
        input_video: Path,
        overlay_png: Path,
        output_video: Path
    ) -> bool:
        """
        Dodaj intro overlay do video z fade in/out

        ffmpeg overlay z fade:
        - 0.0-0.3s: Fade in
        - 0.3-2.5s: Full visible
        - 2.5-3.0s: Fade out
        """
        try:
            intro_config = self.config.shorts.intro
            duration = getattr(intro_config, 'duration', 2.5)
            fade_in = getattr(intro_config, 'fade_in', 0.3)
            fade_out = getattr(intro_config, 'fade_out', 0.5)

            fade_out_start = duration - fade_out

            # ffmpeg filter: overlay z fade (alpha channel aware)
            # fade=t=in:st=0:d=0.3:alpha=1 - fade in alpha channel
            # fade=t=out:st=2.0:d=0.5:alpha=1 - fade out alpha channel
            filter_complex = (
                f"[1:v]fade=t=in:st=0:d={fade_in}:alpha=1,"
                f"fade=t=out:st={fade_out_start}:d={fade_out}:alpha=1[ovr];"
                f"[0:v][ovr]overlay=0:0:format=auto:shortest=1"
            )

            cmd = [
                'ffmpeg',
                '-i', str(input_video),
                '-i', str(overlay_png),
                '-filter_complex', filter_complex,
                '-c:a', 'copy',
                '-c:v', 'libx264',
                '-preset', 'medium',
                '-crf', '23',
                '-y',
                str(output_video)
            ]

            print(f"      🔧 ffmpeg overlay command:")
            print(f"         Filter: {filter_complex}")

            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
                encoding='utf-8'
            )

            # Check output for warnings
            if result.stderr and 'error' in result.stderr.lower():
                print(f"      ⚠️  ffmpeg warnings: {result.stderr[:300]}")
            else:
                print(f"      ✓ ffmpeg overlay successful")

            return True

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            print(f"      ❌ Overlay ffmpeg error: {error_msg[:500]}")
            return False
        except Exception as e:
            print(f"      ❌ Overlay error: {e}")
            return False