"""
Main Pipeline Processor
Orchestruje wszystkie etapy przetwarzania (7 głównych + opcjonalnie YouTube)
"""

import time
import json
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
    """

    def __init__(self, config: Config, upload_profile: Optional[str] = None, use_queue: bool = False):
        """
        Initialize pipeline processor

        Args:
            config: Pipeline configuration
            upload_profile: Optional upload profile name ('sejm', 'stream', etc.)
                          If None, auto-detects or uses default
            use_queue: If True, add videos to Upload Queue instead of immediate upload
        """
        self.config = config
        self.config.validate()

        # Upload profile for YouTube
        self.upload_profile = upload_profile

        # Upload Queue mode
        self.use_queue = use_queue
        self.upload_queue = None
        if use_queue:
            from .upload_queue import UploadQueue
            self.upload_queue = UploadQueue()

        # Progress callback
        self.progress_callback: Optional[Callable] = None

        # Cancellation flag
        self._cancelled = False

        # Timing stats
        self.timing_stats = {}
        
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
        """Utwórz katalog dla tej sesji przetwarzania"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        input_name = Path(input_file).stem
        
        session_name = f"{input_name}_{timestamp}"
        session_dir = self.config.temp_dir / session_name
        session_dir.mkdir(parents=True, exist_ok=True)
        
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

    def _add_to_upload_queue(self, video_file: str, title: str, description: str,
                            tags: List[str], video_type: str = "main",
                            thumbnail_file: Optional[str] = None) -> str:
        """Add video to upload queue"""
        from .upload_queue import QueueItem
        import uuid

        item = QueueItem(
            id=f"upload_{uuid.uuid4().hex[:8]}",
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            profile_name=self.upload_profile or "sejm",
            video_type=video_type,
            thumbnail_file=thumbnail_file,
            duration=None,  # Can be added if needed
            file_size=Path(video_file).stat().st_size if Path(video_file).exists() else None
        )

        item_id = self.upload_queue.add(item)
        print(f"   ✅ Dodano do Upload Queue: {item_id}")
        return item_id

    def process(self, input_file: str) -> Dict[str, Any]:
            """
            Główna metoda przetwarzania
            
            Returns:
                Dict z wynikami i metadanymi
            """
            start_time = time.time()
            
            try:
                # Validate input
                input_path = Path(input_file)
                if not input_path.exists():
                    raise FileNotFoundError(f"Plik nie istnieje: {input_file}")
                
                # Create session directory
                self.session_dir = self._create_session_directory(input_file)
                
                self._report_progress("Initialize", 0, "Inicjalizacja...")
                
                # === ETAP 1: Ingest & Preprocessing ===
                self._check_cancelled()
                stage_start = time.time()
                self._report_progress("Stage 1/7", 5, "Audio extraction i normalizacja...")
                
                ingest_result = self.stages['ingest'].process(
                    input_file=input_file,
                    output_dir=self.session_dir
                )
                
                source_duration = ingest_result['metadata']['duration']
                self.timing_stats['ingest'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 1/7", 14, "✅ Audio extraction zakończony")
                
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
                self._report_progress("Stage 2/7", 20, "Voice Activity Detection...")
                
                vad_result = self.stages['vad'].process(
                    audio_file=self._get_audio_file_from_ingest(ingest_result),
                    output_dir=self.session_dir
                )
                
                self.timing_stats['vad'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 2/7", 28, "✅ VAD zakończony")
                
                # === ETAP 3: ASR/Transcribe (Whisper) ===
                self._check_cancelled()
                stage_start = time.time()
                self._report_progress("Stage 3/7", 30, "Transkrypcja audio (Whisper)...")
                
                transcribe_result = self.stages['transcribe'].process(
                    audio_file=self._get_audio_file_from_ingest(ingest_result),
                    vad_segments=vad_result['segments'],
                    output_dir=self.session_dir
                )
                
                self.timing_stats['transcribe'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 3/7", 50, "✅ Transkrypcja zakończona")
                
                # === ETAP 4: Feature Extraction ===
                self._check_cancelled()
                stage_start = time.time()
                self._report_progress("Stage 4/7", 52, "Ekstrakcja features...")
                
                features_result = self.stages['features'].process(
                    audio_file=self._get_audio_file_from_ingest(ingest_result),
                    segments=transcribe_result['segments'],
                    output_dir=self.session_dir
                )
                
                self.timing_stats['features'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 4/7", 60, "✅ Features ekstrahowane")
                
                # === ETAP 5: Scoring (GPT) ===
                self._check_cancelled()
                stage_start = time.time()
                self._report_progress("Stage 5/7", 62, "Scoring segmentów (GPT-4)...")
                
                scoring_result = self.stages['scoring'].process(
                    segments=features_result['segments'],
                    output_dir=self.session_dir
                )
                
                self.timing_stats['scoring'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 5/7", 75, "✅ Scoring zakończony")
                
                # === ETAP 6: Selection (wybór top klipów) ===
                self._check_cancelled()
                stage_start = time.time()
                self._report_progress("Stage 6/7", 77, "Selekcja najlepszych klipów...")
                
                # Jeśli jest split_strategy, użyj wyższego threshold
                min_score = split_strategy['min_score_threshold'] if split_strategy else 0.0  # Bez filtrowania gdy brak strategii
                
                selection_result = self.stages['selection'].process(
                    segments=scoring_result['segments'],
                    total_duration=source_duration,
                    output_dir=self.session_dir,
                    min_score=min_score
                )
                
                self.timing_stats['selection'] = self._format_duration(time.time() - stage_start)
                self._report_progress("Stage 6/7", 85, f"✅ Wybrano {len(selection_result['clips'])} klipów")
                
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
                export_results = []
                thumbnail_results = []
                
                if parts_metadata:
                    # Multi-part export
                    for part_meta in parts_metadata:
                        print(f"\n🎬 Eksport części {part_meta['part_number']}/{part_meta['total_parts']}...")
                        
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
                    if self.use_queue:
                        # ADD TO QUEUE MODE
                        print("\n📋 Dodawanie filmów do Upload Queue...")

                        if parts_metadata:
                            # Multi-part - add each part to queue
                            for i, part_meta in enumerate(parts_metadata):
                                video_title = self.smart_splitter.generate_enhanced_title(
                                    part_meta,
                                    part_meta['clips'],
                                    use_politicians=self.config.splitter.use_politicians_in_titles
                                )

                                description = f"Posiedzenie Sejmu - Część {part_meta['part_number']}/{part_meta['total_parts']}"
                                tags = ["Sejm", "Polityka", "Polska", "Parliament"]

                                item_id = self._add_to_upload_queue(
                                    video_file=export_results[i]['output_file'],
                                    title=video_title,
                                    description=description,
                                    tags=tags,
                                    video_type="main",
                                    thumbnail_file=thumbnail_results[i].get('thumbnail_path') if thumbnail_results else None
                                )

                                youtube_results.append({'success': True, 'queue_id': item_id})
                        else:
                            # Single video - add to queue
                            video_title = self._generate_youtube_title(selection_result)
                            description = "Najlepsze momenty z posiedzenia Sejmu"
                            tags = ["Sejm", "Polityka", "Polska", "Parliament"]

                            item_id = self._add_to_upload_queue(
                                video_file=export_results[0]['output_file'],
                                title=video_title,
                                description=description,
                                tags=tags,
                                video_type="main",
                                thumbnail_file=thumbnail_results[0].get('thumbnail_path') if thumbnail_results else None
                            )

                            youtube_results.append({'success': True, 'queue_id': item_id})

                        print(f"✅ Dodano {len(youtube_results)} filmów do Upload Queue")

                    else:
                        # IMMEDIATE UPLOAD MODE
                        from .stage_09_youtube import YouTubeStage
                        youtube_stage = YouTubeStage(self.config, profile_name=self.upload_profile)
                        youtube_stage.authorize()

                        # Get profile settings for main videos
                        main_settings = youtube_stage.get_profile_settings('main')

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

                                # Determine privacy/premiere status from profile
                                premiere_datetime = datetime.fromisoformat(part_meta['premiere_datetime'])

                                if main_settings.get('schedule_as_premiere', False):
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
                                    # Upload with profile privacy settings
                                    youtube_result = youtube_stage.process(
                                        video_file=export_results[i]['output_file'],
                                        thumbnail_file=thumbnail_results[i].get('thumbnail_path') if thumbnail_results else None,
                                        title=video_title,
                                        clips=part_meta['clips'],
                                        segments=scoring_result['segments'],
                                        output_dir=self.config.output_dir,
                                        privacy_status=main_settings['privacy_status']
                                    )

                                # Add to playlist if specified in profile
                                if youtube_result.get('success') and main_settings.get('playlist_id'):
                                    youtube_stage.playlist_manager.add_video_to_playlist(
                                        main_settings['playlist_id'],
                                        youtube_result['video_id']
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
                                privacy_status=main_settings['privacy_status']
                            )

                            # Add to playlist if specified in profile
                            if youtube_result.get('success') and main_settings.get('playlist_id'):
                                youtube_stage.playlist_manager.add_video_to_playlist(
                                    main_settings['playlist_id'],
                                    youtube_result['video_id']
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
                        session_dir=self.session_dir
                    )
                    
                    shorts_results = shorts_result.get('shorts', [])
                    self.timing_stats['shorts'] = self._format_duration(time.time() - stage_start)
                    self._report_progress("Stage 8/8", 98, f"✅ Wygenerowano {len(shorts_results)} Shorts")
                    
                    # Optional: Upload Shorts to YouTube
                    if self.config.shorts.upload_to_youtube and self.config.youtube.enabled:
                        if self.use_queue:
                            # ADD SHORTS TO QUEUE MODE
                            print("\n📋 Dodawanie Shorts do Upload Queue...")

                            for short_meta in shorts_results:
                                short_title = short_meta['title']
                                if '#Shorts' not in short_title:
                                    short_title += " #Shorts"

                                item_id = self._add_to_upload_queue(
                                    video_file=short_meta['file'],
                                    title=short_title,
                                    description=short_meta['description'],
                                    tags=short_meta['tags'],
                                    video_type="shorts"
                                )

                                short_meta['queue_id'] = item_id

                            print(f"✅ Dodano {len(shorts_results)} Shorts do Upload Queue")

                        else:
                            # IMMEDIATE UPLOAD MODE
                            print("\n📤 Upload Shorts na YouTube...")
                            from .stage_09_youtube import YouTubeStage
                            shorts_youtube_stage = YouTubeStage(self.config, profile_name=self.upload_profile)
                            shorts_youtube_stage.authorize()

                            # Get profile settings for Shorts
                            shorts_settings = shorts_youtube_stage.get_profile_settings('shorts')

                            for short_meta in shorts_results:
                                try:
                                    # Upload as Short (dodaj #Shorts w tytule)
                                    short_title = short_meta['title']
                                    if shorts_settings.get('add_hashtags', False) and '#Shorts' not in short_title:
                                        short_title += " #Shorts"

                                    # Upload using profile settings
                                    upload_result = shorts_youtube_stage.upload_video(
                                        video_file=short_meta['file'],
                                        title=short_title,
                                        description=short_meta['description'],
                                        tags=short_meta['tags'],
                                        category_id=shorts_settings['category_id'],
                                        privacy_status=shorts_settings['privacy_status']
                                    )

                                    if upload_result.get('success'):
                                        short_meta['youtube_url'] = upload_result['video_url']
                                        print(f"   ✅ Short uploaded: {upload_result['video_url']}")

                                        # Add to playlist if specified in profile
                                        if shorts_settings.get('playlist_id'):
                                            shorts_youtube_stage.playlist_manager.add_video_to_playlist(
                                                shorts_settings['playlist_id'],
                                                upload_result['video_id']
                                            )

                                except Exception as e:
                                    print(f"   ⚠️ Błąd uploadu Short: {e}")
                
                # === Finalize result ===
                result = {
                    'success': True,
                    'input_file': input_file,
                    'export_results': export_results,
                    'youtube_results': youtube_results,
                    'shorts_results': shorts_results,
                    'split_strategy': split_strategy,
                    'parts_metadata': parts_metadata,
                    'timing': self.timing_stats
                }
                
                return result
                
            except InterruptedError:
                self._report_progress("Cancelled", 0, "Anulowano przez użytkownika")
                raise
            except Exception as e:
                self._report_progress("Error", 0, f"Błąd: {str(e)}")
                raise
    
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