# 🚨 NAPRAW BRAKUJĄCE GUI - sejm_app.py

## Problem
Uruchamiasz starą wersję sejm_app.py - brakuje tabów i opcji!

## Rozwiązanie

### Krok 1: Pobierz najnowszą wersję z repo
```powershell
# Na Twoim Windows, w folderze projektu
git fetch origin

# Sprawdź current branch
git branch

# Pull najnowszą wersję
git pull origin claude/fix-pkg-resources-warning-01Wb9pwbhPvztS6Fe7dVrC49
```

### Krok 2: Sprawdź czy apps/ folder się pojawił
```powershell
dir apps
```

Powinno pokazać:
```
apps/
  README.md
  sejm_app.py (1385 linii!)
  stream_app.py
```

### Krok 3: Uruchom NOWĄ wersję
```powershell
python apps\sejm_app.py
```

## Co powinieneś zobaczyć:

✅ **6 TABÓW:**
1. 📊 Output
2. 🤖 Smart Splitter
3. 🎯 Scoring & Selection ← NOWY!
4. 🧠 AI Models
5. ⚙️ Advanced
6. 📺 YouTube

✅ **URL Download** (pobieranie z YouTube)

✅ **Wszystkie opcje** z config.yml

## Jeśli git pull nie działa:

### Opcja A: Stash local changes
```powershell
git stash
git pull origin claude/fix-pkg-resources-warning-01Wb9pwbhPvztS6Fe7dVrC49
git stash pop
```

### Opcja B: Hard reset (OSTROŻNIE - traci lokalne zmiany!)
```powershell
git fetch origin
git reset --hard origin/claude/fix-pkg-resources-warning-01Wb9pwbhPvztS6Fe7dVrC49
```

### Opcja C: Fresh clone
```powershell
cd ..
git clone https://github.com/AdamStankiewic/Sejm-Highlights-Final.git "Sejm Highlights Final NEW"
cd "Sejm Highlights Final NEW"
git checkout claude/fix-pkg-resources-warning-01Wb9pwbhPvztS6Fe7dVrC49
python apps\sejm_app.py
```

## Weryfikacja

Po git pull, uruchom:
```powershell
python apps\sejm_app.py
```

Powinieneś zobaczyć:
- Tytuł: "Sejm Highlights AI - Automated Video Compiler v2.0"
- 6 tabów na górze
- Tab "Scoring & Selection" z wagami (GPT Semantic: 0.70, etc.)
- Wszystkie kontrolki

## Jeśli NADAL nie działa:

Wyślij mi output z:
```powershell
git status
git log --oneline -5
dir apps
```

I pomogę zdiagnozować!
