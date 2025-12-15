#!/usr/bin/env python3
"""
Test weryfikujący mechanizm single-flight w PipelineProcessor

Symuluje podwójne uruchomienie pipeline'u i sprawdza czy:
1. Pierwsze uruchomienie działa normalnie
2. Drugie uruchomienie jest blokowane z RuntimeError
3. Lock jest poprawnie zwalniany po zakończeniu

UWAGA: Ten test NIE uruchamia faktycznego pipeline'u (wymaga GPU, API keys, etc.)
       Używa mock'ów aby przetestować tylko logikę single-flight.
"""

import threading
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path


def test_single_flight():
    """
    Test mechanizmu single-flight
    """
    print("\n" + "=" * 80)
    print("TEST: Single-Flight Mechanism")
    print("=" * 80 + "\n")

    # Reset class-level state before test
    from pipeline.processor import PipelineProcessor
    PipelineProcessor._is_running = False
    PipelineProcessor._current_run_id = None

    # Mock config
    mock_config = Mock()
    mock_config.validate = Mock()
    mock_config.temp_dir = Path("temp")
    mock_config.output_dir = Path("output")
    mock_config.keep_intermediate = False

    # Mock config attributes
    mock_config.splitter = Mock()
    mock_config.splitter.enabled = False

    mock_config.shorts = Mock()
    mock_config.shorts.enabled = False

    mock_config.youtube = Mock()
    mock_config.youtube.enabled = False

    # === TEST 1: Pojedyncze uruchomienie powinno działać ===
    print("TEST 1: Pojedyncze uruchomienie")
    print("-" * 40)

    processor1 = PipelineProcessor(mock_config)

    # Mock metody aby nie uruchamiać faktycznego pipeline'u
    with patch.object(processor1, '_create_session_directory_with_run_id', return_value=Path("temp/test")):
        with patch.object(processor1.stages['ingest'], 'process', return_value={
            'audio_normalized': 'test.wav',
            'metadata': {'duration': 100, 'width': 1920, 'height': 1080, 'fps': 30}
        }):
            # Mock pozostałe stages aby zwracały minimal data
            for stage_name in ['vad', 'transcribe', 'features', 'scoring', 'selection', 'export']:
                mock_result = {
                    'segments': [],
                    'clips': [],
                    'total_duration': 0,
                    'output_file': 'test.mp4'
                }
                processor1.stages[stage_name].process = Mock(return_value=mock_result)

            # Create fake input file
            fake_input = "test_video.mp4"
            with patch('pathlib.Path.exists', return_value=True):
                try:
                    # Ten process() call powinien działać normalnie
                    result = processor1.process(fake_input)

                    print(f"✅ Uruchomienie zakończone pomyślnie")
                    print(f"   RUN_ID: {result.get('run_id')}")
                    print(f"   Lock released: {not PipelineProcessor._is_running}")

                    assert result['success'] is True
                    assert result['run_id'] is not None
                    assert not PipelineProcessor._is_running, "Lock powinien być zwolniony!"

                except Exception as e:
                    print(f"❌ FAIL: {e}")
                    raise

    print()

    # === TEST 2: Równoległe uruchomienia - drugie powinno być zablokowane ===
    print("TEST 2: Podwójne uruchomienie (concurrent)")
    print("-" * 40)

    # Reset lock
    PipelineProcessor._is_running = False
    PipelineProcessor._current_run_id = None

    results = {'first': None, 'second': None}
    errors = {'first': None, 'second': None}

    def run_pipeline(name: str, delay: float = 0):
        """Helper do uruchomienia pipeline w osobnym wątku"""
        time.sleep(delay)

        processor = PipelineProcessor(mock_config)

        with patch.object(processor, '_create_session_directory_with_run_id', return_value=Path("temp/test")):
            # Mock długie przetwarzanie (1 sekunda)
            def slow_ingest(*args, **kwargs):
                time.sleep(1)
                return {
                    'audio_normalized': 'test.wav',
                    'metadata': {'duration': 100, 'width': 1920, 'height': 1080, 'fps': 30}
                }

            with patch.object(processor.stages['ingest'], 'process', side_effect=slow_ingest):
                # Mock pozostałe stages
                for stage_name in ['vad', 'transcribe', 'features', 'scoring', 'selection', 'export']:
                    mock_result = {
                        'segments': [],
                        'clips': [],
                        'total_duration': 0,
                        'output_file': 'test.mp4'
                    }
                    processor.stages[stage_name].process = Mock(return_value=mock_result)

                with patch('pathlib.Path.exists', return_value=True):
                    try:
                        result = processor.process("test_video.mp4")
                        results[name] = result
                        print(f"   [{name}] ✅ Zakończone - RUN_ID: {result.get('run_id')}")
                    except RuntimeError as e:
                        errors[name] = str(e)
                        print(f"   [{name}] 🚫 Zablokowane: {e}")
                    except Exception as e:
                        errors[name] = str(e)
                        print(f"   [{name}] ❌ Błąd: {e}")

    # Uruchom dwa thready równolegle
    thread1 = threading.Thread(target=run_pipeline, args=("first", 0))
    thread2 = threading.Thread(target=run_pipeline, args=("second", 0.1))  # 100ms delay

    thread1.start()
    thread2.start()

    thread1.join()
    thread2.join()

    print()

    # === WERYFIKACJA ===
    print("WERYFIKACJA:")
    print("-" * 40)

    # Jeden powinien się udać, drugi powinien być zablokowany
    success_count = sum(1 for r in results.values() if r is not None)
    blocked_count = sum(1 for e in errors.values() if e and "already running" in e)

    print(f"Udane uruchomienia: {success_count}")
    print(f"Zablokowane uruchomienia: {blocked_count}")

    if success_count == 1 and blocked_count == 1:
        print("\n✅ TEST PASSED - Single-flight działa poprawnie!")
        print("   - Pierwsze uruchomienie: OK")
        print("   - Drugie uruchomienie: Zablokowane (expected)")
        print("   - Lock zwolniony po zakończeniu")
    else:
        print(f"\n❌ TEST FAILED")
        print(f"   Expected: 1 success, 1 blocked")
        print(f"   Got: {success_count} success, {blocked_count} blocked")
        raise AssertionError("Single-flight nie działa poprawnie!")

    # Final check - lock powinien być zwolniony
    assert not PipelineProcessor._is_running, "Lock powinien być zwolniony po wszystkich operacjach!"

    print("\n" + "=" * 80)
    print("✅ WSZYSTKIE TESTY ZAKOŃCZONE POMYŚLNIE")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    test_single_flight()
