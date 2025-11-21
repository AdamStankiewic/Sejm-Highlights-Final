"""
Political controversy scoring using GPT
Part of Highlights AI Platform - Politics Module (Sejm)
"""
import os
import json
import numpy as np
from typing import List, Dict, Optional, Callable
from scipy.special import expit as sigmoid
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

load_dotenv()


class PoliticsScorer:
    """Score political segments using GPT semantic analysis"""

    def __init__(self, config):
        self.config = config
        self.openai_client = None
        self._init_gpt()

    def _init_gpt(self):
        """Initialize GPT API"""
        if not self.config.use_gpt_scoring:
            return

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("   Warning: OPENAI_API_KEY not found")
            return

        if OpenAI is None:
            print("   Warning: openai library not installed")
            return

        try:
            self.openai_client = OpenAI(api_key=api_key)
        except Exception as e:
            print(f"   Warning: GPT init failed: {e}")

    def score_segments(
        self,
        segments: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """
        Score political segments

        Pipeline:
        1. Pre-filter candidates (acoustic + keyword heuristics)
        2. GPT semantic analysis (top candidates only)
        3. Compute final composite score
        """
        # Pre-filter
        candidates = self._prefilter_candidates(segments)

        # GPT semantic analysis
        if self.openai_client:
            candidates = self._semantic_analysis_gpt(candidates, progress_callback)
        else:
            candidates = self._semantic_analysis_fallback(candidates)

        # Compute final scores
        scored = self._compute_final_scores(segments, candidates)

        return scored

    def _prefilter_candidates(self, segments: List[Dict]) -> List[Dict]:
        """Pre-filter: select top candidates based on acoustic + keyword scores"""
        candidates = []

        for seg in segments:
            features = seg.get('acoustic_features', {})
            lexical = seg.get('lexical_features', {})

            # Acoustic score (RMS energy)
            rms = features.get('rms', 0)
            acoustic_score = min(rms * 10, 1.0)

            # Keyword score
            keyword_score = min(lexical.get('keyword_score', 0) / 5.0, 1.0)

            # Pre-filter score
            prefilter_score = acoustic_score * 0.4 + keyword_score * 0.6

            candidates.append({
                **seg,
                'prefilter_score': prefilter_score
            })

        # Sort and take top N
        candidates.sort(key=lambda x: x['prefilter_score'], reverse=True)
        top_n = min(self.config.prefilter_top_n, len(candidates))

        return candidates[:top_n]

    def _semantic_analysis_gpt(
        self,
        candidates: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """GPT semantic analysis for political content"""
        labels = self.config.get_interest_labels_list()
        labels_str = "\n".join(f"- {label}" for label in labels)

        system_prompt = f"""Jesteś ekspertem od analizy polskich debat sejmowych.
Oceń fragment wypowiedzi pod kątem interesującości dla widza YouTube.

ETYKIETY INTERESUJĄCOŚCI:
{labels_str}

Dla każdego fragmentu:
1. Przypisz 0-3 etykiety (tylko pasujące)
2. Oceń confidence (0.0-1.0)

Odpowiedz w JSON: {{"labels": ["etykieta1"], "confidence": 0.8, "reason": "krótkie uzasadnienie"}}"""

        for i, seg in enumerate(candidates):
            if progress_callback:
                progress_callback(i / len(candidates), f"GPT: {i+1}/{len(candidates)}")

            transcript = seg.get('transcript', '')[:500]

            try:
                response = self.openai_client.chat.completions.create(
                    model=self.config.gpt_model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Fragment:\n{transcript}"}
                    ],
                    response_format={"type": "json_object"},
                    temperature=self.config.gpt_temperature,
                    max_tokens=150
                )

                result = json.loads(response.choices[0].message.content)

                # Calculate semantic score from labels
                semantic_score = 0.0
                for label in result.get('labels', []):
                    semantic_score += self.config.get_label_weight(label)

                semantic_score = sigmoid(semantic_score)
                confidence = result.get('confidence', 0.5)

                seg['gpt_result'] = result
                seg['semantic_score'] = float(semantic_score * confidence)

            except Exception as e:
                seg['semantic_score'] = 0.3  # Default fallback
                seg['gpt_error'] = str(e)

        return candidates

    def _semantic_analysis_fallback(self, candidates: List[Dict]) -> List[Dict]:
        """Fallback scoring when GPT not available"""
        for seg in candidates:
            # Use keyword score as proxy for semantic score
            lexical = seg.get('lexical_features', {})
            keyword_score = lexical.get('keyword_score', 0)
            seg['semantic_score'] = min(keyword_score / 5.0, 1.0)

        return candidates

    def _compute_final_scores(
        self,
        all_segments: List[Dict],
        scored_candidates: List[Dict]
    ) -> List[Dict]:
        """Compute final composite scores for all segments"""
        # Create lookup for scored candidates
        scored_lookup = {seg['id']: seg for seg in scored_candidates}

        for seg in all_segments:
            seg_id = seg['id']

            if seg_id in scored_lookup:
                scored = scored_lookup[seg_id]

                acoustic = seg.get('acoustic_features', {}).get('rms', 0) * 10
                acoustic = min(acoustic, 1.0)

                lexical = seg.get('lexical_features', {}).get('keyword_score', 0) / 5.0
                lexical = min(lexical, 1.0)

                semantic = scored.get('semantic_score', 0.3)

                # Weighted composite
                final_score = (
                    acoustic * self.config.acoustic_weight +
                    lexical * self.config.lexical_weight +
                    semantic * self.config.semantic_weight
                )

                seg['final_score'] = float(final_score)
                seg['semantic_score'] = semantic
                if 'gpt_result' in scored:
                    seg['gpt_result'] = scored['gpt_result']
            else:
                # Not in candidates - low score
                seg['final_score'] = 0.1

        return all_segments
