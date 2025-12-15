"""
Smart Content Splitter
Inteligentnie dzieli długie materiały na części i scheduluje premiery YouTube
"""

from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import math


@dataclass
class SplitPlan:
    """
    Single source of truth dla strategii podziału.
    Wyliczany RAZ i używany przez cały pipeline.
    """
    # Input
    source_duration: float  # Długość źródła w sekundach

    # Strategy (computed once)
    num_parts: int
    target_duration_per_part: int  # sekundy
    total_target_duration: int  # sekundy
    min_score_threshold: float
    compression_ratio: float

    # Reasoning (why this strategy)
    reason: str = ""

    # Computed parts (filled after selection)
    parts_metadata: List[Dict[str, Any]] = field(default_factory=list)

    def __str__(self) -> str:
        """Human-readable opis planu"""
        hours = self.source_duration / 3600
        mins_per_part = self.target_duration_per_part / 60

        if self.num_parts == 1:
            return f"Pojedynczy film ({hours:.1f}h → ~{mins_per_part:.0f}min)"
        else:
            return f"Podział na {self.num_parts} części ({hours:.1f}h → {self.num_parts}x ~{mins_per_part:.0f}min)"

    def has_parts(self) -> bool:
        """Czy plan ma wygenerowane części (po selection)"""
        return len(self.parts_metadata) > 0


