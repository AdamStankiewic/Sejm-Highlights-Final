"""
Pipeline Configuration Manager
Zarządza wszystkimi parametrami przetwarzania
"""

import yaml
import os
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()


@dataclass
class AudioConfig:
    """Konfiguracja przetwarzania audio"""
    sample_rate: int = 16000
    channels: int = 1
    normalization: str = "ebu_r128"
    target_loudness: float = -16.0  # LUFS


@dataclass
class VADConfig:
    """Voice Activity Detection settings"""
    model: str = "silero_v4"
    threshold: float = 0.5
    min_speech_duration: float = 3.0
    min_silence_duration: float = 1.5
    max_segment_duration: float = 180.0  # 3 min hard limit


@dataclass
class ASRConfig:
    """Automatic Speech Recognition settings"""
    model: str = "large-v3"  # large-v3, medium, small
    compute_type: str = "float16"
    beam_size: int = 3
    language: str = "pl"
    condition_on_previous_text: bool = True
    temperature: list = None
    
    # Initial prompt dla lepszej accuracy nazwisk
    initial_prompt: str = """
    Posiedzenie Sejmu Rzeczypospolitej Polskiej.
    Posłowie: Donald Tusk, Jarosław Kaczyński, Szymon Hołownia,
    Krzysztof Bosak, Władysław Kosiniak-Kamysz, Przemysław Czarnek,
    Borys Budka, Bartłomiej Sienkiewicz, Radosław Fogiel.
    Tematy: budżet państwa, polityka zagraniczna, sprawy wewnętrzne.
    """
    
    batch_size: int = 10  # Liczba segmentów przetwarzanych jednocześnie
    
    def __post_init__(self):
        if self.temperature is None:
            self.temperature = [0.0, 0.2]


@dataclass
class FeatureConfig:
    """Feature engineering settings"""
    # Acoustic features
    compute_rms: bool = True
    compute_spectral_centroid: bool = True
    compute_spectral_flux: bool = True
    compute_zcr: bool = True
    
    # Prosodic features
    compute_speech_rate: bool = True
    compute_pitch_variance: bool = True
    compute_pause_analysis: bool = True
    
    # Lexical features
    keywords_file: str = "models/keywords.csv"
    compute_entity_density: bool = True
    
    # NLP model dla entity recognition
    spacy_model: str = "pl_core_news_lg"


@dataclass
class ScoringConfig:
    """AI Semantic Scoring settings"""
    # Pre-filtering
    prefilter_top_n: int = 40
    prefilter_keyword_threshold: float = 5.0
    
    # AI Model
    nli_model: str = "clarin-pl/roberta-large-nli"
    batch_size: int = 8
    device: int = 0  # GPU device ID, -1 dla CPU
    
    # Interest labels z wagami
    interest_labels: Dict[str, float] = None
    
    # Score weights (final composite)
    weight_acoustic: float = 0.25
    weight_keyword: float = 0.15
    weight_semantic: float = 0.50
    weight_speaker_change: float = 0.10
    
    # Position diversity bonus
    position_diversity_bonus: float = 0.1
    
    def __post_init__(self):
        if self.interest_labels is None:
            self.interest_labels = {
                "ostra polemika i wymiana oskarżeń między posłami": 2.2,
                "emocjonalna lub podniesiona wypowiedź": 1.7,
                "kontrowersyjne stwierdzenie lub oskarżenie": 2.0,
                "pytanie retoryczne lub zaczepka": 1.5,
                "konkretne fakty liczby i dane": 1.3,
                "humor sarkazm lub memiczny moment": 1.8,
                "przerwanie przemówienia lub reakcja sali": 1.6,
                "formalna procedura sejmowa": -2.5,
                "podziękowania i grzecznościowe formuły": -2.0,
                "odczytywanie regulaminu": -3.0
            }


