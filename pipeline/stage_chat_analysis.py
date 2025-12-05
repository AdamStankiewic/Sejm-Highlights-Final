"""
Chat Analysis Module - Analyze Twitch/YouTube/Kick chat for viral moments
Tylko dla Stream mode gdy chat.json jest podany

KLUCZOWA CECHA: Chat Lag Compensation
Czat reaguje z opóźnieniem 3-8 sekund po akcji na streamie!
Jeśli spike czatu jest o 15:30, akcja zaczęła się ~15:25.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import numpy as np
from collections import defaultdict


class ChatAnalyzer:
    """
    Analizuj aktywność czatu dla wykrywania viralowych momentów

    Obsługuje formaty:
    - Twitch (TwitchDownloader, chat-downloader)
    - YouTube (yt-dlp, chat-downloader)
    - Kick (podobny do Twitch)
    """

    def __init__(self, chat_config):
        self.config = chat_config
        self.messages = []
        self.baseline_rate = 0
        self.platform = "unknown"

    def load_chat(self, chat_json_path: Path) -> bool:
        """
        Załaduj chat.json (auto-detect platform z formatu)

        Returns:
            True jeśli sukces, False jeśli błąd
        """
        try:
            with open(chat_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Auto-detect platform i normalizuj format
            self.messages = self._normalize_chat_format(data)

            if not self.messages:
                print("   ⚠️ Brak wiadomości w chat.json")
                return False

            # Sort by timestamp
            self.messages.sort(key=lambda x: x['timestamp'])

            # Calculate baseline activity
            if len(self.messages) > 1:
                duration = self.messages[-1]['timestamp'] - self.messages[0]['timestamp']
                self.baseline_rate = len(self.messages) / duration if duration > 0 else 0
            else:
                self.baseline_rate = 0

            print(f"   📨 Załadowano {len(self.messages)} wiadomości czatu ({self.platform})")
            print(f"   📊 Baseline: {self.baseline_rate:.2f} msg/s ({self.baseline_rate * 60:.1f} msg/min)")

            return True

        except Exception as e:
            print(f"   ❌ Błąd ładowania chat.json: {e}")
            return False

    def _normalize_chat_format(self, data: Any) -> List[Dict]:
        """
        Normalizuj różne formaty chat.json do unified format

        Returns:
            Lista: [{'timestamp': float, 'author': str, 'text': str, 'emotes': [str]}]
        """
        messages = []

        # === FORMAT 1: TwitchDownloader (dict z 'comments') ===
        if isinstance(data, dict) and 'comments' in data:
            self.platform = "Twitch (TwitchDownloader)"
            for comment in data['comments']:
                try:
                    timestamp = comment.get('content_offset_seconds', 0)
                    author = comment.get('commenter', {}).get('display_name', 'Unknown')
                    message_data = comment.get('message', {})
                    text = message_data.get('body', '')

                    # Extract Twitch emotes z fragments
                    emotes = self._extract_twitch_emotes(message_data)

                    messages.append({
                        'timestamp': float(timestamp),
                        'author': author,
                        'text': text,
                        'emotes': emotes
                    })
                except Exception:
                    continue

        # === FORMAT 2: YouTube (lista wiadomości) ===
        elif isinstance(data, list) and len(data) > 0:
            first_msg = data[0]

            # YouTube format (yt-dlp, chat-downloader)
            if 'time_in_seconds' in first_msg or 'time_text' in first_msg:
                self.platform = "YouTube"
                for msg in data:
                    try:
                        # Różne klucze dla timestamp
                        timestamp = msg.get('time_in_seconds')
                        if timestamp is None:
                            timestamp = msg.get('timestamp', 0)

                        author = msg.get('author', {})
                        if isinstance(author, dict):
                            author_name = author.get('name', 'Unknown')
                        else:
                            author_name = str(author) if author else 'Unknown'

                        text = msg.get('message', '')

                        # Extract emotes (YouTube emoji)
                        emotes = self._extract_youtube_emotes(text)

                        messages.append({
                            'timestamp': float(timestamp),
                            'author': author_name,
                            'text': text,
                            'emotes': emotes
                        })
                    except Exception:
                        continue

            # Kick format (similar to Twitch)
            elif 'content_offset_seconds' in first_msg or 'created_at' in first_msg:
                self.platform = "Kick"
                for msg in data:
                    try:
                        timestamp = msg.get('content_offset_seconds', msg.get('created_at', 0))
                        author = msg.get('sender', {}).get('username', 'Unknown')
                        text = msg.get('content', '')

                        # Extract Kick emotes
                        emotes = self._extract_kick_emotes(text)

                        messages.append({
                            'timestamp': float(timestamp),
                            'author': author,
                            'text': text,
                            'emotes': emotes
                        })
                    except Exception:
                        continue

        return messages

    def _extract_twitch_emotes(self, message: Dict) -> List[str]:
        """Wyciągnij Twitch emotes z message fragments"""
        emotes = []
        fragments = message.get('fragments', [])

        for frag in fragments:
            # Fragment z emoticon
            if frag.get('emoticon'):
                emote_text = frag.get('text', '')
                if emote_text and emote_text in self.config.emote_weights:
                    emotes.append(emote_text)
            # Zwykły tekst - check for text-based emotes (np. "KEKW")
            else:
                text = frag.get('text', '')
                words = text.split()
                for word in words:
                    if word in self.config.emote_weights:
                        emotes.append(word)

        return emotes

    def _extract_youtube_emotes(self, text: str) -> List[str]:
        """Wyciągnij emotes/emoji z YouTube message"""
        emotes = []

        # Check text-based emotes (lol, lmao, etc)
        text_lower = text.lower()
        words = text_lower.split()
        for word in words:
            if word in self.config.emote_weights:
                emotes.append(word)

        # Check emoji w tekście
        for emoji, weight in self.config.emote_weights.items():
            if emoji in text and len(emoji) <= 2:  # Emoji są 1-2 znaki
                count = text.count(emoji)
                emotes.extend([emoji] * count)

        return emotes

    def _extract_kick_emotes(self, text: str) -> List[str]:
        """Wyciągnij Kick emotes (similar to Twitch)"""
        emotes = []
        words = text.split()

        for word in words:
            if word in self.config.emote_weights:
                emotes.append(word)

        return emotes

    def score_segment(self, t0: float, t1: float) -> Dict[str, Any]:
        """
        Oblicz chat score dla segmentu [t0, t1]

        KLUCZOWE: Chat lag compensation!
        - Czat reaguje 3-8s po akcji
        - Analizujemy okno [t0 - lag_offset, t1]
        - Rozszerzamy pre-window dla context

        Args:
            t0: Start timestamp segmentu (seconds)
            t1: End timestamp segmentu (seconds)

        Returns:
            Dict z scores i metadanymi
        """
        if not self.messages:
            return self._empty_score()

        # === CHAT LAG COMPENSATION ===
        # Czat spike o 15:30 → akcja zaczęła się ~15:25
        lag_offset = self.config.chat_lag_offset  # Default: 5.0s
        window_expansion = self.config.chat_window_expansion  # Default: 3.0s

        # Rozszerzone okno z compensation
        # Pre-window: złap lead-up do momentu
        # Post-window: złap reakcję czatu
        analysis_t0 = t0 - lag_offset - window_expansion
        analysis_t1 = t1 + window_expansion  # Pozwól na reakcję po klipie

        # Get messages w rozszerzonym oknie
        msgs_in_window = [
            m for m in self.messages
            if analysis_t0 <= m['timestamp'] <= analysis_t1
        ]

        # Get messages w oryginalnym oknie (dla comparison)
        msgs_original_window = [
            m for m in self.messages
            if t0 <= m['timestamp'] <= t1
        ]

        if not msgs_in_window:
            return self._empty_score()

        duration = analysis_t1 - analysis_t0
        original_duration = t1 - t0

        msg_rate_expanded = len(msgs_in_window) / duration if duration > 0 else 0
        msg_rate_original = len(msgs_original_window) / original_duration if original_duration > 0 else 0

        # === 1. ACTIVITY SCORE (Spike Detection) ===
        if self.baseline_rate > 0:
            # Use expanded window dla spike detection (złap pre-spike)
            spike_ratio = msg_rate_expanded / self.baseline_rate

            # Log scale dla spike (2x = 0.5, 4x = 0.75, 8x = 1.0)
            activity_score = min(np.log1p(spike_ratio) / 2.5, 1.0)

            spike_detected = spike_ratio >= self.config.spike_threshold
        else:
            activity_score = 0.0
            spike_detected = False

        # === 2. EMOTE SCORE ===
        emote_scores = []
        emote_counts = defaultdict(int)

        for msg in msgs_in_window:
            for emote in msg['emotes']:
                weight = self.config.emote_weights.get(emote, 0)
                emote_scores.append(weight)
                emote_counts[emote] += 1

        if emote_scores:
            # Mean emote weight
            avg_emote_weight = np.mean(emote_scores)
            # Normalize to [0, 1] (weights are typically -3 to +3)
            emote_score = np.clip(avg_emote_weight / 3, 0, 1)
        else:
            emote_score = 0.0

        # === 3. VELOCITY SCORE (Momentum) ===
        # Sprawdź czy aktywność rośnie (good sign)
        mid_point = (analysis_t0 + analysis_t1) / 2
        msgs_first_half = [m for m in msgs_in_window if m['timestamp'] < mid_point]
        msgs_second_half = [m for m in msgs_in_window if m['timestamp'] >= mid_point]

        if len(msgs_first_half) > 0:
            velocity_ratio = len(msgs_second_half) / len(msgs_first_half)
            # Rosnąca trajektoria = good (1.5x+ = max score)
            velocity_score = min((velocity_ratio - 0.5) / 1.0, 1.0)
            velocity_score = max(velocity_score, 0)
        else:
            velocity_score = 0.0

        # === 4. TOTAL CHAT SCORE ===
        total_score = (
            0.50 * activity_score +    # Spike detection najważniejszy
            0.35 * emote_score +       # Emocje widzów
            0.15 * velocity_score      # Momentum
        )

        # === TOP EMOTES (debugging) ===
        top_emotes = sorted(
            emote_counts.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        return {
            'chat_activity': float(activity_score),
            'emote_score': float(emote_score),
            'velocity_score': float(velocity_score),
            'total_score': float(total_score),
            'spike_detected': spike_detected,
            'spike_ratio': float(spike_ratio) if self.baseline_rate > 0 else 0.0,
            'msg_count': len(msgs_in_window),
            'msg_count_original': len(msgs_original_window),
            'msg_rate': float(msg_rate_expanded),
            'msg_rate_original': float(msg_rate_original),
            'top_emotes': [(e, c) for e, c in top_emotes],
            'lag_compensated': True,
            'analysis_window': (analysis_t0, analysis_t1),
            'original_window': (t0, t1)
        }

    def _empty_score(self) -> Dict[str, Any]:
        """Return empty score gdy brak danych czatu"""
        return {
            'chat_activity': 0.0,
            'emote_score': 0.0,
            'velocity_score': 0.0,
            'total_score': 0.0,
            'spike_detected': False,
            'spike_ratio': 0.0,
            'msg_count': 0,
            'msg_count_original': 0,
            'msg_rate': 0.0,
            'msg_rate_original': 0.0,
            'top_emotes': [],
            'lag_compensated': False,
            'analysis_window': (0, 0),
            'original_window': (0, 0)
        }

    def get_spike_moments(self, min_spike_ratio: float = 3.0) -> List[Dict]:
        """
        Znajdź wszystkie spike momenty w czacie (dla debugging)

        Args:
            min_spike_ratio: Minimum spike (3x baseline = major spike)

        Returns:
            Lista spike moments z timestamps
        """
        if not self.messages or self.baseline_rate == 0:
            return []

        spikes = []
        window_size = 30  # 30s window

        # Sliding window przez cały chat
        for i in range(0, int(self.messages[-1]['timestamp']), 10):
            t0 = i
            t1 = i + window_size

            msgs = [m for m in self.messages if t0 <= m['timestamp'] <= t1]
            rate = len(msgs) / window_size

            if rate > 0:
                spike_ratio = rate / self.baseline_rate

                if spike_ratio >= min_spike_ratio:
                    spikes.append({
                        't0': t0,
                        't1': t1,
                        'spike_ratio': spike_ratio,
                        'msg_count': len(msgs),
                        'msg_rate': rate
                    })

        # Merge overlapping spikes
        merged = []
        for spike in spikes:
            if not merged or spike['t0'] > merged[-1]['t1']:
                merged.append(spike)
            else:
                # Extend previous spike
                merged[-1]['t1'] = spike['t1']
                merged[-1]['spike_ratio'] = max(merged[-1]['spike_ratio'], spike['spike_ratio'])

        return merged


# === Test standalone ===
if __name__ == "__main__":
    from pathlib import Path
    from config import ChatConfig

    # Test config
    config = ChatConfig()
    config.chat_lag_offset = 5.0
    config.spike_threshold = 2.0

    analyzer = ChatAnalyzer(config)

    # Test data (fake)
    test_chat_json = {
        "comments": [
            {
                "content_offset_seconds": 100.0,
                "commenter": {"display_name": "User1"},
                "message": {
                    "body": "KEKW this is funny",
                    "fragments": [
                        {"text": "KEKW", "emoticon": {"emoticon_id": "123"}},
                        {"text": " this is funny"}
                    ]
                }
            },
            {
                "content_offset_seconds": 102.0,
                "commenter": {"display_name": "User2"},
                "message": {
                    "body": "OMEGALUL",
                    "fragments": [
                        {"text": "OMEGALUL", "emoticon": {"emoticon_id": "456"}}
                    ]
                }
            }
        ]
    }

    # Save test file
    test_file = Path("test_chat.json")
    with open(test_file, 'w') as f:
        json.dump(test_chat_json, f)

    # Load and test
    if analyzer.load_chat(test_file):
        score = analyzer.score_segment(95.0, 110.0)
        print(f"\n📊 Test score: {score}")

    # Cleanup
    test_file.unlink()
    print("✅ Test completed")
