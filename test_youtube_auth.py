"""
Test autoryzacji YouTube API
"""

import os
import sys
from pathlib import Path

# Dodaj ścieżkę do projektu
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_auth():
    """Test OAuth flow"""
    
    from pipeline.stage_09_youtube import YouTubeStage
    from pipeline.config import Config
    
    print("🔐 Test autoryzacji YouTube API\n")
    
    # Sprawdź czy istnieje plik credentials
    creds_file = project_root / "client_secret.json"
    if not creds_file.exists():
        print(f"❌ Brak pliku: {creds_file}")
        print("\n📋 Pobierz credentials z:")
        print("   https://console.cloud.google.com/apis/credentials")
        return False
    
    print(f"✅ Znaleziono credentials: {creds_file}\n")
    
    try:
        # Utwórz config
        config = Config()
        config.youtube.enabled = True
        config.youtube.credentials_path = creds_file
        
        # Utwórz stage
        stage = YouTubeStage(config)
        
        # Authorize
        print("🌐 Otwieram przeglądarkę dla OAuth...")
        print("   Zaloguj się i zatwierdź dostęp\n")
        
        service = stage.authorize()
        
        if service:
            print("\n✅ Autoryzacja udana!")
            print(f"   Token zapisany w: youtube_token.json\n")
            
            # Sprawdź kanał
            try:
                response = service.channels().list(
                    part="snippet,statistics",
                    mine=True
                ).execute()
                
                if response.get('items'):
                    channel = response['items'][0]
                    print(f"📺 Kanał: {channel['snippet']['title']}")
                    print(f"   Subskrybenci: {channel['statistics'].get('subscriberCount', 'N/A')}")
                    print(f"   Filmy: {channel['statistics'].get('videoCount', 'N/A')}")
                else:
                    print("⚠️ Brak danych o kanale")
            except Exception as e:
                print(f"⚠️ Nie można pobrać danych kanału: {e}")
            
            return True
        else:
            print("❌ Autoryzacja nieudana")
            return False
            
    except Exception as e:
        print(f"❌ Błąd: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_auth()
    sys.exit(0 if success else 1)