@dataclass
class SelectionConfig:
    """Clip selection settings"""
    # Duration constraints
    min_clip_duration: float = 90.0
    max_clip_duration: float = 180.0
    target_total_duration: float = 900.0  # 15 min
    
    # Number of clips
    min_clips: int = 8
    max_clips: int = 15
    
    # Temporal constraints
    min_time_gap: float = 30.0  # Między klipami
    smart_merge_gap: float = 5.0  # Gap dla merge'owania
    smart_merge_min_score: float = 0.6
    
    # Coverage optimization
    position_bins: int = 5  # Fazy transmisji
    max_clips_per_bin: int = 4  # Max klipów z jednej fazy
    
    # Trimming
    enable_trimming: bool = True
    trim_percentage: float = 0.2
    duration_tolerance: float = 1.1  # 10% tolerance


@dataclass
class ExportConfig:
    """Video export settings"""
    # Video codec
    video_codec: str = "libx264"
    video_preset: str = "medium"  # ultrafast, fast, medium, slow
    crf: int = 21  # Quality (18-28, lower=better)
    
    # Audio codec
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    
    # Transitions
    add_transitions: bool = True
    title_card_duration: float = 3.0
    fade_in_duration: float = 0.5
    fade_out_duration: float = 0.5
    
    # Title card styling
    title_font: str = "Arial"
    title_fontsize: int = 48
    title_fontcolor: str = "white"
    title_bgcolor: str = "black"
    
    # Pre/post roll
    clip_preroll: float = 1.5
    clip_postroll: float = 1.0
    
    # Hardsub
    generate_hardsub: bool = False
    subtitle_fontsize: int = 28
    subtitle_style: str = "Bold=1,Outline=2,Shadow=1,MarginV=40"
    
    # Misc
    movflags: str = "+faststart"

@dataclass
class SmartSplitterConfig:
    enabled: bool = True
    premiere_hour: int = 18
    premiere_minute: int = 0
    min_duration_for_split: float = 3600.0
    use_politicians_in_titles: bool = True
    first_premiere_days_offset: int = 1


@dataclass
class YouTubeConfig:
    """YouTube Upload settings"""
    enabled: bool = False
    schedule_as_premiere: bool = True
    privacy_status: str = "unlisted"  # public, private, unlisted
    credentials_path: Optional[Path] = None
    channel_id: Optional[str] = None  # ← DODAJ TĘ LINIĘ
    category_id: str = "25"  # 25 = News & Politics
    language: str = "pl"
    tags: list = field(default_factory=lambda: ["sejm", "polska", "polityka", "highlights"])
    
    # Auto-generated metadata
    auto_title: bool = True
    auto_description: bool = True
    auto_tags: bool = True
    
    def __post_init__(self):
        # Convert string path to Path object
        if isinstance(self.credentials_path, str):
            self.credentials_path = Path(self.credentials_path)
        
        # Default credentials path
        if self.enabled and self.credentials_path is None:
            self.credentials_path = Path("client_secret.json")

@dataclass
class ShortsConfig:
    """YouTube Shorts generation settings"""
    enabled: bool = False

    # Selection criteria
    min_duration: float = 15.0  # Min 15s
    max_duration: float = 60.0  # Max 60s (YouTube limit)
    max_shorts_count: int = 10

    # Video format (9:16 vertical)
    width: int = 1080
    height: int = 1920

    # Timing
    pre_roll: float = 0.5
    post_roll: float = 0.5

    # Subtitles styling
    subtitle_fontsize: int = 48
    subtitle_position: str = "center"

    # Title overlay styling (displayed throughout entire Short)
    title_fontsize: int = 90  # Większy rozmiar dla tytułu (zwiększone z 72)
    title_color: str = "&H00FFFF"  # Żółty w ASS format (BGR: FFFF00)
    title_position_y: int = 230  # Pozycja Y od góry (piksel) - bezpieczna strefa
    title_outline: int = 5  # Grubość obrysu (zwiększone z 4)
    title_shadow: int = 3  # Cień (zwiększone z 2)
    title_bold: bool = True  # Pogrubienie

    # Upload settings
    upload_to_youtube: bool = False
    shorts_category_id: str = "25"
    add_hashtags: bool = True
    privacy_status: str = "unlisted"  # For backwards compatibility with old config.yml


@dataclass
class FrameSelectionConfig:
    """Frame selection settings for thumbnails"""
    strategy: str = "face_priority"  # face_priority, quality, center
    quality_check: bool = True
    search_window: int = 30  # frames to search around target


