import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.links import build_public_url


def test_build_youtube_url():
    assert build_public_url("youtube", "abc123") == "https://www.youtube.com/watch?v=abc123"
    assert build_public_url("youtube_shorts", "short") == "https://www.youtube.com/watch?v=short"


def test_build_facebook_url():
    assert build_public_url("facebook", "999") == "https://www.facebook.com/watch/?v=999"


def test_returns_none_when_unknown_or_missing():
    assert build_public_url("instagram", "id") is None
    assert build_public_url("tiktok", "id") is None
    assert build_public_url("youtube", "") is None


def test_prefers_provided_result_url():
    cfg = {"result_url": "https://example.com/custom"}
    assert build_public_url("instagram", "mid", cfg) == "https://example.com/custom"
