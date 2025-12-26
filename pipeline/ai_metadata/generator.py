"""
Metadata Generator - Main orchestration for AI-powered title/description generation.
"""
from typing import Dict, List, Optional, Tuple
import logging
import json
import hashlib
import time
from datetime import datetime
from pathlib import Path
import sqlite3

from .context_builder import ContextBuilder, StreamingBrief
from .prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class MetadataGenerator:
    """
    Main orchestration class for AI metadata generation.

    Features:
    - Integrates ContextBuilder + PromptBuilder
    - Database caching (avoid regeneration)
    - Few-shot learning from seed + learned examples
    - Cost tracking
    - Fallback to simple generation
    """

    def __init__(
        self,
        openai_client,
        streamer_manager,
        platform_config: Dict,
        db_path: str = "data/uploader.db"
    ):
        """
        Args:
            openai_client: OpenAI client (from existing pipeline)
            streamer_manager: StreamerManager instance
            platform_config: Platform constraints from config/platforms.yaml
            db_path: Path to SQLite database
        """
        self.openai_client = openai_client
        self.streamer_manager = streamer_manager
        self.platform_config = platform_config
        self.db_path = Path(db_path)

        # Initialize sub-components
        self.context_builder = ContextBuilder(openai_client)
        self.prompt_builder = None  # Created per-language

    def generate_metadata(
        self,
        clips: List[Dict],
        streamer_id: str,
        platform: str = "youtube",
        video_type: str = "long",
        language: Optional[str] = None,
        content_type: Optional[str] = None,
        force_regenerate: bool = False
    ) -> Dict:
        """
        Generate title and description for video.

        Args:
            clips: List of clip dicts from stage_06_selection.py
            streamer_id: Streamer identifier
            platform: Target platform (youtube/twitch/kick)
            video_type: Video type (long/shorts)
            language: Override language (defaults to profile language)
            content_type: Content type (e.g., sejm_meeting_pl, asmongold_gaming)
            force_regenerate: Skip cache and regenerate

        Returns:
            Dict with 'title', 'description', 'brief', 'cost', 'cached', 'content_type'
        """
        try:
            # Get streamer profile
            profile = self.streamer_manager.get(streamer_id)
            if not profile:
                logger.warning(f"Streamer profile not found: {streamer_id}, using fallback")
                return self._generate_fallback(clips, language or "pl")

            # Determine language
            lang = language or profile.primary_language

            # Auto-detect content type if not specified (SIMPLE heuristics)
            if not content_type:
                content_type = self._auto_detect_content_type(clips, streamer_id, lang)

            logger.info(f"Content type: {content_type}")

            # Create video facts hash for caching
            video_facts = self._create_video_facts(clips, streamer_id, platform, content_type)
            facts_hash = self._hash_video_facts(video_facts)

            # Check cache first (unless force regenerate)
            if not force_regenerate:
                cached = self._get_cached_metadata(facts_hash)
                if cached:
                    logger.info(f"✅ Using cached metadata for {streamer_id}")
                    return cached

            # Generate new metadata
            logger.info(f"🤖 Generating AI metadata for {streamer_id} ({platform}/{video_type}/{content_type})")

            # Step 1: Build context (StreamingBrief)
            brief = self._build_context(clips, lang, profile)

            # Step 2: Get few-shot examples (filtered by content_type)
            examples = self._get_few_shot_examples(streamer_id, platform, content_type)

            # Step 3: Generate title and description
            metadata = self._generate_with_ai(
                brief, profile, platform, video_type, lang, examples
            )

            # Step 4: Cache results
            self._cache_metadata(
                video_facts, facts_hash, brief, metadata, streamer_id, platform, content_type
            )

            return {
                **metadata,
                "brief": brief.to_dict(),
                "content_type": content_type,
                "cached": False
            }

        except Exception as e:
            logger.error(f"❌ AI metadata generation failed: {e}, using fallback")
            import traceback
            traceback.print_exc()
            return self._generate_fallback(clips, language or "pl")

    def _create_video_facts(
        self,
        clips: List[Dict],
        streamer_id: str,
        platform: str,
        content_type: str = "default"
    ) -> Dict:
        """Create deterministic video facts for hashing"""
        # Extract deterministic facts from clips
        facts = {
            "streamer_id": streamer_id,
            "platform": platform,
            "content_type": content_type,
            "clips": [
                {
                    "title": clip.get("title", ""),
                    "transcript": clip.get("transcript", "")[:500],  # First 500 chars
                    "keywords": clip.get("keywords", []),
                    "score": round(clip.get("final_score", 0), 2)
                }
                for clip in clips[:5]  # Top 5 clips only
            ]
        }
        return facts

    def _hash_video_facts(self, facts: Dict) -> str:
        """Create hash of video facts for deduplication"""
        facts_json = json.dumps(facts, sort_keys=True)
        return hashlib.sha256(facts_json.encode()).hexdigest()[:16]

    def _auto_detect_content_type(
        self,
        clips: List[Dict],
        streamer_id: str,
        language: str
    ) -> str:
        """
        Simple auto-detection of content type from clips.

        Uses keyword matching in clip titles/transcripts.
        For MVP - SIMPLE heuristics only!
        """
        # Get first few clip titles and transcripts for analysis
        text = ""
        for clip in clips[:3]:
            text += " " + clip.get("title", "").lower()
            text += " " + clip.get("transcript", "")[:200].lower()

        # Language suffix
        lang_suffix = "_pl" if language == "pl" else "_en"

        # Sejm-specific detection
        if streamer_id == "sejm":
            if any(kw in text for kw in ["posiedzenie", "obrady sejmu", "obrady"]):
                return f"sejm_meeting{lang_suffix}"
            elif any(kw in text for kw in ["konferencja prasowa"]):
                return f"sejm_press_conference{lang_suffix}"
            elif any(kw in text for kw in ["briefing", "komunikat"]):
                return f"sejm_briefing{lang_suffix}"
            elif any(kw in text for kw in ["komisja", "posiedzenie komisji"]):
                return f"sejm_committee{lang_suffix}"
            elif any(kw in text for kw in ["wystąpienie", "przemówienie"]):
                return f"sejm_speech{lang_suffix}"
            else:
                return f"sejm_other{lang_suffix}"

        # Gaming streamers - simple heuristic
        else:
            if any(kw in text for kw in ["irl", "just chatting", "talking", "reacts"]):
                return f"{streamer_id}_irl"
            else:
                return f"{streamer_id}_gaming"

    def _get_cached_metadata(self, facts_hash: str) -> Optional[Dict]:
        """Check if metadata already generated for these facts"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                SELECT generated_metadata_json, streaming_brief_json, metadata_cost
                FROM video_generation_cache
                WHERE video_facts_hash = ?
                AND generated_metadata_json IS NOT NULL
                ORDER BY created_at DESC
                LIMIT 1
            """, (facts_hash,))

            row = cursor.fetchone()
            conn.close()

            if row:
                metadata = json.loads(row[0])
                brief = json.loads(row[1]) if row[1] else None
                cost = row[2] or 0.0

                return {
                    **metadata,
                    "brief": brief,
                    "cost": cost,
                    "cached": True
                }

            return None

        except Exception as e:
            logger.warning(f"Cache lookup failed: {e}")
            return None

    def _build_context(
        self,
        clips: List[Dict],
        language: str,
        profile
    ) -> StreamingBrief:
        """Build StreamingBrief from clips"""
        start = time.time()

        # Use LLM for context if configured
        use_llm = profile.generation.context_model == "gpt-4o-mini"

        brief = self.context_builder.build_from_clips(
            clips,
            language=language,
            use_llm=use_llm
        )

        latency_ms = int((time.time() - start) * 1000)

        # Track cost if LLM was used
        if use_llm:
            # Rough estimate: ~1000 tokens for context extraction
            self._track_cost(
                operation="context_extraction",
                model="gpt-4o-mini",
                input_tokens=800,
                output_tokens=200,
                latency_ms=latency_ms
            )

        return brief

    def _get_few_shot_examples(
        self,
        streamer_id: str,
        platform: str,
        content_type: str = None,
        max_examples: int = 3
    ) -> List[Dict]:
        """Get few-shot examples: learned + seed (filtered by content_type)"""
        # Get profile seed examples
        profile = self.streamer_manager.get(streamer_id)
        seed_examples = profile.seed_examples if profile else []

        # Filter seed examples by content_type if specified
        if content_type:
            seed_examples = [
                ex for ex in seed_examples
                if (hasattr(ex, 'metadata') and ex.metadata and
                    ex.metadata.get('content_type') == content_type)
            ]

        # Get learned examples from database (filtered by content_type)
        learned_examples = self._get_learned_examples(streamer_id, platform, content_type, max_examples)

        # Combine with PromptBuilder utility
        prompt_builder = PromptBuilder(self.platform_config, language="pl")
        combined = prompt_builder.format_few_shot_examples(
            seed_examples=[ex.to_dict() if hasattr(ex, 'to_dict') else ex for ex in seed_examples],
            learned_examples=learned_examples,
            max_total=max_examples
        )

        return combined

    def _get_learned_examples(
        self,
        streamer_id: str,
        platform: str,
        content_type: str = None,
        limit: int = 3
    ) -> List[Dict]:
        """Get top-performing examples from database (filtered by content_type)"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Build query with optional content_type filter
            query = """
                SELECT title, description, brief_json, content_type
                FROM streamer_learned_examples
                WHERE streamer_id = ?
                AND platform = ?
                AND is_active = 1
            """
            params = [streamer_id, platform]

            # Filter by content_type if specified
            if content_type:
                query += " AND content_type = ?"
                params.append(content_type)

            query += " ORDER BY performance_score DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, tuple(params))

            examples = []
            for row in cursor.fetchall():
                brief = json.loads(row[2]) if row[2] else {}
                examples.append({
                    "title": row[0],
                    "description": row[1],
                    "metadata": {
                        "content_type": row[3] if len(row) > 3 else brief.get("content_type", "default"),
                        "emotional_tone": brief.get("emotional_state", "neutral")
                    }
                })

            conn.close()
            logger.info(f"Loaded {len(examples)} learned examples for content_type={content_type}")
            return examples

        except Exception as e:
            logger.warning(f"Failed to load learned examples: {e}")
            return []

    def _generate_with_ai(
        self,
        brief: StreamingBrief,
        profile,
        platform: str,
        video_type: str,
        language: str,
        examples: List[Dict]
    ) -> Dict:
        """Generate title and description using AI"""
        # Create language-specific prompt builder
        prompt_builder = PromptBuilder(self.platform_config, language)

        # Generate title
        title_start = time.time()
        title_prompts = prompt_builder.build_title_prompt(
            brief, platform, video_type, examples
        )

        title_response = self.openai_client.chat.completions.create(
            model=profile.generation.title_model,
            messages=[
                {"role": "system", "content": title_prompts["system"]},
                {"role": "user", "content": title_prompts["user"]}
            ],
            temperature=profile.generation.temperature,
            max_tokens=150
        )

        title = title_response.choices[0].message.content.strip()
        title_tokens = title_response.usage

        title_latency_ms = int((time.time() - title_start) * 1000)

        # Track title generation cost
        self._track_cost(
            operation="title_generation",
            model=profile.generation.title_model,
            input_tokens=title_tokens.prompt_tokens,
            output_tokens=title_tokens.completion_tokens,
            latency_ms=title_latency_ms
        )

        # Generate description
        desc_start = time.time()
        desc_prompts = prompt_builder.build_description_prompt(
            brief, title, platform, video_type, examples
        )

        desc_response = self.openai_client.chat.completions.create(
            model=profile.generation.description_model,
            messages=[
                {"role": "system", "content": desc_prompts["system"]},
                {"role": "user", "content": desc_prompts["user"]}
            ],
            temperature=profile.generation.temperature,
            max_tokens=500
        )

        description = desc_response.choices[0].message.content.strip()
        desc_tokens = desc_response.usage

        desc_latency_ms = int((time.time() - desc_start) * 1000)

        # Track description generation cost
        self._track_cost(
            operation="description_generation",
            model=profile.generation.description_model,
            input_tokens=desc_tokens.prompt_tokens,
            output_tokens=desc_tokens.completion_tokens,
            latency_ms=desc_latency_ms
        )

        # Calculate total cost (rough estimate)
        total_cost = self._estimate_cost(
            title_tokens.prompt_tokens + desc_tokens.prompt_tokens,
            title_tokens.completion_tokens + desc_tokens.completion_tokens,
            profile.generation.title_model
        )

        return {
            "title": title,
            "description": description,
            "cost": total_cost,
            "model": profile.generation.title_model,
            "examples_used": len(examples)
        }

    def _cache_metadata(
        self,
        video_facts: Dict,
        facts_hash: str,
        brief: StreamingBrief,
        metadata: Dict,
        streamer_id: str,
        platform: str,
        content_type: str = "default"
    ):
        """Cache generated metadata in database"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Generate video_id from facts hash
            video_id = f"{streamer_id}_{facts_hash}"

            cursor.execute("""
                INSERT OR REPLACE INTO video_generation_cache (
                    video_id,
                    streamer_id,
                    platform,
                    content_type,
                    video_facts_hash,
                    video_facts_json,
                    streaming_brief_json,
                    brief_generated_at,
                    brief_model,
                    generated_metadata_json,
                    metadata_generated_at,
                    metadata_model,
                    metadata_cost
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_id,
                streamer_id,
                platform,
                content_type,
                facts_hash,
                json.dumps(video_facts),
                json.dumps(brief.to_dict()),
                datetime.now().isoformat(),
                "gpt-4o-mini",
                json.dumps({
                    "title": metadata["title"],
                    "description": metadata["description"]
                }),
                datetime.now().isoformat(),
                metadata.get("model", "gpt-4o"),
                metadata.get("cost", 0.0)
            ))

            conn.commit()
            conn.close()

            logger.info(f"✅ Cached metadata for {video_id} (content_type={content_type})")

        except Exception as e:
            logger.warning(f"Failed to cache metadata: {e}")

    def _track_cost(
        self,
        operation: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
        video_id: Optional[str] = None,
        streamer_id: Optional[str] = None
    ):
        """Track API cost in database"""
        try:
            cost_usd = self._estimate_cost(input_tokens, output_tokens, model)

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO api_cost_tracking (
                    video_id,
                    streamer_id,
                    operation,
                    model,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                video_id,
                streamer_id,
                operation,
                model,
                input_tokens,
                output_tokens,
                cost_usd,
                latency_ms
            ))

            conn.commit()
            conn.close()

        except Exception as e:
            logger.warning(f"Failed to track cost: {e}")

    def _estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        model: str
    ) -> float:
        """Estimate API cost in USD"""
        # OpenAI pricing (as of 2024)
        pricing = {
            "gpt-4o": {
                "input": 0.0025 / 1000,   # $2.50 per 1M input tokens
                "output": 0.01 / 1000      # $10 per 1M output tokens
            },
            "gpt-4o-mini": {
                "input": 0.00015 / 1000,   # $0.15 per 1M input tokens
                "output": 0.0006 / 1000    # $0.60 per 1M output tokens
            }
        }

        model_pricing = pricing.get(model, pricing["gpt-4o"])
        cost = (input_tokens * model_pricing["input"]) + (output_tokens * model_pricing["output"])
        return round(cost, 6)

    def _generate_fallback(
        self,
        clips: List[Dict],
        language: str = "pl"
    ) -> Dict:
        """Fallback to simple generation (no AI)"""
        logger.info("Using fallback simple generation")

        # Build simple brief
        brief = self.context_builder.build_from_clips(
            clips,
            language=language,
            use_llm=False
        )

        # Simple title from top clip
        title = clips[0].get("title", "Highlights") if clips else "Highlights"

        # Simple description
        if language == "pl":
            description = f"{brief.main_narrative}\n\nNajlepsze momenty z transmisji!"
        else:
            description = f"{brief.main_narrative}\n\nBest moments from the stream!"

        return {
            "title": title,
            "description": description,
            "brief": brief.to_dict(),
            "cost": 0.0,
            "cached": False,
            "fallback": True
        }
