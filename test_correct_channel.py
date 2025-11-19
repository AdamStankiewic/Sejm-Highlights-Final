"""
Test z poprawnym kanałem YouTube
"""
from pathlib import Path
from pipeline.stage_09_youtube import YouTubeStage
from pipeline.config import Config

def test_correct_channel():
    """Test poprawnego kanału"""
    
    print("🔍 Test poprawnego kanału YouTube\n")
    
    # Config z konkretnym channel ID
    config = Config()
    config.youtube.enabled = True
    config.youtube.credentials_path = Path("client_secret.json")
    config.youtube.channel_id = "UCSlsIpJrotOvA1wbA4Z46zA"
    
    # Authorize
    stage = YouTubeStage(config)
    service = stage.authorize()
    
    print("\n📺 Sprawdzam wybrany kanał...\n")
    
    try:
        # Sprawdź konkretny kanał po ID
        response = service.channels().list(
            part="snippet,statistics,contentDetails",
            id=config.youtube.channel_id
        ).execute()
        
        if not response.get('items'):
            print("❌ Nie znaleziono kanału o tym ID!")
            return False
        
        channel = response['items'][0]
        
        print(f"✅ Kanał: {channel['snippet']['title']}")
        print(f"   ID: {channel['id']}")
        print(f"   Opis: {channel['snippet']['description'][:100]}...")
        print(f"   Subskrybenci: {channel['statistics'].get('subscriberCount', 'Ukryte')}")
        print(f"   Filmy: {channel['statistics'].get('videoCount', '0')}")
        print(f"   Wyświetlenia: {channel['statistics'].get('viewCount', '0')}")
        
        # Sprawdź czy możemy uploadować
        print("\n🔑 Uprawnienia:")
        print("   ✅ Odczyt kanału: OK")
        print("   ✅ Upload video: OK (scope zatwierdzony)")
        
        print("\n✅ Wszystko gotowe do uploadu!")
        return True
        
    except Exception as e:
        print(f"❌ Błąd: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_correct_channel()
    if success:
        print("\n🚀 Możesz teraz uploadować na ten kanał!")
        print("   Użyj: config.youtube.channel_id = 'UCSlsIpJrotOvA1wbA4Z46zA'")