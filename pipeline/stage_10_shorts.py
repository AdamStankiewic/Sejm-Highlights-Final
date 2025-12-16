"""
Stage 10: YouTube Shorts Generator (Refactored Edition)
- Format pionowy 9:16 (1080x1920)
- Modular template system
- Clean delegation to ShortsGenerator
- Integrated copyright protection
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, List, Optional

from .config import Config
from shorts import ShortsGenerator, Segment
from shorts.face_detection import FaceDetector
from utils.copyright_protection import CopyrightProtector, CopyrightSettings

logger = logging.getLogger(__name__)


class ShortsStage:
    """Stage 10: YouTube Shorts Generation - Simplified orchestration layer

    This stage delegates all rendering logic to ShortsGenerator and templates.
    Its only responsibility is to:
    1. Validate inputs
    2. Convert pipeline data structures to Segment objects
    3. Initialize copyright protection if enabled
    4. Call ShortsGenerator with proper config
    5. Return results in expected format
    """

    def __init__(self, config: Config):
        self.config = config
        logger.info("Shorts Stage initialized with template: %s", config.shorts.template)

        # Initialize face detector if needed
        self.face_detector = None
        if getattr(config.shorts, 'face_detection', False):
            try:
                self.face_detector = FaceDetector(
                    confidence_threshold=getattr(config.shorts, 'webcam_detection_confidence', 0.5),
                    consensus_threshold=getattr(config.shorts, 'detection_threshold', 0.3),
                    num_samples=getattr(config.shorts, 'num_samples', 5)
                )
                logger.info("Face detection enabled")
            except Exception as e:
                logger.warning("Failed to initialize face detection: %s", e)

        # Initialize copyright protection if enabled
        self.copyright_protector = None
        if getattr(config, 'copyright', None) and getattr(config.copyright, 'enable_protection', False):
            try:
                self.copyright_protector = CopyrightProtector(
                    CopyrightSettings(
                        enable_protection=True,
                        audd_api_key=os.getenv('AUDD_API_KEY', getattr(config.copyright, 'audd_api_key', '')),
                        music_detection_threshold=getattr(config.copyright, 'music_detection_threshold', 0.7),
                        royalty_free_folder=Path(getattr(config.copyright, 'royalty_free_folder', 'assets/royalty_free'))
                    )
                )
                logger.info("Copyright protection enabled")
            except Exception as e:
                logger.warning("Failed to initialize copyright protection: %s", e)

    def process(
        self,
        input_file: str,
        shorts_clips: List[Dict],
        segments: List[Dict],
        output_dir: Path,
        session_dir: Path,
        template: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate YouTube Shorts from selected clips

        Args:
            input_file: Source video path
            shorts_clips: List of clip dicts with {t0, t1, score, ...}
            segments: Full segments with transcription data
            output_dir: Base output directory
            session_dir: Session-specific directory
            template: Override template (None = use config)

        Returns:
            Dict with generated shorts metadata
        """
        logger.info("🎬 YouTube Shorts Generator")
        logger.info(f"📱 Generating {len(shorts_clips)} Shorts...")

        # Validation: Check if shorts_clips is empty
        if not shorts_clips:
            print("   ⚠️ Brak kandydatów na Shorts (pusta lista)")
            print("   → Shorts generation skipped")
            return {
                'shorts': [],
                'shorts_dir': '',
                'count': 0
            }

        # Validation: Check if clips have scores
        clips_with_scores = [c for c in shorts_clips if c.get('final_score', 0) > 0]
        if len(clips_with_scores) < len(shorts_clips):
            missing = len(shorts_clips) - len(clips_with_scores)
            print(f"   ⚠️ WARNING: {missing}/{len(shorts_clips)} clips have score=0.00!")
            print(f"   → Check if scored_segments were properly passed to selection stage")

        # Backward compatibility: None = simple (dla Sejmu)
        if template is None:
            template = "simple"
            print(f"   ℹ️ Template: simple (backward compatibility)")
        else:
            print(f"   🎨 Template: {template}")

        input_path = Path(input_file)

        # Create output directory
        shorts_dir = session_dir / "shorts"
        shorts_dir.mkdir(exist_ok=True)

        # Auto-detect template if requested
        detected_webcam = None
        if template == "auto":
            print(f"   🔍 Automatyczna detekcja szablonu...")
            detected_webcam = self._detect_webcam_region(input_path, t_sample=shorts_clips[0]['t0'] + 5.0)
            template = self._select_template(detected_webcam)

        # Generate each Short
        generated_shorts = []

        for i, clip in enumerate(shorts_clips, 1):
            clip_score = clip.get('final_score', 0)
            clip_id = clip.get('id', 'unknown')
            print(f"\n   📱 Short {i}/{len(shorts_clips)} (score={clip_score:.2f}, id={clip_id})")

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
                print(f"      ⭐ Score: {short_result['score']:.2f}")

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

        # Convert clips to Segment objects
        clip_segments = [
            Segment(
                start=clip.get('t0', 0),
                end=clip.get('t1', 0),
                score=clip.get('score', 0),
                subtitles=self._extract_subtitles(clip, segments)
            )
            for clip in shorts_clips
        ]

        # Generate shorts with copyright protection
        try:
            shorts_paths = generator.generate(
                input_path,
                clip_segments,
                template=effective_template,
                count=getattr(self.config.shorts, 'num_shorts', 5),
                speedup=getattr(self.config.shorts, 'speedup_factor', 1.0),
                add_subtitles=getattr(self.config.shorts, 'add_subtitles', False),
                subtitle_lang=getattr(self.config.shorts, 'subtitle_lang', 'pl'),
                copyright_processor=self.copyright_protector
            )
        except Exception as e:
            logger.exception("Failed to generate shorts")
            raise RuntimeError(f"Shorts generation failed: {e}") from e

        logger.info(f"✅ Generated {len(shorts_paths)} Shorts")
        logger.info(f"📁 Location: {shorts_dir}")

        return {
            'shorts': [str(p) for p in shorts_paths],
            'shorts_dir': str(shorts_dir),
            'count': len(shorts_paths)
        }

    def _extract_subtitles(
        self,
        clip: Dict,
        segments: List[Dict]
    ) -> Optional[List[tuple]]:
        """Extract subtitle tuples from segments for this clip

        Returns:
            List of (text, start, end) tuples or None
        """
        if not getattr(self.config.shorts, 'add_subtitles', False):
            return None

        # Find matching segment
        clip_start = clip.get('t0', 0)
        clip_end = clip.get('t1', 0)

        matching_segment = None
        for seg in segments:
            if abs(seg.get('t0', 0) - clip_start) < 1.0:
                matching_segment = seg
                break

        if not matching_segment:
            return None

        # Extract words and convert to subtitle format
        words = matching_segment.get('words', [])
        if not words:
            # Fallback to full segment text
            text = matching_segment.get('text', '').strip()
            if text:
                return [(text, 0, clip_end - clip_start)]
            return None

        # Group words into phrases (4 words per phrase)
        subtitles = []
        phrase_length = 4

        for i in range(0, len(words), phrase_length):
            phrase_words = words[i:i+phrase_length]
            if not phrase_words:
                continue

            # Calculate timing relative to clip start
            start_time = max(0, phrase_words[0].get('start', 0) - clip_start)
            end_time = max(start_time + 0.5, phrase_words[-1].get('end', 0) - clip_start)

            text = ' '.join(w.get('word', '') for w in phrase_words)
            subtitles.append((text, start_time, end_time))

        return subtitles if subtitles else None
