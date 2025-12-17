"""
Stage 10: YouTube Shorts Generator (PROFESSIONAL TEMPLATES EDITION)
- Format pionowy 9:16 (1080x1920)
- 4 profesjonalne szablony dla streamów (gaming + IRL)
- Automatyczna detekcja kamerki (MediaPipe Face Detection)
- Żółte napisy z safe zones
- AI-generowane viralne tytuły
"""

import subprocess
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import os
import tempfile
import numpy as np

from .config import Config
from shorts import ShortsGenerator, Segment


class ShortsStage:
    """Stage 10: YouTube Shorts Generation with Professional Templates"""

    def __init__(self, config: Config):
        self.config = config
        self._check_ffmpeg()

        # Initialize GPT for title generation
        self._init_gpt()

        # Initialize Face Detection for webcam region detection
        self._init_face_detection()

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

    def _init_face_detection(self):
        """Inicjalizacja MediaPipe Face Detection"""
        self.face_detector = None

        if not self.config.shorts.face_detection:
            print("   ℹ️ Face detection wyłączone w konfiguracji")
            return

        try:
            import mediapipe as mp
            import cv2

            self.mp = mp
            self.cv2 = cv2

            # Initialize MediaPipe Face Detection
            self.mp_face_detection = mp.solutions.face_detection
            self.face_detector = self.mp_face_detection.FaceDetection(
                model_selection=0,  # 0 = short-range (< 2m), 1 = full-range
                min_detection_confidence=self.config.shorts.webcam_detection_confidence
            )

            print("   ✓ MediaPipe Face Detection gotowy")

        except ImportError:
            print("   ⚠️ Brak biblioteki mediapipe - zainstaluj: pip install mediapipe")
            print("   → Face detection będzie niedostępne (fallback do simple template)")
            self.face_detector = None
        except Exception as e:
            print(f"   ⚠️ Błąd inicjalizacji Face Detection: {e}")
            self.face_detector = None

    def _check_ffmpeg(self):
        """Sprawdź czy ffmpeg jest dostępny"""
        try:
            subprocess.run(['ffmpeg', '-version'],
                         stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE,
                         check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError("ffmpeg nie jest zainstalowany lub niedostępny w PATH")

    def _detect_webcam_region(self, input_file: Path, t_sample: float = 5.0) -> Dict[str, Any]:
        """
        Wykryj region kamerki streamera w video

        Args:
            input_file: Ścieżka do pliku wideo
            t_sample: Timestamp do próbkowania (środek video)

        Returns:
            Dict z informacjami:
            {
                'type': 'bottom_bar' | 'corner' | 'full_face' | 'none',
                'x': int, 'y': int, 'w': int, 'h': int,
                'confidence': float,
                'num_faces': int
            }
        """

        if not self.face_detector:
            return {
                'type': 'none',
                'x': 0, 'y': 0, 'w': 0, 'h': 0,
                'confidence': 0.0,
                'num_faces': 0
            }

        try:
            # Extract single frame at t_sample using ffmpeg
            with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                tmp_frame = tmp.name

            cmd = [
                'ffmpeg',
                '-ss', str(t_sample),
                '-i', str(input_file),
                '-vframes', '1',
                '-q:v', '2',
                '-y',
                tmp_frame
            ]

            subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

            # Load frame with OpenCV
            frame = self.cv2.imread(tmp_frame)
            if frame is None:
                return {'type': 'none', 'x': 0, 'y': 0, 'w': 0, 'h': 0, 'confidence': 0.0, 'num_faces': 0}

            # Convert BGR to RGB
            frame_rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
            h, w, _ = frame.shape

            # Detect faces
            results = self.face_detector.process(frame_rgb)

            # Clean up temp file
            os.unlink(tmp_frame)

            if not results.detections:
                return {'type': 'none', 'x': 0, 'y': 0, 'w': 0, 'h': 0, 'confidence': 0.0, 'num_faces': 0}

            # Analyze detected faces
            faces = []
            for detection in results.detections:
                bbox = detection.location_data.relative_bounding_box
                confidence = detection.score[0]

                # Convert to absolute coordinates
                x = int(bbox.xmin * w)
                y = int(bbox.ymin * h)
                fw = int(bbox.width * w)
                fh = int(bbox.height * h)

                faces.append({
                    'x': x, 'y': y, 'w': fw, 'h': fh,
                    'confidence': confidence,
                    'center_x': x + fw // 2,
                    'center_y': y + fh // 2
                })

            num_faces = len(faces)

            # Classify webcam region type based on face positions
            if num_faces == 0:
                return {'type': 'none', 'x': 0, 'y': 0, 'w': 0, 'h': 0, 'confidence': 0.0, 'num_faces': 0}

            # Sort by confidence
            faces = sorted(faces, key=lambda f: f['confidence'], reverse=True)
            main_face = faces[0]

            # Classify based on position and size
            face_area = main_face['w'] * main_face['h']
            frame_area = w * h
            face_ratio = face_area / frame_area

            # Check if face is in bottom region (bottom 40% of frame)
            is_bottom = main_face['center_y'] > h * 0.6

            # Check if face is in corner (within 30% from edges)
            is_corner = (
                (main_face['center_x'] < w * 0.3 or main_face['center_x'] > w * 0.7) and
                (main_face['center_y'] < h * 0.3 or main_face['center_y'] > h * 0.7)
            )

            # Classify
            if face_ratio > 0.3 and not is_corner:
                # Large face, likely full-screen IRL stream
                region_type = 'full_face'
                region_bbox = main_face
            elif is_bottom and face_ratio < 0.15:
                # Small face at bottom - likely gaming with webcam bar
                region_type = 'bottom_bar'
                # Estimate full webcam bar region (assume full width)
                region_bbox = {
                    'x': 0,
                    'y': main_face['y'] - int(main_face['h'] * 0.2),  # Slight padding
                    'w': w,
                    'h': int(h * 0.35),  # 35% of screen height
                    'confidence': main_face['confidence']
                }
            elif is_corner:
                # Face in corner - likely PIP setup
                region_type = 'corner'
                region_bbox = main_face
            else:
                # Default - treat as full face
                region_type = 'full_face'
                region_bbox = main_face

            return {
                'type': region_type,
                'x': region_bbox['x'],
                'y': region_bbox['y'],
                'w': region_bbox['w'],
                'h': region_bbox['h'],
                'confidence': main_face['confidence'],
                'num_faces': num_faces
            }

        except Exception as e:
            print(f"      ⚠️ Błąd wykrywania kamerki: {e}")
            return {'type': 'none', 'x': 0, 'y': 0, 'w': 0, 'h': 0, 'confidence': 0.0, 'num_faces': 0}

    def _select_template(self, webcam_detection: Dict[str, Any]) -> str:
        """
        Automatyczny wybór szablonu na podstawie wykrycia kamerki

        Args:
            webcam_detection: Wynik z _detect_webcam_region()

        Returns:
            Nazwa szablonu: 'classic_gaming' | 'pip_modern' | 'irl_fullface' | 'simple'
        """

        region_type = webcam_detection['type']
        num_faces = webcam_detection['num_faces']

        # Decision tree
        if region_type == 'none':
            # No faces detected - use simple crop
            print(f"      🤖 Auto-select: simple (brak twarzy)")
            return 'simple'

        elif region_type == 'bottom_bar':
            # Gaming setup - kamerka na dole
            print(f"      🤖 Auto-select: classic_gaming (kamerka na dole)")
            return 'classic_gaming'

        elif region_type == 'corner':
            # PIP setup
            print(f"      🤖 Auto-select: pip_modern (kamerka w rogu)")
            return 'pip_modern'

        elif region_type == 'full_face':
            # IRL stream
            if num_faces >= 2:
                # Multiple faces - good candidate for speaker tracking
                print(f"      🤖 Auto-select: dynamic_speaker (wykryto {num_faces} twarzy)")
                return 'dynamic_speaker'
            else:
                print(f"      🤖 Auto-select: irl_fullface (pojedyncza twarz fullscreen)")
                return 'irl_fullface'

        else:
            # Fallback
            return 'simple'

    def process(
        self,
        input_file: str,
        shorts_clips: List[Dict],
        segments: List[Dict],
        output_dir: Path,
        session_dir: Path,
        template: str = None  # None = backward compatibility (simple), "auto" = auto-detect
    ) -> Dict[str, Any]:
        """
        Główna metoda generowania Shorts

        Args:
            input_file: Plik źródłowy
            shorts_clips: Już wybrane klipy dla Shorts (z Stage 6)
            segments: Segmenty z transkrypcją
            output_dir: Katalog wyjściowy
            session_dir: Katalog sesji
            template: Szablon layoutu:
                - None (default): backward compatibility - prosty crop (dla Sejmu)
                - "auto": automatyczna detekcja na podstawie webcam region
                - "simple": prosty crop 9:16
                - "classic_gaming": gaming layout (kamerka dół)
                - "pip_modern": PIP layout
                - "irl_fullface": IRL fullscreen
                - "dynamic_speaker": speaker tracking

        Returns:
            Dict zawierający listę wygenerowanych Shorts
        """
        print(f"\n🎬 YouTube Shorts Generator (PROFESSIONAL TEMPLATES)")
        print(f"📱 Generowanie {len(shorts_clips)} Shorts...")

        # Backward compatibility: None = simple (dla Sejmu)
        if template is None:
            template = "simple"
            print(f"   ℹ️ Template: simple (backward compatibility)")
        else:
            print(f"   🎨 Template: {template}")

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

        # Nowy modularny generator (Gaming/Universal/IRL)
        modern_templates = {"gaming", "universal", "irl"}
        if template in modern_templates:
            generator = ShortsGenerator(output_dir=shorts_dir, face_regions=self.config.shorts.face_regions)
            segs = [
                Segment(start=clip.get('t0', 0), end=clip.get('t1', 0), score=clip.get('score', 0))
                for clip in shorts_clips
            ]
            paths = generator.generate(
                input_path,
                segs,
                template=template,
                count=getattr(self.config.shorts, 'num_shorts', getattr(self.config.shorts, 'count', len(segs))),
                speedup=getattr(self.config.shorts, 'speedup_factor', getattr(self.config.shorts, 'speedup', 1.0)),
                enable_subtitles=getattr(
                    self.config.shorts,
                    'enable_subtitles',
                    getattr(self.config.shorts, 'add_subtitles', getattr(self.config.shorts, 'subtitles', False)),
                ),
                subtitle_lang=getattr(self.config.shorts, 'subtitle_lang', 'pl'),
            )
            return {"shorts": [str(p) for p in paths], "shorts_dir": str(shorts_dir), "count": len(paths)}

        # Auto-detect template if requested
        detected_webcam = None
        if template == "auto":
            print(f"   🔍 Automatyczna detekcja szablonu...")
            detected_webcam = self._detect_webcam_region(input_path, t_sample=shorts_clips[0]['t0'] + 5.0)
            template = self._select_template(detected_webcam)

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
                    i,
                    template=template,
                    webcam_detection=detected_webcam
                )
                generated_shorts.append(short_result)

                print(f"      ✅ Zapisano: {short_result['filename']}")
                print(f"      📝 Tytuł: {short_result['title']}")
                print(f"      🎨 Szablon: {short_result['template']}")

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
        index: int,
        template: str = "simple",
        webcam_detection: Optional[Dict] = None
    ) -> Dict:
        """Generuj pojedynczy Short z wybranym szablonem"""

        # Extract clip times
        t0 = max(0, clip['t0'] - self.config.shorts.pre_roll)
        t1 = clip['t1'] + self.config.shorts.post_roll
        duration = t1 - t0

        # Output files
        output_file = output_dir / f"short_{index:02d}_{template}.mp4"
        srt_file = output_dir / f"short_{index:02d}.srt"
        ass_file = output_dir / f"short_{index:02d}.ass"

        # Shorts format: 1080x1920 (9:16)
        width = self.config.shorts.width
        height = self.config.shorts.height

        print(f"      🎬 Renderowanie video (szablon: {template})...")

        # STEP 1: Generuj ASS napisy (z safe zones)
        self._generate_shorts_subtitles(clip, segments, t0, t1, ass_file, template)

        # STEP 2: Wybierz filter_complex na podstawie szablonu
        if template == "simple":
            filter_complex = self._build_simple_template(width, height, str(ass_file))
        elif template == "classic_gaming":
            filter_complex = self._build_classic_gaming_template(width, height, str(ass_file), webcam_detection)
        elif template == "pip_modern":
            filter_complex = self._build_pip_modern_template(width, height, str(ass_file), webcam_detection)
        elif template == "irl_fullface":
            filter_complex = self._build_irl_fullface_template(width, height, str(ass_file))
        elif template == "dynamic_speaker":
            filter_complex = self._build_dynamic_speaker_tracker_template(
                width, height, str(ass_file), clip, segments, t0, t1
            )
        else:
            # Fallback to simple
            print(f"      ⚠️ Nieznany szablon '{template}', używam 'simple'")
            filter_complex = self._build_simple_template(width, height, str(ass_file))

        # STEP 3: Renderuj video z FFmpeg
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

        # Generate AI title and metadata
        title = self._generate_ai_short_title(clip, segments)
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
            'template': template,
            'clip_id': clip.get('id'),
            'score': clip.get('final_score', 0),
            'source_timestamp': f"{t0:.1f}-{t1:.1f}s"
        }

    # ============================================================================
    # TEMPLATE BUILDERS - FFmpeg filter_complex dla każdego szablonu
    # ============================================================================

    def _build_simple_template(self, width: int, height: int, ass_file: str) -> str:
        """
        Szablon SIMPLE - prosty crop + scale do 9:16
        Backward compatibility - dla materiałów z Sejmu
        """
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[v];"
            f"[v]ass='{ass_file.replace(chr(92), '/')}'"
        )
        return filter_complex

    def _build_classic_gaming_template(
        self,
        width: int,
        height: int,
        ass_file: str,
        webcam_detection: Optional[Dict] = None
    ) -> str:
        """
        Szablon CLASSIC GAMING
        Layout:
        - Tytuł u góry (pasek 220px)
        - Gameplay wyżej (skalowany, max 15% crop z boków)
        - Kamerka streamera na dole (pełna szerokość, 33% wysokości)
        - Napisy pod kamerką (safe zone)
        """

        title_height = self.config.shorts.title_height  # 220px
        webcam_height_ratio = self.config.shorts.webcam_height_ratio  # 0.33

        webcam_h = int(height * webcam_height_ratio)  # 633px dla 1920
        gameplay_h = height - webcam_h - title_height  # 1067px

        # Gameplay: scale do szerokości, crop do wysokości (max 15% crop z boków)
        gameplay_target_w = int(width * 1.15)  # Allow 15% crop

        filter_complex = (
            # [0] = Original video
            # Split video into 2 streams - gameplay (top) i webcam (bottom)
            f"[0:v]split=2[gameplay][webcam];"

            # === GAMEPLAY (top region) ===
            # Zakładamy że gameplay to górna część ekranu
            # Crop top region, scale to fit, center crop
            f"[gameplay]crop=iw:ih*0.65:0:0,"  # Top 65% of original
            f"scale={gameplay_target_w}:{gameplay_h}:force_original_aspect_ratio=decrease,"
            f"crop={width}:{gameplay_h}[gameplay_scaled];"

            # === WEBCAM (bottom region) ===
            # Zakładamy że kamerka to dolna część ekranu
            f"[webcam]crop=iw:ih*0.35:0:ih*0.65,"  # Bottom 35%
            f"scale={width}:{webcam_h}:force_original_aspect_ratio=increase,"
            f"crop={width}:{webcam_h}[webcam_scaled];"

            # === TITLE BAR (black bg with text overlay) ===
            f"color=black:{width}x{title_height}:d=1[title_bg];"

            # === STACK: Title + Gameplay + Webcam ===
            f"[title_bg][gameplay_scaled][webcam_scaled]vstack=inputs=3[stacked];"

            # === ADD SUBTITLES ===
            f"[stacked]ass='{ass_file.replace(chr(92), '/')}'"
        )

        return filter_complex

    def _build_pip_modern_template(
        self,
        width: int,
        height: int,
        ass_file: str,
        webcam_detection: Optional[Dict] = None
    ) -> str:
        """
        Szablon PIP MODERN
        Layout:
        - Cały stream skalowany do 9:16 (max 15% crop)
        - Kamerka jako mały PIP w prawym dolnym rogu (zaokrąglone rogi + cień)
        - Napisy w środkowej safe zone
        """

        pip_size_ratio = self.config.shorts.pip_size_ratio  # 0.25
        pip_w = int(width * pip_size_ratio)  # 270px
        pip_h = int(pip_w * 1.33)  # 4:3 ratio dla kamerki = 360px

        # Position: prawy dolny róg z marginesem
        pip_x = width - pip_w - 30  # 30px margin
        pip_y = height - pip_h - 150  # 150px margin (żeby nie zasłaniał napisów)

        corner_radius = self.config.shorts.pip_corner_radius  # 20px

        filter_complex = (
            # [0] = Original video
            # Split into main (fullscreen) and pip (webcam)
            f"[0:v]split=2[main][pip_src];"

            # === MAIN (fullscreen) ===
            # Scale to 9:16, allow max 15% crop from sides
            f"[main]scale={int(width*1.15)}:{height}:force_original_aspect_ratio=decrease,"
            f"crop={width}:{height}[main_scaled];"

            # === PIP (webcam corner) ===
            # Detect webcam region or assume bottom portion
            f"[pip_src]crop=iw:ih*0.35:0:ih*0.65,"  # Bottom 35%
            f"scale={pip_w}:{pip_h}:force_original_aspect_ratio=increase,"
            f"crop={pip_w}:{pip_h}[pip_cropped];"

            # Add rounded corners to PIP
            # Create alpha mask with rounded corners
            f"color=black:{pip_w}x{pip_h},format=rgba,"
            f"geq=r='255':g='255':b='255':"
            f"a='if(lt(abs(W/2-X),W/2-{corner_radius})*lt(abs(H/2-Y),H/2-{corner_radius}),"
            f"255,"
            f"if(lte(hypot({corner_radius}-(W-abs(W-2*X)),{corner_radius}-(H-abs(H-2*Y))),{corner_radius}),"
            f"255,0))'[pip_mask];"

            # Apply mask to PIP
            f"[pip_cropped][pip_mask]alphamerge[pip_rounded];"

            # === OVERLAY PIP on MAIN ===
            f"[main_scaled][pip_rounded]overlay={pip_x}:{pip_y}[composed];"

            # === ADD SUBTITLES ===
            f"[composed]ass='{ass_file.replace(chr(92), '/')}'"
        )

        return filter_complex

    def _build_irl_fullface_template(self, width: int, height: int, ass_file: str) -> str:
        """
        Szablon IRL FULL-FACE
        Layout:
        - Powiększenie (zoom 1.2x)
        - Delikatny crop 12% z boków
        - Brak PIP - tylko główna twarz
        - Napisy w safe zone
        """

        zoom_factor = self.config.shorts.irl_zoom_factor  # 1.2
        crop_ratio = self.config.shorts.irl_crop_ratio  # 0.12

        # Calculate scaled dimensions
        scaled_w = int(width * (1 + crop_ratio) * zoom_factor)
        scaled_h = int(height * zoom_factor)

        filter_complex = (
            # Zoom + crop
            f"[0:v]scale={scaled_w}:{scaled_h}:force_original_aspect_ratio=decrease,"
            f"crop={width}:{height}[zoomed];"

            # Add subtle gradient border/vignette effect
            # (optional - można dodać gradient overlay)
            f"[zoomed]ass='{ass_file.replace(chr(92), '/')}'"
        )

        return filter_complex

    def _build_dynamic_speaker_tracker_template(
        self,
        width: int,
        height: int,
        ass_file: str,
        clip: Dict,
        segments: List[Dict],
        clip_start: float,
        clip_end: float
    ) -> str:
        """
        Szablon DYNAMIC SPEAKER TRACKER
        Layout:
        - Automatyczne wykrywanie mówiącego (word-level timestamps + face detection)
        - Płynne przejścia (cross-fade) co 3-5 sekund
        - Zoom na aktualnie mówiącego

        UWAGA: To najbardziej zaawansowany szablon - wymaga dodatkowej logiki
        Na razie fallback do IRL template, pełna implementacja wymaga:
        - Multi-face tracking per frame
        - Speaker diarization (kto mówi kiedy)
        - Keyframe-based zooming
        """

        # TODO: Pełna implementacja speaker tracking
        # Na razie używamy uproszczonej wersji - zoom + crop jak IRL

        print(f"      ℹ️ Dynamic Speaker Tracker: używam uproszczonej wersji (IRL template)")

        return self._build_irl_fullface_template(width, height, ass_file)

    # ============================================================================
    # SUBTITLES GENERATION
    # ============================================================================

    def _generate_shorts_subtitles(
        self,
        clip: Dict,
        segments: List[Dict],
        clip_start: float,
        clip_end: float,
        ass_file: Path,
        template: str = "simple"
    ):
        """
        Generuj napisy w formacie ASS dla Shorts
        Z automatycznym safe zone w zależności od szablonu
        """

        # Znajdź segment odpowiadający clipowi
        segment = None
        for seg in segments:
            if abs(seg['t0'] - clip['t0']) < 1.0:
                segment = seg
                break

        if not segment or 'words' not in segment:
            self._generate_simple_subtitle(clip, ass_file, clip_start, clip_end)
            return

        # Determine MarginV (vertical position) based on template
        if template == "classic_gaming":
            # Napisy pod kamerką - wyżej niż zwykle
            margin_v = 800  # Wyżej, żeby nie zasłaniać kamerki na dole
        elif template == "pip_modern":
            # Napisy w środku
            margin_v = 600
        elif template in ["irl_fullface", "dynamic_speaker"]:
            # Napisy niżej - bezpieczna strefa
            margin_v = 650
        else:
            # Simple - default
            margin_v = 600

        # ASS Header - optymalizowany dla Shorts (9:16)
        ass_content = f"""[Script Info]
Title: YouTube Short Subtitle
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,68,&H00FFFF00,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,2,2,30,30,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        # Generuj linie napisów z word-level timing
        words = segment.get('words', [])

        if not words:
            # Fallback
            text = segment.get('text', '').strip()
            if text:
                ass_content += f"Dialogue: 0,{self._format_ass_time(0)},{self._format_ass_time(clip_end - clip_start)},Default,,0,0,0,,{text}\n"
        else:
            # Grupuj słowa w krótkie frazy (4 słowa)
            phrase_length = 4
            i = 0

            while i < len(words):
                phrase_words = words[i:i+phrase_length]

                if not phrase_words:
                    break

                # Oblicz timing względem początku clipu
                start_time = phrase_words[0]['start'] - clip['t0']
                end_time = phrase_words[-1]['end'] - clip['t0']

                start_time = max(0, start_time)
                end_time = max(start_time + 0.5, end_time)

                text = ' '.join(w['word'] for w in phrase_words)

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
        text = clip.get('title', 'Gorący moment! 🔥')

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

    # ============================================================================
    # TITLE & METADATA GENERATION
    # ============================================================================

    def _generate_ai_short_title(self, clip: Dict, segments: List[Dict]) -> str:
        """Generuj viralny tytuł dla Shorta używając GPT-4o-mini"""

        if not self.gpt_client:
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
        prompt = f"""Jesteś ekspertem od viralowych tytułów YouTube Shorts.

