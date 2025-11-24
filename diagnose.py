#!/usr/bin/env python3
"""
Diagnostic Script for Sejm Highlights AI
Sprawdza konfigurację i zależności
"""

import sys
import subprocess
from pathlib import Path
import os

def check_python_version():
    """Sprawdź wersję Pythona"""
    version = sys.version_info
    print(f"🐍 Python: {version.major}.{version.minor}.{version.micro}")

    if version.major < 3 or (version.major == 3 and version.minor < 11):
        print("   ❌ BŁĄD: Wymagany Python 3.11+")
        return False
    else:
        print("   ✅ OK")
        return True

def check_ffmpeg():
    """Sprawdź ffmpeg"""
    print("\n🎬 ffmpeg:")
    try:
        result = subprocess.run(
            ['ffmpeg', '-version'],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            # Pobierz pierwszą linię wersji
            first_line = result.stdout.split('\n')[0]
            print(f"   ✅ {first_line}")
            return True
        else:
            print(f"   ❌ BŁĄD: {result.stderr[:200]}")
            return False

    except FileNotFoundError:
        print("   ❌ BŁĄD: ffmpeg nie jest zainstalowany")
        print("   Instalacja:")
        print("      Windows: https://ffmpeg.org/download.html lub choco install ffmpeg")
        print("      Linux: sudo apt install ffmpeg")
        print("      Mac: brew install ffmpeg")
        return False
    except Exception as e:
        print(f"   ❌ BŁĄD: {e}")
        return False

def check_env_file():
    """Sprawdź plik .env"""
    print("\n📄 Plik .env:")
    env_path = Path('.env')

    if not env_path.exists():
        print("   ⚠️ Brak pliku .env")
        print("   Utwórz plik .env z:")
        print("      OPENAI_API_KEY=sk-your-key-here")
        return False

    # Sprawdź czy ma OPENAI_API_KEY
    with open(env_path, 'r') as f:
        content = f.read()

    if 'OPENAI_API_KEY' in content:
        # Sprawdź czy nie jest pusty
        for line in content.split('\n'):
            if line.startswith('OPENAI_API_KEY='):
                key = line.split('=', 1)[1].strip()
                if key and key != 'your-key-here':
                    print(f"   ✅ OPENAI_API_KEY obecny ({key[:10]}...)")
                    return True
                else:
                    print("   ⚠️ OPENAI_API_KEY pusty lub placeholder")
                    return False

    print("   ⚠️ Brak OPENAI_API_KEY")
    return False

def check_directories():
    """Sprawdź katalogi"""
    print("\n📁 Katalogi:")

    dirs = {
        'output': Path('output'),
        'temp': Path('temp'),
        'models': Path('models'),
        'pipeline': Path('pipeline')
    }

    all_ok = True
    for name, path in dirs.items():
        if path.exists():
            print(f"   ✅ {name}/ exists")
        else:
            print(f"   ⚠️ {name}/ BRAK - tworzę...")
            try:
                path.mkdir(parents=True, exist_ok=True)
                print(f"      ✅ Utworzono {name}/")
            except Exception as e:
                print(f"      ❌ Błąd: {e}")
                all_ok = False

    return all_ok

def check_config_file():
    """Sprawdź config.yml"""
    print("\n⚙️ config.yml:")
    config_path = Path('config.yml')

    if not config_path.exists():
        print("   ⚠️ Brak config.yml - użyję domyślnych ustawień")
        return True

    try:
        import yaml
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)

        # Sprawdź kluczowe sekcje
        required_sections = ['selection', 'export', 'shorts']
        for section in required_sections:
            if section in config:
                print(f"   ✅ [{section}] present")
            else:
                print(f"   ⚠️ [{section}] BRAK - użyję domyślnych")

        # Sprawdź kluczowe parametry
        if 'selection' in config:
            target_dur = config['selection'].get('target_total_duration', 'N/A')
            max_clips = config['selection'].get('max_clips', 'N/A')
            print(f"      Target duration: {target_dur}s")
            print(f"      Max clips: {max_clips}")

        if 'shorts' in config:
            shorts_enabled = config['shorts'].get('enabled', False)
            print(f"      Shorts enabled: {shorts_enabled}")

        return True

    except Exception as e:
        print(f"   ❌ Błąd parsowania: {e}")
        return False

def check_packages():
    """Sprawdź zainstalowane pakiety"""
    print("\n📦 Pakiety Python:")

    required = {
        'torch': 'torch',
        'faster_whisper': 'faster-whisper',
        'transformers': 'transformers',
        'openai': 'openai',
        'PyQt6': 'PyQt6',
        'librosa': 'librosa',
        'yaml': 'pyyaml'
    }

    all_ok = True
    for module, package in required.items():
        try:
            __import__(module)
            print(f"   ✅ {package}")
        except ImportError:
            print(f"   ❌ {package} BRAK")
            print(f"      Instalacja: pip install {package}")
            all_ok = False

    return all_ok

def check_gpu():
    """Sprawdź dostępność GPU"""
    print("\n🎮 GPU:")

    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            print(f"   ✅ CUDA available: {device_name}")
            print(f"   GPU Memory: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")
            return True
        else:
            print("   ⚠️ CUDA nie jest dostępne - użyję CPU (wolniejsze)")
            return False

    except Exception as e:
        print(f"   ⚠️ Nie mogę sprawdzić GPU: {e}")
        return False

def test_config_load():
    """Test załadowania config"""
    print("\n🧪 Test Config:")

    try:
        from pipeline.config import Config

        config = Config.load_default()
        print("   ✅ Config załadowany")

        config.validate()
        print("   ✅ Config walidacja OK")

        return True

    except Exception as e:
        print(f"   ❌ Błąd: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Główna funkcja diagnostyczna"""
    print("=" * 60)
    print("🔍 Sejm Highlights AI - Diagnostic Check")
    print("=" * 60)

    results = {
        'Python version': check_python_version(),
        'ffmpeg': check_ffmpeg(),
        '.env file': check_env_file(),
        'Directories': check_directories(),
        'config.yml': check_config_file(),
        'Python packages': check_packages(),
        'GPU': check_gpu(),
        'Config load': test_config_load()
    }

    print("\n" + "=" * 60)
    print("📊 PODSUMOWANIE")
    print("=" * 60)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for name, status in results.items():
        status_icon = "✅" if status else "❌"
        print(f"{status_icon} {name}")

    print(f"\n📈 Wynik: {passed}/{total} testów OK")

    if passed == total:
        print("\n🎉 Wszystko działa! Możesz uruchomić aplikację:")
        print("   python app.py")
    else:
        print("\n⚠️ Znaleziono problemy. Sprawdź powyżej i napraw przed uruchomieniem.")
        print("\nPomoc:")
        print("   - Zobacz TROUBLESHOOTING.md")
        print("   - Sprawdź requirements.txt: pip install -r requirements.txt")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
