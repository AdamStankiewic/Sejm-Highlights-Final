"""
Pipeline Configuration Manager
Zarządza wszystkimi parametrami przetwarzania
"""

import yaml
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import Optional, Dict, Any

from shorts.config import ShortsConfig


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

    # Initial prompt dla lepszej accuracy nazwisk (language-aware)
    # Will be set based on language in Config.__post_init__
    initial_prompt: Optional[str] = None

    batch_size: int = 10  # Liczba segmentów przetwarzanych jednocześnie

    def __post_init__(self):
        if self.temperature is None:
            self.temperature = [0.0, 0.2]

        # Set language-aware initial prompt if not explicitly set
        if self.initial_prompt is None:
            if self.language == "pl":
                self.initial_prompt = """
                Posiedzenie Sejmu Rzeczypospolitej Polskiej.
                Posłowie: Donald Tusk, Jarosław Kaczyński, Szymon Hołownia,
                Krzysztof Bosak, Władysław Kosiniak-Kamysz, Przemysław Czarnek,
                Borys Budka, Bartłomiej Sienkiewicz, Radosław Fogiel.
                Tematy: budżet państwa, polityka zagraniczna, sprawy wewnętrzne.
                """
            else:  # English
                self.initial_prompt = """
                Live streaming session.
                Topics: gaming, commentary, discussion, entertainment.
                """


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
    # Will be set to keywords_pl.csv or keywords_en.csv based on language
    keywords_file: Optional[str] = None
    compute_entity_density: bool = True

    # NLP model dla entity recognition
    # Will be set to pl_core_news_lg or en_core_web_lg based on language
    spacy_model: Optional[str] = None


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
    weight_semantic: float = 0.50
    
    # Position diversity bonus
    position_diversity_bonus: float = 0.1

    # Dynamic threshold percentile for fallback selection
    dynamic_threshold_percentile: int = 80

    # Language (will be set from Config.language)
    _language: Optional[str] = None

    def set_language_aware_labels(self, language: str):
        """Set interest labels based on language"""
        self._language = language
        if self.interest_labels is None:
            if language == "pl":
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
            else:  # English
                self.interest_labels = {
                    "heated debate and exchange of accusations": 2.2,
                    "emotional or raised voice": 1.7,
                    "controversial statement or accusation": 2.0,
                    "rhetorical question or challenge": 1.5,
                    "concrete facts numbers and data": 1.3,
                    "humor sarcasm or meme moment": 1.8,
                    "interruption or audience reaction": 1.6,
                    "exciting gameplay moment or clutch play": 2.0,
                    "funny fail or mistake": 1.9,
                    "formal procedure": -2.5,
                    "thank yous and pleasantries": -2.0,
                    "reading rules or technical details": -3.0,
                    "dead air or waiting": -2.8
                }

    def __post_init__(self):
        # interest_labels will be set by Config.__post_init__
        pass


@dataclass
class SelectionConfig:
    """Clip selection settings"""
    # Duration constraints
    min_clip_duration: float = 8.0
    max_clip_duration: float = 120.0
    target_total_duration: float = 900.0  # 15 min

    # Number of clips
    min_clips: int = 8
    max_clips: int = 40

    # Dynamic scoring threshold (GUI slider 0.1-0.8)
    min_score_threshold: float = 0.35
    
    # Temporal constraints
    min_time_gap: float = 10.0  # Między klipami
    smart_merge_gap: float = 10.0  # Gap dla merge'owania
    smart_merge_min_score: float = 0.6
    
    # Coverage optimization
    position_bins: int = 5  # Fazy transmisji
    max_clips_per_bin: int = 4  # Max klipów z jednej fazy
    
    # Trimming
    enable_trimming: bool = True
    trim_percentage: float = 0.2
    duration_tolerance: float = 1.1  # 10% tolerance


@dataclass
class CompositeWeights:
    """Wagi kompozytowego scoringu."""

    chat_burst_weight: float = 0.65
    acoustic_weight: float = 0.15
    semantic_weight: float = 0.15