class SmartSplitter:
    """
    Inteligentny podział treści na części z auto-schedulingiem premier
    """
    
    # Progi czasowe dla podziału (w sekundach)
    THRESHOLDS = {
        'short': 3600,      # < 1h → 1 część (15-20 min)
        'medium': 7200,     # 1-2h → 2 części (12-15 min każda)
        'long': 14400,      # 2-4h → 3 części (15-20 min każda)
        'very_long': 21600  # 4-6h → 4 części (15-20 min każda)
        # > 6h → 5+ części
    }
    
    # Optymalne długości części (w sekundach)
    OPTIMAL_PART_DURATION = {
        'min': 720,   # 12 min (minimum dla dobrej retencji)
        'ideal': 900, # 15 min (sweet spot dla YouTube)
        'max': 1200   # 20 min (maximum przed spadkiem retencji)
    }
    
    def __init__(self, premiere_hour: int = 18, premiere_minute: int = 0):
        """
        Args:
            premiere_hour: Godzina premier (domyślnie 18:00)
            premiere_minute: Minuta premier (domyślnie :00)
        """
        self.premiere_hour = premiere_hour
        self.premiere_minute = premiere_minute
    
    def calculate_split_strategy(
        self,
        source_duration: float,
        override_parts: Optional[int] = None,
        override_target_minutes: Optional[int] = None
    ) -> SplitPlan:
        """
        Oblicz optymalną strategię podziału (wyliczana RAZ!)

        Args:
            source_duration: Długość źródła w sekundach
            override_parts: Wymuszenie liczby części (opcjonalne)
            override_target_minutes: Wymuszenie długości części w minutach (opcjonalne)

        Returns:
            SplitPlan - single source of truth dla strategii
        """
        # Określ liczbę części
        if override_parts:
            num_parts = override_parts
            reason = f"Manual override: {override_parts} części wymuszonych przez użytkownika"
        else:
            num_parts = self._calculate_num_parts(source_duration)
            hours = source_duration / 3600
            reason = self._explain_num_parts_decision(source_duration, num_parts)

        # Oblicz docelową długość każdej części
        if override_target_minutes:
            target_duration_per_part = override_target_minutes * 60
            reason += f" | Target duration: {override_target_minutes}min (manual override)"
        else:
            target_duration_per_part = self._calculate_target_duration(source_duration, num_parts)

        total_target_duration = target_duration_per_part * num_parts

        # Oblicz score threshold (wyższy dla dłuższych materiałów)
        min_score_threshold = self._calculate_score_threshold(source_duration, num_parts)

        compression_ratio = total_target_duration / source_duration

        return SplitPlan(
            source_duration=source_duration,
            num_parts=num_parts,
            target_duration_per_part=target_duration_per_part,
            total_target_duration=total_target_duration,
            min_score_threshold=min_score_threshold,
            compression_ratio=compression_ratio,
            reason=reason
        )
    
    def _calculate_num_parts(self, duration: float) -> int:
        """Oblicz optymalną liczbę części"""
        if duration < self.THRESHOLDS['short']:
            return 1
        elif duration < self.THRESHOLDS['medium']:
            return 2
        elif duration < self.THRESHOLDS['long']:
            return 3
        elif duration < self.THRESHOLDS['very_long']:
            return 4
        else:
            # Dla bardzo długich: ceil(duration / 4h) z max 6 części
            return min(6, math.ceil(duration / 14400))

    def _explain_num_parts_decision(self, duration: float, num_parts: int) -> str:
        """Wyjaśnij dlaczego wybrano daną liczbę części"""
        hours = duration / 3600

        if num_parts == 1:
            return f"Material {hours:.1f}h < 1h → pojedynczy film (optymalna retencja)"
        elif num_parts == 2:
            return f"Material {hours:.1f}h = 1-2h → 2 części (dobra dla daily schedule)"
        elif num_parts == 3:
            return f"Material {hours:.1f}h = 2-4h → 3 części (optimal split dla retencji)"
        elif num_parts == 4:
            return f"Material {hours:.1f}h = 4-6h → 4 części (długi live, premium content)"
        else:
            return f"Material {hours:.1f}h > 6h → {num_parts} części (bardzo długi live, serialized content)"
    
    def _calculate_target_duration(self, source_duration: float, num_parts: int) -> int:
        """Oblicz docelową długość jednej części"""
        # Cel: 10% źródła, ale podzielone na części
        total_target = source_duration * 0.10
        duration_per_part = total_target / num_parts
        
        # Clamp do optymalnego zakresu
        if duration_per_part < self.OPTIMAL_PART_DURATION['min']:
            return self.OPTIMAL_PART_DURATION['min']
        elif duration_per_part > self.OPTIMAL_PART_DURATION['max']:
            return self.OPTIMAL_PART_DURATION['max']
        else:
            return int(duration_per_part)
    
    def _calculate_score_threshold(self, source_duration: float, num_parts: int) -> float:
        """
        Oblicz minimalny score threshold
        Im więcej materiału, tym wyższy threshold (tylko TOP momenty)
        
        Note: Scoring zwraca wartości 0.0-1.0, nie 0-10!
        """
        base_threshold = 0.45  # 45% score (było 0.65 - obniżone v1.3)
        
        # Zwiększ threshold dla długich materiałów
        if source_duration > self.THRESHOLDS['long']:
            base_threshold = 0.50  # 50% (było 0.70 - obniżone v1.3)
        if source_duration > self.THRESHOLDS['very_long']:
            base_threshold = 0.55  # 55% (było 0.75 - obniżone v1.3 - GŁÓWNA POPRAWA!)
        
        # Dodatkowy boost dla wielu części (chcemy tylko najlepsze)
        #         if num_parts >= 4:
        #             base_threshold += 0.03  # +3%
        
        return round(base_threshold, 2)
    
    def _describe_strategy(self, duration: float, num_parts: int) -> str:
        """Opisz strategię podziału"""
        hours = duration / 3600
        
        if num_parts == 1:
            return f"Pojedynczy film ({hours:.1f}h → ~15-20 min)"
        else:
            return f"Podział na {num_parts} części ({hours:.1f}h → {num_parts}x ~12-18 min)"
    
    def split_clips_into_parts(
        self, 
        clips: List[Dict], 
        num_parts: int,
        target_duration_per_part: int
    ) -> List[List[Dict]]:
        """
        Podziel klipy na części z równomiernym rozkładem czasu i jakości
        
        Args:
            clips: Lista wszystkich klipów (posortowane według score)
            num_parts: Liczba części do stworzenia
            target_duration_per_part: Docelowa długość każdej części
            
        Returns:
            Lista list klipów (każda lista = jedna część)
        """
        if num_parts == 1:
            return [clips]
        
        # Strategia: Round-robin z balansowaniem czasu i jakości
        parts = [[] for _ in range(num_parts)]
        part_durations = [0.0] * num_parts
        part_quality_scores = [0.0] * num_parts
        
        # Sortuj klipy według timestamp (chronologicznie)
        sorted_clips = sorted(clips, key=lambda c: c['t0'])
        
        # Przydziel klipy do części, balansując czas i jakość
        for clip in sorted_clips:
            # Znajdź część z najmniejszą kombinacją czasu i jakości
            # Preferuj części z mniej czasu, ale też dbaj o równomierne rozłożenie jakości
            scores = []
            for i in range(num_parts):
                # Jeśli część już pełna, daj jej bardzo wysoki score
                if part_durations[i] >= target_duration_per_part * 1.15:  # 15% tolerancja
                    scores.append(float('inf'))
                else:
                    # Score składa się z: 60% wypełnienie czasowe + 40% równowaga jakości
                    time_score = part_durations[i] / target_duration_per_part
                    quality_score = part_quality_scores[i] / (len(parts[i]) + 1) if len(parts[i]) > 0 else 0
                    combined_score = 0.6 * time_score + 0.4 * (1 - quality_score)
                    scores.append(combined_score)
            
            # Wybierz część z najniższym score
            best_part_idx = scores.index(min(scores))
            
            # Dodaj klip do tej części
            parts[best_part_idx].append(clip)
            part_durations[best_part_idx] += clip['duration']
            part_quality_scores[best_part_idx] += clip.get('final_score', 0.7)
        
        # Usuń puste części (nie powinno się zdarzyć, ale dla pewności)
        parts = [part for part in parts if len(part) > 0]
        
        # Posortuj klipy w każdej części według timestamp
        for part in parts:
            part.sort(key=lambda c: c['t0'])
        
        return parts
    
    def generate_part_metadata(
        self,
        parts: List[List[Dict]],
        base_title: str,
        base_date: datetime = None
    ) -> List[Dict[str, Any]]:
        """
        Generuj metadata dla każdej części (tytuł, numer, premiere schedule)
        
        Args:
            parts: Lista części (każda część = lista klipów)
            base_title: Bazowy tytuł (np. "Gorące Momenty Sejmu")
            base_date: Data bazowa dla premier (domyślnie: jutro)
            
        Returns:
            Lista dict z metadata dla każdej części
        """
        if base_date is None:
            # Domyślnie: pierwsza premiera jutro
            base_date = datetime.now() + timedelta(days=1)
        
        num_parts = len(parts)
        metadata_list = []
        
        for i, part_clips in enumerate(parts, start=1):
            # Oblicz premiere datetime
            premiere_datetime = self._calculate_premiere_datetime(base_date, i - 1)
            
            # Generuj tytuł z numerem
            if num_parts > 1:
                part_title = f"{base_title} - Część {i}/{num_parts}"
            else:
                part_title = base_title
            
            # Oblicz statystyki części
            total_duration = sum(clip['duration'] for clip in part_clips)
            avg_score = sum(clip.get('final_score', 0.7) for clip in part_clips) / len(part_clips)
            
            # Wyciągnij top keywords z tej części
            all_keywords = []
            for clip in part_clips[:5]:  # Top 5 klipów
                features = clip.get('features', {})
                matched_keywords = features.get('matched_keywords', [])
                for kw_dict in matched_keywords:
                    kw = kw_dict.get('token', '') if isinstance(kw_dict, dict) else kw_dict
                    if kw and kw not in all_keywords:
                        all_keywords.append(kw)
            
            metadata = {
                'part_number': i,
                'total_parts': num_parts,
                'title': part_title,
                'premiere_datetime': premiere_datetime.isoformat(),
                'premiere_timestamp': int(premiere_datetime.timestamp()),
                'clips': part_clips,
                'duration': total_duration,
                'num_clips': len(part_clips),
                'avg_score': avg_score,
                'keywords': all_keywords[:10],  # Top 10 keywords
                'filename_suffix': f"_part{i}of{num_parts}" if num_parts > 1 else ""
            }
            
            metadata_list.append(metadata)
        
        return metadata_list
    
    def _calculate_premiere_datetime(self, base_date: datetime, day_offset: int) -> datetime:
        """
        Oblicz datetime premiery dla danej części
        
        Args:
            base_date: Data bazowa (np. jutro)
            day_offset: Przesunięcie w dniach (0 = base_date, 1 = day after, etc.)
            
        Returns:
            datetime premiery
        """
        premiere_date = base_date + timedelta(days=day_offset)
        
        # Ustaw godzinę premiery
        premiere_datetime = premiere_date.replace(
            hour=self.premiere_hour,
            minute=self.premiere_minute,
            second=0,
            microsecond=0
        )
        
        return premiere_datetime
    
    def generate_enhanced_title(
        self,
        part_metadata: Dict,
        clips: List[Dict],
        use_politicians: bool = True
    ) -> str:
        """
        Generuj clickbaitowy tytuł z nazwiskami polityków lub keywords
        
        Args:
            part_metadata: Metadata części
            clips: Lista klipów w tej części
            use_politicians: Czy używać nazwisk polityków
            
        Returns:
            Wygenerowany tytuł
        """
        part_num = part_metadata['part_number']
        total_parts = part_metadata['total_parts']
        date_str = datetime.now().strftime('%d.%m.%Y')
        
        # Zbierz keywords i nazwiska
        politician_names = []
        regular_keywords = []
        
        # Lista nazwisk polityków do wykrycia
        politicians = [
            'tusk', 'kaczyński', 'kaczyńskiego', 'morawiecki', 'morawieckiego',
            'hołownia', 'hołowni', 'bosak', 'bosaka', 'czarnek', 'czarnka',
            'kosiniak', 'kosiniak-kamysz', 'budka', 'budki', 'sienkiewicz',
            'duda', 'dudy', 'ziobro', 'ziobry', 'fogiel', 'fogiela'
        ]
        
        for clip in clips[:5]:  # Top 5 klipów
            features = clip.get('features', {})
            matched_keywords = features.get('matched_keywords', [])
            
            for kw_item in matched_keywords[:3]:  # Top 3 per clip
                kw = kw_item.get('token', '') if isinstance(kw_item, dict) else kw_item
                kw_lower = kw.lower()
                
                # Sprawdź czy to nazwisko
                is_politician = any(pol in kw_lower for pol in politicians)
                
                if is_politician and kw not in politician_names:
                    politician_names.append(kw.capitalize())
                elif kw not in regular_keywords:
                    regular_keywords.append(kw)
        
        # Buduj tytuł bazując na dostępnych danych
        if use_politicians and len(politician_names) >= 2:
            # Starcie nazwisk
            title = f"🔥 {politician_names[0]} VS {politician_names[1]} - Posiedzenie Sejmu"
        elif use_politicians and len(politician_names) == 1:
            # Jedno nazwisko
            title = f"💥 {politician_names[0]} w Sejmie - Najgorętsze Momenty"
        elif len(regular_keywords) >= 2:
            # Keywords bez nazwisk
            title = f"⚡ Sejm: {regular_keywords[0].title()} vs {regular_keywords[1].title()}"
        else:
            # Fallback - ogólny
            title = f"🎯 Posiedzenie Sejmu - Gorące Momenty"
        
        # Dodaj numer części jeśli > 1
        if total_parts > 1:
            title += f" | CZ. {part_num}/{total_parts}"
        
        # Dodaj datę
        title += f" | {date_str}"
        
        # YouTube limit: 100 znaków
        if len(title) > 100:
            title = title[:97] + "..."
        
        return title
    
    @staticmethod
    def format_duration_readable(seconds: float) -> str:
        """Format duration do czytelnej formy"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"
    
    def print_split_summary(self, plan: SplitPlan):
        """
        Wydrukuj podsumowanie planu podziału (single source of truth!)

        Args:
            plan: SplitPlan z pełną strategią i (opcjonalnie) wygenerowanymi częściami
        """
        print("\n" + "="*80)
        print("📊 SMART SPLITTER - PLAN PODZIAŁU")
        print("="*80)

        # Podstawowe info
        print(f"\n🎯 Strategia: {plan}")
        print(f"📦 Liczba części: {plan.num_parts}")
        print(f"⏱️  Czas na część: ~{self.format_duration_readable(plan.target_duration_per_part)}")
        print(f"📊 Score threshold: {plan.min_score_threshold:.2f}")
        print(f"🎬 Kompresja: {plan.compression_ratio:.1%}")

        # Wyjaśnienie "dlaczego"
        if plan.reason:
            print(f"\n💡 Powód:\n   {plan.reason}")

        # Jeśli target duration został zmieniony - wyjaśnij
        if hasattr(plan, '_config_change_reason'):
            print(f"\n⚙️  Config adjustment: {plan._config_change_reason}")

        # Jeśli są już wygenerowane części - pokaż szczegóły
        if plan.has_parts():
            print(f"\n📅 HARMONOGRAM PREMIER ({len(plan.parts_metadata)} części):")
            print("-" * 80)

            for part_meta in plan.parts_metadata:
                premiere_dt = datetime.fromisoformat(part_meta['premiere_datetime'])
                print(f"\n  Część {part_meta['part_number']}/{part_meta['total_parts']}:")
                print(f"  📺 Tytuł: {part_meta['title']}")
                print(f"  🗓️  Premiera: {premiere_dt.strftime('%d.%m.%Y o %H:%M')}")
                print(f"  ⏱️  Długość: {self.format_duration_readable(part_meta['duration'])}")
                print(f"  🎬 Klipy: {part_meta['num_clips']}")
                print(f"  ⭐ Średni score: {part_meta['avg_score']:.2f}")
                if part_meta['keywords']:
                    print(f"  🔑 Keywords: {', '.join(part_meta['keywords'][:5])}")
        else:
            print(f"\n⏳ Części będą wygenerowane po Selection Stage...")

        print("\n" + "="*80)


if __name__ == "__main__":
    # Test
    splitter = SmartSplitter(premiere_hour=18, premiere_minute=0)

    # Test case: 5h live z Sejmu
    test_duration = 5 * 3600  # 5 godzin

    # Wylicz plan (nowe API - zwraca SplitPlan)
    split_plan = splitter.calculate_split_strategy(test_duration)

    print(f"\nStrategia dla {test_duration/3600:.1f}h materiału:")
    print(f"  - Części: {split_plan.num_parts}")
    print(f"  - Czas na część: {split_plan.target_duration_per_part}s (~{split_plan.target_duration_per_part/60:.1f} min)")
    print(f"  - Threshold: {split_plan.min_score_threshold:.2f}")
    print(f"  - Powód: {split_plan.reason}")

    # Mock clips dla testu
    mock_clips = [
        {'id': f'clip_{i}', 't0': i*100, 't1': i*100+150, 'duration': 150, 'final_score': 0.8 - i*0.05}
        for i in range(30)
    ]

    # Podziel na części
    parts = splitter.split_clips_into_parts(
        mock_clips,
        split_plan.num_parts,
        split_plan.target_duration_per_part
    )

    print(f"\nPodzielono {len(mock_clips)} klipów na {len(parts)} części:")
    for i, part in enumerate(parts, 1):
        total_dur = sum(c['duration'] for c in part)
        print(f"  Część {i}: {len(part)} klipów, {total_dur/60:.1f} min")

    # Generuj metadata dla każdej części
    parts_metadata = splitter.generate_part_metadata(
        parts,
        "Gorące Momenty Sejmu",
        base_date=datetime.now() + timedelta(days=1)
    )

    # Wypełnij plan metadata (single source of truth!)
    split_plan.parts_metadata = parts_metadata

    # Wyświetl FINALNY plan (z pełnymi danymi)
    splitter.print_split_summary(split_plan)