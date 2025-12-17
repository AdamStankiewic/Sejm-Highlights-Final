"""TikTok upload integration with manual fallbacks."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from .meta import ManualRequiredUploadError, NonRetryableUploadError, RetryableUploadError

logger = logging.getLogger(__name__)


TIKTOK_API_BASE = "https://open.tiktokapis.com"


@dataclass
class TikTokAccount:
    mode: str
    access_token_env: str | None = None
    advertiser_id: str | None = None
    default_caption: str | None = None


class TikTokClient:
    def __init__(self, access_token: str, *, base_url: str = TIKTOK_API_BASE, session: requests.Session | None = None):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def api_post(self, path: str, *, data: dict | None = None, files=None):
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        try:
            response = self.session.post(url, data=data, files=files, headers=headers, timeout=30)
        except requests.Timeout as exc:  # pragma: no cover - network
            raise RetryableUploadError("TikTok API timeout") from exc
        except requests.RequestException as exc:  # pragma: no cover - network
            raise RetryableUploadError("TikTok API connection error") from exc
        return self._handle_response(response)

    def _handle_response(self, response: requests.Response):
        status = response.status_code
        try:
            payload = response.json()
        except ValueError:  # pragma: no cover - defensive
            payload = {"message": response.text}

        if 200 <= status < 300:
            return payload

        message = None
        if isinstance(payload, dict):
            message = payload.get("message") or payload.get("error", {}).get("message")
        message = message or str(payload)
        logger.warning("TikTok API error status=%s message=%s", status, message)
        lowered = message.lower()
        if status == 429 or 500 <= status <= 599:
            raise RetryableUploadError(message, status_code=status)
        if "not supported" in lowered or "permission" in lowered or "access" in lowered:
            raise ManualRequiredUploadError(message, status_code=status)
        if status in {400, 401, 403}:
            raise NonRetryableUploadError(message, status_code=status)
        raise RetryableUploadError(message, status_code=status)


def _resolve_account(target, accounts_config: dict | None) -> TikTokAccount:
    accounts = (accounts_config or {}).get("tiktok", {}) if accounts_config else {}
    if target.account_id not in accounts:
        raise NonRetryableUploadError(
            f"Unknown TikTok account_id={target.account_id}; configure it under accounts.yml -> tiktok.",
            status_code=400,
        )
    cfg = accounts[target.account_id] or {}
    mode = cfg.get("mode") or "MANUAL_ONLY"
    token_env = cfg.get("access_token_env")
    advertiser_id = cfg.get("advertiser_id")
    default_caption = cfg.get("default_caption")
    return TikTokAccount(mode=mode, access_token_env=token_env, advertiser_id=advertiser_id, default_caption=default_caption)


def _manual_required(reason: str):
    logger.warning("TikTok upload not available via official API for this setup -> MANUAL_REQUIRED (%s)", reason)
    return ManualRequiredUploadError(reason)


def upload_tiktok_target(
    job,
    target,
    *,
    accounts_config: dict | None = None,
    client_factory: Callable[[str], TikTokClient] = lambda token: TikTokClient(token),
):
    account = _resolve_account(target, accounts_config)

    if account.mode.upper() == "MANUAL_ONLY":
        raise _manual_required(
            f"TikTok account configured for manual uploads only; upload {job.file_path} manually and set mode=OFFICIAL_API with a token if API access is available"
        )

    if account.mode.upper() != "OFFICIAL_API":
        raise _manual_required(
            f"TikTok account mode unsupported; upload {job.file_path} manually or set mode=OFFICIAL_API/MANUAL_ONLY"
        )

    if not account.access_token_env:
        raise _manual_required(
            f"TikTok account missing access_token_env; upload {job.file_path} manually or set access_token_env to an env var with a valid TikTok API token"
        )

    token = os.getenv(account.access_token_env)
    if not token:
        raise _manual_required(
            f"Missing TikTok access token in env {account.access_token_env}; upload {job.file_path} manually or set the token env var"
        )

    if not job.file_path.exists():
        raise NonRetryableUploadError(f"File not found for TikTok upload: {job.file_path}")

    caption = account.default_caption or job.description or job.title
    client = client_factory(token)
    return upload_tiktok_video(job.file_path, caption, account, client)


def upload_tiktok_video(file_path: Path, caption: str, account: TikTokAccount, client: TikTokClient) -> str:
    """
    Attempt an official TikTok upload. If the API responds that publishing is not
    supported or configuration is insufficient, surface MANUAL_REQUIRED.
    """
    data = {
        "caption": caption,
    }
    if account.advertiser_id:
        data["advertiser_id"] = account.advertiser_id

    logger.info(
        "Uploading TikTok video via official API (advertiser_id=%s, caption_len=%s)",
        account.advertiser_id,
        len(caption) if caption else 0,
    )

    try:
        with open(file_path, "rb") as f:
            files = {"video": f}
            response = client.api_post("/v2/post/publish/video/", data=data, files=files)
    except FileNotFoundError as exc:
        raise NonRetryableUploadError(f"TikTok file missing: {file_path}") from exc

    if isinstance(response, dict):
        data_field = response.get("data") or {}
        video_id = data_field.get("video_id") or response.get("video_id")
        if video_id:
            logger.info("TikTok upload succeeded video_id=%s", video_id)
            return video_id
        message = data_field.get("message") or response.get("message") or "No video_id in TikTok response"
        if "not supported" in message.lower():
            raise ManualRequiredUploadError(
                message + " (TikTok official API not available for this account); please upload manually"
            )
    raise NonRetryableUploadError("TikTok upload failed to return a video_id")

