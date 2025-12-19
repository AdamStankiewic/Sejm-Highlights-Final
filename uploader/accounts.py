"""Centralized account registry and validation for uploads."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

STATUS_OK = "OK"
STATUS_INVALID_CONFIG = "INVALID_CONFIG"
STATUS_MISSING_CONFIG = STATUS_INVALID_CONFIG  # backwards-compatible alias
STATUS_MISSING_ENV = "MISSING_ENV"
STATUS_MANUAL_REQUIRED = "MANUAL_REQUIRED"


def _normalize_platform(platform: str) -> str:
    if platform.startswith("youtube"):
        return "youtube"
    if platform in {"facebook", "instagram", "tiktok", "meta"}:
        return platform
    return platform


@dataclass
class AccountSpec:
    platform: str
    account_id: str
    config: dict
    status: str = STATUS_OK
    message: str | None = None
    default_for: list[str] = field(default_factory=list)
    is_default: bool = False

    def label(self, kind: str | None = None) -> str:
        badges: list[str] = []
        if kind and kind in self.default_for:
            badges.append("default")
        elif self.is_default:
            badges.append("default")
        badge_str = f" [{' / '.join(badges)}]" if badges else ""
        return f"{self.account_id} ({self.status}){badge_str}"


class AccountRegistry:
    def __init__(
        self,
        accounts_by_platform: Dict[str, Dict[str, AccountSpec]] | None = None,
        *,
        legacy_mode: bool = False,
        raw_config: dict | None = None,
    ):
        self.accounts_by_platform = accounts_by_platform or {}
        self.legacy_mode = legacy_mode
        self.raw_config = raw_config or {}

    def get(self, platform: str, account_id: str) -> AccountSpec | None:
        key = _normalize_platform(platform)
        return (self.accounts_by_platform.get(key) or {}).get(account_id)

    def list(self, platform: str) -> List[AccountSpec]:
        key = _normalize_platform(platform)
        platform_accounts = self.accounts_by_platform.get(key, {})
        if key in {"facebook", "instagram"}:
            return [spec for spec in platform_accounts.values() if spec.platform == key]
        if platform == "meta":
            return list((self.accounts_by_platform.get("facebook") or {}).values()) + list(
                (self.accounts_by_platform.get("instagram") or {}).values()
            )
        if platform.startswith("youtube") and not platform_accounts and self.legacy_mode:
            return [
                AccountSpec(
                    platform="youtube",
                    account_id="default",
                    config={},
                    status=self._legacy_youtube_status(),
                    message="Legacy single-account mode",
                )
            ]
        return list(platform_accounts.values())

    def default_account(self, platform: str, kind: str | None = None) -> Optional[str]:
        options = self.list(platform)
        normalized = _normalize_platform(platform)
        requested_kind = kind
        if normalized == "youtube" and not requested_kind:
            requested_kind = "shorts" if platform == "youtube_shorts" else "long"

        for spec in options:
            if requested_kind and requested_kind in spec.default_for:
                return spec.account_id
        for spec in options:
            if spec.is_default:
                return spec.account_id
        return options[0].account_id if options else None

    def _legacy_youtube_status(self) -> str:
        default_secret = Path("secrets/youtube_client_secret.json")
        if default_secret.exists():
            return STATUS_OK
        return STATUS_MISSING_CONFIG


def _status_worse(current: str, new: str) -> bool:
    priority = {
        STATUS_OK: 0,
        STATUS_INVALID_CONFIG: 1,
        STATUS_MISSING_ENV: 2,
        STATUS_MANUAL_REQUIRED: 3,
    }
    return priority.get(new, 0) > priority.get(current, 0)


def _validate_youtube(account_id: str, cfg: dict) -> AccountSpec:
    status = STATUS_OK
    message = None
    client_secret = Path(cfg.get("client_secret_path") or "secrets/youtube_client_secret.json")
    credential_profile = cfg.get("credential_profile") or account_id or "default"
    if not credential_profile:
        status = STATUS_INVALID_CONFIG
        message = "credential_profile missing"
    if not client_secret.exists():
        status = STATUS_INVALID_CONFIG
        message = "client_secret_path not found"

    default_for = cfg.get("default_for") or []
    if cfg.get("default") is True and "long" not in default_for and "shorts" not in default_for:
        default_for = ["long", "shorts"]

    return AccountSpec(
        platform="youtube",
        account_id=account_id,
        config={
            **cfg,
            "client_secret_path": client_secret,
            "credential_profile": credential_profile,
        },
        status=status,
        message=message,
        default_for=list(default_for),
        is_default=bool(cfg.get("default")),
    )


def _validate_meta(account_id: str, cfg: dict) -> AccountSpec:
    platform = cfg.get("platform") or "facebook"
    status = STATUS_OK
    message = None
    access_token_env = cfg.get("access_token_env")
    if not access_token_env:
        status = STATUS_INVALID_CONFIG
        message = "access_token_env missing"
    elif not os.getenv(access_token_env):
        status = STATUS_MISSING_ENV
        message = f"env {access_token_env} not set"

    if platform == "facebook":
        if not cfg.get("page_id"):
            if _status_worse(status, STATUS_INVALID_CONFIG):
                status = STATUS_INVALID_CONFIG
            message = message or "page_id required"
    elif platform == "instagram":
        if not cfg.get("ig_user_id"):
            if _status_worse(status, STATUS_INVALID_CONFIG):
                status = STATUS_INVALID_CONFIG
            message = message or "ig_user_id required"
        if not cfg.get("page_id"):
            if _status_worse(status, STATUS_INVALID_CONFIG):
                status = STATUS_INVALID_CONFIG
            message = message or "page_id required"

    default_for = cfg.get("default_for") or []
    if cfg.get("default") and not default_for:
        default_for = ["long"]

    return AccountSpec(
        platform=platform,
        account_id=account_id,
        config=cfg,
        status=status,
        message=message,
        default_for=list(default_for),
        is_default=bool(cfg.get("default")),
    )


def _validate_tiktok(account_id: str, cfg: dict) -> AccountSpec:
    status = STATUS_OK
    message = None
    mode = (cfg.get("mode") or "MANUAL_ONLY").upper()
    access_token_env = cfg.get("access_token_env")
    if mode == "OFFICIAL_API":
        if not access_token_env:
            status = STATUS_INVALID_CONFIG
            message = "access_token_env required for OFFICIAL_API"
        elif not os.getenv(access_token_env):
            status = STATUS_MISSING_ENV
            message = f"env {access_token_env} not set"
    else:
        status = STATUS_MANUAL_REQUIRED
        message = "Manual upload required"

    default_for = cfg.get("default_for") or []
    if cfg.get("default") and not default_for:
        default_for = ["shorts"]

    return AccountSpec(
        platform="tiktok",
        account_id=account_id,
        config=cfg,
        status=status,
        message=message,
        default_for=list(default_for),
        is_default=bool(cfg.get("default")),
    )


def load_accounts(path: str | Path = "accounts.yml") -> AccountRegistry:
    config_path = Path(path)
    if not config_path.exists():
        logger.warning("accounts.yml not found -> using legacy single-account mode")
        return AccountRegistry(legacy_mode=True)

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except Exception:  # pragma: no cover - defensive
        logger.exception("Failed to read accounts config from %s", config_path)
        return AccountRegistry(legacy_mode=True)

    accounts_by_platform: Dict[str, Dict[str, AccountSpec]] = {}

    for account_id, cfg in (raw.get("youtube") or {}).items():
        spec = _validate_youtube(account_id, cfg or {})
        accounts_by_platform.setdefault("youtube", {})[account_id] = spec

    for account_id, cfg in (raw.get("meta") or {}).items():
        spec = _validate_meta(account_id, cfg or {})
        accounts_by_platform.setdefault(spec.platform, {})[account_id] = spec

    for account_id, cfg in (raw.get("tiktok") or {}).items():
        spec = _validate_tiktok(account_id, cfg or {})
        accounts_by_platform.setdefault("tiktok", {})[account_id] = spec

    registry = AccountRegistry(accounts_by_platform, raw_config=raw)
    _log_registry_summary(registry)
    return registry


def _log_registry_summary(registry: AccountRegistry):
    for platform, specs in registry.accounts_by_platform.items():
        logger.info(
            "Loaded %s accounts for %s: %s",
            len(specs),
            platform,
            ", ".join(f"{acc.account_id} ({acc.status})" for acc in specs.values()),
        )


def _print_validation_report(registry: AccountRegistry):
    for platform in sorted(registry.accounts_by_platform.keys()):
        print(f"[{platform}]")
        for spec in registry.list(platform):
            msg = f"  - {spec.account_id}: {spec.status}"
            if spec.message:
                msg += f" ({spec.message})"
            print(msg)


if __name__ == "__main__":  # pragma: no cover - manual utility
    import argparse

    parser = argparse.ArgumentParser(description="Validate upload accounts configuration")
    parser.add_argument("--validate-accounts", action="store_true", help="Validate and print account statuses")
    parser.add_argument("--path", default="accounts.yml", help="Path to accounts.yml")
    args = parser.parse_args()

    if args.validate_accounts:
        registry = load_accounts(args.path)
        _print_validation_report(registry)
    else:
        parser.print_help()