@dataclass
class ImageEnhancementsConfig:
    """Image enhancement settings for thumbnails"""
    contrast: float = 1.3
    saturation: float = 1.2
    sharpness: float = 1.1


@dataclass
class ThumbnailConfig:
    """Thumbnail generation settings"""
    enabled: bool = True
    width: int = 1280
    height: int = 720
    frame_selection: FrameSelectionConfig = None
    enhancements: ImageEnhancementsConfig = None
    templates: Dict[str, Dict[str, Any]] = None

    def __post_init__(self):
        if self.frame_selection is None:
            self.frame_selection = FrameSelectionConfig()

        if self.enhancements is None:
            self.enhancements = ImageEnhancementsConfig()

        if self.templates is None:
            # Default thumbnail templates
            self.templates = {
                'aggressive': {
                    'style': 'top_bottom',
                    'text_color': '#FFFF00',  # Yellow
                    'outline_color': '#FF0000',  # Red
                    'emoji': '🔥😡'
                },
                'sensational': {
                    'style': 'center',
                    'text_color': '#FFFFFF',  # White
                    'outline_color': '#000000',  # Black
                    'emoji': '😱💥'
                },
                'neutral': {
                    'style': 'split',
                    'text_color': '#FFFFFF',  # White
                    'outline_color': '#333333',  # Dark gray
                    'emoji': '📺🇵🇱'
                },
                'clickbait': {
                    'style': 'top_bottom',
                    'text_color': '#FF00FF',  # Magenta
                    'outline_color': '#000000',  # Black
                    'emoji': '🚨⚡'
                }
            }


@dataclass
class StreamingConfig:
    """Streaming-specific settings (for stream_app.py)"""
    # Chat analysis
    chat_delay_offset: float = 10.0  # Stream delay (action happens before chat reacts)

    # Copyright detection (DMCA-safe clips)
    enable_copyright_detection: bool = True  # Scan selected clips for copyrighted music
    audd_api_key: Optional[str] = None  # Get from https://audd.io (free tier: 300 requests/day)
    auto_vocal_isolation: bool = True  # Auto-apply vocal isolation if music detected

    # Vocal isolation settings (post-processing)
    vocal_isolation_method: str = "highpass"  # highpass, bandpass, or spleeter
    highpass_frequency: int = 300  # Hz - removes bass/music, keeps voice

    # Detection thresholds
    music_confidence_threshold: float = 0.7  # 0.0-1.0, higher = more strict
    max_music_percentage: float = 0.3  # Skip clip if >30% is copyrighted music


