"""
Main Pipeline Processor
Orchestruje wszystkie etapy przetwarzania (7 głównych + opcjonalnie YouTube)
"""

import time
import json
import threading
import random
import string
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from datetime import datetime, timedelta

from .config import Config
from .cache_manager import CacheManager
from .highlight_packer import HighlightPacker
from .stage_01_ingest import IngestStage
from .stage_02_vad import VADStage
from .stage_03_transcribe import TranscribeStage
from .stage_04_features import FeaturesStage
from .stage_05_scoring_gpt import ScoringStage
from .stage_06_selection import SelectionStage
from .stage_07_export import ExportStage
from .stage_08_thumbnail import ThumbnailStage




class PipelineProcessor:
    """
    Główny processor zarządzający całym pipeline'em

    Implementuje mechanizm "single flight" - tylko jedna instancja może działać jednocześnie.
    """

    # Class-level lock dla single-flight mechanism (współdzielony między wszystkie instancje)
    _global_lock = threading.Lock()
    _is_running = False
    _current_run_id: Optional[str] = None

    def __init__(self, config: Config):
        self.config = config
        self.config.validate()

        # Progress callback
        self.progress_callback: Optional[Callable] = None

        # Cancellation flag
        self._cancelled = False

        # Timing stats
        self.timing_stats = {}

        # RUN_ID dla tej sesji (będzie wygenerowany w process())
        self.run_id: Optional[str] = None

        # Initialize stages
        self.stages = {
            'ingest': IngestStage(config),
            'vad': VADStage(config),
            'transcribe': TranscribeStage(config),
            'features': FeaturesStage(config),
            'scoring': ScoringStage(config),
            'selection': SelectionStage(config),
            'export': ExportStage(config)
        }

        # Initialize thumbnail stage
        self.thumbnail_stage = ThumbnailStage(config)

        # Highlight Packer (pakowanie selected_clips do części z premierami)
        self.highlight_packer = None
        if hasattr(config, 'packer') and config.packer.enabled:
            self.highlight_packer = HighlightPacker(
                premiere_hour=config.packer.premiere_hour,
                premiere_minute=config.packer.premiere_minute,
                language=config.language
            )

        # Cache Manager (cache dla kosztownych stages: VAD, Transcribe, Scoring)
        self.cache_manager = CacheManager(
            cache_dir=config.cache.cache_dir,
            enabled=config.cache.enabled,
            force_recompute=config.cache.force_recompute
        )

        self.session_dir: Optional[Path] = None

    @staticmethod
    def _generate_run_id() -> str:
        """
        Generuj unikalny RUN_ID w formacie: YYYYMMDD_HHMMSS_RANDOM

        Przykład: 20250115_143052_a7f3
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"{timestamp}_{random_suffix}"
    
    
    def _get_audio_file_from_ingest(self, ingest_result: Dict) -> str:
        """Bezpieczny accessor dla audio file z ingest_result"""
        # Sprawdź różne możliwe klucze
        possible_keys = ['audio_normalized', 'audio_raw', 'audio_file', 'audio_path', 'output_audio', 'audio']
        for key in possible_keys:
            if key in ingest_result:
                return ingest_result[key]
        
        # Fallback - rzuć błąd z informacją o dostępnych kluczach
        available = list(ingest_result.keys())
        raise KeyError(f"Nie znaleziono klucza audio w ingest_result. Dostępne klucze: {available}")

    def set_progress_callback(self, callback: Callable[[str, int, str], None]):
        """
        Ustaw callback dla progress updates
        callback(stage_name, percent, message)
        """
        self.progress_callback = callback
    
    def cancel(self):
        """Anuluj przetwarzanie"""
        self._cancelled = True
        for stage in self.stages.values():
            if hasattr(stage, 'cancel'):
                stage.cancel()
    
    def _check_cancelled(self):
        """Sprawdź czy anulowano"""
        if self._cancelled:
            raise InterruptedError("Processing cancelled by user")
    
    def _report_progress(self, stage: str, percent: int, message: str):
        """Raportuj progress"""
        if self.progress_callback:
            self.progress_callback(stage, percent, message)
    
    def _create_session_directory(self, input_file: str) -> Path:
        """
        DEPRECATED - używaj _create_session_directory_with_run_id()
        Zachowane dla backward compatibility
        """
        return self._create_session_directory_with_run_id(input_file)

    def _create_session_directory_with_run_id(self, input_file: str) -> Path:
        """
        Utwórz katalog dla tej sesji przetwarzania z RUN_ID

        Format: temp/{RUN_ID}_{input_name}/

        Przykład: temp/20250115_143052_a7f3_sejm_2025_01_12/
        """
        if not self.run_id:
            raise RuntimeError("RUN_ID not initialized - call _generate_run_id() first")

        input_name = Path(input_file).stem

        session_name = f"{self.run_id}_{input_name}"
        session_dir = self.config.temp_dir / session_name
        session_dir.mkdir(parents=True, exist_ok=True)

        print(f"📁 Session directory: {session_dir}")

        return session_dir
    
    def _generate_youtube_title(self, selection_result: Dict) -> str:
        """Generuj clickbaitowy tytuł z nazwiskami polityków"""
        clips = selection_result['clips']
        date_str = datetime.now().strftime('%d.%m.%Y')
        
        # Zbierz wszystkie keywords
        all_keywords = []
        politician_names = []
        
        for clip in clips[:5]:  # Top 5 klipów
            keywords = clip.get('keywords', [])
            
            for kw in keywords:
                kw_lower = kw.lower()
                
                # Lista nazwisk polityków
                politicians = [
                    'tusk', 'kaczyński', 'kaczyńskiego', 'morawiecki', 'morawieckiego',
                    'hołownia', 'hołowni', 'bosak', 'bosaka', 'czarnek', 'czarnka',
                    'kosiniak', 'kosiniak-kamysz', 'budka', 'budki', 'sienkiewicz',
                    'duda', 'dudy', 'ziobro', 'ziobry', 'fogiel', 'fogiela'
                ]
                
                # Sprawdź czy to nazwisko
                is_politician = any(pol in kw_lower for pol in politicians)
                
                if is_politician and kw not in politician_names:
                    politician_names.append(kw.capitalize())
                elif kw not in all_keywords:
                    all_keywords.append(kw)
        
        # Buduj tytuł (language-aware and generic)
        if len(politician_names) >= 2:
            # Two personalities/speakers - generic format
            title = f"🔥 {politician_names[0]} VS {politician_names[1]} - {date_str}"
        elif len(politician_names) == 1:
            # One personality - generic format
            if self.config.language == "pl":
                title = f"💥 {politician_names[0]} - Najgorętsze Momenty | {date_str}"
            else:
                title = f"💥 {politician_names[0]} - Best Moments | {date_str}"
        elif len(all_keywords) >= 2:
            # Keywords (topics)
            title = f"⚡ {all_keywords[0].title()} vs {all_keywords[1].title()} | {date_str}"
        else:
            # Fallback - generic highlights
            if self.config.language == "pl":
                title = f"🎯 Najlepsze Momenty | {date_str}"
            else:
                title = f"🎯 Best Moments | {date_str}"
        
        # YouTube limit
        if len(title) > 100:
            title = title[:97] + "..."
        
        return title
    
    def process(self, input_file: str) -> Dict[str, Any]:
            """
            Główna metoda przetwarzania z mechanizmem single-flight

            Returns:
                Dict z wynikami i metadanymi

            Raises:
                RuntimeError: Jeśli pipeline już działa (single-flight violation)
            """
            # === SINGLE-FLIGHT CHECK ===
            with PipelineProcessor._global_lock:
                if PipelineProcessor._is_running:
                    error_msg = (
                        f"⚠️ PIPELINE ALREADY RUNNING!\n"
                        f"Current RUN_ID: {PipelineProcessor._current_run_id}\n"
                        f"Ignoring duplicate start request to prevent conflicts."
                    )
                    print(error_msg)
                    raise RuntimeError("Pipeline already running - duplicate start prevented")

                # Mark jako running
                PipelineProcessor._is_running = True

                # Generuj unikalny RUN_ID dla tej sesji
                self.run_id = self._generate_run_id()
                PipelineProcessor._current_run_id = self.run_id

                print(f"\n{'='*80}")
                print(f"🚀 PIPELINE START - RUN_ID: {self.run_id}")
                print(f"{'='*80}\n")

            start_time = time.time()

            try:
                # Validate input
                input_path = Path(input_file)
                if not input_path.exists():
                    raise FileNotFoundError(f"Plik nie istnieje: {input_file}")

                # Create session directory z RUN_ID
                self.session_dir = self._create_session_directory_with_run_id(input_file)

                self._report_progress("Initialize", 0, f"Inicjalizacja... [RUN_ID: {self.run_id}]")
                
                # === ETAP 1: Ingest & Preprocessing ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 1/7 - Ingest [RUN_ID: {self.run_id}]")
                self._report_progress("Stage 1/7", 5, f"Audio extraction i normalizacja... [RUN_ID: {self.run_id}]")

                ingest_result = self.stages['ingest'].process(
                    input_file=input_file,
                    output_dir=self.session_dir
                )

                source_duration = ingest_result['metadata']['duration']
                self.timing_stats['ingest'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 1/7", 14, f"✅ Audio extraction zakończony [RUN_ID: {self.run_id}]")

                # === CACHE: Inicjalizacja cache key ===
                self.cache_manager.initialize_cache_key(input_file, self.config)

                # === HIGHLIGHT PACKER: Wstępna analiza strategii pakowania ===
                # (Faktyczne pakowanie nastąpi PO Stage 6 - Selection)
                packing_plan = None
                if self.highlight_packer and source_duration >= self.config.packer.min_duration_for_split:
                    print("\n📦 Materiał kwalifikuje się do pakowania w części - analiza strategii...")

                    # Pobierz opcjonalne overrides z config (jeśli są)
                    override_parts = getattr(self.config.packer, 'force_num_parts', None)
                    override_target_mins = getattr(self.config.packer, 'target_part_minutes', None)

                    # Wylicz plan pakowania RAZ (single source of truth!)
                    packing_plan = self.highlight_packer.calculate_packing_strategy(
                        source_duration,
                        override_parts=override_parts,
                        override_target_minutes=override_target_mins
                    )

                    # Dostosuj config selection do planu (z wyjaśnieniem DLACZEGO)
                    original_target = self.config.selection.target_total_duration
                    if packing_plan.total_target_duration != original_target:
                        change_reason = (
                            f"HighlightPacker dostosował target duration: {original_target}s → {packing_plan.total_target_duration}s\n"
                            f"   Powód: Materiał {source_duration/3600:.1f}h wymaga {packing_plan.num_parts} części "
                            f"po ~{packing_plan.target_duration_per_part/60:.0f}min każda dla optymalnej retencji"
                        )
                        print(f"\n⚙️  {change_reason}")
                        packing_plan._config_change_reason = change_reason  # Zapisz do późniejszego wyświetlenia
                        self.config.selection.target_total_duration = packing_plan.total_target_duration
                
                # === ETAP 2: VAD (Voice Activity Detection) ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 2/7 - VAD [RUN_ID: {self.run_id}]")

                # Check cache
                if self.cache_manager.is_cache_valid('vad'):
                    print("✅ Cache hit: VAD - ładowanie z cache...")
                    vad_result = self.cache_manager.load_from_cache('vad')
                    self.timing_stats['vad'] = "0s (cache)"
                    self._report_progress("Stage 2/7", 28, f"✅ VAD załadowany z cache [RUN_ID: {self.run_id}]")
                else:
                    print("⚠️ Cache miss: VAD - wykonywanie stage...")
                    self._report_progress("Stage 2/7", 20, f"Voice Activity Detection... [RUN_ID: {self.run_id}]")

                    vad_result = self.stages['vad'].process(
                        audio_file=self._get_audio_file_from_ingest(ingest_result),
                        output_dir=self.session_dir
                    )

                    # Save to cache
                    self.cache_manager.save_to_cache(vad_result, 'vad')

                    self.timing_stats['vad'] = self._format_duration(time.time() - stage_start)
                    self._report_progress("Stage 2/7", 28, f"✅ VAD zakończony [RUN_ID: {self.run_id}]")
                
                # === ETAP 3: ASR/Transcribe (Whisper) ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 3/7 - Transcribe [RUN_ID: {self.run_id}]")

                # Check cache
                if self.cache_manager.is_cache_valid('transcribe'):
                    print("✅ Cache hit: Transcribe - ładowanie z cache...")
                    transcribe_result = self.cache_manager.load_from_cache('transcribe')
                    self.timing_stats['transcribe'] = "0s (cache)"
                    self._report_progress("Stage 3/7", 50, f"✅ Transkrypcja załadowana z cache [RUN_ID: {self.run_id}]")
                else:
                    print("⚠️ Cache miss: Transcribe - wykonywanie stage...")
                    self._report_progress("Stage 3/7", 30, f"Transkrypcja audio (Whisper)... [RUN_ID: {self.run_id}]")

                    transcribe_result = self.stages['transcribe'].process(
                        audio_file=self._get_audio_file_from_ingest(ingest_result),
                        vad_segments=vad_result['segments'],
                        output_dir=self.session_dir
                    )

                    # Save to cache
                    self.cache_manager.save_to_cache(transcribe_result, 'transcribe')

                    self.timing_stats['transcribe'] = self._format_duration(time.time() - stage_start)
                    self._report_progress("Stage 3/7", 50, f"✅ Transkrypcja zakończona [RUN_ID: {self.run_id}]")
                
                # === ETAP 4: Feature Extraction ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 4/7 - Features [RUN_ID: {self.run_id}]")
                self._report_progress("Stage 4/7", 52, f"Ekstrakcja features... [RUN_ID: {self.run_id}]")

                features_result = self.stages['features'].process(
                    audio_file=self._get_audio_file_from_ingest(ingest_result),
                    segments=transcribe_result['segments'],
                    output_dir=self.session_dir
                )

                self.timing_stats['features'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 4/7", 60, f"✅ Features ekstrahowane [RUN_ID: {self.run_id}]")
                
                # === ETAP 5: Scoring (GPT) ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 5/7 - Scoring [RUN_ID: {self.run_id}]")

                # Check cache
                if self.cache_manager.is_cache_valid('scoring'):
                    print("✅ Cache hit: Scoring - ładowanie z cache...")
                    scoring_result = self.cache_manager.load_from_cache('scoring')
                    self.timing_stats['scoring'] = "0s (cache)"
                    self._report_progress("Stage 5/7", 75, f"✅ Scoring załadowany z cache [RUN_ID: {self.run_id}]")
                else:
                    print("⚠️ Cache miss: Scoring - wykonywanie stage...")
                    self._report_progress("Stage 5/7", 62, f"Scoring segmentów (GPT-4)... [RUN_ID: {self.run_id}]")

                    scoring_result = self.stages['scoring'].process(
                        segments=features_result['segments'],
                        output_dir=self.session_dir
                    )

                    # Save to cache
                    self.cache_manager.save_to_cache(scoring_result, 'scoring')

                    self.timing_stats['scoring'] = self._format_duration(time.time() - stage_start)
                    self._report_progress("Stage 5/7", 75, f"✅ Scoring zakończony [RUN_ID: {self.run_id}]")
                
                # === ETAP 6: Selection (wybór top klipów) ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 6/7 - Selection [RUN_ID: {self.run_id}]")
                self._report_progress("Stage 6/7", 77, f"Selekcja najlepszych klipów... [RUN_ID: {self.run_id}]")

                # Użyj threshold z planu pakowania (jeśli istnieje)
                min_score = packing_plan.min_score_threshold if packing_plan else 0.0  # Bez filtrowania gdy brak planu

                selection_result = self.stages['selection'].process(
                    segments=scoring_result['segments'],
                    total_duration=source_duration,
                    output_dir=self.session_dir,
                    min_score=min_score
                )

                self.timing_stats['selection'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 6/7", 85, f"✅ Wybrano {len(selection_result['clips'])} klipów [RUN_ID: {self.run_id}]")

                # === HIGHLIGHT PACKER: Pakowanie selected_clips do części ===
                # (FLOW: Stage 6 selected_clips → HighlightPacker → Stage 7 Export per part)
                parts_metadata = None
                if packing_plan:
                    print(f"\n📦 Pakowanie {len(selection_result['clips'])} klipów do {packing_plan.num_parts} części...")
                    parts = self.highlight_packer.split_clips_into_parts(
                        selection_result['clips'],
                        packing_plan.num_parts,
                        packing_plan.target_duration_per_part
                    )

                    # Generuj metadata premier dla każdej części (generic, language-aware base title)
                    base_date = datetime.now() + timedelta(days=self.config.packer.first_premiere_days_offset)

                    # Generic base title (language-aware, no hardcoded parliamentary content)
                    if self.config.language == "pl":
                        base_title = "Najlepsze Momenty"
                    else:
                        base_title = "Best Moments"

                    parts_metadata = self.highlight_packer.generate_part_metadata(
                        parts,
                        base_title,
                        base_date=base_date
                    )

                    # Wypełnij plan pakowania metadata (single source of truth!)
                    packing_plan.parts_metadata = parts_metadata

                    # Pokaż FINALNY plan pakowania (RAZ, z harmonogramem premier!)
                    self.highlight_packer.print_packing_summary(packing_plan)
                
                # === ETAP 7: Export (dla każdej części lub pojedynczy) ===
                print(f"\n📌 STAGE 7/7 - Export [RUN_ID: {self.run_id}]")
                export_results = []
                thumbnail_results = []

                if parts_metadata:
                    # Multi-part export
                    for part_meta in parts_metadata:
                        print(f"\n🎬 Eksport części {part_meta['part_number']}/{part_meta['total_parts']}... [RUN_ID: {self.run_id}]")
                        
                        # Export video
                        part_export = self.stages['export'].process(
                            input_file=input_file,
                            clips=part_meta['clips'],
                            segments=scoring_result['segments'],
                            output_dir=self.config.output_dir,
                            session_dir=self.session_dir,
                            part_number=part_meta['part_number']  # ✅ Przekazanie numeru części
                        )
                        export_results.append(part_export)
                        
                        # Generate thumbnail z numerem części
                        if hasattr(self, 'thumbnail_stage'):
                            part_thumbnail = self._generate_thumbnail_with_part_number(
                                part_export['output_file'],
                                part_meta['part_number'],
                                part_meta['total_parts']
                            )
                            thumbnail_results.append(part_thumbnail)
                else:
                    # Single export (standardowy)
                    print(f"🎬 Eksport pojedynczego filmu... [RUN_ID: {self.run_id}]")
                    export_result = self.stages['export'].process(
                        input_file=input_file,
                        clips=selection_result['clips'],
                        segments=scoring_result['segments'],
                        output_dir=self.config.output_dir,
                        session_dir=self.session_dir
                    )
                    export_results.append(export_result)
                    
                    # Standard thumbnail
                    if hasattr(self, 'thumbnail_stage'):
                        thumbnail_result = self._generate_standard_thumbnail(export_result['output_file'], selection_result['clips'])
                        thumbnail_results.append(thumbnail_result)
                
                # === ETAP 9: YouTube Upload (dla każdej części z premiere scheduling) ===
                youtube_results = []
                if self.config.youtube.enabled:
                    from .stage_09_youtube import YouTubeStage
                    youtube_stage = YouTubeStage(self.config)
                    youtube_stage.authorize()
                    
                    if parts_metadata:
                        # Multi-part upload z premiere scheduling
                        for i, part_meta in enumerate(parts_metadata):
                            print(f"\n📤 Upload części {part_meta['part_number']}/{part_meta['total_parts']}...")
                            
                            # Generuj enhanced title
                            video_title = self.highlight_packer.generate_enhanced_title(
                                part_meta,
                                part_meta['clips'],
                                use_politicians=self.config.packer.use_politicians_in_titles
                            )
                            
                            # Determine privacy/premiere status
                            premiere_datetime = datetime.fromisoformat(part_meta['premiere_datetime'])
                            
                            if self.config.youtube.schedule_as_premiere:
                                # Schedule as premiere
                                youtube_result = youtube_stage.schedule_premiere(
                                    video_file=export_results[i]['output_file'],
                                    thumbnail_file=thumbnail_results[i].get('thumbnail_path') if thumbnail_results else None,
                                    title=video_title,
                                    clips=part_meta['clips'],
                                    segments=scoring_result['segments'],
                                    output_dir=self.config.output_dir,
                                    premiere_datetime=premiere_datetime
                                )
                            else:
                                # Upload unlisted/private
                                youtube_result = youtube_stage.process(
                                    video_file=export_results[i]['output_file'],
                                    thumbnail_file=thumbnail_results[i].get('thumbnail_path') if thumbnail_results else None,
                                    title=video_title,
                                    clips=part_meta['clips'],
                                    segments=scoring_result['segments'],
                                    output_dir=self.config.output_dir,
                                    privacy_status='unlisted'
                                )
                            
                            youtube_results.append(youtube_result)
                    else:
                        # Single upload (standardowy)
                        video_title = self._generate_youtube_title(selection_result)
                        youtube_result = youtube_stage.process(
                            video_file=export_results[0]['output_file'],
                            thumbnail_file=thumbnail_results[0].get('thumbnail_path') if thumbnail_results else None,
                            title=video_title,
                            clips=selection_result['clips'],
                            segments=scoring_result['segments'],
                            output_dir=self.config.output_dir,
                            privacy_status=self.config.youtube.privacy_status
                        )
                        youtube_results.append(youtube_result)
                
                # === ETAP 10: YouTube Shorts Generation (optional) ===
                shorts_results = []
                shorts_clips_list = selection_result.get('shorts_clips', [])

                # Validation: prevent double invocation and empty list processing
                if self.config.shorts.enabled and shorts_clips_list:
                    # Check if shorts already generated (prevent double run)
                    if hasattr(self, '_shorts_generated') and self._shorts_generated:
                        print("\n⚠️ Shorts already generated, skipping duplicate generation")
                    else:
                        self._check_cancelled()
                        stage_start = time.time()
                        self._report_progress("Stage 8/8", 95, "Generowanie YouTube Shorts...")

                        print(f"\n🎬 Starting Shorts generation with {len(shorts_clips_list)} candidates...")

                        from .stage_10_shorts import ShortsStage
                        shorts_stage = ShortsStage(self.config)

                        shorts_result = shorts_stage.process(
                            input_file=input_file,
                            shorts_clips=shorts_clips_list,
                            segments=scoring_result['segments'],
                            output_dir=self.config.output_dir,
                            session_dir=self.session_dir,
                            template=self.config.shorts.default_template  # Przekaż wybrany szablon
                        )

                        shorts_results = shorts_result.get('shorts', [])
                        self.timing_stats['shorts'] = self._format_duration(time.time() - stage_start)
                        self._report_progress("Stage 8/8", 98, f"✅ Wygenerowano {len(shorts_results)} Shorts")

                        # Mark as generated to prevent double run
                        self._shorts_generated = True

                        # Optional: Upload Shorts to YouTube
                        if self.config.shorts.upload_to_youtube and self.config.youtube.enabled and shorts_results:
                            print("\n📤 Upload Shorts na YouTube...")
                            from .stage_09_youtube import YouTubeStage
                            youtube_stage = YouTubeStage(self.config)
                            youtube_stage.authorize()

                            for short_meta in shorts_results:
                                try:
                                    # Upload as Short (dodaj #Shorts w tytule)
                                    short_title = short_meta['title']
                                    if self.config.shorts.add_hashtags and '#Shorts' not in short_title:
                                        short_title += " #Shorts"

                                    upload_result = youtube_stage.upload_video(
                                        video_file=short_meta['file'],
                                        title=short_title,
                                        description=short_meta['description'],
                                        tags=short_meta['tags'],
                                        category_id=self.config.shorts.shorts_category_id,
                                        privacy_status='unlisted'  # lub 'public'
                                    )

                                    if upload_result.get('success'):
                                        short_meta['youtube_url'] = upload_result['video_url']
                                        print(f"   ✅ Short uploaded: {upload_result['video_url']}")

                                except Exception as e:
                                    print(f"   ⚠️ Błąd uploadu Short: {e}")

                elif self.config.shorts.enabled and not shorts_clips_list:
                    print("\n⚠️ Shorts enabled but no clips available (selection returned empty list)")
                    print("   → Check if scored segments have sufficient scores for shorts")
                
                # === Finalize result ===
                result = {
                    'success': True,
                    'run_id': self.run_id,
                    'input_file': input_file,
                    'export_results': export_results,
                    'youtube_results': youtube_results,
                    'shorts_results': shorts_results,
                    'packing_plan': packing_plan,  # Renamed from 'split_plan'
                    'parts_metadata': parts_metadata,
                    'timing': self.timing_stats
                }

                print(f"\n{'='*80}")
                print(f"✅ PIPELINE COMPLETE - RUN_ID: {self.run_id}")
                print(f"Total time: {self._format_duration(time.time() - start_time)}")
                print(f"{'='*80}\n")

                return result

            except InterruptedError:
                self._report_progress("Cancelled", 0, f"Anulowano przez użytkownika [RUN_ID: {self.run_id}]")
                raise
            except Exception as e:
                self._report_progress("Error", 0, f"Błąd: {str(e)} [RUN_ID: {self.run_id}]")
                raise
            finally:
                # === ZWOLNIJ LOCK - KONIEC SINGLE-FLIGHT ===
                with PipelineProcessor._global_lock:
                    PipelineProcessor._is_running = False
                    PipelineProcessor._current_run_id = None
                    print(f"🔓 Pipeline lock released [RUN_ID: {self.run_id}]")
    
    def _cleanup_temp_files(self):
        """Usuń pliki tymczasowe"""
        if self.session_dir and self.session_dir.exists():
            import shutil
            try:
                shutil.rmtree(self.session_dir)
                self._report_progress("Cleanup", 0, "Usunięto pliki tymczasowe")
            except Exception as e:
                print(f"⚠️ Nie udało się usunąć temp files: {e}")
    
    def _build_metadata(
        self, 
        input_file: str,
        export_result: Dict,
        selection_result: Dict,
        ingest_result: Dict
    ) -> Dict[str, Any]:
        """Zbuduj kompletne metadata"""
        return {
            'source': {
                'file': Path(input_file).name,
                'path': input_file,
                'duration': ingest_result['metadata']['duration'],
                'resolution': f"{ingest_result['metadata']['width']}x{ingest_result['metadata']['height']}",
                'fps': ingest_result['metadata']['fps'],
                'date_processed': datetime.now().isoformat()
            },
            'output': {
                'file': Path(export_result['output_file']).name,
                'path': export_result['output_file'],
                'duration': selection_result['total_duration'],
                'num_clips': len(selection_result['clips']),
                'format': "H.264/AAC, MP4"
            },
            'processing': {
                'config': self.config.to_dict(),
                'timing': self.timing_stats,
                'stages_completed': list(self.timing_stats.keys())
            }
        }
    
    def _save_summary(self, result: Dict[str, Any]):
        """Zapisz podsumowanie do JSON"""
        summary_file = self.config.output_dir / f"summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Prepare serializable data
        summary = {
            'input_file': result['input_file'],
            'output_file': result['output_file'],
            'youtube_url': result.get('youtube_url'),
            'statistics': {
                'original_duration': result['original_duration'],
                'output_duration': result['output_duration'],
                'num_clips': result['num_clips'],
                'compression_ratio': f"{(result['num_clips'] * 150) / 14400:.1%}"  # Approx
            },
            'clips': [
                {
                    'id': clip['id'],
                    'timestamp_in_source': f"{self._format_timestamp(clip['t0'])} - {self._format_timestamp(clip['t1'])}",
                    'duration': f"{clip['duration']:.1f}s",
                    'title': clip.get('title', 'N/A'),
                    'score': f"{clip.get('score', 0):.2f}",
                    'keywords': clip.get('keywords', [])
                }
                for clip in result['clips']
            ],
            'timing': result['timing'],
            'date': datetime.now().isoformat()
        }
        
        with open(summary_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        print(f"📄 Summary zapisany: {summary_file}")
    
    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration to human readable"""
        td = timedelta(seconds=int(seconds))
        hours = td.seconds // 3600
        minutes = (td.seconds % 3600) // 60
        secs = td.seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def _generate_thumbnail_with_part_number(
        self, 
        video_file: str, 
        part_num: int, 
        total_parts: int
    ) -> Dict:
        """Generuj thumbnail z numerem części"""
        from .stage_08_thumbnail import ThumbnailStage
        
        if not hasattr(self, 'thumbnail_stage'):
            self.thumbnail_stage = ThumbnailStage(self.config)
        
        thumbnail_result = self.thumbnail_stage.generate_with_part_number(
            video_file=video_file,
            part_number=part_num,
            total_parts=total_parts
        )
        
        return thumbnail_result
    
    def _generate_standard_thumbnail(self, video_file: str, clips: list) -> Dict:
        """Generuj standardową thumbnail"""
        from .stage_08_thumbnail import ThumbnailStage
        
        if not hasattr(self, 'thumbnail_stage'):
            self.thumbnail_stage = ThumbnailStage(self.config)
        
        thumbnail_result = self.thumbnail_stage.process(
            video_file=video_file,
            clips=clips,
            output_dir=self.config.output_dir
        )
        
        return thumbnail_result


class ProcessingError(Exception):
    """Custom exception dla błędów przetwarzania"""
    pass