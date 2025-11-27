"""
Stage 9: YouTube Upload
Automatyczny upload gotowego video na YouTube
"""

import os
import pickle
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from .youtube_playlist_manager import PlaylistManager


class YouTubeStage:
    """
    Stage 9: Upload video na YouTube with multi-channel profile support
    """

    # Scopes wymagane do uploadu video
    SCOPES = [
        'https://www.googleapis.com/auth/youtube.upload',
        'https://www.googleapis.com/auth/youtube',
        'https://www.googleapis.com/auth/youtube.readonly'
    ]

    def __init__(self, config, profile_name: Optional[str] = None):
        """
        Initialize YouTube Stage

        Args:
            config: Pipeline config
            profile_name: Optional upload profile name (e.g., 'sejm', 'stream')
                         If None, uses default YouTube config
        """
        self.config = config
        self.credentials = None
        self.youtube_service = None
        self.playlist_manager = None

        # Profile management
        self.current_profile = None
        self.current_profile_name = profile_name

        # Load profile if specified
        if profile_name:
            self.set_profile(profile_name)

    def set_profile(self, profile_name: str):
        """
        Set active upload profile

        Args:
            profile_name: Name of profile from config (e.g., 'sejm', 'stream')
        """
        profile = self.config.get_upload_profile(profile_name)

        if not profile:
            available = self.config.list_upload_profiles()
            raise ValueError(
                f"Profile '{profile_name}' not found. Available: {available}"
            )

        self.current_profile = profile
        self.current_profile_name = profile_name

        print(f"📺 Profil uploadowy: {profile.name} (kanał: {profile.channel_id[:15]}...)")

    def get_profile_settings(self, video_type: str = 'main') -> Dict[str, Any]:
        """
        Get upload settings from current profile

        Args:
            video_type: 'main' or 'shorts'

        Returns:
            Dict with privacy_status, category_id, playlist_id, etc.
        """
        # Use profile if set, otherwise use global config
        if self.current_profile:
            if video_type == 'shorts':
                settings = self.current_profile.shorts
                return {
                    'privacy_status': settings.privacy_status,
                    'category_id': settings.category_id,
                    'playlist_id': settings.playlist_id,
                    'add_hashtags': settings.add_hashtags,
                    'channel_id': self.current_profile.channel_id
                }
            else:  # main videos
                settings = self.current_profile.main_videos
                return {
                    'privacy_status': settings.privacy_status,
                    'schedule_as_premiere': settings.schedule_as_premiere,
                    'category_id': settings.category_id,
                    'playlist_id': settings.playlist_id,
                    'channel_id': self.current_profile.channel_id
                }
        else:
            # Fallback to global YouTube config
            return {
                'privacy_status': self.config.youtube.privacy_status,
                'schedule_as_premiere': self.config.youtube.schedule_as_premiere,
                'category_id': self.config.youtube.category_id,
                'playlist_id': '',
                'channel_id': self.config.youtube.channel_id
            }

    def _get_token_file(self) -> str:
        """Get token file path for current profile"""
        if self.current_profile:
            return self.current_profile.token_file
        return "youtube_token.json"

    def _generate_clickbait_title(self, clips: list) -> str:
        """Generuj clickbaitowy tytuł"""
        date_str = datetime.now().strftime('%d.%m.%Y')
        
        # Znajdź najciekawsze keywords
        all_keywords = []
        for clip in clips[:3]:  # Top 3 klipy
            keywords = clip.get('keywords', [])
            all_keywords.extend(keywords[:2])
        
        # Usuń duplikaty
        unique_keywords = []
        for kw in all_keywords:
            if kw.lower() not in [k.lower() for k in unique_keywords]:
                unique_keywords.append(kw)
        
        top_keywords = unique_keywords[:3]
        
        # Opcje tytułów clickbaitowych
        templates = [
            f"🔥 SEJM: {' vs '.join(top_keywords[:2]).upper()} - Najgorętsze Momenty!",
            f"💥 SEJM Eksploduje! {top_keywords[0].upper()} - Top Momenty {date_str}",
            f"⚡ SEJM: {top_keywords[0].upper()} - TO MUSISZ ZOBACZYĆ! {date_str}",
            f"🎯 Najlepsze Momenty SEJMU - {date_str}",
        ]
        
        # Wybierz odpowiedni template
        if len(top_keywords) >= 2:
            title = templates[0]
        elif len(top_keywords) >= 1:
            title = templates[1]
        else:
            title = templates[3]
        
        # Ogranicz do 100 znaków
        if len(title) > 100:
            title = title[:97] + "..."
        
        return title        
    
    def authorize(self):
        """
        Autoryzacja OAuth 2.0 dla YouTube API
        Uses profile-specific token file if profile is set

        Returns: Authenticated YouTube service
        """
        token_file = Path(self._get_token_file())
        
        # Sprawdź czy credentials_path istnieje
        if not self.config.youtube.credentials_path:
            raise ValueError("youtube.credentials_path nie jest ustawiony!")
        
        if not self.config.youtube.credentials_path.exists():
            raise FileNotFoundError(
                f"Plik credentials nie istnieje: {self.config.youtube.credentials_path}\n"
                f"Pobierz go z: https://console.cloud.google.com/apis/credentials"
            )
        
        # Load existing token if available
        if token_file.exists():
            print("📂 Ładuję zapisany token...")
            self.credentials = Credentials.from_authorized_user_file(
                str(token_file), 
                self.SCOPES
            )
        
        # If no valid credentials, do OAuth flow
        if not self.credentials or not self.credentials.valid:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                print("🔄 Odświeżam token...")
                self.credentials.refresh(Request())
            else:
                print("🔐 Rozpoczynam OAuth flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.config.youtube.credentials_path),
                    self.SCOPES
                )
                self.credentials = flow.run_local_server(
                    port=8080,
                    prompt='consent',
                    success_message='Autoryzacja zakończona! Możesz zamknąć to okno.'
                )
            
            # Save credentials for next time
            print(f"💾 Zapisuję token do: {token_file}")
            with open(token_file, 'w') as f:
                f.write(self.credentials.to_json())
        
        # Build YouTube service
        self.youtube_service = build('youtube', 'v3', credentials=self.credentials)

        # Initialize Playlist Manager
        self.playlist_manager = PlaylistManager(self.youtube_service)

        # === POBIERZ WSZYSTKIE KANAŁY UŻYTKOWNIKA ===
        try:
            channels_response = self.youtube_service.channels().list(
                part='snippet,contentDetails',
                mine=True,
                maxResults=50
            ).execute()
            
            all_channels = channels_response.get('items', [])
            
            if not all_channels:
                print("⚠️ Brak kanałów YouTube dla tego konta!")
                return self.youtube_service
            
            # Wyświetl wszystkie dostępne kanały
            print(f"\n📺 DOSTĘPNE KANAŁY YOUTUBE ({len(all_channels)}):")
            for i, channel in enumerate(all_channels, 1):
                channel_id = channel['id']
                channel_title = channel['snippet']['title']
                is_default = i == 1
                
                marker = "→" if is_default else " "
                print(f"   {marker} {i}. {channel_title}")
                print(f"      ID: {channel_id}")
            
            # Sprawdź który kanał jest ustawiony w config
            target_channel = self.config.youtube.channel_id
            selected_channel = None
            
            # Znajdź kanał z config w liście
            for channel in all_channels:
                if channel['id'] == target_channel:
                    selected_channel = channel
                    break
            
            # Jeśli nie znaleziono w config, użyj pierwszego (domyślnego)
            if not selected_channel:
                selected_channel = all_channels[0]
                print(f"\n⚠️  Kanał z config nie znaleziony!")
                print(f"   Oczekiwany ID: {target_channel}")
                print(f"   Używam domyślnego: {selected_channel['snippet']['title']}")
            
            # Wyświetl wybrany kanał
            channel_id = selected_channel['id']
            channel_title = selected_channel['snippet']['title']
            
            print(f"\n✅ WYBRANY KANAŁ DO UPLOADU:")
            print(f"   Nazwa: {channel_title}")
            print(f"   ID: {channel_id}")
            
            # Sprawdź czy to właściwy
            if channel_id != target_channel:
                print(f"\n⚠️  To NIE jest kanał z config!")
                print(f"   Aby zmienić:")
                print(f"   1. Zaktualizuj config.yml → youtube.channel_id")
                print(f"   2. Lub w YouTube Studio ustaw '{channel_title}' jako domyślny")
                
                # Zapytaj użytkownika czy kontynuować
                print(f"\n❓ Kontynuować upload na: {channel_title}? (y/n)")
                # Auto-kontynuuj (w trybie automatycznym)
                print(f"   Auto-kontynuacja za 5 sekund...")
                import time
                time.sleep(5)
            else:
                print(f"   ✅ Zgodny z config!")
            
            # Zapisz wybrany kanał do użycia w uploadzie
            self.selected_channel_id = channel_id
            
        except Exception as e:
            print(f"⚠️ Nie można pobrać kanałów: {e}")
            self.selected_channel_id = None
        
        print("✅ Połączono z YouTube API")
        
        return self.youtube_service
    
    def _generate_description(self, clips: list, segments: list) -> str:
        """Generuj opisowy opis z fragmentami wypowiedzi"""
        description_parts = [
            "🎯 Najciekawsze i najbardziej kontrowersyjne momenty z Sejmu RP!",
            "",
            "📋 CO W ODCINKU:",
        ]
        
        current_time = 0.0
        for i, clip in enumerate(clips, 1):
            timestamp = self._format_timestamp(current_time)
            
            # Znajdź segmenty dla tego klipu
            clip_segments = [
                s for s in segments
                if s['t0'] >= clip['t0'] and s['t1'] <= clip['t1']
            ]
            
            # Weź pierwsze zdanie lub fragment
            if clip_segments:
                first_segment = clip_segments[0]
                text = first_segment.get('text', '')
                
                # Pierwsze 10 słów
                words = text.split()[:10]
                title = ' '.join(words)
                
                if len(title) > 70:
                    title = title[:67] + "..."
                
                # Capitalize
                title = title[0].upper() + title[1:] if title else f"Moment {i}"
            else:
                title = clip.get('title', f'Moment {i}')
            
            description_parts.append(f"⏱️ {timestamp} - {title}")
            current_time += clip['duration']
        
        description_parts.extend([
            "",
            "━━━━━━━━━━━━━━━━━━━━━━━━━━",
            "🤖 Wygenerowane automatycznie przez AI",
            "📊 Analiza semantyczna + wykrywanie emocji w czasie rzeczywistym",
            f"📅 {datetime.now().strftime('%d.%m.%Y')}",
            "",
            "🔔 Subskrybuj dla codziennych najlepszych momentów z Sejmu!",
            "👍 Zostaw like jeśli podobał Ci się materiał!",
            "",
            "#Sejm #Polska #Polityka #SejmRP #PolskaPolityka #News #Tusk #Kaczyński"
        ])
        
        return "\n".join(description_parts)
        
    def _generate_tags(self, clips: list) -> list:
        """Generuj tagi na podstawie klipów"""
        tags = list(self.config.youtube.tags)  # Start z default tags
        
        # Dodaj keywords z klipów
        for clip in clips[:5]:  # Max 5 klipów dla tagów
            keywords = clip.get('keywords', [])
            for kw in keywords[:3]:  # Max 3 keywords per clip
                if kw not in tags and len(tags) < 30:  # YouTube max 30 tags
                    tags.append(kw)
        
        return tags
    
    def schedule_premiere(
        self,
        video_file: str,
        title: str,
        clips: list,
        segments: list,
        output_dir: Path,
        premiere_datetime: datetime,
        thumbnail_file: Optional[str] = None
    ) -> Dict[str, Any]:
        """Upload video zaschedulowany jako premiere"""
        
        if not self.youtube_service:
            self.authorize()
        
        print(f"📅 Schedulowanie premiery na: {premiere_datetime.strftime('%d.%m.%Y %H:%M')}")
        
        # Generate description and tags
        description = self._generate_description(clips, segments)
        tags = self._generate_tags(clips)
        
        # Use upload_video with premiere settings
        # Note: YouTube API nie ma bezpośredniego wsparcia dla premiere przez publishAt
        # Trzeba ustawić privacy na private i publishAt - ale to nie działa jak premiere
        # Alternatywnie: upload jako unlisted i ręcznie ustawić premiere przez YouTube Studio
        
        # Upload as unlisted for now (user will need to set premiere in YouTube Studio)
        return self.upload_video(
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            category_id=self.config.youtube.category_id,
            privacy_status='unlisted',  # Use unlisted instead of premiere
            thumbnail_file=thumbnail_file
        )
    
    def upload_video(
        self,
        video_file: str,
        title: str,
        description: str,
        tags: list,
        category_id: str = "25",
        privacy_status: str = "unlisted",
        thumbnail_file: Optional[str] = None,
        srt_file: Optional[str] = None  # ← NOWE!
    ) -> Dict[str, Any]:
        """Upload video na YouTube"""
        
        if not self.youtube_service:
            raise RuntimeError("Nie zalogowano do YouTube.")
        
        # DODAJ TO - wybór kanału
        if self.config.youtube.channel_id:
            print(f"📺 Upload na kanał: {self.config.youtube.channel_id}")
        print(f"   Tytuł: {title}")
        print(f"   Prywatność: {privacy_status}")
        
        # Prepare request body
        body = {
            'snippet': {
                'title': title,
                'description': description,
                'tags': tags,
                'categoryId': category_id,
                'defaultLanguage': self.config.youtube.language,
                'defaultAudioLanguage': self.config.youtube.language
            },
            'status': {
                'privacyStatus': privacy_status,
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Create media upload
        media = MediaFileUpload(
            video_file,
            chunksize=1024*1024,  # 1MB chunks
            resumable=True,
            mimetype='video/mp4'
        )
        
        try:
            # Execute upload
            request = self.youtube_service.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )
            
            response = None
            print("⏳ Upload w toku...")
            
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"   Postęp: {progress}%", end='\r')
            
            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"
            
            print(f"\n✅ Upload zakończony!")
            print(f"   Video ID: {video_id}")
            print(f"   URL: {video_url}")
            
            # Upload thumbnail if provided
            if thumbnail_file and Path(thumbnail_file).exists():
                self._upload_thumbnail(video_id, thumbnail_file)
            
            # Upload captions if provided
            if srt_file and Path(srt_file).exists():
                self._upload_captions(video_id, srt_file, language='pl')

            # Add to playlist if specified in profile
            playlist_added = False
            if hasattr(self, 'playlist_to_add') and self.playlist_to_add:
                playlist_added = self.playlist_manager.add_video_to_playlist(
                    self.playlist_to_add,
                    video_id
                )

            return {
                'success': True,
                'video_id': video_id,
                'video_url': video_url,
                'title': title,
                'playlist_added': playlist_added
            }
            
        except HttpError as e:
            print(f"❌ HTTP Error: {e.resp.status} - {e.content}")
            return {
                'success': False,
                'error': str(e)
            }
        except Exception as e:
            print(f"❌ Upload failed: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _upload_thumbnail(self, video_id: str, thumbnail_file: str):
        """Upload miniaturki do video"""
        try:
            print(f"🖼️ Upload miniaturki...")
            self.youtube_service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_file)
            ).execute()
            print("✅ Miniaturka dodana")
        except Exception as e:
            print(f"⚠️ Nie udało się dodać miniaturki: {e}")
    
    def _upload_captions(self, video_id: str, srt_file: str, language: str = 'pl'):
        """
        Upload napisów (captions) na YouTube
        
        Args:
            video_id: ID filmu na YouTube  
            srt_file: Ścieżka do pliku SRT
            language: Kod języka (pl, en, etc.)
        """
        if not Path(srt_file).exists():
            print(f"   ⚠️ Plik SRT nie istnieje: {srt_file}")
            return False
        
        try:
            print(f"📝 Upload napisów...")
            
            # Insert caption track
            insert_request = self.youtube_service.captions().insert(
                part='snippet',
                body={
                    'snippet': {
                        'videoId': video_id,
                        'language': language,
                        'name': f'Polski',  # Nazwa track
                        'isDraft': False
                    }
                },
                media_body=MediaFileUpload(
                    srt_file,
                    mimetype='application/octet-stream',
                    resumable=True
                )
            )
            
            response = insert_request.execute()
            print(f"✅ Napisy dodane (język: {language})")
            return True
            
        except HttpError as e:
            error_str = str(e)
            if 'captionTrackAlreadyExists' in error_str:
                print(f"   ⚠️ Napisy już istnieją dla tego filmu")
            else:
                print(f"   ⚠️ Błąd uploadu napisów: {e}")
            return False
    
    def process(
        self,
        video_file: str,
        title: str,
        clips: list,
        segments: list,
        output_dir: Path,
        thumbnail_file: Optional[str] = None,
        privacy_status: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Główna metoda stage'u - authorize i upload
        """
        print("\n" + "="*60)
        print("STAGE 9: YouTube Upload")
        print("="*60)
        
        # Authorize
        self.authorize()
        
        # Generate metadata if auto-enabled
        if self.config.youtube.auto_title:
            title = self._generate_clickbait_title(clips)  # ← ZMIENIONE
        else:
            title = title  # użyj przekazanego tytułu

        if self.config.youtube.auto_description:
            description = self._generate_description(clips, segments)
        else:
            description = "Najciekawsze momenty z Sejmu RP"
        
        # Use config privacy status if not specified
        if privacy_status is None:
            privacy_status = self.config.youtube.privacy_status
        
        # Upload
        result = self.upload_video(
            video_file=video_file,
            title=title,
            description=description,
            tags=tags,
            category_id=self.config.youtube.category_id,
            privacy_status=privacy_status,
            thumbnail_file=thumbnail_file
        )
        
        # Save metadata
        if result.get('success'):
            metadata_file = output_dir / f"youtube_upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            import json
            with open(metadata_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'video_id': result['video_id'],
                    'video_url': result['video_url'],
                    'title': title,
                    'description': description,
                    'tags': tags,
                    'privacy': privacy_status,
                    'uploaded_at': datetime.now().isoformat()
                }, f, indent=2, ensure_ascii=False)
            
            print(f"📄 Metadata zapisane: {metadata_file}")
        
        return result
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Format seconds to MM:SS"""
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes:02d}:{secs:02d}"