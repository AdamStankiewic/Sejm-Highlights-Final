"""
Politics module configuration
Part of Highlights AI Platform - Politics Module (Sejm)
"""
from dataclasses import dataclass, field
from typing import Dict, Optional
from pathlib import Path

from shared.config_base import BaseModuleConfig


@dataclass
class PoliticsConfig(BaseModuleConfig):
    """
    Configuration for political content analysis.
    Extends base config with Sejm-specific settings.
    """

    # GPT-based semantic scoring
    use_gpt_scoring: bool = True
    gpt_model: str = "gpt-4o-mini"
    gpt_temperature: float = 0.3
    prefilter_top_n: int = 100

    # Keywords file
    keywords_file: str = "models/keywords.csv"

    # Interest labels with weights (for GPT semantic scoring)
    interest_labels: Dict[str, float] = field(default_factory=lambda: {
        "ostra polemika i wymiana oskarżeń między posłami": 2.2,
        "emocjonalna lub podniesiona wypowiedź": 1.7,
        "kontrowersyjne stwierdzenie lub oskarżenie": 2.0,
        "pytanie retoryczne lub zaczepka": 1.5,
        "konkretne fakty liczby i dane": 1.3,
        "humor sarkazm lub memiczny moment": 1.8,
        "przerwanie przemówienia lub reakcja sali": 1.6,
        "formalna procedura sejmowa": -2.5,
        "podziękowania i grzecznościowe formuły": -2.0,
        "odczytywanie regulaminu": -3.0
    })

    # Scoring weights
    acoustic_weight: float = 0.15
    lexical_weight: float = 0.25
    semantic_weight: float = 0.60

    # Selection
    target_duration: float = 900.0  # 15 minutes highlights
    min_clip_duration: float = 90.0
    max_clip_duration: float = 180.0
    clip_gap_min: float = 60.0  # Min gap between clips

    # Polish-specific
    language: str = "pl"
    whisper_model: str = "small"
    initial_prompt: str = "To jest debata sejmowa w języku polskim. Posłowie dyskutują o polityce."

    # spaCy for NER
    spacy_model: str = "pl_core_news_lg"

    def get_interest_labels_list(self) -> list:
        """Get interest labels as list for GPT prompt"""
        return list(self.interest_labels.keys())

    def get_label_weight(self, label: str) -> float:
        """Get weight for specific label"""
        return self.interest_labels.get(label, 0.0)
