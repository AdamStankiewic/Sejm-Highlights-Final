# MIGRATION: Shorts 2.0 (Vertical Templates)

## Zakres zmian
- Usunięto wsparcie dla starych układów `side_left`/`side_right`; nowe szablony pionowe zastępują poprzednie layouty.
- Dodano zależność **MediaPipe** do detekcji twarzy (zainstaluj: `pip install mediapipe`).
- Pipeline `stage_10_shorts.py` korzysta teraz z multi-frame detekcji (5 próbek) i nowych szablonów 9:16.

## Kroki migracji
1. **Zaktualizuj konfigurację** – w sekcji `shorts:` w `config.yml` dodaj pola:
   - `face_detection`, `num_samples`, `detection_threshold`, `webcam_detection_confidence`
   - `template`, `manual_template`
   - sekcje `game_top_face_bar` oraz `floating_face` z parametrami layoutu
2. **Zainstaluj zależności** – upewnij się, że środowisko ma MediaPipe (oraz FFmpeg, OpenCV zgodnie z README).
3. **Dostosuj wywołania** – wszelkie odwołania do `side_left`/`side_right` usuń lub zamień na nowe szablony (`game_top_face_bottom_bar`, `full_game_with_floating_face`, `simple_game_only`, `big_face_reaction`).
4. **Sprawdź pipeline** – uruchom generowanie pojedynczego shorta, obserwuj logi detekcji (`zone`, `detection_rate`) i wybrany template.

## Backward compatibility
- Jeśli musisz wygenerować shorty po staremu, użyj brancha `backup-before-vertical-templates` utworzonego przed migracją.
- Format wyjściowy pozostaje 1080x1920 MP4, więc integracja z uploaderami nie wymaga zmian.

## Rollback
- W razie krytycznych problemów: revert merge/commit nowego systemu lub przełącz się na `backup-before-vertical-templates`.
- Zmiany są głównie w `stage_10_shorts.py` i `config.yml`, więc rollback jest prosty.

## Notatki wdrożeniowe
- Rekomendowany rollout: canary 10% → 50% → 100% (patrz README sekcja "Plan wdrożenia Shorts 2.0").
- Monitoruj: czasy renderu, `detection_rate`, oraz dystrybucję wybranych szablonów; w razie błędów rozważ korektę `detection_threshold` lub wymuszenie szablonu.
