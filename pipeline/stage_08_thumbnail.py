"""
Stage 8: AI Thumbnail Generation v2.0
- GPT-powered clickbait titles (3 variants)
- Face detection z OpenCV (priorytet twarzy)
- Multi-variant generation (aggressive/question/viral)
- Mobile readability test
- Ultra-optimized dla wysokiego CTR
"""

from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import cv2
import numpy as np
from datetime import datetime
import json
import os
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

load_dotenv()


class ThumbnailStage:
    """
    Stage 8: Ultra-Clickable Thumbnail Generation

    Features:
    - GPT-4o-mini dla clickbaitowych tytułów
    - Face detection (OpenCV) - twarze = 2x CTR
    - Multi-variant (3 style templates)
    - Mobile optimization & testing
    - Metadata tracking dla A/B testing
    """

    def __init__(self, config):
        self.config = config

        # Wymiary
        self.target_width = getattr(config.thumbnails, 'width', 1920)
        self.target_height = getattr(config.thumbnails, 'height', 1080)

        # GPT Client
        self.openai_client = None
        if getattr(config.thumbnails, 'use_gpt_titles', True):
            self._init_gpt()

        # Face detection
        self.face_cascade = None
        self._init_face_detection()

        # Fonts
        self.font_paths = self._get_font_paths()

    def _init_gpt(self):
        """Inicjalizuj GPT dla tytułów"""
        if OpenAI is None:
            print("⚠️ openai nie zainstalowany, pomijam GPT titles")
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("⚠️ OPENAI_API_KEY nie znaleziony, pomijam GPT titles")
            return

        try:
            self.openai_client = OpenAI(api_key=api_key)
            print("✓ GPT-4o-mini gotowy do generowania tytułów")
        except Exception as e:
            print(f"⚠️ Błąd GPT init: {e}")

    def _init_face_detection(self):
        """Inicjalizuj OpenCV face detection"""
        try:
            cascade_path = cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
            self.face_cascade = cv2.CascadeClassifier(cascade_path)

            if self.face_cascade.empty():
                print("⚠️ Nie można załadować Haar Cascade, face detection wyłączony")
                self.face_cascade = None
            else:
                print("✓ Face detection (OpenCV) gotowy")
        except Exception as e:
            print(f"⚠️ Face detection error: {e}")
            self.face_cascade = None

    def _get_font_paths(self):
        """Pobierz ścieżki do fontów"""
        return {
            'impact': {
                'path': 'C:/Windows/Fonts/impact.ttf',
                'fallback': 'C:/Windows/Fonts/arialbd.ttf'
            },
            'arial_bold': {
                'path': 'C:/Windows/Fonts/arialbd.ttf',
                'fallback': 'arial.ttf'
            }
        }

    def _generate_clickbait_titles_gpt(
        self,
        clip: Dict,
        num_variants: int = 3
    ) -> Dict[str, str]:
        """
        Użyj GPT do wygenerowania ultra-kliknych tytułów

        Returns:
            Dict z 3 wariantami: {aggressive, question, mysterious}
        """
        if not self.openai_client:
            # Fallback - proste tytuły
            return self._generate_simple_titles(clip)

        keywords = clip.get('keywords', [])[:5]
        transcript_preview = clip.get('transcript_preview', '')[:200]
        score = clip.get('final_score', 0)

        # Wykryj kontekst
        event_type = self._detect_event_type(keywords)
        politicians = self._extract_politicians(keywords, transcript_preview)

        prompt = f"""Wygeneruj 3 ultra-klikalne tytuły dla miniaturki YouTube (polskie wydarzenie polityczne):

KONTEKST:
- Typ: {event_type}
- Politycy: {', '.join(politicians) if politicians else 'nieznani'}
- Keywords: {', '.join(keywords)}
- Fragment: "{transcript_preview}"
- Score interesantości: {score:.2f}/1.0

WYMAGANIA:
- Max 25 znaków (WŁĄCZNIE z emoji!)
- 3 różne style (patrz niżej)
- POLSKIE trigger words: SKANDAL, SZOK, PRAWDA, NIE UWIERZYSZ, UJAWNIŁ, AFERA
- Konkretne imiona jeśli są (TUSK, KACZYŃSKI, HOŁOWNIA)
- ALL CAPS dla kluczowych słów
- 1-2 emoji per tytuł

STYLE:
1. AGGRESSIVE: Maksymalny clickbait, emocje, wykrzykniki
   Przykład: "TUSK ATAKUJE! 💥😱"

2. QUESTION: Prowokacyjne pytanie, ciekawość
   Przykład: "Czy Sejm oszalał?! 🤔"

3. MYSTERIOUS: Suspens, tajemnica, "musisz zobaczyć"
   Przykład: "To ZMIENI WSZYSTKO... 🔥"

WAŻNE:
- Krótko i czytelnie (mobile!)
- Emocje > fakty
- Konflikt > zgoda
- Konkret > abstrakcja

Format JSON:
{{
  "aggressive": "...",
  "question": "...",
  "mysterious": "..."
}}"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Jesteś ekspertem od viralowych tytułów YouTube dla polskiego contentu politycznego. Twoje tytuły generują miliony wyświetleń."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=getattr(self.config.thumbnails, 'gpt_temperature', 0.8),
                max_tokens=200
            )

            result = json.loads(response.choices[0].message.content)

            # Validacja długości
            max_len = getattr(self.config.thumbnails, 'max_title_length', 25)
            for key in result:
                if len(result[key]) > max_len:
                    result[key] = result[key][:max_len-3] + "..."

            print(f"✓ GPT wygenerował tytuły: {list(result.values())}")
            return result

        except Exception as e:
            print(f"⚠️ GPT titles error: {e}, używam fallback")
            return self._generate_simple_titles(clip)

    def _generate_simple_titles(self, clip: Dict) -> Dict[str, str]:
        """Fallback titles bez GPT"""
        keywords = clip.get('keywords', [])

        if not keywords:
            return {
                'aggressive': "GORĄCE MOMENTY! 🔥",
                'question': "CO SIĘ STAŁO?! 😱",
                'mysterious': "MUSISZ TO ZOBACZYĆ..."
            }

        kw = keywords[0].upper()
        return {
            'aggressive': f"{kw} EKSPLODUJE! 💥",
            'question': f"Co z {kw}?! 🤔",
            'mysterious': f"{kw} - PRAWDA... 🔥"
        }

    def _detect_event_type(self, keywords: List[str]) -> str:
        """Wykryj typ wydarzenia z keywords"""
        keywords_lower = [k.lower() for k in keywords]

        if any(k in keywords_lower for k in ['konferencja', 'briefing']):
            return 'konferencja prasowa'
        elif any(k in keywords_lower for k in ['debata', 'polemika', 'kłótnia']):
            return 'debata'
        elif any(k in keywords_lower for k in ['wywiad', 'rozmowa']):
            return 'wywiad'
        elif any(k in keywords_lower for k in ['skandal', 'afera']):
            return 'skandal'
        else:
            return 'wydarzenie sejmowe'

    def _extract_politicians(self, keywords: List[str], transcript: str) -> List[str]:
        """Wyciągnij nazwiska polityków"""
        known_politicians = [
            'Tusk', 'Kaczyński', 'Hołownia', 'Duda', 'Trzaskowski',
            'Morawiecki', 'Bosak', 'Kosiniak-Kamysz', 'Czarnek', 'Ziobro'
        ]

        found = []
        text = ' '.join(keywords) + ' ' + transcript

        for pol in known_politicians:
            if pol.lower() in text.lower():
                found.append(pol.upper())

        return found[:2]  # Max 2 dla czytelności

    def _select_best_frame_with_faces(
        self,
        video_file: str,
        clip: Dict
    ) -> Tuple[Image.Image, Dict]:
        """
        Wybierz najlepszą klatkę z priorytetem na twarze

        Returns:
            (best_frame_pil, metadata)
        """
        t0 = clip.get('t0', 0)
        t1 = clip.get('t1', 0)

        strategy = getattr(self.config.thumbnails.frame_selection, 'strategy', 'face_priority')
        sample_frames = getattr(self.config.thumbnails.frame_selection, 'sample_frames', 20)

        cap = cv2.VideoCapture(video_file)
        if not cap.isOpened():
            raise ValueError(f"Nie można otworzyć video: {video_file}")

        fps = cap.get(cv2.CAP_PROP_FPS)

        frames_data = []

        # Sample frames z klipu
        for t in np.linspace(t0, t1, sample_frames):
            frame_num = int(t * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
            ret, frame = cap.read()

            if not ret:
                continue

            # Multi-criteria scoring
            face_score = 0
            composition_score = 0

            # Face detection
            if self.face_cascade is not None and strategy in ['face_priority', 'multi_criteria']:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = self.face_cascade.detectMultiScale(gray, 1.3, 5)

                if len(faces) > 0:
                    # Face size score (bigger = better)
                    face_areas = [w * h for (x, y, w, h) in faces]
                    face_score = max(face_areas) / (frame.shape[0] * frame.shape[1])

                    # Composition check (face in upper third?)
                    for (x, y, w, h) in faces:
                        face_center_y = y + h/2
                        if face_center_y < frame.shape[0] * 0.4:  # Upper 40%
                            composition_score += 0.5

            # Blur detection
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blur_score = cv2.Laplacian(gray, cv2.CV_64F).var()

            # Brightness
            brightness = np.mean(gray)
            brightness_score = 1 - abs(brightness - 128) / 128

            # Total weighted score
            if strategy == 'face_priority':
                total_score = (
                    face_score * 0.60 +  # NAJWAŻNIEJSZE!
                    blur_score * 0.00001 +  # Normalized
                    brightness_score * 0.20 +
                    composition_score * 0.20
                )
            elif strategy == 'best_score':
                total_score = clip.get('final_score', 0)
            else:  # multi_criteria
                total_score = (
                    face_score * 0.40 +
                    blur_score * 0.00001 +
                    brightness_score * 0.30 +
                    composition_score * 0.30
                )

            frames_data.append({
                't': t,
                'frame': frame,
                'score': total_score,
                'face_score': face_score,
                'blur_score': blur_score,
                'faces_detected': len(faces) if 'faces' in locals() else 0
            })

        cap.release()

        if not frames_data:
            raise ValueError("Nie znaleziono żadnych klatek")

        # Wybierz najlepszą
        best = max(frames_data, key=lambda x: x['score'])

        # Convert to PIL
        frame_rgb = cv2.cvtColor(best['frame'], cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        metadata = {
            'timestamp': best['t'],
            'face_score': best['face_score'],
            'faces_detected': best['faces_detected'],
            'blur_score': best['blur_score'],
            'total_score': best['score']
        }

        print(f"   🎯 Wybrano klatkę: t={best['t']:.1f}s, twarzy={best['faces_detected']}, score={best['score']:.3f}")

        return pil_image, metadata

    def _enhance_image(self, image: Image.Image) -> Image.Image:
        """Popraw jakość obrazu"""
        contrast = getattr(self.config.thumbnails.enhancements, 'contrast', 1.3)
        saturation = getattr(self.config.thumbnails.enhancements, 'saturation', 1.2)
        sharpness = getattr(self.config.thumbnails.enhancements, 'sharpness', 1.1)

        image = ImageEnhance.Contrast(image).enhance(contrast)
        image = ImageEnhance.Color(image).enhance(saturation)
        image = ImageEnhance.Sharpness(image).enhance(sharpness)

        return image

    def _add_gradient_overlay(
        self,
        image: Image.Image,
        direction: str = 'both'
    ) -> Image.Image:
        """Dodaj gradient dla czytelności tekstu"""
        overlay = Image.new('RGBA', image.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        width, height = image.size

        if direction in ['bottom', 'both']:
            for y in range(int(height * 0.6), height):
                alpha = int((y - height * 0.6) / (height * 0.4) * 160)
                draw.rectangle([(0, y), (width, y+1)], fill=(0, 0, 0, alpha))

        if direction in ['top', 'both']:
            for y in range(0, int(height * 0.4)):
                alpha = int((height * 0.4 - y) / (height * 0.4) * 120)
                draw.rectangle([(0, y), (width, y+1)], fill=(0, 0, 0, alpha))

        image = Image.alpha_composite(image.convert('RGBA'), overlay)
        return image.convert('RGB')

    def _load_font(self, font_type: str, size: int) -> ImageFont.FreeTypeFont:
        """Załaduj font z fallback"""
        font_config = self.font_paths.get(font_type, self.font_paths['arial_bold'])

        for path in [font_config['path'], font_config['fallback']]:
            try:
                return ImageFont.truetype(path, size)
            except:
                pass

        print(f"⚠️ Nie można załadować fontu {font_type}")
        return ImageFont.load_default()

    def _wrap_text(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_width: float
    ) -> List[str]:
        """Podziel tekst na linie"""
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

        # Max 2 linie dla czytelności
        if len(lines) > 2:
            lines = lines[:2]
            lines[1] = lines[1][:20] + "..."

        return lines

    def _draw_text_with_outline(
        self,
        draw: ImageDraw.ImageDraw,
        position: Tuple[int, int],
        text: str,
        font: ImageFont.FreeTypeFont,
        text_color: str,
        outline_color: str = '#000000',
        outline_width: int = 8
    ):
        """Rysuj tekst z grubym outline"""
        x, y = position

        # Parse colors
        if isinstance(text_color, str) and text_color.startswith('#'):
            text_color = tuple(int(text_color[i:i+2], 16) for i in (1, 3, 5))
        if isinstance(outline_color, str) and outline_color.startswith('#'):
            outline_color = tuple(int(outline_color[i:i+2], 16) for i in (1, 3, 5))

        # Rysuj outline
        for adj_x in range(-outline_width, outline_width + 1):
            for adj_y in range(-outline_width, outline_width + 1):
                if adj_x != 0 or adj_y != 0:
                    draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)

        # Rysuj główny tekst
        draw.text((x, y), text, font=font, fill=text_color)

    def _create_thumbnail_with_template(
        self,
        base_image: Image.Image,
        title: str,
        template_name: str,
        bottom_text: Optional[str] = None
    ) -> Image.Image:
        """
        Stwórz miniaturkę z danym templatem

        Args:
            base_image: Bazowy obraz (klatka z video)
            title: Tytuł (już z emoji!)
            template_name: 'aggressive', 'question', 'viral'
            bottom_text: Opcjonalny tekst dolny (data)
        """
        # Load template config
        template = self.config.thumbnails.templates[template_name]

        # Enhance
        image = self._enhance_image(base_image)

        # Gradient
        gradient_dir = getattr(template, 'gradient_direction', 'both')
        image = self._add_gradient_overlay(image, gradient_dir)

        draw = ImageDraw.Draw(image)
        width, height = image.size

        # Colors
        primary_color = getattr(template, 'primary_color', '#FFFF00')
        secondary_color = getattr(template, 'secondary_color', '#FF0000')
        outline_color = getattr(template, 'outline_color', '#000000')
        outline_width = getattr(template, 'outline_width', 8)

        # Font size
        font_multiplier = getattr(template, 'font_size_multiplier', 1.0)
        font_size = int(height * 0.11 * font_multiplier)
        font = self._load_font('impact', font_size)

        # Text position
        text_position = getattr(template, 'text_position', 'center')

        title_upper = title.upper()

        if text_position == 'center':
            # Center position
            lines = self._wrap_text(title_upper, font, width * 0.9)
            line_height = font_size + 10
            total_height = len(lines) * line_height
            y_offset = (height - total_height) // 2 - int(height * 0.05)

            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2

                self._draw_text_with_outline(
                    draw, (x, y_offset), line, font,
                    text_color=primary_color,
                    outline_color=outline_color,
                    outline_width=outline_width
                )
                y_offset += line_height

        elif text_position == 'top_bottom':
            # Split text na 2 części
            words = title_upper.split()
            mid = len(words) // 2
            top_part = ' '.join(words[:mid])
            bottom_part = ' '.join(words[mid:])

            # TOP
            bbox = draw.textbbox((0, 0), top_part, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = int(height * 0.15)

            self._draw_text_with_outline(
                draw, (x, y), top_part, font,
                text_color=primary_color,
                outline_color=outline_color,
                outline_width=outline_width
            )

            # BOTTOM
            bbox = draw.textbbox((0, 0), bottom_part, font=font)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = int(height * 0.75)

            self._draw_text_with_outline(
                draw, (x, y), bottom_part, font,
                text_color=secondary_color,  # Inny kolor dla diversity
                outline_color=outline_color,
                outline_width=outline_width
            )

        elif text_position == 'split':
            # Split z różnymi kolorami per linia
            lines = self._wrap_text(title_upper, font, width * 0.9)
            line_height = font_size + 10
            total_height = len(lines) * line_height
            y_offset = (height - total_height) // 2

            colors = [primary_color, secondary_color, '#FF6600']

            for i, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=font)
                text_width = bbox[2] - bbox[0]
                x = (width - text_width) // 2

                color = colors[i % len(colors)]

                self._draw_text_with_outline(
                    draw, (x, y_offset), line, font,
                    text_color=color,
                    outline_color=outline_color,
                    outline_width=outline_width
                )
                y_offset += line_height

        # Bottom text (data)
        if bottom_text:
            font_size_bottom = int(height * 0.06)
            font_bottom = self._load_font('arial_bold', font_size_bottom)

            bbox = draw.textbbox((0, 0), bottom_text, font=font_bottom)
            text_width = bbox[2] - bbox[0]
            x = (width - text_width) // 2
            y = int(height * 0.90)

            # Tło pod datą
            padding = 10
            bg_box = [
                (x - padding, y - 5),
                (x + text_width + padding, y + font_size_bottom + 5)
            ]
            draw.rectangle(bg_box, fill=(0, 0, 0, 200))

            self._draw_text_with_outline(
                draw, (x, y), bottom_text, font_bottom,
                text_color='#FFD700',  # Złoty
                outline_color='#000000',
                outline_width=3
            )

        # Emoji z template
        emoji_pool = getattr(template, 'emoji_pool', ['🔥'])
        if emoji_pool:
            try:
                import random
                emoji = random.choice(emoji_pool)
                emoji_size = int(height * 0.08)
                emoji_font = ImageFont.truetype("C:/Windows/Fonts/seguiemj.ttf", emoji_size)

                # Top-right position
                pos = (int(width * 0.88), int(height * 0.04))
                draw.text(pos, emoji, font=emoji_font, fill=(255, 255, 255))
            except:
                pass  # Emoji optional

        return image

    def _test_mobile_readability(self, thumbnail: Image.Image, title: str) -> float:
        """
        Test czytelności na mobile

        Returns:
            Readability score (0.0-1.0)
        """
        if not getattr(self.config.thumbnails.mobile_test, 'enabled', True):
            return 1.0

        test_width = getattr(self.config.thumbnails.mobile_test, 'test_width', 320)
        test_height = getattr(self.config.thumbnails.mobile_test, 'test_height', 180)

        # Resize to mobile size
        thumb_mobile = thumbnail.resize((test_width, test_height), Image.Resampling.LANCZOS)

        # Simple heuristic: contrast check
        # W prawdziwej wersji można użyć pytesseract OCR
        gray = np.array(thumb_mobile.convert('L'))
        contrast = gray.std() / 127.5  # Normalized

        # Assume good contrast = readable
        readability = min(contrast * 2, 1.0)

        return readability

    def generate_multi_variant(
        self,
        video_file: str,
        clips: List[Dict],
        output_dir: Path,
        part_number: Optional[int] = None,
        total_parts: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Generuj wiele wariantów miniaturek

        Returns:
            Dict z wariantami i metadata
        """
        print("\n" + "="*70)
        print("🎨 STAGE 8: Multi-Variant AI Thumbnail Generation v2.0")
        print("="*70)

        if not clips:
            print("❌ Brak klipów do generowania miniaturki")
            return {'success': False, 'error': 'No clips', 'variants': []}

        try:
            # Wybierz najlepszy klip
            best_clip = max(clips, key=lambda c: c.get('final_score', 0))

            print(f"📊 Najlepszy klip: score={best_clip.get('final_score', 0):.2f}")

            # Wybierz najlepszą klatkę (z face detection!)
            print("🎯 Szukam najlepszej klatki (face priority)...")
            base_frame, frame_metadata = self._select_best_frame_with_faces(video_file, best_clip)

            # Resize to target
            base_frame = base_frame.resize(
                (self.target_width, self.target_height),
                Image.Resampling.LANCZOS
            )

            # Generuj clickbaitowe tytuły z GPT
            print("🤖 Generuję clickbaitowe tytuły z GPT...")
            titles = self._generate_clickbait_titles_gpt(best_clip)

            # Bottom text
            if part_number and total_parts:
                bottom_text = f"📺 CZ. {part_number}/{total_parts} | {datetime.now().strftime('%d.%m.%Y')}"
            else:
                bottom_text = f"📅 {datetime.now().strftime('%d.%m.%Y')}"

            # Generuj 3 warianty
            variants = []
            template_names = ['aggressive', 'question', 'viral']
            title_styles = ['aggressive', 'question', 'mysterious']

            num_variants = min(
                getattr(self.config.thumbnails, 'num_variants', 3),
                len(template_names)
            )

            for i in range(num_variants):
                template_name = template_names[i]
                title_style = title_styles[i]
                title = titles.get(title_style, titles['aggressive'])

                print(f"\n   🎨 Wariant {i+1}/{num_variants}: {template_name.upper()}")
                print(f"      Tytuł: '{title}'")

                # Generuj thumbnail
                thumbnail = self._create_thumbnail_with_template(
                    base_frame.copy(),
                    title,
                    template_name,
                    bottom_text
                )

                # Final sharpening
                thumbnail = thumbnail.filter(ImageFilter.SHARPEN)

                # Mobile test
                mobile_score = self._test_mobile_readability(thumbnail, title)
                print(f"      📱 Mobile readability: {mobile_score:.2%}")

                # Zapisz
                variant_id = f"v{i+1}_{template_name}"
                if part_number:
                    filename = f"thumbnail_part{part_number}_{variant_id}.jpg"
                else:
                    filename = f"thumbnail_{variant_id}.jpg"

                filepath = output_dir / filename

                quality = getattr(self.config.thumbnails, 'quality', 92)
                thumbnail.save(filepath, 'JPEG', quality=quality, optimize=True)

                file_size = filepath.stat().st_size / 1024
                print(f"      💾 Zapisano: {filename} ({file_size:.1f} KB)")

                # Metadata
                variant_meta = {
                    'id': variant_id,
                    'path': str(filepath),
                    'template': template_name,
                    'title': title,
                    'title_style': title_style,
                    'file_size_kb': file_size,
                    'mobile_readability': mobile_score,
                    'frame_metadata': frame_metadata,
                    'clip_score': best_clip.get('final_score', 0),
                    'created_at': datetime.now().isoformat()
                }

                variants.append(variant_meta)

            # Zapisz metadata JSON
            if getattr(self.config.thumbnails, 'save_metadata', True):
                metadata_file = output_dir / "thumbnail_metadata.json"
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump({
                        'variants': variants,
                        'best_clip_id': best_clip.get('id'),
                        'generation_date': datetime.now().isoformat()
                    }, f, indent=2, ensure_ascii=False)

                print(f"\n📄 Metadata zapisana: thumbnail_metadata.json")

            print("\n" + "="*70)
            print(f"✅ Wygenerowano {len(variants)} wariantów miniaturek!")
            print("="*70)

            # Podsumowanie
            print("\n🎯 PODSUMOWANIE WARIANTÓW:")
            for i, var in enumerate(variants, 1):
                print(f"   [{i}] {var['template'].upper()}: \"{var['title']}\"")
                print(f"       └─ {var['path']}")

            return {
                'success': True,
                'variants': variants,
                'num_variants': len(variants),
                'best_variant_id': variants[0]['id'],  # Default: pierwszy
                'metadata_file': str(metadata_file) if variants else None
            }

        except Exception as e:
            print(f"❌ Błąd generowania miniaturek: {e}")
            import traceback
            traceback.print_exc()

            return {
                'success': False,
                'error': str(e),
                'variants': []
            }

    def process(
        self,
        video_file: str,
        clips: list,
        output_dir: Path,
        part_number: Optional[int] = None,
        total_parts: Optional[int] = None,
        custom_title: Optional[str] = None,
        custom_bottom_text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Główna metoda - compatibility wrapper dla multi_variant
        """
        return self.generate_multi_variant(
            video_file,
            clips,
            output_dir,
            part_number,
            total_parts
        )

    def generate_with_part_number(
        self,
        video_file: str,
        part_number: int,
        total_parts: int,
        clips: Optional[list] = None,
        output_dir: Optional[Path] = None,
        custom_title: Optional[str] = None
    ) -> Dict[str, Any]:
        """Compatibility method dla Smart Splitter"""
        if output_dir is None:
            output_dir = Path("output")
            output_dir.mkdir(exist_ok=True)

        if clips is None:
            clips = []

        return self.generate_multi_variant(
            video_file,
            clips,
            output_dir,
            part_number,
            total_parts
        )


# === Test standalone ===
if __name__ == "__main__":
    print("Stage 8: AI Thumbnail Generator v2.0")
    print("Test mode - requires actual video file and config")
