"""
Stage 5: AI Semantic Scoring with GPT-4o-mini
- Pre-filtering używając acoustic + keyword scores
- Deep semantic analysis z GPT (tylko top 40)
- Composite scoring (acoustic + lexical + semantic)
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import numpy as np
from scipy.special import expit as sigmoid
import os
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    print("⚠️ openai nie zainstalowany. Instaluję...")
    import subprocess
    subprocess.check_call(["pip", "install", "openai"])
    from openai import OpenAI

from .config import Config

# Load environment variables
load_dotenv()


class ScoringStage:
    """Stage 5: AI Semantic Scoring with GPT"""

    def __init__(self, config: Config):
        self.config = config
        self.openai_client = None
        self._load_gpt()

        # Chat analyzer (optional - tylko dla Stream mode)
        self.chat_analyzer = None
        self._load_chat_analyzer()
    
    def _load_gpt(self):
        """Załaduj GPT API"""
        api_key = os.getenv("OPENAI_API_KEY")

        if not api_key:
            print("⚠️ OPENAI_API_KEY nie znaleziony w .env")
            print("   Używam fallback (bez GPT scoring)")
            return

        try:
            self.openai_client = OpenAI(api_key=api_key)
            print("✓ GPT-4o-mini API załadowane")
        except Exception as e:
            print(f"⚠️ Błąd ładowania GPT: {e}")
            self.openai_client = None

    def _load_chat_analyzer(self):
        """Załaduj Chat Analyzer (tylko gdy chat.json podany)"""
        if not hasattr(self.config, 'chat'):
            return

        if not self.config.chat.enabled:
            return

        if not self.config.chat.chat_json_path:
            return

        try:
            from .stage_chat_analysis import ChatAnalyzer
            self.chat_analyzer = ChatAnalyzer(self.config.chat)

            success = self.chat_analyzer.load_chat(self.config.chat.chat_json_path)
            if success:
                print(f"✓ Chat analyzer załadowany ({self.chat_analyzer.platform})")
                print(f"   Lag compensation: {self.config.chat.chat_lag_offset}s przed spike")
            else:
                self.chat_analyzer = None

        except Exception as e:
            print(f"⚠️ Nie można załadować chat.json: {e}")
            self.chat_analyzer = None

    def process(
        self,
        segments: List[Dict],
        output_dir: Path,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """
        Główna metoda przetwarzania
        
        Returns:
            Dict zawierający segments z finalnym scoring
        """
        print(f"🧠 AI Semantic Scoring dla {len(segments)} segmentów...")
        
        # STAGE 1: Pre-filtering (acoustic + keyword heuristics)
        print("📊 Stage 1: Pre-filtering...")
        candidates = self._prefilter_candidates(segments)
        
        print(f"   ✓ Wybrano {len(candidates)} kandydatów do AI eval")
        
        # STAGE 2: Deep semantic analysis (GPT)
        print("🤖 Stage 2: GPT Semantic Analysis...")
        if self.openai_client:
            candidates = self._semantic_analysis_gpt(
                candidates,
                progress_callback=progress_callback
            )
        else:
            print("   ⚠️ GPT niedostępne, używam fallback scoring")
            candidates = self._semantic_analysis_fallback(candidates)
        
        # STAGE 3: Final composite scoring
        print("⚖️ Stage 3: Final Composite Scoring...")
        scored_segments = self._compute_final_scores(segments, candidates)
        
        # Sort by score
        scored_segments.sort(key=lambda x: x['final_score'], reverse=True)
        
        # Zapisz
        output_file = output_dir / "scored_segments.json"
        self._save_segments(scored_segments, output_file)
        
        # Stats
        avg_score = np.mean([s['final_score'] for s in scored_segments])
        print(f"   Średni score: {avg_score:.3f}")
        print(f"   Top score: {scored_segments[0]['final_score']:.3f}")
        
        print("✅ Stage 5 zakończony")
        
        return {
            'segments': scored_segments,
            'num_segments': len(scored_segments),
            'num_ai_evaluated': len(candidates),
            'output_file': str(output_file)
        }
    
    def _prefilter_candidates(self, segments: List[Dict]) -> List[Dict]:
        """Pre-filtering: wybierz top-N segmentów do GPT evaluation"""
        candidates = []
        
        for seg in segments:
            features = seg.get('features', {})
            
            # Acoustic score (normalized features)
            acoustic_score = (
                0.35 * features.get('rms_z', 0) +
                0.25 * features.get('spectral_centroid_z', 0) +
                0.20 * features.get('speech_rate_wpm', 0) / 200 +
                0.15 * features.get('spectral_flux', 0) +
                0.05 * features.get('dramatic_pauses', 0)
            )
            
            # Keyword boost
            keyword_score = features.get('keyword_score', 0)
            keyword_score_norm = min(keyword_score / 10, 1.0)
            
            # Pre-score
            pre_score = 0.6 * acoustic_score + 0.4 * keyword_score_norm
            seg['pre_score'] = float(pre_score)
            
            # Force include high keyword scores
            if keyword_score >= self.config.scoring.prefilter_keyword_threshold:
                candidates.append(seg)
        
        # Sort by pre_score
        segments_sorted = sorted(segments, key=lambda x: x.get('pre_score', 0), reverse=True)
        
        # Take top-N
        top_n = segments_sorted[:self.config.scoring.prefilter_top_n]
        
        # Merge with force-included (deduplicate)
        candidate_ids = {c['id'] for c in candidates}
        for seg in top_n:
            if seg['id'] not in candidate_ids:
                candidates.append(seg)
                candidate_ids.add(seg['id'])
        
        return candidates
    
    def _semantic_analysis_gpt(
        self,
        candidates: List[Dict],
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """Deep semantic analysis używając GPT-4o-mini"""
        
        if not candidates:
            return []
        
        # Batch processing - 10 segmentów na raz
        batch_size = 10
        total = len(candidates)
        
        for batch_idx in range(0, total, batch_size):
            batch = candidates[batch_idx:batch_idx + batch_size]
            
            # Progress
            progress_pct = batch_idx / total
            if progress_callback:
                progress_callback(
                    progress_pct,
                    f"GPT eval batch {batch_idx//batch_size + 1}/{(total + batch_size - 1)//batch_size}"
                )
            
            # Przygotuj transkrypty
            transcripts_text = ""
            for i, seg in enumerate(batch):
                transcript = seg.get('transcript', '')[:400]  # Max 400 chars
                transcripts_text += f"\n[{i}] {transcript}\n"
            
            prompt = f"""Oceń te fragmenty debaty sejmowej pod kątem INTERESANTOŚCI dla widza YouTube (0.0-1.0):

