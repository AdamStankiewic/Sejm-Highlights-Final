"""
Stage 6: Intelligent Clip Selection v1.1
- Greedy selection z Non-Maximum Suppression
- Smart merge sąsiednich segmentów (NAPRAWIONY gap bug)
- Temporal coverage optimization (DYNAMICZNE dla długich materiałów)
- Duration adjustment
"""

import json
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
from collections import defaultdict

from .config import Config


class SelectionStage:
    """Stage 6: Clip Selection v1.1"""
    
    def __init__(self, config: Config):
        self.config = config
    
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

        # STEP 0: Filter by minimum score if specified (with fallback to top 20%)
        score_threshold = max(min_score, getattr(self.config.selection, 'min_score_threshold', 0.0) or 0.0)
        segments = self._filter_by_score_with_fallback(segments, score_threshold)
        print(f"   Po filtrze score (>= {score_threshold:.2f} lub top20): {len(segments)} segmentów")
        
        # STEP 1: Filter by minimum duration
        candidates = self._filter_by_duration(segments)
        print(f"   Po filtrze duration: {len(candidates)} kandydatów")
        
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
        
        # Calculate stats
        total_clip_duration = sum(clip['duration'] for clip in final_clips)
        
        # Sort chronologically
        final_clips.sort(key=lambda x: x['t0'])
        
        # Add sequential IDs
        for i, clip in enumerate(final_clips):
            clip['clip_id'] = f"clip_{i+1:03d}"
            clip['title'] = self._generate_title(clip)
        
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
        
        # Need to trim
        print(f"   ⚠️ Total {total:.1f}s przekracza target {target:.1f}s, trimming...")
        
        # Strategy: trim longest clips first
        clips_sorted = sorted(clips, key=lambda x: x.get('duration', 0), reverse=True)
        
        for clip in clips_sorted:
            if total <= target:
                break
            
            # Trim percentage from end
            current_duration = clip.get('duration', 0)
            if current_duration <= 0:
                continue
            
            trim_amount = min(
                current_duration * self.config.selection.trim_percentage,
                total - target
            )
            
            clip['t1'] = clip.get('t1', 0) - trim_amount
            clip['duration'] = clip.get('t1', 0) - clip.get('t0', 0)
            total -= trim_amount
        
        # SAFETY: Remove clips with invalid duration
        valid_clips = [c for c in clips if c.get('duration', 0) > 10]
        
        return valid_clips
    
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

            if not shorts_candidates and segments:
                percentile = getattr(self.config.scoring, 'dynamic_threshold_percentile', 80)
                dynamic_threshold = float(np.percentile([s.get('final_score', 0) for s in segments], percentile))
                shorts_candidates = [
                    seg for seg in segments
                    if self.config.shorts.min_duration <= seg['duration'] <= self.config.shorts.max_duration
                    and seg.get('final_score', 0) >= dynamic_threshold
                ]
                print(
                    f"   ⚠️ Shorts fallback: brak kandydatów dla progu {min_score:.2f} → top {percentile}% (>= {dynamic_threshold:.2f})"
                )
        
        # Sort by score (descending)
        shorts_candidates.sort(key=lambda x: x.get('final_score', 0), reverse=True)
        
        # Take top N
        max_shorts = getattr(self.config.shorts, 'count', 10)
        selected_shorts = shorts_candidates[:max_shorts]
        
        # Sort chronologically
        selected_shorts.sort(key=lambda x: x['t0'])
        
        # Add shorts-specific metadata
        for i, clip in enumerate(selected_shorts, 1):
            clip['shorts_id'] = f"short_{i:02d}"
            clip['shorts_title'] = self._generate_shorts_title(clip)
            clip['is_shorts_candidate'] = True
        
        return selected_shorts
    
    def _generate_shorts_title(self, clip: Dict) -> str:
        """
        Generuj tytuł dla Short (krótki, bez emoji - encoding issues)
        
        Max 100 znaków dla YouTube Shorts
        """
        # Try to get existing title, or generate from transcript
        if 'title' in clip and clip['title']:
            base = clip['title']
        else:
            # Generate from transcript (dla segments bez title)
            transcript = clip.get('transcript', '')
            words = transcript.split()[:10]  # First 10 words
            base = ' '.join(words)
            
            # Clean up
            if len(base) > 50:
                base = base[:47] + "..."
            
            if not base:
                base = "Goracy moment"
        
        # Prefix na podstawie score (bez emoji - problemy z encoding)
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
    
    def _save_clips(self, clips: List[Dict], output_file: Path, is_shorts: bool = False):
        """Zapisz selected clips"""
        # Prepare serializable
        serializable = []
        
        for clip in clips:
            clip_copy = {
                'clip_id': clip.get('clip_id', ''),
                'id': clip['id'],
                't0': float(clip['t0']),
                't1': float(clip['t1']),
                'duration': float(clip['duration']),
                'final_score': float(clip['final_score']),
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
                clip_copy['is_shorts_candidate'] = True
            
            serializable.append(clip_copy)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        
        file_type = "Shorts candidates" if is_shorts else "Selected clips"
        print(f"   💾 {file_type} zapisane: {output_file.name}")
    
    def cancel(self):
        """Anuluj operację"""
        pass