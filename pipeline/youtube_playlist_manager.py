"""
YouTube Playlist Manager
Manages playlists - list, create, add videos
"""

from typing import Dict, List, Optional, Any
from googleapiclient.errors import HttpError


class PlaylistManager:
    """Manages YouTube playlists"""

    def __init__(self, youtube_service):
        """
        Args:
            youtube_service: Authenticated YouTube API service
        """
        self.youtube = youtube_service

    def list_playlists(self, channel_id: Optional[str] = None, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        List all playlists for a channel

        Args:
            channel_id: Channel ID (if None, uses 'mine')
            max_results: Max number of playlists to return

        Returns:
            List of playlist dicts with id, title, itemCount
        """
        try:
            request_params = {
                'part': 'snippet,contentDetails',
                'maxResults': max_results
            }

            if channel_id:
                request_params['channelId'] = channel_id
            else:
                request_params['mine'] = True

            response = self.youtube.playlists().list(**request_params).execute()

            playlists = []
            for item in response.get('items', []):
                playlists.append({
                    'id': item['id'],
                    'title': item['snippet']['title'],
                    'description': item['snippet'].get('description', ''),
                    'item_count': item['contentDetails']['itemCount'],
                    'privacy': item.get('status', {}).get('privacyStatus', 'unknown')
                })

            return playlists

        except HttpError as e:
            print(f"   ⚠️ Błąd listowania playlist: {e}")
            return []

    def create_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "public"
    ) -> Optional[str]:
        """
        Create new playlist

        Args:
            title: Playlist title
            description: Playlist description
            privacy_status: public, private, or unlisted

        Returns:
            Playlist ID if successful, None otherwise
        """
        try:
            request_body = {
                'snippet': {
                    'title': title,
                    'description': description
                },
                'status': {
                    'privacyStatus': privacy_status
                }
            }

            response = self.youtube.playlists().insert(
                part='snippet,status',
                body=request_body
            ).execute()

            playlist_id = response['id']
            print(f"   ✅ Utworzono playlist: {title} (ID: {playlist_id})")
            return playlist_id

        except HttpError as e:
            print(f"   ❌ Błąd tworzenia playlist: {e}")
            return None

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Add video to playlist

        Args:
            playlist_id: Playlist ID
            video_id: Video ID to add

        Returns:
            True if successful
        """
        try:
            request_body = {
                'snippet': {
                    'playlistId': playlist_id,
                    'resourceId': {
                        'kind': 'youtube#video',
                        'videoId': video_id
                    }
                }
            }

            self.youtube.playlistItems().insert(
                part='snippet',
                body=request_body
            ).execute()

            print(f"   ✅ Dodano video do playlist")
            return True

        except HttpError as e:
            print(f"   ⚠️ Błąd dodawania do playlist: {e}")
            return False

    def get_playlist_by_title(self, title: str, channel_id: Optional[str] = None) -> Optional[str]:
        """
        Find playlist by title

        Args:
            title: Playlist title to search for
            channel_id: Optional channel ID

        Returns:
            Playlist ID if found, None otherwise
        """
        playlists = self.list_playlists(channel_id=channel_id)

        for playlist in playlists:
            if playlist['title'].lower() == title.lower():
                return playlist['id']

        return None

    def ensure_playlist(
        self,
        title: str,
        description: str = "",
        privacy_status: str = "public",
        channel_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get playlist ID by title, create if doesn't exist

        Args:
            title: Playlist title
            description: Description for new playlist
            privacy_status: Privacy for new playlist
            channel_id: Optional channel ID

        Returns:
            Playlist ID
        """
        # Check if playlist exists
        playlist_id = self.get_playlist_by_title(title, channel_id)

        if playlist_id:
            print(f"   📋 Używam istniejącej playlist: {title}")
            return playlist_id

        # Create new playlist
        print(f"   📋 Tworzę nową playlist: {title}")
        return self.create_playlist(title, description, privacy_status)
