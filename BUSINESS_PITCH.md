# Biznesowy Pitch – Shorts 2.0 (layout pionowy)

## Problem
- Dotychczasowe shorty wykorzystywały układ z bocznymi paskami (facecam obok gameplay), co zmniejszało czytelność akcji na ekranie mobilnym.
- Detekcja facecama była mało skuteczna (~60%), przez co wymagała wielu ręcznych poprawek kadrów.
- Renderowanie batcha ~50 shortów zajmowało 3–4 godziny, obciążając zasoby i opóźniając publikacje.

## Rozwiązanie
- **Layout pionowy 9:16**: gameplay na pełną szerokość, facecam jako pasek na dole lub PIP – lepsza widoczność gry.
- **Detekcja multi-frame (5 klatek)**: MediaPipe + konsensus stref (6 bocznych), ignorowanie centrum, aby unikać fałszywych detekcji.
- **Auto-wybór szablonu**: mapowanie stref na 4 układy (bar, PIP, fallback bez facecama, duża reakcja), z możliwością manualnego override.
- **Lżejszy pipeline FFmpeg**: prostsze filtry, brak bocznych pasów – szybsze renderowanie.

## Korzyści
- **5–10x szybszy render**: est. 50 shortów w 40–60 minut (vs 180–240 min). 
- **Automatyzacja ~90%**: znacznie mniej ręcznych poprawek kadrów/układów.
- **Wyższa jakość**: pełnoekranowy gameplay w kadrze mobilnym, facecam nadal widoczny, ale nie dominuje.
- **Większa różnorodność**: kilka dopasowanych layoutów zamiast jednego powtarzalnego.
- **Oszczędność zasobów**: szacunkowo nawet 8x mniejsze zużycie RAM i niższe obciążenie CPU podczas renderu.

## ROI
- Oszczędność 2–3 h pracy per batch 50 shortów; przy ~30 batchach/mies. to 60–90 h mniej (ok. 3000 zł/mies. przy stawce 50 zł/h).
- Lepsze CTR/watch time dzięki czytelniejszemu gameplayowi i bardziej atrakcyjnym ujęciom.
- Nakład wdrożenia: ok. 1 dzień pracy deweloperskiej + testy; zwrot natychmiastowy po uruchomieniu.

## Timeline wdrożenia
- Dev + QA: 1 dzień (implementacja, testy jednostkowe/integracyjne).
- Rollout etapowy: 
  - Tydzień 1: canary 10% shortów.
  - Tydzień 2: 50% (A/B ze starym systemem).
  - Tydzień 3: 100% produkcja, monitoring.

## Ryzyka i mitigacja
- **Błędy detekcji AI**: możliwość natychmiastowego manual_template lub globalnego template w config; rollout etapowy pozwala wykryć problemy.
- **Ewentualny rollback**: dostępny branch `backup-before-vertical-templates`; zmiany izolowane w `stage_10_shorts.py` i `config.yml`.

## Decyzja
- Rekomendacja: **APPROVE** – niskie ryzyko, wysoka poprawa jakości i produktywności.