@dataclass
class ModeWeights:
    """Wagi dla trybu Stream/Sejm."""

    stream_mode: CompositeWeights = field(default_factory=CompositeWeights)
    sejm_mode: CompositeWeights = field(
        default_factory=lambda: CompositeWeights(
            chat_burst_weight=0.05,
            acoustic_weight=0.35,
            semantic_weight=0.55,
        )
    )


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
class HighlightPackerConfig:
    """
    Konfiguracja pakowania highlightów do części z harmonogramem premier.

    UWAGA: To NIE jest chunking materiału źródłowego.
           To jest pakowanie WYBRANYCH klipów (Stage 6) do części dla YouTube.
    """
    enabled: bool = True
    premiere_hour: int = 18
    premiere_minute: int = 0
    min_duration_for_split: float = 3600.0  # Min długość źródła aby pakować do części
    use_politicians_in_titles: bool = True
    first_premiere_days_offset: int = 1

    # Manual overrides (opcjonalne parametry CLI/GUI)
    force_num_parts: Optional[int] = None  # Wymuszenie liczby części (np. --parts 3)
    target_part_minutes: Optional[int] = None  # Wymuszenie długości części (np. --target-part-minutes 20)


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
class CopyrightConfig:
    enabled: bool = False
    provider: str = "demucs"  # audd | demucs
    audd_api_key: str = ""
    keep_sfx: bool = True
    enable_protection: bool = True
    music_detection_threshold: float = 0.7
    royalty_free_folder: str = "assets/royalty_free"


@dataclass
class UploaderConfig:
    youtube_credentials: str = "credentials_youtube.json"
    meta_app_id: str = ""
    meta_app_secret: str = ""
    tiktok_access_token: str = ""


