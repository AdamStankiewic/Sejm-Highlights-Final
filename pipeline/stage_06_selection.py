"""
Stage 6: Intelligent Clip Selection v1.1
- Greedy selection z Non-Maximum Suppression
- Smart merge sąsiednich segmentów (NAPRAWIONY gap bug)
- Temporal coverage optimization (DYNAMICZNE dla długich materiałów)
- Duration adjustment
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
import numpy as np
from collections import defaultdict

from .config import Config

logger = logging.getLogger(__name__)


class SelectionStage:
    """Stage 6: Clip Selection v1.1"""

    def __init__(self, config: Config):
        self.config = config
        self.ai_generator = None

        # Initialize AI metadata generator if enabled
        if getattr(config, 'ai_metadata_enabled', False):
            try:
                from .ai_metadata.generator import MetadataGenerator
                from .streamers.manager import StreamerManager
                import yaml

                # Load platform config
                platforms_file = Path(__file__).parent / "config" / "platforms.yaml"
                if platforms_file.exists():
                    with open(platforms_file, 'r', encoding='utf-8') as f:
                        platform_config = yaml.safe_load(f)
                else:
                    platform_config = {}

                # Initialize streamer manager and AI generator
                streamer_manager = StreamerManager()

                # Initialize OpenAI client if needed
                if hasattr(config, 'openai_client'):
                    openai_client = config.openai_client
                else:
                    import os
                    from openai import OpenAI
                    api_key = os.getenv('OPENAI_API_KEY')
                    if api_key:
                        openai_client = OpenAI(api_key=api_key)
                        self.ai_generator = MetadataGenerator(
                            openai_client=openai_client,
                            streamer_manager=streamer_manager,
                            platform_config=platform_config
                        )
                        logger.info("✅ AI metadata generator enabled for Shorts")
                    else:
                        logger.warning("OPENAI_API_KEY not set, AI metadata disabled")

            except Exception as e:
                logger.warning(f"Failed to initialize AI metadata generator: {e}")
                self.ai_generator = None
    
    def process(
        self,
        segments: List[Dict],
        total_duration: float,
        output_dir: Path,
        min_score: float = 0.0
    ) -> Dict[str, Any]:
        """
        Główna metoda przetwarzania
        
        Args:
            min_score: Minimalny wymagany score (domyślnie 0.0)
        
        Returns:
            Dict zawierający:
                - clips: Lista wybranych klipów
                - total_duration: Suma czasu klipów
        """
        print(f"🎯 Selekcja klipów z {len(segments)} segmentów...")

        # Pre-merge bardzo krótkie bursty, aby nie odpaść na filtrze długości
        merged_segments = self._merge_short_bursts(list(segments))
        segments = merged_segments

        # STEP 0: Filter by minimum score if specified (with fallback to top 20%)
        base_threshold = max(
            min_score,
            getattr(self.config.selection, 'min_score_threshold', 0.35) or 0.35,
        )
        segments = self._filter_by_score_with_fallback(segments, base_threshold)
        print(f"   Po filtrze score (>= {base_threshold:.2f} lub top20): {len(segments)} segmentów")

        # STEP 1: Filter by duration bounds (>=8s, <= configured max)
        min_dur = 8
        if getattr(self.config, "mode", "stream") == "stream":
            min_dur = 8
        else:
            min_dur = max(min_dur, int(self.config.selection.min_clip_duration))
        min_dur = max(min_dur, 8)
        max_dur = int(self.config.selection.max_clip_duration)
        candidates = [
            seg for seg in segments if min_dur <= seg['duration'] <= max_dur
        ]
        print(f"   Po filtrze duration [{min_dur}s-{max_dur}s]: {len(candidates)} kandydatów")

        # Dynamic lowering if coverage is too low
        if len(candidates) < 30 or sum(c['duration'] for c in candidates) < self.config.selection.target_total_duration * 0.5:
            relaxed_threshold = max(0.25, base_threshold - 0.10)
            relaxed_segments = self._filter_by_score_with_fallback(merged_segments, relaxed_threshold)
            relaxed_candidates = [
                seg for seg in relaxed_segments if min_dur <= seg['duration'] <= max_dur
            ]
            if len(relaxed_candidates) > len(candidates):
                print(
                    f"   ⚠️ Za mało materiału ({len(candidates)} klipów) → obniżam próg do {relaxed_threshold:.2f}"
                )
                segments = relaxed_segments
                candidates = relaxed_candidates
                base_threshold = relaxed_threshold

        # STEP 2: Greedy selection + NMS
        selected = self._greedy_selection_with_nms(candidates)
        print(f"   Po greedy selection: {len(selected)} klipów")
        
        # STEP 3: Smart merge sąsiednich segmentów (NAPRAWIONY!)
        merged = self._smart_merge(selected, segments)
        print(f"   Po smart merge: {len(merged)} klipów")
        
        # STEP 4: Temporal coverage optimization (DYNAMICZNE dla długich materiałów!)
        balanced = self._optimize_temporal_coverage(merged, total_duration)
        print(f"   Po balance coverage: {len(balanced)} klipów")

        # STEP 5: Duration adjustment (trim if needed)
        final_clips = self._adjust_duration(balanced)
        print(f"   Final: {len(final_clips)} klipów")

        final_clips = self._top_up_if_needed(final_clips, segments, merged_segments, min_dur)

        # Calculate stats
        total_clip_duration = sum(clip['duration'] for clip in final_clips)
        
        # Sort chronologically
        final_clips.sort(key=lambda x: x['t0'])
        
        # Add sequential IDs
        for i, clip in enumerate(final_clips):
            clip['clip_id'] = f"clip_{i+1:03d}"
            clip['title'] = self._generate_title(clip)
        
        # Debug plot if not enough clips
        if len(final_clips) < 10:
            self._save_debug_plot(final_clips or segments, segments, output_dir)

        # Save
        output_file = output_dir / "selected_clips.json"
        self._save_clips(final_clips, output_file)
        
        print(f"   ✓ Całkowity czas: {total_clip_duration/60:.1f} min")
        print(f"   ✓ Target był: {self.config.selection.target_total_duration/60:.1f} min")
        
        # STEP 6: Select Shorts candidates (if enabled)
        shorts_clips = []
        if self.config.shorts.enabled:
            print(f"\n📱 Selekcja klipów dla YouTube Shorts...")
            shorts_clips = self._select_shorts_candidates(segments, min_score)
            
            # Save shorts candidates
            shorts_output = output_dir / "shorts_candidates.json"
            self._save_clips(shorts_clips, shorts_output, is_shorts=True)
            print(f"   ✓ Wybrano {len(shorts_clips)} kandydatów na Shorts")
        
        print("✅ Stage 6 zakończony")
        
        return {
            'clips': final_clips,
            'shorts_clips': shorts_clips,
            'total_duration': total_clip_duration,
            'num_clips': len(final_clips),
            'num_shorts': len(shorts_clips),
            'output_file': str(output_file)
        }
    
    def _filter_by_duration(self, segments: List[Dict]) -> List[Dict]:
        """Filter segmenty po minimalnej długości"""
        min_dur = self.config.selection.min_clip_duration
        return [seg for seg in segments if seg['duration'] >= min_dur]

    def _merge_short_bursts(self, segments: List[Dict]) -> List[Dict]:
        """
        Połącz bardzo krótkie bursty (<8s) z sąsiadami, żeby nie odpaść na filtrze długości.
        Prosty greedy w czasie, łączy gdy gap <= smart_merge_gap i średni score pozostaje wiarygodny.
        """
        if not segments:
            return []

        sorted_segments = sorted(segments, key=lambda s: s['t0'])
        merged: List[Dict] = []
        idx = 0
        min_target = 8
        gap_limit = getattr(self.config.selection, 'smart_merge_gap', 10.0)

        while idx < len(sorted_segments):
            current = sorted_segments[idx]
            if current.get('duration', 0) >= min_target:
                merged.append(current)
                idx += 1
                continue

            # próbuj dołączyć kolejne segmenty aż osiągniesz min_target lub brak sąsiada
            start = current['t0']
            end = current['t1']
            collected = [current]
            j = idx + 1
            while j < len(sorted_segments):
                nxt = sorted_segments[j]
                gap = nxt['t0'] - end
                if gap > gap_limit:
                    break
                end = nxt['t1']
                collected.append(nxt)
                if end - start >= min_target:
                    break
                j += 1

            new_duration = end - start
            if new_duration >= min_target:
                merged_clip = {
                    'id': '+'.join(seg['id'] for seg in collected),
                    't0': start,
                    't1': end,
                    'duration': new_duration,
                    'final_score': float(np.mean([seg.get('final_score', 0) for seg in collected])),
                    'merged_from': [seg['id'] for seg in collected],
                    'transcript': ' '.join(seg.get('transcript', '') for seg in collected),
                    'features': collected[0].get('features', {}),
                    'subscores': collected[0].get('subscores', {}),
                }
                merged.append(merged_clip)
                idx = j + 1
            else:
                merged.append(current)
                idx += 1

        return merged

    def _filter_by_score_with_fallback(self, segments: List[Dict], min_score: float) -> List[Dict]:
        """Filter by score, fallback to top 20% percentile when empty."""

        if min_score <= 0:
            return segments

        filtered = [seg for seg in segments if seg.get('final_score', 0) >= min_score]
        if filtered:
            return filtered

        scores = [seg.get('final_score', 0) for seg in segments]
        if not scores:
            return []

        percentile = getattr(self.config.scoring, 'dynamic_threshold_percentile', 80)
        dynamic_threshold = float(np.percentile(scores, percentile))
        fallback = [seg for seg in segments if seg.get('final_score', 0) >= dynamic_threshold]
        if not fallback and segments:
            fallback = [max(segments, key=lambda s: s.get('final_score', 0))]

        print(
            f"   ⚠️ Brak klipów dla progu {min_score:.2f} → fallback top {percentile}% (>= {dynamic_threshold:.2f})"
        )
        return fallback
    
    def _greedy_selection_with_nms(self, candidates: List[Dict]) -> List[Dict]:
        """
        Greedy selection z Non-Maximum Suppression
        Wybiera najwyżej scorowane segmenty, unikając temporal overlap
        """
        # Sort by score (descending)
        sorted_candidates = sorted(
            candidates,
            key=lambda x: x['final_score'],
            reverse=True
        )
        
        selected = []
        target_duration = self.config.selection.target_total_duration
        max_clips = self.config.selection.max_clips
        min_gap = self.config.selection.min_time_gap
        
        for candidate in sorted_candidates:
            # Check if we're done
            if len(selected) >= max_clips:
                break
            
            current_total = sum(s['duration'] for s in selected)
            if current_total >= target_duration:
                break
            
            # Check temporal overlap/proximity z już wybranymi
            if self._has_overlap(candidate, selected, min_gap):
                continue
            
            # Check if adding this would exceed max duration
            if current_total + candidate['duration'] > target_duration * 1.2:  # 20% tolerance
                continue
            
            selected.append(candidate)
        
        return selected
    
    def _has_overlap(
        self,
        candidate: Dict,
        selected: List[Dict],
        min_gap: float
    ) -> bool:
        """Sprawdź czy kandydat ma overlap z wybranymi"""
        for sel in selected:
            # Check overlap
            if not (candidate['t1'] < sel['t0'] or candidate['t0'] > sel['t1']):
                return True
            
            # Check minimum gap
            if sel['t0'] - candidate['t1'] < min_gap and sel['t0'] > candidate['t1']:
                return True
            if candidate['t0'] - sel['t1'] < min_gap and candidate['t0'] > sel['t1']:
                return True
        
        return False
    
    def _smart_merge(
        self,
        selected: List[Dict],
        all_segments: List[Dict]
    ) -> List[Dict]:
        """
        Smart merge: jeśli dwa wybrane segmenty są blisko + oba wysokie score
        → merge je w jeden klip
        
        NAPRAWIONY v1.0: Uwzględnia gap w obliczeniach długości!
        """
        # Sort by time
        selected_sorted = sorted(selected, key=lambda x: x['t0'])
        
        merged = []
        i = 0
        
        while i < len(selected_sorted):
            current = selected_sorted[i]
            
            # Look for next segment in time from selected
            if i + 1 < len(selected_sorted):
                next_selected = selected_sorted[i + 1]
                gap = next_selected['t0'] - current['t1']
                
                # NAPRAWIONE: Oblicz faktyczną długość po merge (z gap!)
                merged_duration = current['duration'] + gap + next_selected['duration']
                
                # Conditions for merge:
                # 1. Gap < threshold
                # 2. FAKTYCZNA combined duration (z gap!) < max
                # 3. Next has good score
                should_merge = (
                    gap < self.config.selection.smart_merge_gap and
                    merged_duration <= self.config.selection.max_clip_duration and  # NAPRAWIONE!
                    next_selected['final_score'] >= self.config.selection.smart_merge_min_score
                )
                
                if should_merge:
                    # MERGE
                    merged_clip = {
                        'id': f"{current['id']}+{next_selected['id']}",
                        't0': current['t0'],
                        't1': next_selected['t1'],
                        'duration': merged_duration,  # NAPRAWIONE: używa faktycznej długości
                        'final_score': (current['final_score'] + next_selected['final_score']) / 2,
                        'merged_from': [current['id'], next_selected['id']],
                        'transcript': current.get('transcript', '') + ' ' + next_selected.get('transcript', ''),
                        'features': current.get('features', {}),
                        'subscores': current.get('subscores', {})
                    }
                    
                    # BEZPIECZEŃSTWO: Sprawdź czy merge nie utworzył za długiego klipu
                    if merged_clip['duration'] > self.config.selection.max_clip_duration * 1.1:
                        print(f"   ⚠️ Merge {current['id']}+{next_selected['id']} = {merged_clip['duration']:.1f}s > max, pomijam")
                        merged.append(current)
                        i += 1
                        continue
                    
                    merged.append(merged_clip)
                    i += 2  # Skip next
                    continue
            
            # No merge, add as-is
            merged.append(current)
            i += 1
        
        # Fallback merge if coverage is too low
        total_duration = sum(c['duration'] for c in merged)
        target = self.config.selection.target_total_duration
        if merged and total_duration < target * 0.7:
            merged = self._force_merge_for_coverage(merged)
        return merged

    def _force_merge_for_coverage(self, clips: List[Dict]) -> List[Dict]:
        """Dodatkowe łączenie sąsiadów gdy łączny czas <70% targetu."""
        if len(clips) < 2:
            return clips

        merged: List[Dict] = []
        idx = 0
        while idx < len(clips):
            current = clips[idx]
            if idx + 1 < len(clips):
                nxt = clips[idx + 1]
                gap = nxt['t0'] - current['t1']
                combined_duration = current['duration'] + gap + nxt['duration']
                if gap <= self.config.selection.smart_merge_gap and combined_duration <= self.config.selection.max_clip_duration * 1.1:
                    merged_clip = {
                        'id': f"{current['id']}+{nxt['id']}",
                        't0': current['t0'],
                        't1': nxt['t1'],
                        'duration': combined_duration,
                        'final_score': (current['final_score'] + nxt['final_score']) / 2,
                        'merged_from': [current.get('id'), nxt.get('id')],
                        'transcript': current.get('transcript', '') + ' ' + nxt.get('transcript', ''),
                        'features': current.get('features', {}),
                        'subscores': current.get('subscores', {})
                    }
                    merged.append(merged_clip)
                    idx += 2
                    continue
            merged.append(current)
            idx += 1
        return merged
    
    def _optimize_temporal_coverage(
        self,
        clips: List[Dict],
        total_duration: float
    ) -> List[Dict]:
        """
        Optimizuj coverage transmisji
        Ensure clips są równomiernie rozłożone w czasie
        
        NOWE v1.1: Dynamiczne max_clips_per_bin dla długich materiałów!
        """
        if not clips:
            return []
        
        num_bins = self.config.selection.position_bins
        max_per_bin = self.config.selection.max_clips_per_bin
        
        # NOWE v1.1: Dynamiczne skalowanie dla długich materiałów
        hours = total_duration / 3600
        if hours > 12:
            # Bardzo długie materiały (>12h): zwiększ limit per bin
            max_per_bin = max(max_per_bin, 8)  # Min 8 klipów per bin
            print(f"   📈 Długi materiał ({hours:.1f}h) → max_per_bin: {max_per_bin}")
        elif hours > 6:
            # Długie materiały (6-12h): trochę zwiększ
            max_per_bin = max(max_per_bin, 6)
        
        # Create time bins
        bin_size = total_duration / num_bins
        bins = defaultdict(list)
        
        # Assign clips to bins
        for clip in clips:
            bin_idx = int(clip['t0'] / bin_size)
            bin_idx = min(bin_idx, num_bins - 1)  # Clamp
            bins[bin_idx].append(clip)
        
        # Select top N from each bin
        balanced = []
        for bin_idx in range(num_bins):
            bin_clips = bins[bin_idx]
            
            if not bin_clips:
                continue
            
            # Sort by score
            bin_clips.sort(key=lambda x: x.get('final_score', 0), reverse=True)
            
            # Take top N
            balanced.extend(bin_clips[:max_per_bin])
        
        # SAFETY v1.1: Zwiększone minimum dla długich materiałów
        min_clips_required = self.config.selection.min_clips
        if hours > 12:
            min_clips_required = max(min_clips_required, 15)  # Min 15 dla bardzo długich
        elif hours > 6:
            min_clips_required = max(min_clips_required, 10)  # Min 10 dla długich
        
        if len(balanced) < min_clips_required:
            print(f"   ⚠️ Tylko {len(balanced)} klipów po balansowaniu (min: {min_clips_required}), dodaję więcej...")
            # Sort all clips by score and take top ones
            all_sorted = sorted(clips, key=lambda x: x.get('final_score', 0), reverse=True)
            balanced = all_sorted[:min_clips_required]
        
        return balanced
    
    def _adjust_duration(self, clips: List[Dict]) -> List[Dict]:
        """
        Adjust total duration jeśli przekracza target
        Trim longest clips
        """
        if not clips:
            return []

        target = self.config.selection.target_total_duration
        tolerance = self.config.selection.duration_tolerance

        total = sum(clip.get('duration', 0) for clip in clips)

        if total <= target * tolerance:
            return clips  # OK, within tolerance

        overshoot = total - target
        slight_overshoot_limit = target * 0.05
        if overshoot <= slight_overshoot_limit:
            # Minimalny overshoot - nie tnij agresywnie
            return clips

        print(f"   ⚠️ Total {total:.1f}s przekracza target {target:.1f}s, trimming...")

        max_trim_fraction = 0.15
        min_duration_guard = max(6, int(self.config.selection.min_clip_duration))

        # Strategy: trim longest clips first, z limitem per klip
        clips_sorted = sorted(clips, key=lambda x: x.get('duration', 0), reverse=True)

        for clip in clips_sorted:
            if overshoot <= 0:
                break

            current_duration = clip.get('duration', 0)
            if current_duration <= min_duration_guard:
                continue

            allowed_trim = current_duration * max_trim_fraction
            max_possible_trim = current_duration - min_duration_guard
            trim_amount = min(allowed_trim, max_possible_trim, overshoot)

            if trim_amount <= 0:
                continue

            clip['t1'] = clip.get('t1', 0) - trim_amount
            clip['duration'] = clip.get('t1', 0) - clip.get('t0', 0)
            overshoot -= trim_amount

        valid_clips = [c for c in clips if c.get('duration', 0) >= min_duration_guard]

        return valid_clips

    def _top_up_if_needed(
        self,
        clips: List[Dict],
        scored_segments: List[Dict],
        all_segments: List[Dict],
        min_duration: int,
    ) -> List[Dict]:
        """Jeśli łączny czas jest poniżej targetu, dobierz dodatkowe klipy (max 40)."""

        target = self.config.selection.target_total_duration
        total = sum(c.get('duration', 0) for c in clips)

        if (total >= target or len(clips) >= 40) and total >= target * 0.5:
            return clips

        # Prefer segmenty już przefiltrowane po score, ale jeśli coverage <50% targetu, bierz pełen zbiór
        pool = scored_segments if total >= target * 0.5 else all_segments
        relaxed_min = max(4, int(min_duration * 0.6))

        used_ids = {c.get('id') for c in clips}
        remaining = [
            seg
            for seg in pool
            if seg.get('id') not in used_ids and seg.get('duration', 0) >= relaxed_min
        ]
        remaining.sort(key=lambda x: x.get('final_score', 0), reverse=True)

        for seg in remaining:
            if len(clips) >= 40 or total >= target:
                break
            if self._has_overlap(seg, clips, self.config.selection.min_time_gap):
                continue
            if total + seg.get('duration', 0) > target * 1.15:
                continue
            clips.append(seg)
            total += seg.get('duration', 0)

        return clips

    def _save_debug_plot(
        self,
        clips: List[Dict],
        all_segments: List[Dict],
        output_dir: Path,
    ) -> None:
        """Zapisz debugowy wykres score/burst, gdy klipów jest mało."""

        try:
            import matplotlib.pyplot as plt

            scores = [c.get("final_score", 0) for c in all_segments]
            burst_scores = [
                (c.get("subscores", {}) or {}).get("chat_burst_score", 0.0)
                for c in all_segments
            ]

            fig, ax1 = plt.subplots(figsize=(6, 4))
            ax1.hist(scores, bins=20, color="#3f51b5", alpha=0.7)
            ax1.set_xlabel("final_score")
            ax1.set_ylabel("Liczba segmentów")
            ax1.set_title("Debug score/burst (klipy <10)")

            ax2 = ax1.twinx()
            ax2.plot(sorted(burst_scores), color="#ff9800", linewidth=1.2)
            ax2.set_ylabel("chat_burst_score (posortowane)")

            fig.tight_layout()
            debug_path = output_dir / "debug_selection.png"
            fig.savefig(debug_path)
            plt.close(fig)
            print(f"   💾 Debug plot zapisany: {debug_path}")
        except Exception as exc:  # pragma: no cover
            print(f"   ⚠️ Nie udało się zapisać debug plot: {exc}")
    
    def _generate_title(self, clip: Dict) -> str:
        """Generuj tytuł klipu z AI categories lub keywords"""
        # Try AI categories first
        ai_categories = clip.get('ai_categories', [])
        if ai_categories:
            top_category = ai_categories[0]['label']
            # Capitalize first letter
            return top_category.capitalize()
        
        # Fallback: keywords
        features = clip.get('features', {})
        keywords = features.get('matched_keywords', [])
        
        if keywords:
            top_keywords = [kw['token'].capitalize() for kw in keywords[:3]]
            return " • ".join(top_keywords)
        
        # Last resort
        return "Ciekawy moment"
    
    def _select_shorts_candidates(
        self,
        segments: List[Dict],
        min_score: float
    ) -> List[Dict]:
        """
        Wybierz najlepsze segmenty dla YouTube Shorts

        Kryteria:
        - Długość: 15-60s (idealne dla Shorts)
        - Wysokie score
        - Różnorodność

        Returns:
            Lista klipów optymalnych dla Shorts
        """
        # Validation: check if segments have scores
        missing_score_count = sum(1 for seg in segments if 'final_score' not in seg)
        if missing_score_count > 0:
            print(f"   ⚠️ WARNING: {missing_score_count}/{len(segments)} segments missing final_score!")

        # Filter by Shorts duration constraints
        shorts_candidates = [
            seg for seg in segments
            if self.config.shorts.min_duration <= seg['duration'] <= self.config.shorts.max_duration
        ]

        # Filter by score if specified
        if min_score > 0:
            shorts_candidates = [
                seg for seg in shorts_candidates
                if seg.get('final_score', 0) >= min_score
            ]

        # Sort by score (descending)
        shorts_candidates.sort(key=lambda x: x.get('final_score', 0), reverse=True)

        # Take top N
        max_shorts = getattr(self.config.shorts, 'count', 10)
        selected_shorts = shorts_candidates[:max_shorts]

        # Sort chronologically
        selected_shorts.sort(key=lambda x: x['t0'])

        # Add shorts-specific metadata and validate scores
        for i, clip in enumerate(selected_shorts, 1):
            clip['shorts_id'] = f"short_{i:02d}"
            clip['shorts_title'] = self._generate_shorts_title(clip)
            clip['shorts_description'] = self._generate_shorts_description(clip)
            clip['is_shorts_candidate'] = True

            # Log score for debugging
            score = clip.get('final_score', 0)
            print(f"   📱 Short {i}: score={score:.2f}, duration={clip['duration']:.1f}s, id={clip.get('id', 'unknown')}")

        return selected_shorts
    
    def _generate_shorts_title(self, clip: Dict) -> str:
        """
        Generuj tytuł dla Short - używa AI jeśli dostępne

        Max 100 znaków dla YouTube Shorts
        """
        # Try AI generation first (much better quality)
        if self.ai_generator and hasattr(self.config, 'streamer_id'):
            try:
                metadata = self.ai_generator.generate_metadata(
                    clips=[clip],
                    streamer_id=self.config.streamer_id,
                    platform="youtube",
                    video_type="shorts",
                    content_type=f"{self.config.streamer_id}_shorts"
                )

                title = metadata.get('title', '')
                if title and len(title) <= 100:
                    logger.info(f"   🤖 AI-generated Shorts title: {title}")
                    return title

            except Exception as e:
                logger.warning(f"AI title generation failed: {e}, using fallback")

        # FALLBACK: Simple keyword concatenation (old method)
        if 'title' in clip and clip['title']:
            base = clip['title']
        else:
            # Generate from transcript
            transcript = clip.get('transcript', '')
            words = transcript.split()[:10]  # First 10 words
            base = ' '.join(words)

            # Clean up
            if len(base) > 50:
                base = base[:47] + "..."

            if not base:
                base = "Goracy moment"

        # Prefix based on score
        score = clip.get('final_score', 0)
        if score >= 0.9:
            prefix = "[TOP]"
        elif score >= 0.8:
            prefix = "[HOT]"
        elif score >= 0.7:
            prefix = "[NEW]"
        else:
            prefix = ""

        # Format: [PREFIX] Krótki tytuł
        if prefix:
            title = f"{prefix} {base}"
        else:
            title = base

        # Trim to 100 chars
        if len(title) > 100:
            title = title[:97] + "..."

        return title

    def _generate_shorts_description(self, clip: Dict) -> str:
        """
        Generuj opis dla Short - używa AI jeśli dostępne

        Max 5000 znaków dla YouTube Shorts (praktycznie: 200-300)
        """
        # Try AI generation first
        if self.ai_generator and hasattr(self.config, 'streamer_id'):
            try:
                metadata = self.ai_generator.generate_metadata(
                    clips=[clip],
                    streamer_id=self.config.streamer_id,
                    platform="youtube",
                    video_type="shorts",
                    content_type=f"{self.config.streamer_id}_shorts"
                )

                description = metadata.get('description', '')
                if description:
                    logger.info(f"   🤖 AI-generated Shorts description ({len(description)} chars)")
                    return description

            except Exception as e:
                logger.warning(f"AI description generation failed: {e}, using fallback")

        # FALLBACK: Simple description
        transcript_preview = clip.get('transcript', '')[:150]
        if transcript_preview:
            return f"{transcript_preview}...\n\n#Shorts #Highlights"
        else:
            return "Epic moment from the stream!\n\n#Shorts #Highlights"
    
    def _save_clips(self, clips: List[Dict], output_file: Path, is_shorts: bool = False):
        """Zapisz selected clips"""
        # Prepare serializable
        serializable = []

        for clip in clips:
            # Defensively get final_score with fallback
            final_score = clip.get('final_score', 0.0)
            if final_score == 0.0 and 'final_score' not in clip:
                print(f"   ⚠️ WARNING: Clip {clip.get('id', 'unknown')} missing final_score, using 0.0")

            clip_copy = {
                'clip_id': clip.get('clip_id', ''),
                'id': clip['id'],
                't0': float(clip['t0']),
                't1': float(clip['t1']),
                'duration': float(clip['duration']),
                'final_score': float(final_score),
                'title': clip.get('title', ''),
                'transcript_preview': clip.get('transcript', '')[:200] + '...' if clip.get('transcript') else '',
                'keywords': [kw['token'] for kw in clip.get('features', {}).get('matched_keywords', [])[:5]],
                'ai_category': clip.get('ai_categories', [{}])[0].get('label', 'N/A') if clip.get('ai_categories') else 'N/A',
                'merged_from': clip.get('merged_from', [])
            }

            # Add Shorts-specific fields
            if is_shorts:
                clip_copy['shorts_id'] = clip.get('shorts_id', '')
                clip_copy['shorts_title'] = clip.get('shorts_title', '')
                clip_copy['shorts_description'] = clip.get('shorts_description', '')
                clip_copy['is_shorts_candidate'] = True

            serializable.append(clip_copy)

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)

        file_type = "Shorts candidates" if is_shorts else "Selected clips"
        print(f"   💾 {file_type} zapisane: {output_file.name}")
    
    def cancel(self):
        """Anuluj operację"""
        pass