TRANSKRYPCJA MOMENTU:
{transcript[:300]}

SŁOWA KLUCZOWE: {keywords}

Wygeneruj JEDEN chwytliwy tytuł dla YouTube Short (max 60 znaków):
- Krótki, dynamiczny, emocjonalny
- Polskie litery (ą, ę, ć, etc.)
- Może zawierać emoji (🔥, 💥, 😱, ⚡)
- W stylu: "To ZMIAŻDŻYŁO czat! 💥", "Taka reakcja! 😱"
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
                temperature=0.9,
                max_tokens=50
            )

            title = response.choices[0].message.content.strip()
            title = title.strip('"').strip("'")

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

            templates = [
                f"{main_keyword.upper()}! 🔥",
                f"GORĄCY moment - {main_keyword}! 💥",
                f"To musisz zobaczyć! 😱",
                f"{main_keyword} - WOW! ⚡"
            ]

            idx = min(int(score * len(templates)), len(templates) - 1)
            return templates[idx]
        else:
            return "Niesamowity moment! 🔥"

    def _generate_short_description_fixed(self) -> str:
        """Stały opis dla wszystkich Shorts"""
        return """Najlepsze momenty ze streamów! Emocje, akcja i epicki content. Subskrybuj po więcej! 💥

#Shorts #Gaming #Stream #PolishStreamer"""

    def _generate_short_tags(self, clip: Dict) -> List[str]:
        """Generuj tagi dla Short"""
        tags = [
            'Shorts',
            'Gaming',
            'Stream',
            'Polish',
            'Twitch',
            'Highlight'
        ]

        # Dodaj keywords z clipu
        keywords = clip.get('keywords', [])
        for kw in keywords[:3]:
            if kw not in tags:
                tags.append(kw)

        return tags[:15]
