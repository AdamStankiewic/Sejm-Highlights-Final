"""
Lexical/NLP feature extraction (keywords, entities)
Part of Highlights AI Platform - Core Engine
"""
import csv
from pathlib import Path
from typing import Dict, List, Any, Optional

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


class LexicalFeatureExtractor:
    """Extract lexical and NLP features from transcripts"""

    def __init__(
        self,
        keywords_file: Optional[str] = None,
        spacy_model: str = "pl_core_news_lg",
        use_spacy: bool = True
    ):
        self.keywords_db = {}
        self.nlp = None

        if keywords_file:
            self._load_keywords(keywords_file)

        if use_spacy and SPACY_AVAILABLE:
            self._load_spacy(spacy_model)

    def _load_keywords(self, keywords_file: str):
        """Load keywords database from CSV"""
        keywords_path = Path(keywords_file)

        if not keywords_path.exists():
            return

        with open(keywords_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['token'].startswith('#'):
                    continue

                token = row['token'].lower().strip()
                weight = float(row['weight'])
                category = row['category'].strip()

                self.keywords_db[token] = {
                    'weight': weight,
                    'category': category
                }

    def _load_spacy(self, model_name: str):
        """Load spaCy model for NER"""
        try:
            self.nlp = spacy.load(model_name)
        except OSError:
            # Model not installed
            self.nlp = None

    def extract_for_segments(self, segments: List[Dict]) -> List[Dict]:
        """
        Extract lexical features for all segments

        Args:
            segments: List of segment dicts with transcript

        Returns:
            Segments with added lexical features
        """
        enriched = []
        for seg in segments:
            features = self._extract_segment_features(seg)
            enriched.append({**seg, 'lexical_features': features})

        return enriched

    def _extract_segment_features(self, segment: Dict) -> Dict[str, Any]:
        """Extract lexical features for single segment"""

        transcript = segment.get('transcript', '').lower()

        if not transcript:
            return {
                'keyword_score': 0.0,
                'matched_keywords': [],
                'entity_density': 0.0,
                'has_question': False
            }

        # Keyword matching
        keyword_score = 0.0
        matched_keywords = []

        for token, data in self.keywords_db.items():
            if token in transcript:
                keyword_score += data['weight']
                matched_keywords.append({
                    'token': token,
                    'weight': data['weight'],
                    'category': data['category']
                })

        # Entity density (if spaCy available)
        entity_density = 0.0
        entities = []

        if self.nlp:
            doc = self.nlp(segment.get('transcript', ''))
            entities = [
                {'text': ent.text, 'label': ent.label_}
                for ent in doc.ents
                if ent.label_ in ['PER', 'ORG', 'LOC', 'GPE']
            ]
            entity_density = len(entities) / len(doc) if len(doc) > 0 else 0.0

        # Question detection
        has_question = '?' in segment.get('transcript', '')

        return {
            'keyword_score': float(keyword_score),
            'matched_keywords': matched_keywords[:5],
            'entity_density': float(entity_density),
            'entities': entities[:3],
            'has_question': has_question
        }

    def match_keywords(self, text: str) -> List[Dict]:
        """Match keywords in text and return matches with weights"""
        text_lower = text.lower()
        matches = []

        for token, data in self.keywords_db.items():
            if token in text_lower:
                matches.append({
                    'token': token,
                    'weight': data['weight'],
                    'category': data['category']
                })

        return sorted(matches, key=lambda x: x['weight'], reverse=True)
