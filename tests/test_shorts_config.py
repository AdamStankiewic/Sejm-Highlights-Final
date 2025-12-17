import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shorts.config import ShortsConfig


def test_default_template_falls_back_to_template():
    cfg = ShortsConfig(template="gaming")
    assert cfg.default_template == "gaming"


def test_default_template_uses_auto_when_blank():
    cfg = ShortsConfig(template="")
    assert cfg.default_template == "auto"
