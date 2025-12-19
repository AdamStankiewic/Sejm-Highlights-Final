"""
Prompt Builder - Constructs AI prompts with few-shot learning for metadata generation.
"""
from typing import Dict, List, Optional
import logging
from .context_builder import StreamingBrief

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Builds dynamic prompts for AI title/description generation.

    Integrates with:
    - StreamerProfile (from pipeline.streamers)
    - StreamingBrief (from context_builder)
    - Platform constraints (from config/platforms.yaml)
    """

    def __init__(
        self,
        platform_config: Dict,
        language: str = "pl"
    ):
        """
        Args:
            platform_config: Platform constraints from config/platforms.yaml
            language: Target language (pl/en)
        """
        self.platform_config = platform_config
        self.language = language

    def build_title_prompt(
        self,
        brief: StreamingBrief,
        platform: str = "youtube",
        video_type: str = "long",
        few_shot_examples: Optional[List[Dict]] = None
    ) -> Dict[str, str]:
        """
        Build title generation prompt with few-shot learning.

        Args:
            brief: StreamingBrief with video context
            platform: Target platform (youtube/twitch/kick)
            video_type: Video type (long/shorts for YouTube)
            few_shot_examples: List of example dicts with 'title' and 'metadata'

        Returns:
            Dict with 'system' and 'user' prompts
        """
        # Get platform constraints
        constraints = self._get_constraints(platform, video_type)

        # Build system prompt
        system_prompt = self._get_system_prompt_title(constraints)

        # Build user prompt with context and examples
        user_prompt = self._build_title_user_prompt(
            brief,
            constraints,
            few_shot_examples or []
        )

        return {
            "system": system_prompt,
            "user": user_prompt
        }

    def build_description_prompt(
        self,
        brief: StreamingBrief,
        title: str,
        platform: str = "youtube",
        video_type: str = "long",
        few_shot_examples: Optional[List[Dict]] = None
    ) -> Dict[str, str]:
        """
        Build description generation prompt.

        Args:
            brief: StreamingBrief with video context
            title: Generated title
            platform: Target platform
            video_type: Video type (long/shorts)
            few_shot_examples: List of example dicts

        Returns:
            Dict with 'system' and 'user' prompts
        """
        constraints = self._get_constraints(platform, video_type)

        system_prompt = self._get_system_prompt_description(constraints)

        user_prompt = self._build_description_user_prompt(
            brief,
            title,
            constraints,
            few_shot_examples or []
        )

        return {
            "system": system_prompt,
            "user": user_prompt
        }

    def _get_constraints(self, platform: str, video_type: str = "long") -> Dict:
        """Get platform-specific constraints"""
        if platform == "youtube":
            config = self.platform_config.get("youtube", {})
            return config.get(video_type, config.get("long", {}))
        else:
            return self.platform_config.get(platform, {})

    def _get_system_prompt_title(self, constraints: Dict) -> str:
        """Generate system prompt for title generation"""
        if self.language == "pl":
            return f"""Jesteś ekspertem od tworzenia angażujących tytułów dla treści wideo na platformach streamingowych.

ZASADY:
- Maksymalna długość: {constraints.get('title_max', 100)} znaków
- Używaj emocjonalnych słów kluczowych
- Możesz używać emoji (🔥💥⚡) jeśli pasują do contentu
- Tytuł musi być clickbait, ale NIE MOŻE kłamać o treści
- Zachowaj autentyczny styl streamera

JĘZYK: Polski
FORMAT: Zwróć TYLKO tytuł, bez cudzysłowów ani dodatkowego tekstu."""
        else:
            return f"""You are an expert at creating engaging titles for streaming video content.

RULES:
- Maximum length: {constraints.get('title_max', 100)} characters
- Use emotional keywords
- You can use emoji (🔥💥⚡) if they fit the content
- Title must be clickbait but CANNOT lie about content
- Maintain authentic streamer style

