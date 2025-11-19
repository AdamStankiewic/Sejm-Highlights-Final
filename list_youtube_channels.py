"""
Lista wszystkich kanałów YouTube powiązanych z kontem
"""
from pathlib import Path
from pipeline.stage_09_youtube import YouTubeStage
from pipeline.config import Config

def list_channels():
    """Wyświetl wszystkie kanały"""
    
    config = Config()
    config.youtube.enabled = True
    config.youtube.credentials_path = Path("client_secret.json")
    
    stage = YouTubeStage(config)
    service = stage.authorize()
    
    print("\n📺 Twoje kanały YouTube:\n")
    
    try:
        # Pobierz WSZYSTKIE kanały
        response = service.channels().list(
            part="snippet,contentDetails,statistics",
            mine=True,
            maxResults=50
        ).execute()
        
        if not response.get('items'):
            print("❌ Nie znaleziono kanałów")
            return
        
        channels = response['items']
        
        for i, channel in enumerate(channels, 1):
            channel_id = channel['id']
            title = channel['snippet']['title']
            description = channel['snippet']['description'][:100]
            subs = channel['statistics'].get('subscriberCount', '0')
            videos = channel['statistics'].get('videoCount', '0')
            
            print(f"{i}. {title}")
            print(f"   ID: {channel_id}")
            print(f"   Opis: {description}...")
            print(f"   Subskrybenci: {subs}")
            print(f"   Filmy: {videos}")
            print()
        
        print(f"\n✅ Znaleziono {len(channels)} kanałów")
        print("\n💡 Skopiuj ID właściwego kanału i użyj go w konfiguracji")
        
    except Exception as e:
        print(f"❌ Błąd: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    list_channels()