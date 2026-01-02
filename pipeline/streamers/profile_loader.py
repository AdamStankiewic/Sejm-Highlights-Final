"""
Streamer Profile Loader
Handles loading and auto-detection of streamer profiles
"""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional, List
from ..config import Config


class StreamerProfile:
    """Streamer profile with all configuration overrides"""

    def __init__(self, profile_path: Path):
        self.path = profile_path
        self.data = self._load_yaml(profile_path)

        # Basic info
        self.streamer_id = self.data.get('streamer_id', profile_path.stem)  # ✅ FIX: Add streamer_id
        self.name = self.data.get('name', 'Unknown')
        self.display_name = self.data.get('display_name', self.name)
        self.language = self.data.get('language', 'pl')
        self.content_type = self.data.get('content_type', 'generic')

        # YouTube info
        self.youtube = self.data.get('youtube', {})
        self.channel_id = self.youtube.get('channel_id', '')
        self.channel_name = self.youtube.get('channel_name', '')

        # Detection patterns
        self.detection = self.data.get('detection', {})
        self.filename_patterns = self.detection.get('filename_patterns', [])
        self.channel_indicators = self.detection.get('channel_indicators', [])

    def _load_yaml(self, path: Path) -> Dict[str, Any]:
        """Load YAML profile file"""
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def apply_to_config(self, config: Config) -> None:
        """Apply this profile's settings to a Config object"""
        # Language
        config.language = self.language
        config.asr.language = self.language

        # Streamer ID (for AI metadata generation)
        config.streamer_id = self.streamer_id

        # AI Metadata Generation
        ai_metadata_enabled = self.data.get('ai_metadata_enabled', False)
        if ai_metadata_enabled:
            config.ai_metadata_enabled = True

        # Keywords file
        keywords_file = self.data.get('features', {}).get('keywords_file')
        if keywords_file:
            config.features.keywords_file = keywords_file

        # spaCy model
        spacy_model = self.data.get('features', {}).get('spacy_model')
        if spacy_model:
            config.features.spacy_model = spacy_model

        # YouTube channel
        if self.channel_id:
            config.youtube.channel_id = self.channel_id
        if self.channel_name:
            config.youtube.channel_name = self.channel_name

        # Shorts template
        shorts_config = self.data.get('shorts', {})
        if 'template' in shorts_config:
            config.shorts.template = shorts_config['template']
        if 'subtitle_lang' in shorts_config:
            config.shorts.subtitle_lang = shorts_config['subtitle_lang']

        # ASR model override (e.g., "small" for ohnepixel)
        asr_config = self.data.get('asr', {})
        if 'model' in asr_config:
            config.asr.model = asr_config['model']

    def matches_filename(self, filename: str) -> bool:
        """Check if this profile matches the given filename"""
        filename_lower = filename.lower()
        return any(pattern.lower() in filename_lower for pattern in self.filename_patterns)

    def __repr__(self):
        return f"<StreamerProfile: {self.display_name} ({self.language})>"


class ProfileLoader:
    """Manages loading and detection of streamer profiles"""

    def __init__(self, profiles_dir: str = "pipeline/streamers/profiles"):
        self.profiles_dir = Path(profiles_dir)
        self.profiles: Dict[str, StreamerProfile] = {}
        self._load_all_profiles()

    def _load_all_profiles(self) -> None:
        """Load all YAML profiles from the profiles directory"""
        if not self.profiles_dir.exists():
            print(f"⚠️ Profiles directory not found: {self.profiles_dir}")
            return

        for profile_file in self.profiles_dir.glob("*.yaml"):
            try:
                profile = StreamerProfile(profile_file)
                profile_key = profile_file.stem  # filename without extension
                self.profiles[profile_key] = profile
                print(f"✓ Loaded profile: {profile.display_name} ({profile_key})")
            except Exception as e:
                print(f"⚠️ Failed to load profile {profile_file}: {e}")

    def get_profile(self, profile_name: str) -> Optional[StreamerProfile]:
        """Get a profile by name/key"""
        return self.profiles.get(profile_name.lower())

    def list_profiles(self) -> List[str]:
        """Get list of available profile names"""
        return list(self.profiles.keys())

    def auto_detect_profile(self, filename: str) -> Optional[StreamerProfile]:
        """Auto-detect the correct profile based on filename"""
        for profile in self.profiles.values():
            if profile.matches_filename(filename):
                return profile
        return None

    def apply_profile_to_config(self, profile_name: str, config: Config) -> bool:
        """Apply a profile to a Config object"""
        profile = self.get_profile(profile_name)
        if profile:
            profile.apply_to_config(config)
            print(f"✓ Applied profile: {profile.display_name}")
            return True
        else:
            print(f"⚠️ Profile not found: {profile_name}")
            return False


# Singleton instance for easy access
_loader: Optional[ProfileLoader] = None

def get_profile_loader() -> ProfileLoader:
    """Get the global ProfileLoader instance"""
    global _loader
    if _loader is None:
        _loader = ProfileLoader()
    return _loader
