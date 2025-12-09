# Quick Fix Guide - Numpy Error

## Problem
```
❌ Błąd: Błąd wczytywania audio: Numpy is not available
```

## Przyczyna
Brak zainstalowanych dependencies (numpy, torchaudio) w środowisku Python.

## Rozwiązanie

### Krok 1: Aktywuj virtual environment (jeśli używasz)
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

### Krok 2: Zainstaluj wszystkie dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Krok 3: Weryfikacja
```bash
python -c "import numpy; print('numpy OK:', numpy.__version__)"
python -c "import torchaudio; print('torchaudio OK:', torchaudio.__version__)"
```

### Jeśli nadal problem - Manualna instalacja:
```bash
# Core dependencies
pip install numpy>=1.24.0
pip install torch>=2.1.0 torchaudio>=2.1.0

# For CUDA GPU (optional)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# All other dependencies
pip install librosa soundfile pydub scipy
pip install spacy transformers faster-whisper
pip install PyQt6 PyYAML openai
```

### Sprawdź Python version:
```bash
python --version  # Should be 3.11+
```

## Dodatkowe kroki jeśli błąd persist:

### 1. Usuń stare instalacje:
```bash
pip uninstall numpy torch torchaudio -y
```

### 2. Zainstaluj ponownie:
```bash
pip install numpy torch torchaudio
```

### 3. Sprawdź czy używasz właściwego Python:
```bash
which python  # Linux/Mac
where python  # Windows
```

Upewnij się, że jest to Python z twojego venv!

## Najczęstsze przyczyny:

1. **Brak aktywowanego venv** - Packages zainstalowane globalnie, nie w projekcie
2. **Zły interpreter** - IDE używa innego Python niż terminal
3. **Broken dependencies** - Konflikt wersji między pakietami
4. **Cache issues** - Stary pip cache

## Szybki test całego środowiska:

```bash
# Uruchom to w terminalu:
python -c "
import sys
print('Python:', sys.version)
try:
    import numpy
    print('✓ numpy:', numpy.__version__)
except:
    print('✗ numpy missing!')

try:
    import torch
    print('✓ torch:', torch.__version__)
except:
    print('✗ torch missing!')

try:
    import torchaudio
    print('✓ torchaudio:', torchaudio.__version__)
except:
    print('✗ torchaudio missing!')
"
```

## W PyCharm/VS Code:

1. Otwórz Settings → Project Interpreter
2. Sprawdź czy wybrany jest właściwy venv
3. Zainstaluj brakujące pakiety przez GUI lub:
   ```bash
   pip install -r requirements.txt
   ```

## Nuclear option (ostateczność):

```bash
# Usuń venv i stwórz od nowa
rm -rf venv  # Linux/Mac
rmdir /s venv  # Windows

python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

pip install --upgrade pip
pip install -r requirements.txt
```
