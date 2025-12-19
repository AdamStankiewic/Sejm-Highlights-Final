import yaml
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.accounts import STATUS_MANUAL_REQUIRED, STATUS_MISSING_ENV, STATUS_OK, load_accounts


def test_load_accounts_with_validation(tmp_path, monkeypatch):
    client_secret = tmp_path / "yt_secret.json"
    client_secret.write_text("{}")
    monkeypatch.setenv("META_TOKEN_FB", "token")
    data = {
        "youtube": {
            "yt_main": {
                "credential_profile": "main",
                "client_secret_path": str(client_secret),
                "default_for": ["long"],
            },
            "yt_shorts": {
                "credential_profile": "shorts",
                "client_secret_path": str(client_secret),
                "default_for": ["shorts"],
            },
        },
        "meta": {
            "fb_page": {
                "platform": "facebook",
                "page_id": "123",
                "access_token_env": "META_TOKEN_FB",
            },
            "ig_main": {
                "platform": "instagram",
                "page_id": "123",
                "ig_user_id": "999",
                "access_token_env": "META_TOKEN_IG",
            },
        },
        "tiktok": {
            "tt_manual": {
                "mode": "MANUAL_ONLY",
            },
            "tt_official": {
                "mode": "OFFICIAL_API",
                "access_token_env": "TT_TOKEN",
            },
        },
    }
    path = tmp_path / "accounts.yml"
    path.write_text(yaml.safe_dump(data))

    registry = load_accounts(path)

    yt_long_default = registry.default_account("youtube_long", "long")
    yt_short_default = registry.default_account("youtube_shorts", "shorts")
    assert yt_long_default == "yt_main"
    assert yt_short_default == "yt_shorts"

    fb_spec = registry.get("facebook", "fb_page")
    assert fb_spec and fb_spec.status == STATUS_OK

    ig_spec = registry.get("instagram", "ig_main")
    assert ig_spec and ig_spec.status == STATUS_MISSING_ENV

    tt_manual = registry.get("tiktok", "tt_manual")
    assert tt_manual and tt_manual.status == STATUS_MANUAL_REQUIRED


def test_legacy_mode_defaults(tmp_path):
    registry = load_accounts(tmp_path / "missing.yml")
    assert registry.legacy_mode
    assert registry.default_account("youtube_long") == "default"
    options = registry.list("youtube")
    assert options and options[0].account_id == "default"