@dataclass
class Config:
    """Główna konfiguracja pipeline'u"""
    # Sub-configs
    audio: AudioConfig = None
    vad: VADConfig = None
    asr: ASRConfig = None
    features: FeatureConfig = None
    scoring: ScoringConfig = None
    selection: SelectionConfig = None
    export: ExportConfig = None
    splitter: SmartSplitterConfig = None
    youtube: YouTubeConfig = None
    shorts: ShortsConfig = None
    thumbnails: ThumbnailConfig = None
    streaming: StreamingConfig = None
    
    # General settings
    output_dir: Path = Path("output")
    temp_dir: Path = Path("temp")
    keep_intermediate: bool = False
    
    # Hardware
    use_gpu: bool = True
    gpu_device: int = 0
    num_workers: int = 4
    
    # Logging
    log_level: str = "INFO"
    save_logs: bool = True
    
    def __post_init__(self):
        # Initialize sub-configs if None
        if self.audio is None:
            self.audio = AudioConfig()
        if self.vad is None:
            self.vad = VADConfig()
        if self.asr is None:
            self.asr = ASRConfig()
        if self.features is None:
            self.features = FeatureConfig()
        if self.scoring is None:
            self.scoring = ScoringConfig()
        if self.selection is None:
            self.selection = SelectionConfig()
        if self.export is None:
            self.export = ExportConfig()
        if self.splitter is None:
            self.splitter = SmartSplitterConfig()
        if self.youtube is None:
            self.youtube = YouTubeConfig()
        if self.shorts is None:
            self.shorts = ShortsConfig()
        if self.thumbnails is None:
            self.thumbnails = ThumbnailConfig()
        if self.streaming is None:
            self.streaming = StreamingConfig()

        # Load AudD API key from environment if not set
        if self.streaming.audd_api_key is None:
            env_key = os.getenv('AUDD_API_KEY')
            if env_key:
                self.streaming.audd_api_key = env_key
                self.streaming.enable_copyright_detection = True
                print(f"✓ AudD API key loaded from .env")

        # Ensure paths are Path objects
        self.output_dir = Path(self.output_dir)
        self.temp_dir = Path(self.temp_dir)
        
        # Create directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def load_from_yaml(cls, yaml_path: str) -> 'Config':
        """Load config z pliku YAML"""
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        # Parse sub-configs
        audio = AudioConfig(**data.get('audio', {}))
        vad = VADConfig(**data.get('vad', {}))
        asr = ASRConfig(**data.get('asr', {}))
        features = FeatureConfig(**data.get('features', {}))
        scoring = ScoringConfig(**data.get('scoring', {}))
        selection = SelectionConfig(**data.get('selection', {}))
        export = ExportConfig(**data.get('export', {}))
        youtube = YouTubeConfig(**data.get('youtube', {}))
        splitter = SmartSplitterConfig(**data.get('splitter', {}))
        shorts = ShortsConfig(**data.get('shorts', {}))

        # Parse thumbnails with nested frame_selection
        thumbnails_data = data.get('thumbnails', {})
        if 'frame_selection' in thumbnails_data and isinstance(thumbnails_data['frame_selection'], dict):
            frame_sel = FrameSelectionConfig(**thumbnails_data['frame_selection'])
            thumbnails_data_copy = thumbnails_data.copy()
            thumbnails_data_copy['frame_selection'] = frame_sel
            thumbnails = ThumbnailConfig(**thumbnails_data_copy)
        else:
            thumbnails = ThumbnailConfig(**thumbnails_data)
        
        # General settings
        general = data.get('general', {})
        
        return cls(
            audio=audio,
            vad=vad,
            asr=asr,
            features=features,
            scoring=scoring,
            selection=selection,
            export=export,
            youtube=youtube,
            splitter=splitter,
            shorts=shorts,
            thumbnails=thumbnails,
            **general
        )
    
    @classmethod
    def load_default(cls) -> 'Config':
        """Load default config"""
        config_path = Path("config.yml")
        
        if config_path.exists():
            return cls.load_from_yaml(str(config_path))
        else:
            # Return default config
            return cls()
    
    def save_to_yaml(self, yaml_path: str):
        """Zapisz config do YAML"""
        data = {
            'audio': asdict(self.audio),
            'vad': asdict(self.vad),
            'asr': asdict(self.asr),
            'features': asdict(self.features),
            'scoring': asdict(self.scoring),
            'selection': asdict(self.selection),
            'export': asdict(self.export),
            'youtube': asdict(self.youtube),
            'splitter': asdict(self.splitter),
            'shorts': asdict(self.shorts),
            'thumbnails': asdict(self.thumbnails),
            'general': {
                'output_dir': str(self.output_dir),
                'temp_dir': str(self.temp_dir),
                'keep_intermediate': self.keep_intermediate,
                'use_gpu': self.use_gpu,
                'gpu_device': self.gpu_device,
                'num_workers': self.num_workers,
                'log_level': self.log_level,
                'save_logs': self.save_logs
            }
        }
        
        with open(yaml_path, 'w', encoding='utf-8') as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'audio': asdict(self.audio),
            'vad': asdict(self.vad),
            'asr': asdict(self.asr),
            'features': asdict(self.features),
            'scoring': asdict(self.scoring),
            'selection': asdict(self.selection),
            'export': asdict(self.export),
            'youtube': asdict(self.youtube),
            'splitter': asdict(self.splitter),
            'shorts': asdict(self.shorts),
            'thumbnails': asdict(self.thumbnails),
            'output_dir': str(self.output_dir),
            'temp_dir': str(self.temp_dir),
            'keep_intermediate': self.keep_intermediate,
            'use_gpu': self.use_gpu,
            'gpu_device': self.gpu_device
        }
    
    def update_from_gui(self, gui_values: Dict[str, Any]):
        """Update config z wartości GUI"""
        # Selection
        if 'target_duration' in gui_values:
            self.selection.target_total_duration = gui_values['target_duration']
        if 'num_clips' in gui_values:
            self.selection.max_clips = gui_values['num_clips']
        if 'min_clip_duration' in gui_values:
            self.selection.min_clip_duration = gui_values['min_clip_duration']
        if 'max_clip_duration' in gui_values:
            self.selection.max_clip_duration = gui_values['max_clip_duration']
        
        # Export
        if 'add_transitions' in gui_values:
            self.export.add_transitions = gui_values['add_transitions']
        if 'add_hardsub' in gui_values:
            self.export.generate_hardsub = gui_values['add_hardsub']
        
        # ASR
        if 'whisper_model' in gui_values:
            self.asr.model = gui_values['whisper_model']
        
        # YouTube
        if 'youtube_upload' in gui_values:
            self.youtube.enabled = gui_values['youtube_upload']
        if 'youtube_privacy' in gui_values:
            self.youtube.privacy_status = gui_values['youtube_privacy']
        
        # General
        if 'output_dir' in gui_values:
            self.output_dir = Path(gui_values['output_dir'])
        if 'keep_intermediate' in gui_values:
            self.keep_intermediate = gui_values['keep_intermediate']
    
    def validate(self) -> bool:
        """Walidacja konfiguracji"""
        # Check paths
        if not self.output_dir.exists():
            self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Check durations
        if self.selection.min_clip_duration >= self.selection.max_clip_duration:
            raise ValueError("min_clip_duration musi być < max_clip_duration")
        
        if self.selection.target_total_duration < self.selection.min_clip_duration * self.selection.min_clips:
            raise ValueError("target_total_duration zbyt mały dla min_clips")
        
        # Check Whisper model
        valid_models = ["large-v3", "large-v2", "medium", "small", "base", "tiny"]
        if self.asr.model not in valid_models:
            raise ValueError(f"Nieprawidłowy model Whisper: {self.asr.model}")
        
        # Check YouTube config
        if self.youtube.enabled:
            if not self.youtube.credentials_path:
                raise ValueError("youtube.credentials_path wymagany gdy youtube.enabled=True")
            if not self.youtube.credentials_path.exists():
                raise ValueError(f"YouTube credentials nie istnieją: {self.youtube.credentials_path}")
        
        # Check GPU availability
        if self.use_gpu:
            try:
                import torch
                if not torch.cuda.is_available():
                    print("⚠️ CUDA niedostępne, przełączam na CPU")
                    self.use_gpu = False
            except ImportError:
                print("⚠️ PyTorch nie zainstalowany, przełączam na CPU")
                self.use_gpu = False
        
        return True
    
    def get_upload_profile(self, profile_name: Optional[str] = None) -> YouTubeConfig:
        """
        Get YouTube upload profile by name

        Args:
            profile_name: Name of profile (currently unused, returns default)

        Returns:
            YouTubeConfig object
        """
        # For now, just return the default youtube config
        # In the future, this could support multiple profiles
        return self.youtube

    def __repr__(self) -> str:
        """String representation"""
        return f"""Config(
    ASR Model: {self.asr.model}
    Target Duration: {self.selection.target_total_duration}s
    Max Clips: {self.selection.max_clips}
    GPU: {self.use_gpu}
    YouTube Upload: {self.youtube.enabled}
    Output: {self.output_dir}
)"""


# === Helper functions ===

def create_default_config_yaml(output_path: str = "config.yml"):
    """Utwórz domyślny plik config.yml"""
    config = Config()
    config.save_to_yaml(output_path)
    print(f"✅ Utworzono domyślny config: {output_path}")


if __name__ == "__main__":
    # Test
    config = Config.load_default()
    print(config)
    
    # Validate
    config.validate()
    
    # Save example
    config.save_to_yaml("config_example.yml")
    print("✅ Config zapisany do config_example.yml")