"""
Multi-language, content-aware title and description generator.

Generates YouTube titles and descriptions that adapt to:
- Language (PL, EN, DE)
- Content type (Gaming, IRL, Event, etc.)
- Streamer context
- Chat reactions and highlights
"""

from typing import Dict, List, Optional
import openai
import os


class TitleGenerator:
    """
    Generates context-aware titles and descriptions for streaming highlights.

    Supports:
    - Multiple languages (PL, EN, DE)
    - Content type adaptation (Gaming, IRL, Events, etc.)
    - Streamer-specific branding
    - Chat-based context
    """

    # Language-specific prompt templates
    LANGUAGE_PROMPTS = {
        'pl': {
            'instruction': 'Wygeneruj clickbaitowy tytuł dla YouTube {format_type}',
            'context_label': 'KONTEKST STREAMERA',
            'moment_label': 'MOMENT Z STREAMU',
            'chat_label': 'REAKCJA CZATU',
            'requirements_label': 'WYMAGANIA',
            'requirements': [
                'Język: Polski',
                'Max: {max_chars} znaków',
                'Format: "[{streamer}] [AKCJA/MOMENT]! [EMOJI]"',
                'Clickbait ale autentyczny (bazuj na transkrypcie!)',
                'Dopasuj styl do typu contentu'
            ],
            'examples_label': 'PRZYKŁADY',
            'request': 'Wygeneruj {count} opcje tytułu:'
        },
        'en': {
            'instruction': 'Generate clickbait title for YouTube {format_type}',
            'context_label': 'STREAMER CONTEXT',
            'moment_label': 'STREAM MOMENT',
            'chat_label': 'CHAT REACTION',
            'requirements_label': 'REQUIREMENTS',
            'requirements': [
                'Language: English',
                'Max: {max_chars} characters',
                'Format: "[{streamer}] [ACTION/MOMENT]! [EMOJI]"',
                'Clickbait but authentic (based on transcript!)',
                'Match style to content type'
            ],
            'examples_label': 'EXAMPLES',
            'request': 'Generate {count} title options:'
        },
        'de': {
            'instruction': 'Erstelle clickbait Titel für YouTube {format_type}',
            'context_label': 'STREAMER KONTEXT',
            'moment_label': 'STREAM MOMENT',
            'chat_label': 'CHAT REAKTION',
            'requirements_label': 'ANFORDERUNGEN',
            'requirements': [
                'Sprache: Deutsch',
                'Max: {max_chars} Zeichen',
                'Format: "[{streamer}] [AKTION/MOMENT]! [EMOJI]"',
                'Clickbait aber authentisch (basiert auf Transkript!)',
                'Stil an Content-Typ anpassen'
            ],
            'examples_label': 'BEISPIELE',
            'request': 'Erstelle {count} Titel-Optionen:'
        }
    }

    # Content-type specific examples
    CONTENT_EXAMPLES = {
        'Gaming': {
            'pl': [
                '[{streamer}] ACE CLUTCH W OSTATNIEJ RUNDZIE! 🔥',
                '[{streamer}] NAJLEPSZE ZABICIE W KARIERZE! 💀',
                '[{streamer}] TO SIĘ DOPIERO NIE ZDARZA! 😱'
            ],
            'en': [
                '[{streamer}] INSANE ACE CLUTCH! 🔥',
                '[{streamer}] BEST KILL OF MY CAREER! 💀',
                '[{streamer}] THIS NEVER HAPPENS! 😱'
            ],
            'de': [
                '[{streamer}] KRASSER ACE CLUTCH! 🔥',
                '[{streamer}] BESTES KILL MEINER KARRIERE! 💀',
                '[{streamer}] DAS PASSIERT NIE! 😱'
            ]
        },
        'IRL': {
            'pl': [
                '[{streamer}] TO SIĘ NAPRAWDĘ STAŁO! 😱',
                '[{streamer}] NIE UWIERZYCIE CO ZOBACZYŁEM! 🤯',
                '[{streamer}] NAJDZIWNIEJSZY MOMENT IRL! 🎯'
            ],
            'en': [
                '[{streamer}] THIS ACTUALLY HAPPENED! 😱',
                '[{streamer}] YOU WON\'T BELIEVE WHAT I SAW! 🤯',
                '[{streamer}] WEIRDEST IRL MOMENT! 🎯'
            ],
            'de': [
                '[{streamer}] DAS IST WIRKLICH PASSIERT! 😱',
                '[{streamer}] IHR WERDET NICHT GLAUBEN WAS ICH SAH! 🤯',
                '[{streamer}] SELTSAMSTER IRL MOMENT! 🎯'
            ]
        },
        'Event/Special': {
            'pl': [
                '[{streamer}] REKORD CHARITY STREAM! 🎯',
                '[{streamer}] HISTORYCZNY MOMENT EVENTU! ⚡',
                '[{streamer}] NIKT SIĘ TEGO NIE SPODZIEWAŁ! 🔥'
            ],
            'en': [
                '[{streamer}] CHARITY STREAM RECORD! 🎯',
                '[{streamer}] HISTORIC EVENT MOMENT! ⚡',
                '[{streamer}] NOBODY EXPECTED THIS! 🔥'
            ],
            'de': [
                '[{streamer}] CHARITY STREAM REKORD! 🎯',
                '[{streamer}] HISTORISCHER EVENT MOMENT! ⚡',
                '[{streamer}] DAS HAT KEINER ERWARTET! 🔥'
            ]
        },
        'Just Chatting': {
            'pl': [
                '[{streamer}] SZALONA HISTORIA! 🤯',
                '[{streamer}] CZAT NIE MOŻE W TO UWIERZYĆ! 😂',
                '[{streamer}] NAJBARDZIEJ KONTROWERSYJNE! 🔥'
            ],
            'en': [
                '[{streamer}] CRAZY STORY! 🤯',
                '[{streamer}] CHAT CAN\'T BELIEVE IT! 😂',
                '[{streamer}] MOST CONTROVERSIAL! 🔥'
            ],
            'de': [
                '[{streamer}] VERRÜCKTE GESCHICHTE! 🤯',
                '[{streamer}] CHAT KANN ES NICHT GLAUBEN! 😂',
                '[{streamer}] AM KONTROVERSESTEN! 🔥'
            ]
        },
        'Variety/Mixed': {
            'pl': [
                '[{streamer}] TEN MOMENT! 💀',
                '[{streamer}] CZAT OSZALAŁ! 🔥',
                '[{streamer}] ABSOLUTNY CHAOS! 😱'
            ],
            'en': [
                '[{streamer}] THIS MOMENT! 💀',
                '[{streamer}] CHAT WENT CRAZY! 🔥',
                '[{streamer}] ABSOLUTE CHAOS! 😱'
            ],
            'de': [
                '[{streamer}] DIESER MOMENT! 💀',
                '[{streamer}] CHAT DREHT DURCH! 🔥',
                '[{streamer}] ABSOLUTES CHAOS! 😱'
            ]
        }
    }

    def __init__(self, openai_api_key: Optional[str] = None):
        """
        Initialize title generator.

        Args:
            openai_api_key: OpenAI API key (or uses OPENAI_API_KEY env var)
        """
        self.api_key = openai_api_key or os.getenv('OPENAI_API_KEY')
        if self.api_key:
            openai.api_key = self.api_key

    def generate_title(
        self,
        stream_context: Dict[str, str],
        transcript: str,
        chat_stats: Optional[Dict] = None,
        format_type: str = "Shorts",
        max_chars: int = 70,
        num_options: int = 3
    ) -> List[str]:
        """
        Generate content-aware titles.

        Args:
            stream_context: Dict with keys:
                - streamer: Streamer name
                - content_type: Gaming/IRL/Event/Just Chatting/Variety
                - activity: Specific game/activity (optional)
                - stream_title: Original stream title (optional)
                - language: Language code (pl/en/de)
            transcript: Transcript of the highlight moment
            chat_stats: Optional chat statistics:
                - spike_intensity: Chat spike multiplier
                - top_emotes: List of top emotes
                - avg_viewers: Average viewer count
            format_type: "Shorts" or "Clip"
            max_chars: Maximum title length
            num_options: Number of title options to generate

        Returns:
            List of title options
        """
        language = stream_context.get('language', 'pl')
        streamer = stream_context.get('streamer', 'STREAMER')
        content_type = stream_context.get('content_type', 'Variety/Mixed')
        activity = stream_context.get('activity', '')
        stream_title = stream_context.get('stream_title', '')

        # Get language-specific template
        lang_template = self.LANGUAGE_PROMPTS.get(language, self.LANGUAGE_PROMPTS['pl'])

        # Build context description
        if content_type == 'Gaming' and activity:
            context_desc = f"Gaming stream ({activity})"
        elif content_type == 'IRL':
            context_desc = f"IRL stream{f' - {activity}' if activity else ''}"
        elif content_type == 'Event/Special':
            context_desc = f"Special event{f' - {activity}' if activity else ''}"
        elif content_type == 'Just Chatting':
            context_desc = "Just Chatting stream"
        elif content_type == 'Variety/Mixed':
            context_desc = f"Variety stream{f' ({activity})' if activity else ''}"
        else:
            context_desc = "Stream"

        # Build chat reaction section
        chat_section = ""
        if chat_stats:
            spike = chat_stats.get('spike_intensity', 0)
            emotes = chat_stats.get('top_emotes', [])
            viewers = chat_stats.get('avg_viewers', 0)

            chat_section = f"{lang_template['chat_label']}:\n"
            if spike > 0:
                chat_section += f"- Spike intensity: {spike:.1f}x baseline\n"
            if emotes:
                chat_section += f"- Top emotes: {', '.join(emotes[:5])}\n"
            if viewers > 0:
                chat_section += f"- Viewers: {viewers}\n"

        # Get content-type specific examples
        examples = self.CONTENT_EXAMPLES.get(content_type, self.CONTENT_EXAMPLES['Variety/Mixed'])
        example_list = examples.get(language, examples['pl'])
        formatted_examples = [ex.format(streamer=streamer.upper()) for ex in example_list]

        # Build requirements list
        requirements = [
            req.format(max_chars=max_chars, streamer=streamer.upper())
            for req in lang_template['requirements']
        ]

        # Build full prompt
        prompt = f"""{lang_template['instruction'].format(format_type=format_type)}

{lang_template['context_label']}:
- Streamer: {streamer}
- Content type: {context_desc}
- Stream title: "{stream_title}"

{lang_template['moment_label']}:
{transcript[:500]}

{chat_section}

{lang_template['requirements_label']}:
{chr(10).join(f"- {req}" for req in requirements)}

{lang_template['examples_label']}:
{chr(10).join(formatted_examples)}

{lang_template['request'].format(count=num_options)}
"""

        # Call OpenAI API if key available
        if self.api_key:
            try:
                response = openai.ChatCompletion.create(
                    model="gpt-4",
                    messages=[
                        {"role": "system", "content": f"You are a YouTube title expert for streaming content in {language}."},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.8,
                    max_tokens=200
                )

                # Parse response
                titles_text = response.choices[0].message.content.strip()
                titles = [
                    line.strip().lstrip('123456789.-) ')
                    for line in titles_text.split('\n')
                    if line.strip() and not line.strip().startswith('#')
                ]
                return titles[:num_options]

            except Exception as e:
                print(f"⚠️ OpenAI API error: {e}")
                # Fallback to template-based titles

        # Fallback: Generate template-based titles
        return self._generate_fallback_titles(streamer, content_type, language, num_options)

    def _generate_fallback_titles(
        self,
        streamer: str,
        content_type: str,
        language: str,
        num_options: int
    ) -> List[str]:
        """Generate fallback titles when API unavailable."""
        examples = self.CONTENT_EXAMPLES.get(content_type, self.CONTENT_EXAMPLES['Variety/Mixed'])
        template_list = examples.get(language, examples['pl'])

        titles = [template.format(streamer=streamer.upper()) for template in template_list]
        return titles[:num_options]

    def generate_description(
        self,
        stream_context: Dict[str, str],
        transcript: str,
        chat_stats: Optional[Dict] = None
    ) -> str:
        """
        Generate content-aware description.

        Args:
            stream_context: Stream context dictionary
            transcript: Full transcript
            chat_stats: Optional chat statistics

        Returns:
            Generated description
        """
        language = stream_context.get('language', 'pl')
        streamer = stream_context.get('streamer', 'STREAMER')
        content_type = stream_context.get('content_type', 'Variety/Mixed')
        activity = stream_context.get('activity', '')

        # Language-specific templates
        templates = {
            'pl': {
                'intro': f"Najlepszy moment ze streamu {streamer}!",
                'content': f"Content: {content_type}" + (f" - {activity}" if activity else ""),
                'chat': "Czat oszalał na tym momencie!",
                'cta': f"Subskrybuj dla więcej {streamer} highlights! 🔥"
            },
            'en': {
                'intro': f"Best moment from {streamer}'s stream!",
                'content': f"Content: {content_type}" + (f" - {activity}" if activity else ""),
                'chat': "Chat went crazy for this moment!",
                'cta': f"Subscribe for more {streamer} highlights! 🔥"
            },
            'de': {
                'intro': f"Bester Moment von {streamer}'s Stream!",
                'content': f"Content: {content_type}" + (f" - {activity}" if activity else ""),
                'chat': "Chat ist durchgedreht bei diesem Moment!",
                'cta': f"Abonniere für mehr {streamer} Highlights! 🔥"
            }
        }

        template = templates.get(language, templates['pl'])

        description = f"{template['intro']}\n\n"
        description += f"{template['content']}\n\n"

        if chat_stats and chat_stats.get('spike_intensity', 0) > 2.0:
            description += f"{template['chat']}\n\n"

        description += f"{template['cta']}"

        return description


# Example usage
if __name__ == "__main__":
    generator = TitleGenerator()

    # Test context
    context = {
        'streamer': 'H2P_Gucio',
        'content_type': 'Gaming',
        'activity': 'Escape from Tarkov',
        'stream_title': 'heja',
        'language': 'pl'
    }

    chat_stats = {
        'spike_intensity': 5.2,
        'top_emotes': ['KEKW', 'PogChamp', 'LUL'],
        'avg_viewers': 1500
    }

    transcript = "To był absolutnie niesamowity moment! Clutch 1v5 w ostatniej rundzie!"

    print("🧪 Testing Title Generator\n")
    titles = generator.generate_title(context, transcript, chat_stats)
    print("Generated titles:")
    for i, title in enumerate(titles, 1):
        print(f"{i}. {title}")

    print("\n" + "="*50 + "\n")

    desc = generator.generate_description(context, transcript, chat_stats)
    print("Generated description:")
    print(desc)