{transcripts_text}

Kryteria WYSOKIEGO score (0.7-1.0):
- Ostra polemika, kłótnie, wymiana oskarżeń
- Emocje, podniesiony głos, sarkazm, ironia
- Kontrowersje, skandale, zaskakujące stwierdzenia
- Momenty memiczne, śmieszne, absurdalne
- Przerwania, reakcje sali, oklaski/buczenie

Kryteria NISKIEGO score (0.0-0.3):
- Formalne procedury, regulaminy
- Monotonne odczytywanie list, liczb
- Podziękowania, grzeczności
- Nudne, techniczne szczegóły

Odpowiedz TYLKO w formacie JSON:
{{"scores": [0.8, 0.3, 0.9, ...]}}

Tablica ma {len(batch)} elementów - po jednym score dla każdego [N]."""

            try:
                response = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "Jesteś ekspertem od analizy politycznych debat i treści viralowych."},
                        {"role": "user", "content": prompt}
                    ],
                    response_format={"type": "json_object"},
                    max_tokens=200,
                    temperature=0.3
                )
                
                result = json.loads(response.choices[0].message.content)
                scores = result.get('scores', [])
                
                # Assign scores
                for i, seg in enumerate(batch):
                    if i < len(scores):
                        seg['semantic_score'] = float(min(max(scores[i], 0.0), 1.0))
                    else:
                        seg['semantic_score'] = 0.5
                
                print(f"   ✓ Batch {batch_idx//batch_size + 1}: avg score {np.mean(scores):.2f}")
                
            except Exception as e:
                print(f"   ⚠️ GPT batch {batch_idx//batch_size + 1} error: {e}")
                # Fallback to neutral scores
                for seg in batch:
                    seg['semantic_score'] = 0.5
        
        return candidates
    
    def _semantic_analysis_fallback(self, candidates: List[Dict]) -> List[Dict]:
        """Fallback scoring bez GPT (używa tylko keywords)"""
        for seg in candidates:
            features = seg.get('features', {})
            keyword_score = features.get('keyword_score', 0)
            # Simple heuristic
            seg['semantic_score'] = min(keyword_score / 15.0, 1.0)
        
        return candidates
    
    def _compute_final_scores(
        self,
        all_segments: List[Dict],
        ai_evaluated: List[Dict]
    ) -> List[Dict]:
        """Oblicz finalne composite scores"""
        
        # Create lookup for AI evaluated segments
        ai_scores = {seg['id']: seg for seg in ai_evaluated}
        
        scored = []
        
        for seg in all_segments:
            seg_id = seg['id']
            features = seg.get('features', {})

            # Base scores
            acoustic_score = seg.get('pre_score', 0) * 0.6
            keyword_score = min(features.get('keyword_score', 0) / 10, 1.0)
            speaker_change = features.get('speaker_change_prob', 0.5)

            # === CHAT SCORE (NEW!) ===
            chat_score = 0.0
            if self.chat_analyzer:
                chat_data = self.chat_analyzer.score_segment(seg['t0'], seg['t1'])
                chat_score = chat_data['total_score']
                seg['chat_data'] = chat_data  # Store for debugging

            if seg_id in ai_scores:
                # Full formula z GPT
                semantic_score = ai_scores[seg_id].get('semantic_score', 0)

                # Adjust weights based on chat availability
                if self.chat_analyzer:
                    # Redistribute weights gdy chat dostępny (total = 1.0)
                    # Zmniejszamy inne wagi o ~15% żeby zrobić miejsce na chat
                    final_score = (
                        0.20 * acoustic_score +      # was 0.25
                        0.12 * keyword_score +       # was 0.15
                        0.43 * semantic_score +      # was 0.50
                        0.10 * speaker_change +      # unchanged
                        0.15 * chat_score            # NEW!
                    )
                else:
                    # Original formula (bez chat)
                    final_score = (
                        self.config.scoring.weight_acoustic * acoustic_score +
                        self.config.scoring.weight_keyword * keyword_score +
                        self.config.scoring.weight_semantic * semantic_score +
                        self.config.scoring.weight_speaker_change * speaker_change
                    )

                seg['semantic_score'] = semantic_score

            else:
                # Only heuristics (penalty)
                if self.chat_analyzer:
                    # Z chat score
                    final_score = (acoustic_score + keyword_score + chat_score) / 3 * 0.6
                else:
                    # Bez chat score
                    final_score = (acoustic_score + keyword_score) / 2 * 0.6
                seg['semantic_score'] = 0.0
            
            # Position diversity bonus
            position = features.get('position_in_video', 0.5)
            position_bonus = 1.0 + self.config.scoring.position_diversity_bonus * (1 - abs(position - 0.5))
            
            final_score *= position_bonus
            
            # Clamp to [0, 1]
            final_score = float(np.clip(final_score, 0, 1))
            
            seg['final_score'] = final_score
            seg['subscores'] = {
                'acoustic': float(acoustic_score),
                'keyword': float(keyword_score),
                'semantic': seg['semantic_score'],
                'speaker_change': float(speaker_change),
                'chat': float(chat_score)  # NEW! (0.0 gdy brak chat)
            }

            scored.append(seg)
        
        return scored
    
    def _save_segments(self, segments: List[Dict], output_file: Path):
        """Zapisz scored segments"""
        serializable = []
        for seg in segments:
            seg_copy = seg.copy()
            if 'final_score' in seg_copy:
                seg_copy['final_score'] = float(seg_copy['final_score'])
            serializable.append(seg_copy)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
        
        print(f"   💾 Scored segments zapisane: {output_file.name}")
    
    def cancel(self):
        """Anuluj operację"""
        pass