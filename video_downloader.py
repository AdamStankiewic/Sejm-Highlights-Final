"""
YouTube Downloader Module
Integracja z yt-dlp dla pobierania video z linków (YouTube, Twitch, etc.)
"""

import os
import sys
from pathlib import Path
from typing import Optional, Callable, Dict, Any
import subprocess
import json


class VideoDownloader:
    """
    Wrapper dla yt-dlp do pobierania video z różnych platform
    
    Wspiera:
    - YouTube (w tym transmisje)
    - Twitch (VOD i clippsy)
    - Facebook Live
    - I ~1000 innych platform
    """
    
    def __init__(self, download_dir: str = "downloads"):
        """
        Args:
            download_dir: Folder do zapisywania pobranych video
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(exist_ok=True)
        
        # Progress callback
        self.progress_callback: Optional[Callable] = None
        
        # Check if yt-dlp is installed
        self._check_ytdlp()
    
    def _check_ytdlp(self):
        """Sprawdź czy yt-dlp jest zainstalowane"""
        try:
            result = subprocess.run(
                ['yt-dlp', '--version'],
                capture_output=True,
                text=True,
                check=True
            )
            version = result.stdout.strip()
            print(f"✓ yt-dlp version: {version}")
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise RuntimeError(
                "yt-dlp nie jest zainstalowane!\n"
                "Zainstaluj: pip install yt-dlp"
            )
    
    def set_progress_callback(self, callback: Callable[[str, int], None]):
        """
        Ustaw callback dla postępu pobierania
        
        Args:
            callback(message: str, percent: int)
        """
        self.progress_callback = callback
    
    def get_video_info(self, url: str) -> Dict[str, Any]:
        """
        Pobierz informacje o video bez pobierania
        
        Args:
            url: URL do video
            
        Returns:
            Dict z metadata (tytuł, długość, format, etc.)
        """
        cmd = [
            'yt-dlp',
            '--dump-json',
            '--no-download',
            url
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                encoding='utf-8'
            )
            
            info = json.loads(result.stdout)
            
            # Extract key info
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),  # seconds
                'uploader': info.get('uploader', 'Unknown'),
                'upload_date': info.get('upload_date', ''),
                'view_count': info.get('view_count', 0),
                'description': info.get('description', ''),
                'formats_available': len(info.get('formats', [])),
                'is_live': info.get('is_live', False),
                'was_live': info.get('was_live', False),
            }
            
        except subprocess.CalledProcessError as e:
            error_msg = e.stderr if e.stderr else str(e)
            raise ValueError(f"Nie można pobrać informacji o video: {error_msg}")
        except json.JSONDecodeError:
            raise ValueError("Błąd parsowania informacji o video")
    
    def download(
        self,
        url: str,
        output_name: Optional[str] = None,
        max_quality: str = "1080"
    ) -> str:
        """
        Pobierz video z URL
        
        Args:
            url: URL do video (YouTube, Twitch, etc.)
            output_name: Opcjonalna nazwa wyjściowa (bez rozszerzenia)
            max_quality: Maksymalna jakość (720, 1080, 1440, 2160)
            
        Returns:
            Ścieżka do pobranego pliku
        """
        # Generate output filename
        if output_name:
            output_template = str(self.download_dir / f"{output_name}.%(ext)s")
        else:
            # Use video title as filename
            output_template = str(self.download_dir / "%(title)s.%(ext)s")
        
        # Build yt-dlp command
        # Format selection:
        # - bestvideo[height<=1080]: Najlepsze video do 1080p
        # - bestaudio: Najlepsze audio
        # - best[height<=1080]: Fallback dla platform bez oddzielnych strumieni
        cmd = [
            'yt-dlp',
            
            # Format selection (1080p max dla długich video)
            '-f', f'bestvideo[height<={max_quality}]+bestaudio/best[height<={max_quality}]',
            
            # Merge to MP4
            '--merge-output-format', 'mp4',
            
            # Output
            '-o', output_template,
            
            # Progress
            '--newline',  # Progress na nowych liniach (łatwiej parsować)
            
            # Continue on errors
            '--no-abort-on-error',
            
            # Retry
            '--retries', '3',
            '--fragment-retries', '3',
            
            # No playlist (tylko pojedyncze video)
            '--no-playlist',
            
            # URL
            url
        ]
        
        print(f"📥 Pobieranie video z: {url}")
        print(f"📁 Katalog: {self.download_dir}")
        print(f"🎬 Maksymalna jakość: {max_quality}p")
        
        try:
            # Run yt-dlp with progress tracking
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1
            )
            
            # Parse progress
            for line in process.stdout:
                line = line.strip()
                
                if line:
                    # Parse download progress
                    if '[download]' in line:
                        # Extract percentage
                        if '%' in line:
                            try:
                                # Format: "[download] 45.2% of 123.45MiB at 1.23MiB/s ETA 00:12"
                                parts = line.split()
                                percent_str = parts[1].rstrip('%')
                                percent = float(percent_str)
                                
                                if self.progress_callback:
                                    self.progress_callback(
                                        f"Pobieranie: {percent:.1f}%",
                                        int(percent)
                                    )
                            except (ValueError, IndexError):
                                pass
                        
                        # Print progress
                        print(f"   {line}")
                    
                    # Merge info
                    elif '[Merger]' in line:
                        if self.progress_callback:
                            self.progress_callback("Łączenie video i audio...", 95)
                        print(f"   {line}")
                    
                    # Final destination
                    elif 'Destination:' in line or 'already been downloaded' in line:
                        print(f"   {line}")
            
            # Wait for completion
            return_code = process.wait()
            
            if return_code != 0:
                raise RuntimeError(f"yt-dlp zakończył się błędem (kod: {return_code})")
            
            # Find downloaded file
            downloaded_file = self._find_downloaded_file(output_name)
            
            if not downloaded_file:
                raise RuntimeError("Nie można znaleźć pobranego pliku")
            
            print(f"✅ Pobrano: {downloaded_file}")
            
            if self.progress_callback:
                self.progress_callback("Pobieranie zakończone!", 100)
            
            return str(downloaded_file)
            
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Błąd pobierania: {error_msg}")
            
            if self.progress_callback:
                self.progress_callback(f"Błąd: {error_msg}", 0)
            
            raise
    
    def _find_downloaded_file(self, expected_name: Optional[str] = None) -> Optional[Path]:
        """
        Znajdź ostatnio pobrany plik w katalogu
        
        Args:
            expected_name: Oczekiwana nazwa (bez rozszerzenia)
        """
        # Get all MP4 files
        mp4_files = list(self.download_dir.glob("*.mp4"))
        
        if not mp4_files:
            return None
        
        # If expected name provided, try to find it
        if expected_name:
            for file in mp4_files:
                if expected_name in file.stem:
                    return file
        
        # Otherwise return newest file
        newest_file = max(mp4_files, key=lambda f: f.stat().st_mtime)
        return newest_file
    
    def format_duration(self, seconds: int) -> str:
        """Format duration in seconds to HH:MM:SS"""
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        
        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"


# === Test standalone ===
if __name__ == "__main__":
    import sys
    
    # Test usage
    downloader = VideoDownloader(download_dir="test_downloads")
    
    # Example URL (short test video)
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"  # Rick Astley - Never Gonna Give You Up
    
    # Set progress callback
    def progress(msg, percent):
        print(f"Progress: [{percent:3d}%] {msg}")
    
    downloader.set_progress_callback(progress)
    
    try:
        # Get info first
        print("\n=== Getting video info ===")
        info = downloader.get_video_info(test_url)
        print(f"Title: {info['title']}")
        print(f"Duration: {downloader.format_duration(info['duration'])}")
        print(f"Uploader: {info['uploader']}")
        
        # Download
        print("\n=== Downloading ===")
        output_file = downloader.download(test_url, output_name="test_video")
        print(f"\n✅ Success! Downloaded to: {output_file}")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
