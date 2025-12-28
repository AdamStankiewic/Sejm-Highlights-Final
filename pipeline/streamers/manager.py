"""
StreamerManager - Manages streamer profiles for multi-platform content
"""
from pathlib import Path
from typing import Optional, Dict, List
import yaml
from pydantic import BaseModel, Field, validator
import logging

logger = logging.getLogger(__name__)


class PlatformInfo(BaseModel):
    """Platform-specific account info"""
    channel_id: Optional[str] = None
    channel_url: Optional[str] = None
    username: Optional[str] = None


class GenerationSettings(BaseModel):
    """AI generation settings"""
    context_model: str = "gpt-4o-mini"
    title_model: str = "gpt-4o"
    description_model: str = "gpt-4o"
    temperature: float = 0.8
    enable_research: bool = False


class SeedExample(BaseModel):
    """Example of successful content"""
    title: str
    description: Optional[str] = None
    metadata: Optional[Dict] = None


class StreamerProfile(BaseModel):
    """Complete streamer profile"""
    streamer_id: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    platforms: Dict[str, PlatformInfo] = Field(default_factory=dict)
    content: Dict = Field(default_factory=dict)
    generation: GenerationSettings = Field(default_factory=GenerationSettings)
    seed_examples: List[SeedExample] = Field(default_factory=list)

    @validator('streamer_id')
    def validate_id(cls, v):
        if not v.islower() or ' ' in v:
            raise ValueError('streamer_id must be lowercase with no spaces')
        return v

    @property
    def primary_language(self) -> str:
        """Get primary language (pl/en)"""
        return self.content.get('primary_language', 'pl')

    @property
    def channel_type(self) -> str:
        """Get channel type"""
        return self.content.get('channel_type', 'gaming')

    @property
    def primary_platform(self) -> str:
        """Get main platform"""
        return self.content.get('primary_platform', 'youtube')


class StreamerManager:
    """
    Manages streamer profiles for multi-platform support.

    Integrates with existing pipeline structure:
    - Profiles stored in pipeline/streamers/profiles/*.yaml
    - Works alongside existing config.yml
    - Auto-detects streamer from platform identifiers
    """

    def __init__(self, profiles_dir: Path = None):
        if profiles_dir is None:
            # Default to pipeline/streamers/profiles/
            profiles_dir = Path(__file__).parent / "profiles"

        self.profiles_dir = profiles_dir
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

        # In-memory cache
        self._profiles: Dict[str, StreamerProfile] = {}

        # Lookup indices for fast detection
        self._youtube_index: Dict[str, str] = {}  # channel_id -> streamer_id
        self._twitch_index: Dict[str, str] = {}   # username -> streamer_id
        self._kick_index: Dict[str, str] = {}     # username -> streamer_id

        # Load all profiles
        self._load_all()

    def _load_all(self):
        """Load all YAML profiles"""
        yaml_files = list(self.profiles_dir.glob("*.yaml"))

        # Skip template
        yaml_files = [f for f in yaml_files if not f.name.startswith("_")]

        logger.info(f"Loading {len(yaml_files)} streamer profiles...")

        for yaml_file in yaml_files:
            try:
                with open(yaml_file, 'r', encoding='utf-8') as f:
                    data = yaml.safe_load(f)

                # Convert simple YAML format to Pydantic format if needed
                # Simple format: youtube: {channel_id: ...}
                # Pydantic format: platforms: {youtube: {channel_id: ...}}
                if 'platforms' not in data:
                    platforms = {}

                    # Convert youtube section
                    if 'youtube' in data and isinstance(data['youtube'], dict):
                        platforms['youtube'] = PlatformInfo(**data['youtube'])

                    # Convert twitch section
                    if 'twitch' in data and isinstance(data['twitch'], dict):
                        platforms['twitch'] = PlatformInfo(**data['twitch'])

                    # Convert kick section
                    if 'kick' in data and isinstance(data['kick'], dict):
                        platforms['kick'] = PlatformInfo(**data['kick'])

                    data['platforms'] = platforms

                # Convert content fields to content dict if needed
                if 'content' not in data:
                    data['content'] = {
                        'primary_language': data.get('language', 'pl'),
                        'channel_type': data.get('content_type', 'generic'),
                        'primary_platform': 'youtube'  # Default
                    }

                profile = StreamerProfile(**data)
                self._profiles[profile.streamer_id] = profile

                # Build lookup indices
                if 'youtube' in profile.platforms:
                    yt = profile.platforms['youtube']
                    if yt.channel_id:
                        self._youtube_index[yt.channel_id] = profile.streamer_id

                if 'twitch' in profile.platforms:
                    tw = profile.platforms['twitch']
                    if tw.username:
                        self._twitch_index[tw.username.lower()] = profile.streamer_id

                if 'kick' in profile.platforms:
                    kk = profile.platforms['kick']
                    if kk.username:
                        self._kick_index[kk.username.lower()] = profile.streamer_id

                logger.debug(f"Loaded profile: {profile.streamer_id}")

            except Exception as e:
                logger.error(f"Failed to load {yaml_file}: {e}")

        logger.info(f"Loaded {len(self._profiles)} streamers successfully")

    def get(self, streamer_id: str) -> Optional[StreamerProfile]:
        """Get profile by streamer_id"""
        return self._profiles.get(streamer_id)

    def detect_from_youtube(self, channel_id: str) -> Optional[StreamerProfile]:
        """Auto-detect streamer from YouTube channel ID"""
        streamer_id = self._youtube_index.get(channel_id)
        return self._profiles.get(streamer_id) if streamer_id else None

    def detect_from_twitch(self, username: str) -> Optional[StreamerProfile]:
        """Auto-detect streamer from Twitch username"""
        streamer_id = self._twitch_index.get(username.lower())
        return self._profiles.get(streamer_id) if streamer_id else None

    def detect_from_kick(self, username: str) -> Optional[StreamerProfile]:
        """Auto-detect streamer from Kick username"""
        streamer_id = self._kick_index.get(username.lower())
        return self._profiles.get(streamer_id) if streamer_id else None

    def list_all(self) -> List[StreamerProfile]:
        """Get all loaded profiles"""
        return list(self._profiles.values())

    def create(self, streamer_data: Dict) -> StreamerProfile:
        """Create new streamer profile"""
        profile = StreamerProfile(**streamer_data)

        yaml_file = self.profiles_dir / f"{profile.streamer_id}.yaml"
        if yaml_file.exists():
            raise ValueError(f"Streamer {profile.streamer_id} already exists")

        # Save to YAML
        with open(yaml_file, 'w', encoding='utf-8') as f:
            yaml.dump(profile.dict(), f, allow_unicode=True, sort_keys=False)

        # Reload to update indices
        self._load_all()

        logger.info(f"Created streamer: {profile.streamer_id}")
        return profile

    def reload(self):
        """Reload all profiles from disk"""
        self._profiles.clear()
        self._youtube_index.clear()
        self._twitch_index.clear()
        self._kick_index.clear()
        self._load_all()


# Global singleton
_manager: Optional[StreamerManager] = None

def get_manager() -> StreamerManager:
    """Get global StreamerManager instance"""
    global _manager
    if _manager is None:
        _manager = StreamerManager()
    return _manager
