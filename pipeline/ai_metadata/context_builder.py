"""
Context Builder - Extracts relevant context from video clips for AI generation.
"""
from typing import Dict, List, Optional
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class StreamingBrief:
    """Structured context about a video for AI generation"""

    def __init__(
        self,
        main_narrative: str,
        emotional_state: str,
        content_type: str,
        key_moments: List[Dict],
        memorable_quotes: List[str],
        keywords: List[str],
        language: str = "pl"
    ):
        self.main_narrative = main_narrative
        self.emotional_state = emotional_state
        self.content_type = content_type
        self.key_moments = key_moments
        self.memorable_quotes = memorable_quotes
        self.keywords = keywords
        self.language = language
        self.generated_at = datetime.now().isoformat()

    def to_dict(self) -> Dict:
        return {
            "main_narrative": self.main_narrative,
            "emotional_state": self.emotional_state,
            "content_type": self.content_type,
            "key_moments": self.key_moments,
            "memorable_quotes": self.memorable_quotes,
            "keywords": self.keywords,
            "language": self.language,
            "generated_at": self.generated_at
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'StreamingBrief':
        return cls(
            main_narrative=data['main_narrative'],
            emotional_state=data['emotional_state'],
            content_type=data['content_type'],
            key_moments=data['key_moments'],
            memorable_quotes=data['memorable_quotes'],
            keywords=data['keywords'],
            language=data.get('language', 'pl')
        )


class ContextBuilder:
    """
    Builds context from clip data for AI generation.

    Integrates with existing pipeline data:
    - selected_clips.json (from stage_06_selection.py)
    - scored_segments.json (from stage_05_scoring_gpt.py)
    """

    def __init__(self, openai_client=None):
        """
        Args:
            openai_client: OpenAI client (from existing pipeline)
        """
        self.openai_client = openai_client

    def build_from_clips(
        self,
        clips: List[Dict],
        language: str = "pl",
        use_llm: bool = True
    ) -> StreamingBrief:
        """
        Build context from selected clips.

        Args:
            clips: List of clip dicts from stage_06_selection.py
                   Expected fields: title, transcript, keywords, final_score
            language: Output language (pl/en)
            use_llm: Whether to use LLM for enhancement (vs simple extraction)

        Returns:
            StreamingBrief with extracted context
        """
        # Quick validation
        if not clips:
            raise ValueError("No clips provided")

        # Extract basic info (deterministic, no LLM cost)
        keywords = self._extract_keywords(clips)
        quotes = self._extract_quotes(clips)

        if not use_llm or not self.openai_client:
            # Simple extraction (fast, no cost)
            return self._build_simple(clips, keywords, quotes, language)

        # Enhanced extraction with LLM (better quality)
        return self._build_with_llm(clips, keywords, quotes, language)

    def _extract_keywords(self, clips: List[Dict]) -> List[str]:
        """Extract keywords from clips (deterministic)"""
        all_keywords = []

        for clip in clips:
            # Use existing keywords from stage_06
            if 'keywords' in clip:
                all_keywords.extend(clip['keywords'])

            # Extract from title
            if 'title' in clip:
                title_words = clip['title'].split()
                all_keywords.extend([w for w in title_words if len(w) > 3])

        # Deduplicate and sort by frequency
        from collections import Counter
        keyword_counts = Counter(all_keywords)

        # Return top 10 most common
        return [kw for kw, count in keyword_counts.most_common(10)]

    def _extract_quotes(self, clips: List[Dict], max_quotes: int = 3) -> List[str]:
        """Extract memorable quotes from transcripts"""
        quotes = []

        for clip in clips[:max_quotes]:  # Only top clips
            if 'transcript' in clip:
                transcript = clip['transcript']

                # Simple heuristic: sentences with exclamation or question marks
                sentences = transcript.split('.')
                for sent in sentences:
                    if ('!' in sent or '?' in sent) and len(sent) < 100:
                        quotes.append(sent.strip())

        return quotes[:max_quotes]

    def _build_simple(
        self,
        clips: List[Dict],
        keywords: List[str],
        quotes: List[str],
        language: str
    ) -> StreamingBrief:
        """Build context without LLM (fast, deterministic)"""

        # Infer content type from keywords
        gaming_keywords = {'boss', 'game', 'kill', 'death', 'win', 'lose', 'fight'}
        political_keywords = {'sejm', 'poseł', 'minister', 'rząd', 'ustawa'}

        keyword_set = set(k.lower() for k in keywords)

        if keyword_set & gaming_keywords:
            content_type = "gaming"
        elif keyword_set & political_keywords:
            content_type = "political"
        else:
            content_type = "general"

        # Simple narrative from top clip
        main_narrative = clips[0].get('title', 'Highlights') if clips else 'Highlights'

        # Emotional state from keywords
        emotional_state = "neutral"
        if any(w in keyword_set for w in ['rage', 'angry', 'frustrated', 'wkurza']):
            emotional_state = "frustrated"
        elif any(w in keyword_set for w in ['happy', 'excited', 'epic', 'win']):
            emotional_state = "excited"

        # Key moments from clips
        key_moments = [
            {
                "time": f"{clip.get('t0', 0):.1f}",
                "summary": clip.get('title', 'Moment'),
                "score": clip.get('final_score', 0.0)
            }
            for clip in clips[:5]  # Top 5 clips
        ]

        return StreamingBrief(
            main_narrative=main_narrative,
            emotional_state=emotional_state,
            content_type=content_type,
            key_moments=key_moments,
            memorable_quotes=quotes,
            keywords=keywords,
            language=language
        )

    def _build_with_llm(
        self,
        clips: List[Dict],
        keywords: List[str],
        quotes: List[str],
        language: str
    ) -> StreamingBrief:
        """Build enhanced context using LLM (better quality, costs ~$0.01)"""

        # Prepare input for LLM (top 5 clips only to save tokens)
        top_clips = clips[:5]
        clips_text = "\n\n".join([
            f"Clip {i+1} (score: {clip.get('final_score', 0):.2f}):\n"
            f"Title: {clip.get('title', 'N/A')}\n"
            f"Transcript: {clip.get('transcript', 'N/A')[:200]}..."
            for i, clip in enumerate(top_clips)
        ])

        prompt = f"""Analyze these video clips and extract context:

CLIPS:
{clips_text}

KEYWORDS: {', '.join(keywords)}

Extract:
1. Main narrative (2-3 sentences) - what's the overall story?
2. Emotional state (1-2 words: excited/frustrated/focused/surprised/etc)
3. Content type (gaming/political/irl/music/talk)
4. Memorable moment (if any)

Output JSON only:
{{
  "main_narrative": "...",
  "emotional_state": "...",
  "content_type": "...",
  "memorable_quote": "..." or null
}}
"""

        try:
            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You extract structured context from video clips."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                max_tokens=300,
                temperature=0.3  # Low temperature for consistent extraction
            )

            import json
            result = json.loads(response.choices[0].message.content)

            # Build key moments from clips
            key_moments = [
                {
                    "time": f"{clip.get('t0', 0):.1f}",
                    "summary": clip.get('title', 'Moment'),
                    "score": clip.get('final_score', 0.0)
                }
                for clip in top_clips
            ]

            # Add memorable quote if found
            if result.get('memorable_quote'):
                quotes = [result['memorable_quote']] + quotes

            return StreamingBrief(
                main_narrative=result.get('main_narrative', 'Highlights'),
                emotional_state=result.get('emotional_state', 'neutral'),
                content_type=result.get('content_type', 'general'),
                key_moments=key_moments,
                memorable_quotes=quotes[:3],
                keywords=keywords,
                language=language
            )

        except Exception as e:
            logger.warning(f"LLM context extraction failed: {e}, falling back to simple")
            # Fallback to simple extraction
            return self._build_simple(clips, keywords, quotes, language)
