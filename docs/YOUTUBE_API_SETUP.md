# YouTube Data API v3 - Setup Guide

## Krok po kroku:

### 1. Utwórz projekt w Google Cloud Console

1. Idź do: https://console.cloud.google.com/
2. Zaloguj się kontem Google
3. Kliknij "Select a project" → "New Project"
4. Nazwa: "Sejm Highlights Pipeline" (dowolna)
5. Kliknij "Create"

### 2. Włącz YouTube Data API v3

1. W Google Cloud Console, przejdź do:
   **APIs & Services** → **Library**

   Link bezpośredni: https://console.cloud.google.com/apis/library

2. Wyszukaj: **"YouTube Data API v3"**

3. Kliknij na **YouTube Data API v3**

4. Kliknij **"ENABLE"**

### 3. Utwórz API Key

1. Przejdź do: **APIs & Services** → **Credentials**

   Link bezpośredni: https://console.cloud.google.com/apis/credentials

2. Kliknij **"+ CREATE CREDENTIALS"** → **"API key"**

3. Skopiuj wygenerowany klucz:
   ```
   AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
   ```

4. (Opcjonalnie) Kliknij "RESTRICT KEY" i ogranicz do:
   - Application restrictions: None (lub HTTP referrers jeśli webapp)
   - API restrictions: Restrict key → YouTube Data API v3

### 4. Dodaj do .env

```bash
# .env (w głównym katalogu projektu)
OPENAI_API_KEY=sk-proj-...
YOUTUBE_API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

### 5. Test API key

```python
from pipeline.learning.youtube_api import YouTubeMetricsAPI

api = YouTubeMetricsAPI(api_key="YOUR_API_KEY")

# Test: pobierz filmy z kanału Sejm
channel_id = "UCSlsIpJrotOvA1wbA4Z46zA"
videos = api.get_channel_videos(channel_id, max_results=5)

print(f"✅ Znaleziono {len(videos)} filmów")
```

## Limity i koszty

### Quota limits (FREE tier):
- **10,000 units/day** (domyślnie)
- Operacje:
  - `videos.list`: 1 unit per video
  - `search.list`: 100 units per request

### Przykład zużycia:
```
Learning loop dla 1 streamera (50 filmów):
- search.list (50 videos): ~100 units
- videos.list (50 videos): ~50 units
TOTAL: ~150 units

Możesz uruchomić ~66 razy dziennie na FREE tier!
```

### Zwiększenie limitu:
Jeśli potrzebujesz więcej → Request quota increase:
https://console.cloud.google.com/apis/api/youtube.googleapis.com/quotas

---

## Troubleshooting

### "API key not valid"
- Sprawdź czy YouTube Data API v3 jest włączony
- Sprawdź czy API key jest correct (bez spacji)
- Sprawdź restrictions (może być zbyt restrykcyjny)

### "Quota exceeded"
- Czekaj do północy PST (Pacific Time) - quota resetuje się
- Lub request quota increase

### "The request cannot be completed because you have exceeded your quota"
- To samo co wyżej - dzienny limit przekroczony

---

## Security best practices

1. **Nigdy nie commituj API key do git**
   ```bash
   # .gitignore (powinno już być)
   .env
   ```

2. **Używaj API restrictions**
   - Ogranicz do YouTube Data API v3
   - Ogranicz do IP (jeśli server)

3. **Rotuj klucze regularnie**
   - Co 90 dni
   - Jeśli podejrzewasz leak

4. **Monitoruj usage**
   - Google Cloud Console → APIs & Services → Dashboard
   - Zobacz ile units zużywasz dziennie

---

## Alternatywy (jeśli nie chcesz Google Cloud)

### Opcja 1: Bez learning loop
- Używaj tylko seed examples (ręczne)
- Brak automatycznego uczenia z YouTube metrics
- Wciąż AI generation działa (tytuły/opisy)

### Opcja 2: Scraping (NIE ZALECANE)
- Można scrapować YouTube bez API
- Naruszenie ToS YouTube
- Ryzyko IP ban
- Nie polecam!

---

## Next steps po uzyskaniu API key

1. Dodaj do `.env`:
   ```bash
   YOUTUBE_API_KEY=AIzaSy...
   ```

2. Test:
   ```bash
   python scripts/test_metadata_generation.py
   ```

3. Run learning loop:
   ```bash
   python scripts/run_learning_loop.py --streamer sejm
   ```

4. Verify database populated:
   ```bash
   python scripts/test_metadata_generation.py
   # Should show: streamer_learned_examples: 18+ rows
   ```
