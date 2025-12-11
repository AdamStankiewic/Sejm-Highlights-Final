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
from collections import Counter
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

    def _classify_to_side_zone(self, detection: Dict[str, float], stream_w: int, stream_h: int) -> str:
        """Klasyfikacja twarzy do 6 stref bocznych 3x3 (ignorując centrum).

        Args:
            detection: Bounding box twarzy (x, y, w, h) w pikselach.
            stream_w: Szerokość klatki.
            stream_h: Wysokość klatki.

        Returns:
            Nazwa strefy (left_top, left_middle, left_bottom, right_top, right_middle, right_bottom)
            lub "center_ignored" jeśli twarz jest w kolumnie środkowej.
        """

        center_x = detection['x'] + detection['w'] / 2
        center_y = detection['y'] + detection['h'] / 2

        col_ratio = center_x / stream_w
        row_ratio = center_y / stream_h

        if 1 / 3 <= col_ratio <= 2 / 3:
            return "center_ignored"

        if col_ratio < 1 / 3:
            col = "left"
        else:
            col = "right"

        if row_ratio < 1 / 3:
            row = "top"
        elif row_ratio < 2 / 3:
            row = "middle"
        else:
            row = "bottom"

        return f"{col}_{row}"

    def _detect_webcam_region(
        self, input_file: Path, start_time: float, duration: float, num_samples: int = 5
    ) -> Dict[str, Any]:
        """Wieloklatkowa detekcja kamerki w 6 strefach bocznych.

        Args:
            input_file: Ścieżka do pliku wideo.
            start_time: Początek analizowanego fragmentu.
            duration: Długość fragmentu do próbkowania.
            num_samples: Liczba klatek do analizy (równomiernie rozmieszczone).

        Returns:
            Dict z informacjami o detekcji facecama.
        """

        if not self.face_detector:
            return {
                'type': 'none',
                'zone': None,
                'detection_rate': 0.0,
                'x': 0,
                'y': 0,
                'w': 0,
                'h': 0,
                'confidence': 0.0,
                'num_faces': 0,
            }

        consensus_threshold = getattr(self.config.shorts, 'detection_threshold', 0.3)  # TODO: move to config

        try:
            sample_times = np.linspace(start_time, start_time + duration, num_samples)
            detections: List[Dict[str, Any]] = []
            all_zones: List[str] = []

            for t in sample_times:
                tmp_frame = None
                try:
                    with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
                        tmp_frame = tmp.name

                    cmd = [
                        'ffmpeg',
                        '-ss', str(t),
                        '-i', str(input_file),
                        '-vframes', '1',
                        '-q:v', '5',
                        '-y',
                        tmp_frame,
                    ]
                    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

                    frame = self.cv2.imread(tmp_frame)
                    if frame is None:
                        continue

                    frame_rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
                    h, w, _ = frame.shape

                    results = self.face_detector.process(frame_rgb)
                    if not results or not results.detections:
                        continue

                    faces = []
                    for detection in results.detections:
                        bbox = detection.location_data.relative_bounding_box
                        confidence = detection.score[0]

                        x = max(int(bbox.xmin * w), 0)
                        y = max(int(bbox.ymin * h), 0)
                        fw = int(bbox.width * w)
                        fh = int(bbox.height * h)

                        faces.append(
                            {
                                'x': x,
                                'y': y,
                                'w': fw,
                                'h': fh,
                                'confidence': confidence,
                                'area': max(fw, 0) * max(fh, 0),
                            }
                        )

                    if not faces:
                        continue

                    main_face = max(faces, key=lambda f: f['area'])
                    zone = self._classify_to_side_zone(main_face, w, h)
                    if zone == "center_ignored":
                        continue

                    detections.append({
                        'zone': zone,
                        'bbox': main_face,
                        'num_faces': len(faces),
                    })
                    all_zones.append(zone)
                finally:
                    if tmp_frame and os.path.exists(tmp_frame):
                        os.unlink(tmp_frame)

            if not all_zones:
                return {
                    'type': 'none',
                    'zone': None,
                    'detection_rate': 0.0,
                    'x': 0,
                    'y': 0,
                    'w': 0,
                    'h': 0,
                    'confidence': 0.0,
                    'num_faces': 0,
                }

            zone_counts = Counter(all_zones)
            dominant_zone, dominant_count = zone_counts.most_common(1)[0]
            detection_rate = dominant_count / max(num_samples, 1)

            ambiguous = False
            if len(zone_counts) > 1:
                _, second_count = zone_counts.most_common(2)[1]
                if second_count == dominant_count and detection_rate >= consensus_threshold:
                    ambiguous = True

            if detection_rate < consensus_threshold or ambiguous:
                return {
                    'type': 'none',
                    'zone': dominant_zone if ambiguous else None,
                    'detection_rate': detection_rate,
                    'x': 0,
                    'y': 0,
                    'w': 0,
                    'h': 0,
                    'confidence': 0.0,
                    'num_faces': 0,
                }

            dominant_entry = next((d for d in reversed(detections) if d['zone'] == dominant_zone), detections[-1])
            bbox = dominant_entry['bbox']

            return {
                'type': 'face_detected',
                'zone': dominant_zone,
                'detection_rate': detection_rate,
                'x': bbox['x'],
                'y': bbox['y'],
                'w': bbox['w'],
                'h': bbox['h'],
                'confidence': bbox.get('confidence', 0.0),
                'num_faces': dominant_entry.get('num_faces', 1),
            }

        except Exception as e:
            print(f"      ⚠️ Błąd wykrywania kamerki: {e}")
            return {
                'type': 'none',
                'zone': None,
                'detection_rate': 0.0,
                'x': 0,
                'y': 0,
                'w': 0,
                'h': 0,
                'confidence': 0.0,
                'num_faces': 0,
            }

    def _select_template(self, webcam_detection: Dict[str, Any], manual_override: Optional[str] = None) -> str:
        """Wybór szablonu na podstawie detekcji kamerki lub ręcznego wyboru."""

        if manual_override:
            print(f"      🎨 Template override: {manual_override}")
            return manual_override

        detection_rate = webcam_detection.get("detection_rate", 0.0) if webcam_detection else 0.0
        zone = (webcam_detection or {}).get("zone") if webcam_detection else None

        if not webcam_detection or webcam_detection.get("type") == "none" or detection_rate < 0.30:
            template = "simple_game_only"
        elif zone in {"left_bottom", "right_bottom"}:
            template = "game_top_face_bottom_bar"
        elif zone in {"left_top", "left_middle", "right_top", "right_middle"}:
            template = "full_game_with_floating_face"
        else:
            template = "simple_game_only"

        print(f"      🤖 Auto-select: {template} (zone={zone}, rate={detection_rate:.2f})")
        return template

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
                - "game_top_face_bottom_bar": gameplay u góry, facecam pasek na dole
                - "full_game_with_floating_face": pełny gameplay + PIP facecam
                - "simple_game_only": sam gameplay 9:16
                - "big_face_reaction": duża twarz na rozmytym tle (manualnie)
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
                add_subtitles=getattr(self.config.shorts, 'add_subtitles', getattr(self.config.shorts, 'subtitles', False)),
                subtitle_lang=getattr(self.config.shorts, 'subtitle_lang', 'pl'),
            )
            return {"shorts": [str(p) for p in paths], "shorts_dir": str(shorts_dir), "count": len(paths)}

        # Generate each Short
        generated_shorts = []

        for i, clip in enumerate(shorts_clips, 1):
            print(f"\n   📱 Short {i}/{len(shorts_clips)}")

            try:
                manual_override = getattr(self.config.shorts, "manual_template", None)
                if template not in (None, "auto"):
                    manual_override = template

                webcam_detection = {"type": "none"}
                if template == "auto" and self.config.shorts.face_detection and not manual_override:
                    clip_start = clip.get("t0", 0.0)
                    clip_end = clip.get("t1", clip_start)
                    detection_duration = max(clip_end - clip_start, 1.0)
                    webcam_detection = self._detect_webcam_region(
                        input_path,
                        start_time=clip_start,
                        duration=detection_duration,
                    )

                selected_template = self._select_template(webcam_detection, manual_override)

                short_result = self._generate_single_short(
                    input_path,
                    clip,
                    segments,
                    shorts_dir,
                    i,
                    template=selected_template,
                    webcam_detection=webcam_detection if self.config.shorts.face_detection else None
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
        elif template == "game_top_face_bottom_bar":
            filter_complex = self._build_game_top_face_bottom_bar(width, height, str(ass_file), webcam_detection)
        elif template == "full_game_with_floating_face":
            filter_complex = self._build_full_game_with_floating_face(width, height, str(ass_file), webcam_detection)
        elif template == "simple_game_only":
            filter_complex = self._build_simple_game_only(width, height, str(ass_file))
        elif template == "big_face_reaction":
            filter_complex = self._build_big_face_reaction(width, height, str(ass_file), webcam_detection)
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

    def _build_game_top_face_bottom_bar(
        self,
        width: int,
        height: int,
        ass_file: str,
        webcam_detection: Optional[Dict] = None,
    ) -> str:
        """
        Szablon GAME TOP / FACE BOTTOM BAR (układ pionowy góra-dół)
        Layout:
        - Gameplay w górnych ~70% (1080x1344)
        - Pasek facecam na dole ~30% (1080x576)
        - Całość w 1080x1920
        """

        gameplay_h = int(height * 0.7)
        facecam_h = height - gameplay_h

        # Gameplay: pełna szerokość, crop do 9:16 i 70% wysokości
        filter_parts = [
            f"[0:v]split=2[gameplay][face];",
            # === GAMEPLAY (top 70%) ===
            f"[gameplay]scale={width}:{gameplay_h}:force_original_aspect_ratio=increase,",
            f"crop={width}:{gameplay_h}[gameplay_scaled];",
        ]

        # Facecam crop na bazie detekcji lub fallback do dolnej części
        if webcam_detection and webcam_detection.get('w') and webcam_detection.get('h'):
            bbox = webcam_detection
            x = max(int(bbox.get('x', 0)), 0)
            y = max(int(bbox.get('y', 0)), 0)
            w = max(int(bbox.get('w', 1)), 1)
            h = max(int(bbox.get('h', 1)), 1)
            crop_cmd = f"crop={w}:{h}:{x}:{y}"
        else:
            crop_cmd = "crop=iw:ih*0.35:0:ih*0.65"  # Bottom 35% fallback

        filter_parts.extend(
            [
                # === FACE BAR (bottom 30%) ===
                f"[face]{crop_cmd},",
                f"scale={width}:{facecam_h}:force_original_aspect_ratio=decrease,",
                f"pad={width}:{facecam_h}:(ow-iw)/2:0:black,",
                f"crop={width}:{facecam_h}[face_scaled];",
                # === STACK GAMEPLAY + FACE ===
                f"[gameplay_scaled][face_scaled]vstack=inputs=2[stacked];",
                # === SUBTITLES ===
                f"[stacked]ass='{ass_file.replace(chr(92), '/')}'",
            ]
        )

        return "".join(filter_parts)

    def _build_full_game_with_floating_face(
        self,
        width: int,
        height: int,
        ass_file: str,
        webcam_detection: Optional[Dict] = None,
    ) -> str:
        """
        Szablon FULLSCREEN GAME + FLOATING FACE (PIP)
        Layout:
        - Gameplay pełnoekranowy 1080x1920
        - PIP facecam ~38% szerokości, ~20% wysokości, umieszczony nisko
        - Wyrównanie lewo/prawo zależne od wykrytej strefy
        """

        pip_w = int(width * 0.38)
        pip_h = int(height * 0.20)
        margin = int(width * 0.05)
        pip_y = int(height * 0.625)

        zone = (webcam_detection or {}).get('zone', '') if webcam_detection else ''
        if isinstance(zone, str) and zone.startswith('left'):
            pip_x = margin
        elif isinstance(zone, str) and zone.startswith('right'):
            pip_x = width - pip_w - margin
        else:
            pip_x = width - pip_w - margin

        if pip_y + pip_h + margin > height:
            pip_y = max(height - pip_h - margin, 0)

        # Facecam crop (detected bbox fallback to bottom slice)
        if webcam_detection and webcam_detection.get('w') and webcam_detection.get('h'):
            bbox = webcam_detection
            x = max(int(bbox.get('x', 0)), 0)
            y = max(int(bbox.get('y', 0)), 0)
            w = max(int(bbox.get('w', 1)), 1)
            h = max(int(bbox.get('h', 1)), 1)
            face_crop = f"crop={w}:{h}:{x}:{y}"
        else:
            face_crop = "crop=iw:ih*0.35:0:ih*0.65"

        filter_complex = (
            # === SPLIT MAIN & FACE ===
            f"[0:v]split=2[main][pip_src];"
            # === MAIN FULLSCREEN ===
            f"[main]scale={int(width*1.1)}:{height}:force_original_aspect_ratio=decrease,"
            f"crop={width}:{height}[main_scaled];"
            # === PIP FACE ===
            f"[pip_src]{face_crop},"
            f"scale={pip_w}:{pip_h}:force_original_aspect_ratio=decrease,"
            f"pad={pip_w}:{pip_h}:(ow-iw)/2:(oh-ih)/2:black[pip];"
            # === OVERLAY ===
            f"[main_scaled][pip]overlay={pip_x}:{pip_y}[composed];"
            # === SUBTITLES ===
            f"[composed]ass='{ass_file.replace(chr(92), '/')}'"
        )

        return filter_complex

    def _build_simple_game_only(self, width: int, height: int, ass_file: str) -> str:
        """
        Szablon SIMPLE GAME ONLY - pełnoekranowy gameplay 9:16 bez facecama.
        """

        return (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}[game];"
            f"[game]ass='{ass_file.replace(chr(92), '/')}'"
        )

    def _build_big_face_reaction(
        self,
        width: int,
        height: int,
        ass_file: str,
        webcam_detection: Optional[Dict] = None,
    ) -> str:
        """
        Szablon BIG FACE REACTION - rozmyte tło + duża twarz na froncie.
        Użycie manualne przy mocnych reakcjach.
        """

        face_w = int(width * 0.9)
        face_h = int(height * 0.4)
        face_x = int((width - face_w) / 2)
        face_y = int(height * 0.3)

        if webcam_detection and webcam_detection.get('w') and webcam_detection.get('h'):
            bbox = webcam_detection
            x = max(int(bbox.get('x', 0)), 0)
            y = max(int(bbox.get('y', 0)), 0)
            w = max(int(bbox.get('w', 1)), 1)
            h = max(int(bbox.get('h', 1)), 1)
            face_crop = f"crop={w}:{h}:{x}:{y}"
        else:
            face_crop = "crop=iw:ih*0.35:0:ih*0.65"

        filter_complex = (
            # === BACKGROUND (blurred) ===
            f"[0:v]scale={int(width*1.1)}:{height}:force_original_aspect_ratio=decrease,"
            f"crop={width}:{height},gblur=sigma=30[bg];"
            # === FACE FOREGROUND ===
            f"[0:v]{face_crop},"
            f"scale={face_w}:{face_h}:force_original_aspect_ratio=decrease,"
            f"pad={face_w}:{face_h}:(ow-iw)/2:(oh-ih)/2:black[face];"
            # === COMPOSE ===
            f"[bg][face]overlay={face_x}:{face_y}[composed];"
            # === SUBTITLES (opcjonalnie) ===
            f"[composed]ass='{ass_file.replace(chr(92), '/')}'"
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
