"""
Stage 8: AI Thumbnail Generation
Generuje clickbaitową miniaturkę z napisami do YouTube
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import cv2
import numpy as np
from datetime import datetime


class ThumbnailStage:
    """
    Stage 8: Generowanie profesjonalnych, clickbaitowych miniaturek
    """
    
    def __init__(self, config):
        self.config = config

        # Wymiary YouTube thumbnail
        self.target_width = 1280
        self.target_height = 720

        # Style text
        self.text_styles = {
            'impact': {
                'font_path': 'C:/Windows/Fonts/impact.ttf',
                'fallback': 'Arial.ttf'
            },
            'arial_bold': {
                'font_path': 'C:/Windows/Fonts/arialbd.ttf',
                'fallback': 'Arial.ttf'
            }
        }

    def _translate(self, key: str) -> str:
        """Get translated text based on config language"""
        translations = {
            "part": {"pl": "Część", "en": "Part"},
        }
        language = getattr(self.config, 'language', 'pl')
        return translations.get(key, {}).get(language, key)
    
    def _extract_best_frame(
        self, 
        video_file: str, 
        timestamp: float,
        quality_check: bool = True
    ) -> Image.Image:
        """
        Wyciągnij najlepszą klatkę z video
        
        Args:
            video_file: Ścieżka do video
            timestamp: Timestamp w sekundach
            quality_check: Czy sprawdzić blur/jakość
        
        Returns:
            PIL Image
        """
        cap = cv2.VideoCapture(video_file)
        
        if not cap.isOpened():
            raise ValueError(f"Nie można otworzyć video: {video_file}")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Frame number dla timestamp
        target_frame = int(timestamp * fps)
        
        # Zabezpieczenie przed out of bounds
        target_frame = max(0, min(target_frame, total_frames - 1))
        
        if quality_check:
            # Sprawdź kilka klatek wokół target i wybierz najlepszą
            best_frame = None
            best_score = -1
            
            for offset in [-30, -15, 0, 15, 30]:  # ±1 sekunda
                frame_num = target_frame + offset
                if frame_num < 0 or frame_num >= total_frames:
                    continue
                
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
                ret, frame = cap.read()
                
                if not ret:
                    continue
                
                # Oceń jakość klatki (blur detection)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
                
                # Brightness check
                brightness = np.mean(gray)
                
                # Score: wyższa wartość = lepsza klatka
                score = laplacian_var * (1 - abs(brightness - 128) / 128)
                
                if score > best_score:
                    best_score = score
                    best_frame = frame
            
            cap.release()
            
            if best_frame is None:
                raise ValueError(f"Nie znaleziono dobrej klatki wokół {timestamp}s")
            
            frame = best_frame
        else:
            # Zwykłe wyciągnięcie bez quality check
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                raise ValueError(f"Nie można wyciągnąć klatki z {timestamp}s")
        
        # Convert BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(frame_rgb)
    
    def _enhance_image(self, image: Image.Image) -> Image.Image:
        """Popraw jakość obrazu dla miniaturki"""
        
        # Zwiększ kontrast
        contrast = ImageEnhance.Contrast(image)
        image = contrast.enhance(1.3)
        
        # Zwiększ saturację
        color = ImageEnhance.Color(image)
        image = color.enhance(1.2)
        
        # Lekkie wyostrzenie
        sharpness = ImageEnhance.Sharpness(image)
        image = sharpness.enhance(1.1)
        
        return image
    
    def _add_gradient_overlay(
        self, 
        image: Image.Image, 
        direction: str = 'bottom'
    ) -> Image.Image:
        """
        Dodaj gradient overlay dla lepszej czytelności tekstu
        
        Args:
            direction: 'top', 'bottom', or 'both'
        """
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        
        width, height = image.size
        
        if direction in ['bottom', 'both']:
            # Gradient od dołu
            for y in range(int(height * 0.6), height):
                alpha = int((y - height * 0.6) / (height * 0.4) * 140)
                draw.rectangle(
                    [(0, y), (width, y+1)],
                    fill=(0, 0, 0, alpha)
                )
        
        if direction in ['top', 'both']:
            # Gradient od góry
            for y in range(0, int(height * 0.4)):
                alpha = int((height * 0.4 - y) / (height * 0.4) * 100)
                draw.rectangle(
                    [(0, y), (width, y+1)],
                    fill=(0, 0, 0, alpha)
                )
        
        # Composite
        image = Image.alpha_composite(image.convert('RGBA'), overlay)
        return image.convert('RGB')
    
    def _load_font(
        self, 
        font_type: str, 
        size: int
    ) -> ImageFont.FreeTypeFont:
        """
        Załaduj font z fallback
        
        Args:
            font_type: 'impact' or 'arial_bold'
            size: Rozmiar fontu
        """
        style = self.text_styles.get(font_type, self.text_styles['arial_bold'])
        
        # Próbuj załadować główny font
        try:
            return ImageFont.truetype(style['font_path'], size)
        except:
            pass
        
        # Próbuj fallback
        try:
            fallback_path = f"C:/Windows/Fonts/{style['fallback']}"
            return ImageFont.truetype(fallback_path, size)
        except:
            pass
        
        # Ostateczny fallback - default font
        print(f"⚠️ Nie można załadować fontu {font_type}, używam domyślnego")
        return ImageFont.load_default()

    def _fallback_mid_timestamp(self, video_file: str) -> float:
        """Wylicz środkowy timestamp jako awaryjny wybór klatki."""
        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            return 0.0
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or fps * 60
        cap.release()
        duration = total_frames / max(fps, 1.0)
        return max(0.0, duration / 2)
    
    def _wrap_text(
        self, 
        text: str, 
        font: ImageFont.FreeTypeFont, 
        max_width: float
    ) -> list:
        """
        Podziel tekst na linie żeby zmieścił się w szerokości
        
        Returns:
            Lista linii tekstu
        """
        words = text.split()
        lines = []
        current_line = []
        
        dummy_draw = ImageDraw.Draw(Image.new('RGB', (1, 1)))
        
        for word in words:
            test_line = ' '.join(current_line + [word])
            bbox = dummy_draw.textbbox((0, 0), test_line, font=font)
            width = bbox[2] - bbox[0]
            
            if width <= max_width:
                current_line.append(word)
            else:
                if current_line:
                    lines.append(' '.join(current_line))
                current_line = [word]
        
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    def _draw_text_with_outline(
        self,
        draw: ImageDraw.ImageDraw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        text_color: Tuple[int, int, int],
        outline_color: Tuple[int, int, int] = (0, 0, 0),
        outline_width: int = 4
    ):
        """
        Rysuj tekst z outline dla lepszej czytelności
        """
        x, y = position
        
        # Rysuj outline
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text(
                        (x + adj_x, y + adj_y),
                        text,
                        font=font,
                        fill=outline_color
                    )
        
        # Rysuj główny tekst
        draw.text((x, y), text, font=font, fill=text_color)
    
    def _add_clickbait_text(
        self,
        image: Image.Image,
        top_text: str,
        bottom_text: Optional[str] = None,
        emoji: Optional[str] = "🔥",
        style: str = "auto"  # ← NOWE
    ) -> Image.Image:
        """
        Dodaj clickbaitowy tekst - różne style
        
        Args:
            style: 'center', 'top', 'bottom', 'split', 'auto'
        """
        # Enhance image
        image = self._enhance_image(image)
        
        # Wybierz losowy styl jeśli auto
        if style == "auto":
            import random
            styles = ['center', 'top_bottom', 'split']
            style = random.choice(styles)
        
        # Add gradient based on style
        if style in ['center', 'top_bottom']:
            image = self._add_gradient_overlay(image, direction='both')
        elif style == 'top':
            image = self._add_gradient_overlay(image, direction='top')
        else:
            image = self._add_gradient_overlay(image, direction='bottom')
        
        draw = ImageDraw.Draw(image)
        width, height = image.size
        
        # === STYLE 1: CENTER (jak teraz) ===
        if style == 'center':
            font_size_top = int(height * 0.12)
            font_top = self._load_font('impact', font_size_top)
            
            top_lines = self._wrap_text(top_text.upper(), font_top, width * 0.9)
            line_height = font_size_top + 10
            total_text_height = len(top_lines) * line_height
            y_offset = (height - total_text_height) // 2 - int(height * 0.05)
            
            for line in top_lines:
                bbox = draw.textbbox((0, 0), line, font=font_top)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                
                self._draw_text_with_outline(
                    draw, (x, y_offset), line, font_top,
                    text_color=(255, 255, 0),  # Żółty
                    outline_width=6
                )
                y_offset += line_height
        
        # === STYLE 2: TOP + BOTTOM ===
        elif style == 'top_bottom':
            # Split text na 2 części
            words = top_text.upper().split()
            mid = len(words) // 2
            top_part = ' '.join(words[:mid])
            bottom_part = ' '.join(words[mid:])
            
            font_size = int(height * 0.10)
            font = self._load_font('impact', font_size)
            
            # TOP
            bbox = draw.textbbox((0, 0), top_part, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = int(height * 0.15)
            
            self._draw_text_with_outline(
                draw, (x, y), top_part, font,
                text_color=(255, 255, 0),
                outline_width=5
            )
            
            # BOTTOM
            bbox = draw.textbbox((0, 0), bottom_part, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = int(height * 0.75)
            
            self._draw_text_with_outline(
                draw, (x, y), bottom_part, font,
                text_color=(255, 255, 0),
                outline_width=5
            )
        
        # === STYLE 3: SPLIT (2 kolory) ===
        elif style == 'split':
            font_size_top = int(height * 0.11)
            font_top = self._load_font('impact', font_size_top)
            
            top_lines = self._wrap_text(top_text.upper(), font_top, width * 0.9)
            line_height = font_size_top + 10
            total_text_height = len(top_lines) * line_height
            y_offset = (height - total_text_height) // 2
            
            colors = [(255, 255, 0), (255, 100, 0), (255, 50, 50)]  # Żółty, pomarańczowy, czerwony
            
            for i, line in enumerate(top_lines):
                bbox = draw.textbbox((0, 0), line, font=font_top)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2
                
                color = colors[i % len(colors)]
                
                self._draw_text_with_outline(
                    draw, (x, y_offset), line, font_top,
                    text_color=color,
                    outline_width=6
                )
                y_offset += line_height
        
        # === BOTTOM TEXT (data) - WIĘKSZA I BARDZIEJ WIDOCZNA ===
        if bottom_text:
            font_size_bottom = int(height * 0.08)  # Zwiększone z 0.06
            font_bottom = self._load_font('arial_bold', font_size_bottom)
            
            bbox = draw.textbbox((0, 0), bottom_text, font=font_bottom)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = int(height * 0.88)
            
            # Tło pod datą dla lepszej widoczności
            padding = 10
            bg_box = [
                (x - padding, y - 5),
                (x + text_width + padding, y + font_size_bottom + 5)
            ]
            draw.rectangle(bg_box, fill=(0, 0, 0, 200))
            
            self._draw_text_with_outline(
                draw, (x, y), bottom_text, font_bottom,
                text_color=(255, 200, 0),  # Pomarańczowo-żółty zamiast białego
                outline_width=3
            )
        
        # === EMOJI - różne pozycje ===
        if emoji:
            try:
                emoji_size = int(height * 0.10)
                emoji_font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", emoji_size)
                
                # Losowa pozycja emoji
                import random
                positions = [
                    (int(width * 0.04), int(height * 0.04)),  # Top-left
                    (int(width * 0.90), int(height * 0.04)),  # Top-right
                ]
                pos = random.choice(positions)
                
                draw.text(pos, emoji, font=emoji_font, fill=(255, 255, 255))
            except:
                pass
        
        return image
    
    def _generate_title_from_clip(self, clip: Dict) -> str:
        """
        Generuj clickbaitowy tytuł z danych klipu
        """
        keywords = clip.get('keywords', [])
        
        if not keywords:
            return "GORĄCE MOMENTY!"
        
        # Różne templates
        templates = [
            f"{keywords[0].upper()} EKSPLODUJE!",
            f"SEJM: {keywords[0].upper()}!",
            f"{keywords[0].upper()} - MUSISZ TO ZOBACZYĆ!",
            f"🔥 {keywords[0].upper()} 🔥",
        ]
        
        # Wybierz najkrótszy (żeby się zmieścił)
        templates.sort(key=len)
        
        for template in templates:
            if len(template) <= 30:  # Max długość
                return template
        
        return templates[0][:30]
    
    def generate_with_part_number(
        self,
        video_file: str,
        part_number: int,
        total_parts: int,
        clips: Optional[list] = None,
        output_dir: Optional[Path] = None,
        custom_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Generuj miniaturkę z numerem części

        Args:
            video_file: Ścieżka do source video
            clips: Lista klipów z tej części (używamy najlepszego dla thumbnail)
            output_dir: Katalog wyjściowy
            part_number: Numer części (1, 2, 3...)
            total_parts: Całkowita liczba części
            custom_title: Opcjonalny custom tytuł

        Returns:
            Dict z wynikami
        """
        print(f"\n🎨 Generuję miniaturkę dla części {part_number}/{total_parts}...")

        # Validation and logging
        if clips is None or len(clips) == 0:
            print(f"   ⚠️ Brak klipów dla części {part_number} - używam środkowej klatki z video")
            clips = []
        else:
            # Log clips info
            print(f"   📊 Dostępne klipy: {len(clips)}")
            # Find best clip for logging
            if clips:
                best_clip = max(clips, key=lambda c: c.get('final_score', c.get('score', 0)))
                clip_score = best_clip.get('final_score', best_clip.get('score', 0))
                clip_id = best_clip.get('id', 'unknown')
                clip_t0 = best_clip.get('t0', 0)
                print(f"   🎯 Using top clip for thumbnail: clip_id={clip_id}, score={clip_score:.2f}, timestamp={clip_t0:.1f}s")

        # Jeśli output_dir nie podane, użyj domyślnego
        if output_dir is None:
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)

        # Dodaj numer części do bottom text (language-aware)
        part_word = self._translate("part")
        bottom_text = f"📺 {part_word} {part_number}/{total_parts} | {datetime.now().strftime('%d.%m.%Y')}"

        # Wywołaj normalny process() z custom bottom text
        result = self.process(
            video_file=video_file,
            clips=clips,
            output_dir=output_dir,
            custom_title=custom_title,
            custom_bottom_text=bottom_text
        )
        
        # Zmień nazwę pliku aby zawierała numer części
        if result['success'] and result['thumbnail_path']:
            old_path = Path(result['thumbnail_path'])
            new_filename = f"thumbnail_part{part_number}.jpg"
            new_path = old_path.parent / new_filename

            # Przenieś plik
            if old_path.exists():
                if new_path.exists():
                    new_path.unlink()
                try:
                    os.replace(old_path, new_path)
                except OSError:
                    # Windows potrafi blokować rename gdy plik istnieje – usuń i spróbuj ponownie
                    if new_path.exists():
                        new_path.unlink()
                    os.replace(old_path, new_path)
                result['thumbnail_path'] = str(new_path)
                print(f"   ✅ Miniaturka części {part_number}: {new_path.name}")
        
        return result
    
    def process(
        self,
        video_file: str,
        clips: list,
        output_dir: Path,
        custom_title: Optional[str] = None,
        custom_bottom_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Główna metoda - generuj miniaturkę
        
        Args:
            video_file: Ścieżka do source video
            clips: Lista klipów z selection stage
            output_dir: Katalog wyjściowy
            custom_title: Opcjonalny custom tytuł
            custom_bottom_text: Opcjonalny custom tekst dolny
        
        Returns:
            Dict z wynikami
        """
        print("\n" + "="*60)
        print("STAGE 8: AI Thumbnail Generation")
        print("="*60)

        try:
            # Wybierz timestamp dla thumbnail
            if not clips:
                # Fallback: użyj środkowej klatki video gdy brak klipów
                print(f"   ⚠️ Brak klipów - używam środkowej klatki z video")
                # Extract video duration using ffprobe
                import subprocess
                try:
                    cmd = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                           '-of', 'default=noprint_wrappers=1:nokey=1', video_file]
                    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                    video_duration = float(result.stdout.strip())
                    mid_timestamp = video_duration / 2
                    best_clip = None
                    print(f"   📹 Video duration: {video_duration:.1f}s, using middle frame at {mid_timestamp:.1f}s")
                except Exception as e:
                    print(f"   ⚠️ Could not determine video duration: {e}, using timestamp 30s")
                    mid_timestamp = 30.0  # Default fallback
                    best_clip = None
            else:
                # Normal path: use best clip
                best_clip = max(clips, key=lambda c: c.get('final_score', c.get('score', 0)))

                # Timestamp środka najlepszego klipu
                mid_timestamp = (best_clip['t0'] + best_clip['t1']) / 2

                clip_score = best_clip.get('final_score', best_clip.get('score', 0))
                print(f"📸 Wybieram klatkę z najlepszego klipu:")
                print(f"   Timestamp: {mid_timestamp:.1f}s")
                print(f"   Score: {clip_score:.2f}")
                print(f"   Clip ID: {best_clip.get('id', 'unknown')}")
            
            # Extract best frame
            frame = self._extract_best_frame(
                video_file, 
                mid_timestamp,
                quality_check=True
            )
            
            print(f"✅ Wyciągnięto klatkę: {frame.size[0]}x{frame.size[1]}")
            
            # Resize to YouTube size
            frame = frame.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS
            )
            
            # Generate text
            if custom_title:
                top_text = custom_title
            elif best_clip:
                top_text = self._generate_title_from_clip(best_clip)
            else:
                # Fallback when no clips available
                top_text = "Highlights"
            
            if custom_bottom_text:
                bottom_text = custom_bottom_text
            else:
                bottom_text = f"📅 {datetime.now().strftime('%d.%m.%Y')}"
            
            print(f"✍️ Dodaję napisy:")
            print(f"   Górny: '{top_text}'")
            print(f"   Dolny: '{bottom_text}'")
            
            # Add text overlay
            thumbnail = self._add_clickbait_text(
                frame,
                top_text,
                bottom_text,
                emoji="🔥"
            )
            
            # Final sharpening
            thumbnail = thumbnail.filter(ImageFilter.SHARPEN)
            
            # Save
            thumbnail_filename = "thumbnail.jpg"
            thumbnail_path = output_dir / thumbnail_filename
            if thumbnail_path.exists():
                thumbnail_path.unlink()
            thumbnail.save(thumbnail_path, 'JPEG', quality=95, optimize=True)
            
            print(f"💾 Miniaturka zapisana: {thumbnail_path}")
            print(f"   Rozmiar: {thumbnail_path.stat().st_size / 1024:.1f} KB")
            
            return {
                'success': True,
                'thumbnail_path': str(thumbnail_path),
                'source_timestamp': mid_timestamp,
                'source_clip_id': best_clip.get('id') if best_clip else None,
                'text': top_text,
                'dimensions': f"{self.target_width}x{self.target_height}"
            }
            
        except Exception as e:
            print(f"❌ Błąd generowania miniaturki: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(e),
                'thumbnail_path': None
            }


# === Test standalone ===
if __name__ == "__main__":
    from pathlib import Path
    
    # Test dummy config
    class DummyConfig:
        pass
    
    config = DummyConfig()
    stage = ThumbnailStage(config)
    
    # Test data
    test_clips = [
        {
            'id': 1,
            't0': 100.0,
            't1': 150.0,
            'score': 0.85,
            'keywords': ['Tusk', 'Kaczyński', 'debata']
        }
    ]
    
    result = stage.process(
        video_file="test_video.mp4",  # Podaj swoją ścieżkę
        clips=test_clips,
        output_dir=Path("output"),
        custom_title="SEJM EKSPLODUJE!"
    )
    
    print(f"\n✅ Test zakończony: {result}")