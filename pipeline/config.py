"""
Pipeline Configuration Manager
Zarządza wszystkimi parametrami przetwarzania
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any


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
    spacy_model: str = "pl_core_news_sm"  # Mniejszy model (szybszy, działa z Python 3.11)


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
    # Duration constraints (mode-specific defaults applied in processor)
    min_clip_duration: float = 90.0  # Polityka default
    max_clip_duration: float = 180.0  # Polityka default
    target_total_duration: float = 900.0  # 15 min

    # Stream mode overrides (applied when mode="stream")
    min_clip_duration_stream: float = 20.0  # Shorter for gaming highlights
    max_clip_duration_stream: float = 90.0  # Max 1.5 min for stream clips
    target_total_duration_stream: float = 720.0  # 12 min for streams

    # Number of clips
    min_clips: int = 8
    max_clips: int = 15
    max_clips_stream: int = 25  # More clips for streams (shorter)

    # Temporal constraints
    min_time_gap: float = 30.0  # Między klipami (Polityka)
    min_time_gap_stream: float = 10.0  # Faster paced for streams
    smart_merge_gap: float = 5.0  # Gap dla merge'owania (Polityka)
    smart_merge_gap_stream: float = 3.0  # Tighter for stream action sequences
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

    # Upload settings
    upload_to_youtube: bool = False
    shorts_category_id: str = "25"
    add_hashtags: bool = True

    # === ENHANCED: Professional Templates for Streams ===
    # Available templates: "simple", "classic_gaming", "pip_modern", "irl_fullface", "dynamic_speaker"
    templates: list = field(default_factory=lambda: [
        "simple",           # Prosty crop 9:16 (backward compatibility, Sejm)
        "classic_gaming",   # Kamerka dół + gameplay góra
        "pip_modern",       # Fullscreen + mała kamerka PIP
        "irl_fullface",     # Zoom + crop, brak PIP (dla full-face streamów)
        "dynamic_speaker"   # Speaker tracking (zaawansowany)
    ])

    # Default template: "simple" for Sejm (backward compat), "auto" for streams
    default_template: str = "simple"  # "simple" = prosty crop, "auto" = auto-detect

    # Face detection for webcam region detection
    face_detection: bool = True
    webcam_detection_confidence: float = 0.5  # Min confidence dla MediaPipe

    # Template-specific settings
    # Classic Gaming
    webcam_height_ratio: float = 0.33  # Kamerka zajmuje 33% wysokości
    gameplay_max_crop: float = 0.15    # Max 15% crop z boków dla gameplay

    # PIP Modern
    pip_size_ratio: float = 0.25       # PIP zajmuje 25% szerokości
    pip_corner_radius: int = 20        # Zaokrąglenie rogów PIP (px)
    pip_shadow_blur: int = 10          # Rozmycie cienia (px)

    # IRL Full-face
    irl_zoom_factor: float = 1.2       # Zoom 1.2x dla IRL
    irl_crop_ratio: float = 0.12       # 12% crop z boków

    # Dynamic Speaker Tracker
    speaker_switch_interval: float = 4.0   # Co ile sekund zmiana (3-5s)
    speaker_transition_duration: float = 0.8  # Czas cross-fade (s)
    speaker_zoom_factor: float = 1.15     # Zoom na mówiącego

    # Title card settings
    title_enabled: bool = True
    title_height: int = 220            # Wysokość paska tytułu (px)
    title_fontsize: int = 56
    title_fontcolor: str = "white"
    title_bgcolor: str = "black@0.7"   # Półprzezroczysty

    # Safe zones for subtitles
    subtitle_safe_zone_top: int = 300     # Bezpieczna strefa góra (px)
    subtitle_safe_zone_bottom: int = 1500  # Bezpieczna strefa dół (px)


@dataclass
class StreamingConfig:
    """Configuration for streaming content (Twitch/YouTube/Kick)"""

    # === Mode Selection ===
    mode: str = "polityka"  # "polityka" or "stream"

    # === Chat Scoring ===
    use_chat_scoring: bool = False  # Use chat activity for scoring
    chat_file_path: Optional[str] = None  # Path to chat JSON file
    chat_delay_offset: float = 10.0  # Stream delay in seconds (action -> chat reaction)

    # === Copyright Detection ===
    enable_copyright_detection: bool = False  # Enable DMCA music detection
    audd_api_key: str = ""  # AudD API key (get from https://audd.io)
    music_confidence_threshold: float = 0.7  # Min confidence for music detection (0-1)
    max_music_percentage: float = 0.3  # Skip clips with >30% copyrighted music
    auto_vocal_isolation: bool = False  # Auto-remove vocals from music
    scan_interval: int = 10  # Scan every N seconds

    # === Title Generation ===
    stream_title_style: str = "clickbait"  # "clickbait", "descriptive", "minimal"
    use_caps: bool = True  # Use CAPS for emphasis (NAJLEPSZY MOMENT!)
    use_emojis: bool = True  # Add emojis to titles 🔥⚡

    # === Templates (inherited from ShortsConfig) ===
    # Streams typically use "auto", "classic_gaming", or "pip_modern"
    default_stream_template: str = "auto"


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
        if self.splitter is None:  # ← TO POWINNO BYĆ TUTAJ
            self.splitter = SmartSplitterConfig()  # ← TO POWINNO BYĆ TUTAJ
        if self.youtube is None:
            self.youtube = YouTubeConfig()
        if self.shorts is None:
            self.shorts = ShortsConfig()
        if self.streaming is None:
            self.streaming = StreamingConfig()

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