@dataclass
class CacheConfig:
    """
    Konfiguracja cache dla kosztownych etapów (VAD, Transcribe, Scoring).

    Cache key = hash(input_video) + hash(config_for_stage)
    - Jeśli input i config się nie zmieniły → cache hit → pomiń stage
    - Jeśli coś się zmieniło → cache miss → wykonaj stage i zapisz
    """
    enabled: bool = True
    cache_dir: Path = Path("cache")
    force_recompute: bool = False  # --force flag aby wymusić pełne przeliczenie


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
    packer: HighlightPackerConfig = None  # Renamed from 'splitter'
    youtube: YouTubeConfig = None
    shorts: ShortsConfig = None
    cache: CacheConfig = None  # Cache configuration
    
    # General settings
    output_dir: Path = Path("output")
    temp_dir: Path = Path("temp")
    keep_intermediate: bool = False
    language: str = "pl"  # Pipeline language: "pl" or "en"

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
        if self.scoring_weights is None:
            self.scoring_weights = ModeWeights()
        if self.selection is None:
            self.selection = SelectionConfig()
        if self.export is None:
            self.export = ExportConfig()
        if self.packer is None:  # Renamed from 'splitter'
            self.packer = HighlightPackerConfig()
        if self.youtube is None:
            self.youtube = YouTubeConfig()
        if self.shorts is None:
            self.shorts = ShortsConfig()
        if self.cache is None:
            self.cache = CacheConfig()

        # === Language-aware defaults ===
        # Set ASR language from global language (if not explicitly set)
        if self.asr.language == "pl" and self.language != "pl":
            self.asr.language = self.language

        # Set spaCy model based on language
        if self.features.spacy_model is None:
            self.features.spacy_model = "pl_core_news_lg" if self.language == "pl" else "en_core_web_lg"

        # Set keywords file based on language
        if self.features.keywords_file is None:
            self.features.keywords_file = f"models/keywords_{self.language}.csv"

        # Set language-aware interest labels for scoring
        self.scoring.set_language_aware_labels(self.language)

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
        weights_data = data.get('scoring_weights', {})
        scoring_weights = ModeWeights(
            stream_mode=CompositeWeights(**weights_data.get('stream_mode', {})),
            sejm_mode=CompositeWeights(**weights_data.get('sejm_mode', {})),
        )
        selection = SelectionConfig(**data.get('selection', {}))
        export = ExportConfig(**data.get('export', {}))
        youtube = YouTubeConfig(**data.get('youtube', {}))
        # Support both old 'splitter' and new 'packer' keys for backward compatibility
        packer = HighlightPackerConfig(**data.get('packer', data.get('splitter', {})))
        shorts = ShortsConfig(**data.get('shorts', {}))
        cache = CacheConfig(**data.get('cache', {}))

        # General settings
        general = data.get('general', {})

        return cls(
            audio=audio,
            vad=vad,
            asr=asr,
            features=features,
            scoring=scoring,
            scoring_weights=scoring_weights,
            selection=selection,
            export=export,
            youtube=youtube,
            packer=packer,  # Renamed from 'splitter'
            shorts=shorts,
            cache=cache,  # Cache configuration
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
            'scoring_weights': asdict(self.scoring_weights),
            'selection': asdict(self.selection),
            'export': asdict(self.export),
            'youtube': asdict(self.youtube),
            'shorts': asdict(self.shorts),
            'uploader': asdict(self.uploader),
            'copyright': asdict(self.copyright),
            'general': {
                'output_dir': str(self.output_dir),
                'temp_dir': str(self.temp_dir),
                'keep_intermediate': self.keep_intermediate,
                'language': self.language,  # Language parameter
                'use_gpu': self.use_gpu,
                'gpu_device': self.gpu_device,
                'num_workers': self.num_workers,
                'log_level': self.log_level,
                'save_logs': self.save_logs,
                'mode': self.mode,
                'chat_json_path': str(self.chat_json_path) if self.chat_json_path else None,
                'prompt_text': self.prompt_text,
                'override_weights': self.override_weights,
                'language': self.language,
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
            'scoring_weights': asdict(self.scoring_weights),
            'selection': asdict(self.selection),
            'export': asdict(self.export),
            'youtube': asdict(self.youtube),
            'shorts': asdict(self.shorts),
            'uploader': asdict(self.uploader),
            'copyright': asdict(self.copyright),
            'output_dir': str(self.output_dir),
            'temp_dir': str(self.temp_dir),
            'keep_intermediate': self.keep_intermediate,
            'use_gpu': self.use_gpu,
            'gpu_device': self.gpu_device,
            'mode': self.mode,
            'chat_json_path': str(self.chat_json_path) if self.chat_json_path else None,
            'prompt_text': self.prompt_text,
            'override_weights': self.override_weights,
            'language': self.language,
        }

    def get_active_weights(self) -> CompositeWeights:
        """Zwróć aktywny zestaw wag uwzględniając tryb i nadpisania z GUI."""

        if self.override_weights and self.custom_weights:
            return self.custom_weights

        if self.mode.lower() == "stream":
            return self.scoring_weights.stream_mode

        return self.scoring_weights.sejm_mode

    def get_effective_weights(self, chat_present: bool) -> CompositeWeights:
        """Return weights derived from YAML (or overrides), adapting only to chat availability."""

        base = self.get_active_weights()
        if self.mode.lower() != "stream" or chat_present:
            return base

        # Brak chat.json → wyzeruj wagę czatu i proporcjonalnie przeskaluj pozostałe
        remaining_sum = base.acoustic_weight + base.semantic_weight

        if remaining_sum > 0:
            scale = 1.0 / remaining_sum
            return CompositeWeights(
                chat_burst_weight=0.0,
                acoustic_weight=base.acoustic_weight * scale,
                semantic_weight=base.semantic_weight * scale,
            )

        # Wszystkie wagi poza czatem są zerowe – rozłóż równomiernie, by zachować spójność
        fallback_weight = 0.5
        return CompositeWeights(
            chat_burst_weight=0.0,
            acoustic_weight=fallback_weight,
            semantic_weight=fallback_weight,
        )
    
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
        if 'mode' in gui_values:
            self.mode = gui_values['mode']
        if 'chat_json_path' in gui_values:
            path_val = gui_values['chat_json_path']
            self.chat_json_path = Path(path_val) if path_val else None
        if 'prompt_text' in gui_values:
            self.prompt_text = gui_values['prompt_text']
        if 'override_weights' in gui_values:
            self.override_weights = bool(gui_values['override_weights'])
        if 'custom_weights' in gui_values and isinstance(gui_values['custom_weights'], dict):
            weights = gui_values['custom_weights']
            self.custom_weights = CompositeWeights(**weights)
        if 'language' in gui_values:
            self.language = gui_values['language']
    
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

        if not 0.0 <= self.selection.min_score_threshold <= 1.0:
            raise ValueError("min_score_threshold musi być w przedziale 0-1")
        
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

        # Mode sanity
        if self.mode.lower() not in {"sejm", "stream"}:
            raise ValueError("mode musi być 'sejm' lub 'stream'")
        
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