LANGUAGE: English
FORMAT: Return ONLY the title, without quotes or extra text."""

    def _get_system_prompt_description(self, constraints: Dict) -> str:
        """Generate system prompt for description generation"""
        if self.language == "pl":
            return f"""Jesteś ekspertem od tworzenia opisów wideo dla platform streamingowych.

ZASADY:
- Maksymalna długość: {constraints.get('description_max', 5000)} znaków
- Używaj hashtagów (max {constraints.get('hashtags_max', 15)})
- Opisz kluczowe momenty z wideo
- Dodaj timestamps jeśli dostępne
- Zachowaj naturalny, autentyczny ton

JĘZYK: Polski
FORMAT: Zwróć opis w formacie:
[Krótki wstęp 1-2 zdania]

[Opis kluczowych momentów]

[Hashtagi]"""
        else:
            return f"""You are an expert at creating video descriptions for streaming platforms.

RULES:
- Maximum length: {constraints.get('description_max', 5000)} characters
- Use hashtags (max {constraints.get('hashtags_max', 15)})
- Describe key moments from video
- Add timestamps if available
- Maintain natural, authentic tone

LANGUAGE: English
FORMAT: Return description in format:
[Short intro 1-2 sentences]

[Key moments description]

[Hashtags]"""

    def _build_title_user_prompt(
        self,
        brief: StreamingBrief,
        constraints: Dict,
        examples: List[Dict]
    ) -> str:
        """Build user prompt for title generation with few-shot examples"""
        prompt_parts = []

        # Add few-shot examples if available
        if examples:
            prompt_parts.append("PRZYKŁADY DOBRYCH TYTUŁÓW:" if self.language == "pl" else "EXAMPLES OF GOOD TITLES:")
            for i, example in enumerate(examples[:3], 1):  # Max 3 examples
                prompt_parts.append(f"\nPrzykład {i}:" if self.language == "pl" else f"\nExample {i}:")
                prompt_parts.append(f"Tytuł: {example.get('title', 'N/A')}")
                if 'metadata' in example:
                    meta = example['metadata']
                    prompt_parts.append(f"Typ: {meta.get('content_type', 'N/A')}, Ton: {meta.get('emotional_tone', 'N/A')}")
            prompt_parts.append("")

        # Add current video context
        if self.language == "pl":
            prompt_parts.extend([
                "TWOJE ZADANIE - wygeneruj tytuł dla tego wideo:",
                f"\nNARRACJA: {brief.main_narrative}",
                f"EMOCJE: {brief.emotional_state}",
                f"TYP CONTENTU: {brief.content_type}",
            ])
        else:
            prompt_parts.extend([
                "YOUR TASK - generate title for this video:",
                f"\nNARRATIVE: {brief.main_narrative}",
                f"EMOTIONS: {brief.emotional_state}",
                f"CONTENT TYPE: {brief.content_type}",
            ])

        # Add keywords
        if brief.keywords:
            kw_label = "SŁOWA KLUCZOWE:" if self.language == "pl" else "KEYWORDS:"
            prompt_parts.append(f"{kw_label} {', '.join(brief.keywords[:5])}")

        # Add memorable quotes if available
        if brief.memorable_quotes:
            quote_label = "CYTATY:" if self.language == "pl" else "QUOTES:"
            prompt_parts.append(f"{quote_label}")
            for quote in brief.memorable_quotes[:2]:
                prompt_parts.append(f'- "{quote}"')

        # Add key moments
        if brief.key_moments:
            moments_label = "KLUCZOWE MOMENTY:" if self.language == "pl" else "KEY MOMENTS:"
            prompt_parts.append(f"\n{moments_label}")
            for moment in brief.key_moments[:3]:
                time = moment.get('time', '?')
                summary = moment.get('summary', 'N/A')
                prompt_parts.append(f"- {time}s: {summary}")

        # Add final instruction
        final_instruction = (
            f"\nWygeneruj JEDEN clickbaitowy tytuł (max {constraints.get('title_max', 100)} znaków):"
            if self.language == "pl"
            else f"\nGenerate ONE clickbait title (max {constraints.get('title_max', 100)} characters):"
        )
        prompt_parts.append(final_instruction)

        return "\n".join(prompt_parts)

    def _build_description_user_prompt(
        self,
        brief: StreamingBrief,
        title: str,
        constraints: Dict,
        examples: List[Dict]
    ) -> str:
        """Build user prompt for description generation"""
        prompt_parts = []

        # Add few-shot examples if available
        if examples:
            prompt_parts.append("PRZYKŁADY DOBRYCH OPISÓW:" if self.language == "pl" else "EXAMPLES OF GOOD DESCRIPTIONS:")
            for i, example in enumerate(examples[:2], 1):  # Max 2 examples for descriptions
                if 'description' in example:
                    prompt_parts.append(f"\nPrzykład {i}:" if self.language == "pl" else f"\nExample {i}:")
                    desc = example['description']
                    # Truncate long examples
                    if len(desc) > 200:
                        desc = desc[:200] + "..."
                    prompt_parts.append(desc)
            prompt_parts.append("")

        # Add current video context
        if self.language == "pl":
            prompt_parts.extend([
                "TWOJE ZADANIE - wygeneruj opis dla tego wideo:",
                f"\nTYTUŁ: {title}",
                f"\nNARRACJA: {brief.main_narrative}",
                f"EMOCJE: {brief.emotional_state}",
                f"TYP CONTENTU: {brief.content_type}",
            ])
        else:
            prompt_parts.extend([
                "YOUR TASK - generate description for this video:",
                f"\nTITLE: {title}",
                f"\nNARRATIVE: {brief.main_narrative}",
                f"EMOTIONS: {brief.emotional_state}",
                f"CONTENT TYPE: {brief.content_type}",
            ])

        # Add key moments with timestamps
        if brief.key_moments:
            moments_label = "\nKLUCZOWE MOMENTY (dodaj timestamps):" if self.language == "pl" else "\nKEY MOMENTS (add timestamps):"
            prompt_parts.append(moments_label)
            for moment in brief.key_moments[:5]:
                time = moment.get('time', '?')
                summary = moment.get('summary', 'N/A')
                prompt_parts.append(f"- {time}s: {summary}")

        # Add keywords for hashtags
        if brief.keywords:
            kw_label = "\nSŁOWA KLUCZOWE (użyj jako hashtagi):" if self.language == "pl" else "\nKEYWORDS (use as hashtags):"
            prompt_parts.append(f"{kw_label} {', '.join(brief.keywords)}")

        # Add final instruction
        max_length = constraints.get('description_max', 5000)
        max_hashtags = constraints.get('hashtags_max', 15)

        if self.language == "pl":
            final_instruction = f"""
Wygeneruj opis wideo (max {max_length} znaków):
1. Krótki wstęp (1-2 zdania)
2. Opis kluczowych momentów z timestamps
3. Max {max_hashtags} hashtagów na końcu"""
        else:
            final_instruction = f"""
Generate video description (max {max_length} characters):
1. Short intro (1-2 sentences)
2. Key moments with timestamps
3. Max {max_hashtags} hashtags at the end"""

        prompt_parts.append(final_instruction)

        return "\n".join(prompt_parts)

    def format_few_shot_examples(
        self,
        seed_examples: List[Dict],
        learned_examples: List[Dict],
        max_total: int = 3
    ) -> List[Dict]:
        """
        Combine seed examples (from profile) with learned examples (from database).

        Args:
            seed_examples: Curated examples from streamer profile
            learned_examples: Top-performing examples from database
            max_total: Maximum total examples to return

        Returns:
            Combined list of examples, prioritizing learned > seed
        """
        # Start with learned examples (they have proven performance)
        combined = []

        # Add top learned examples first
        for example in learned_examples:
            if len(combined) >= max_total:
                break
            combined.append(example)

        # Fill remaining slots with seed examples
        for example in seed_examples:
            if len(combined) >= max_total:
                break
            combined.append(example)

        return combined
