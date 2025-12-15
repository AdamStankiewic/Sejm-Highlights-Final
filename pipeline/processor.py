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
from .smart_splitter import SmartSplitter
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


                # Smart Splitter
        self.smart_splitter = None
        if hasattr(config, 'splitter') and config.splitter.enabled:
            self.smart_splitter = SmartSplitter(
                premiere_hour=config.splitter.premiere_hour,
                premiere_minute=config.splitter.premiere_minute
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
        
        # Buduj tytuł
        if len(politician_names) >= 2:
            # Starcie nazwisk
            title = f"🔥 {politician_names[0]} VS {politician_names[1]} - Posiedzenie Sejmu {date_str}"
        elif len(politician_names) == 1:
            # Jedno nazwisko
            title = f"💥 {politician_names[0]} w Sejmie - Najgorętsze Momenty {date_str}"
        elif len(all_keywords) >= 2:
            # Keywords bez nazwisk
            title = f"⚡ Sejm: {all_keywords[0]} vs {all_keywords[1]} | {date_str}"
        else:
            # Fallback - ogólny
            title = f"🎯 Posiedzenie Sejmu - Gorące Momenty {date_str}"
        
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
                
                # === SMART SPLITTER: Analiza strategii podziału ===
                split_strategy = None
                if self.smart_splitter and source_duration >= self.config.splitter.min_duration_for_split:
                    print("\n🤖 Wykryto długi materiał - uruchamiam Smart Splitter...")
                    split_strategy = self.smart_splitter.calculate_split_strategy(source_duration)
                    self.smart_splitter.print_split_summary(split_strategy, [])
                    
                    # Dostosuj parametry selection do strategii
                    original_target = self.config.selection.target_total_duration
                    self.config.selection.target_total_duration = split_strategy['total_target_duration']
                    print(f"📊 Dostosowano target duration: {original_target}s → {split_strategy['total_target_duration']}s")
                
                # === ETAP 2: VAD (Voice Activity Detection) ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 2/7 - VAD [RUN_ID: {self.run_id}]")
                self._report_progress("Stage 2/7", 20, f"Voice Activity Detection... [RUN_ID: {self.run_id}]")

                vad_result = self.stages['vad'].process(
                    audio_file=self._get_audio_file_from_ingest(ingest_result),
                    output_dir=self.session_dir
                )

                self.timing_stats['vad'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 2/7", 28, f"✅ VAD zakończony [RUN_ID: {self.run_id}]")
                
                # === ETAP 3: ASR/Transcribe (Whisper) ===
                self._check_cancelled()
                stage_start = time.time()
                print(f"\n📌 STAGE 3/7 - Transcribe [RUN_ID: {self.run_id}]")
                self._report_progress("Stage 3/7", 30, f"Transkrypcja audio (Whisper)... [RUN_ID: {self.run_id}]")

                transcribe_result = self.stages['transcribe'].process(
                    audio_file=self._get_audio_file_from_ingest(ingest_result),
                    vad_segments=vad_result['segments'],
                    output_dir=self.session_dir
                )

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
                self._report_progress("Stage 5/7", 62, f"Scoring segmentów (GPT-4)... [RUN_ID: {self.run_id}]")

                scoring_result = self.stages['scoring'].process(
                    segments=features_result['segments'],
                    output_dir=self.session_dir
                )

                self.timing_stats['scoring'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 5/7", 75, f"✅ Scoring zakończony [RUN_ID: {self.run_id}]")
                
                # === ETAP 6: Selection (wybór top klipów) ===
                self._check_cancelled()
                stage_start = time.time()
                self._report_progress("Stage 6/7", 77, "Selekcja najlepszych klipów...")
                
                # Jeśli jest split_strategy lub slider threshold, użyj najwyższego progu
                gui_threshold = getattr(self.config.selection, 'min_score_threshold', 0.0)
                min_score = max(split_strategy['min_score_threshold'] if split_strategy else 0.0, gui_threshold)
                
                selection_result = self.stages['selection'].process(
                    segments=scoring_result['segments'],
                    total_duration=source_duration,
                    output_dir=self.session_dir,
                    min_score=min_score
                )

                self.timing_stats['selection'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 6/7", 85, f"✅ Wybrano {len(selection_result['clips'])} klipów")

                if not selection_result['clips']:
                    warning_msg = "Brak klipów – obniż próg lub podłącz chat.json."
                    print(f"⚠️ {warning_msg}")
                    return {
                        'clips': [],
                        'shorts_clips': selection_result.get('shorts_clips', []),
                        'message': warning_msg,
                        'export_results': [],
                    }
                
                # === Po stage 6 (Selection): Podział na części jeśli potrzebny ===
                parts_metadata = None
                if split_strategy:
                    print("\n✂️ Dzielę klipy na części...")
                    parts = self.smart_splitter.split_clips_into_parts(
                        selection_result['clips'],
                        split_strategy['num_parts'],
                        split_strategy['target_duration_per_part']
                    )
                    
                    # Generuj metadata dla każdej części
                    base_date = datetime.now() + timedelta(days=self.config.splitter.first_premiere_days_offset)
                    parts_metadata = self.smart_splitter.generate_part_metadata(
                        parts,
                        "Gorące Momenty Sejmu",
                        base_date=base_date
                    )
                    
                    self.smart_splitter.print_split_summary(split_strategy, parts_metadata)
                
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
                            video_title = self.smart_splitter.generate_enhanced_title(
                                part_meta,
                                part_meta['clips'],
                                use_politicians=self.config.splitter.use_politicians_in_titles
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
                if self.config.shorts.enabled and selection_result.get('shorts_clips'):
                    self._check_cancelled()
                    stage_start = time.time()
                    self._report_progress("Stage 8/8", 95, "Generowanie YouTube Shorts...")
                    
                    from .stage_10_shorts import ShortsStage
                    shorts_stage = ShortsStage(self.config)

                    shorts_result = shorts_stage.process(
                        input_file=input_file,
                        shorts_clips=selection_result['shorts_clips'],
                        segments=scoring_result['segments'],
                        output_dir=self.config.output_dir,
                        session_dir=self.session_dir,
                        template=getattr(self.config.shorts, 'template', 'gaming')
                    )
                    
                    shorts_results = shorts_result.get('shorts', [])
                    self.timing_stats['shorts'] = self._format_duration(time.time() - stage_start)
                    self._report_progress("Stage 8/8", 98, f"✅ Wygenerowano {len(shorts_results)} Shorts")
                    
                    # Optional: Upload Shorts to YouTube
                    if self.config.shorts.upload_to_youtube and self.config.youtube.enabled:
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
                
                # === Finalize result ===
                result = {
                    'success': True,
                    'run_id': self.run_id,
                    'input_file': input_file,
                    'export_results': export_results,
                    'youtube_results': youtube_results,
                    'shorts_results': shorts_results,
                    'split_strategy': split_strategy,
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