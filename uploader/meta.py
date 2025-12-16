from __future__ import annotations

"""Meta (Facebook/Instagram) upload support with manual fallbacks."""

import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict

import requests

logger = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


class RetryableUploadError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class NonRetryableUploadError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class ManualRequiredUploadError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class MetaAccount:
    platform: str
    access_token_env: str
    ig_user_id: str | None = None
    page_id: str | None = None


class MetaClient:
    def __init__(self, access_token: str, *, session: requests.Session | None = None, base_url: str = GRAPH_API_BASE):
        self.access_token = access_token
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()

    def api_post(self, path: str, *, params: dict | None = None, data: dict | None = None, files=None):
        url = self._build_url(path)
        params = self._inject_token(params)
        try:
            response = self.session.post(url, params=params, data=data, files=files, timeout=30)
        except requests.Timeout as exc:  # pragma: no cover - network
            raise RetryableUploadError("Meta API timeout") from exc
        except requests.RequestException as exc:  # pragma: no cover - network
            raise RetryableUploadError("Meta API connection error") from exc
        return self._handle_response(response)

    def api_get(self, path: str, *, params: dict | None = None):
        url = self._build_url(path)
        params = self._inject_token(params)
        try:
            response = self.session.get(url, params=params, timeout=30)
        except requests.Timeout as exc:  # pragma: no cover - network
            raise RetryableUploadError("Meta API timeout") from exc
        except requests.RequestException as exc:  # pragma: no cover - network
            raise RetryableUploadError("Meta API connection error") from exc
        return self._handle_response(response)

    def _inject_token(self, params: dict | None):
        params = params.copy() if params else {}
        params["access_token"] = self.access_token
        return params

    def _build_url(self, path: str) -> str:
        return f"{self.base_url}/{path.lstrip('/')}"

    def _handle_response(self, response: requests.Response):
        status = response.status_code
        try:
            payload = response.json()
        except json.JSONDecodeError:  # pragma: no cover - defensive
            payload = {"message": response.text}

        if 200 <= status < 300:
            return payload

        message = (payload.get("error") or {}).get("message") if isinstance(payload, dict) else None
        message = message or str(payload)
        logger.warning("Meta API error status=%s message=%s", status, message)
        if status in {429} or 500 <= status <= 599:
            raise RetryableUploadError(message, status_code=status)
        if status in {400, 401, 403} and self._looks_like_permission_error(message):
            raise ManualRequiredUploadError(
                message
                + " (permissions required: ensure IG Business/Creator is linked to a Page and token has instagram_content_publish/Page access)"
            )
        raise NonRetryableUploadError(message, status_code=status)

    @staticmethod
    def _looks_like_permission_error(message: str) -> bool:
        lowered = message.lower()
        markers = ["permission", "access", "authorized", "permissions"]
        return any(m in lowered for m in markers)


def _resolve_account(target, accounts_config: Dict) -> MetaAccount:
    meta_accounts = (accounts_config or {}).get("meta", {}) if accounts_config else {}
    if target.account_id not in meta_accounts:
        raise NonRetryableUploadError(
            f"Unknown Meta account_id={target.account_id}; configure it under accounts.yml -> meta.", status_code=400
        )
    cfg = meta_accounts[target.account_id]
    account_platform = cfg.get("platform") or target.platform
    token_env = cfg.get("access_token_env")
    if not token_env:
        raise ManualRequiredUploadError("Meta account missing access_token_env; cannot upload via API")
    ig_user_id = cfg.get("ig_user_id")
    page_id = cfg.get("page_id")
    return MetaAccount(platform=account_platform, access_token_env=token_env, ig_user_id=ig_user_id, page_id=page_id)


def _get_token(account: MetaAccount) -> str:
    token = os.environ.get(account.access_token_env)
    if not token:
        raise ManualRequiredUploadError(
            f"Missing access token for Meta account (env {account.access_token_env}). Provide a valid token to continue."
        )
    return token


def upload_meta_target(
    job, target, *, accounts_config: dict | None = None, client_factory: Callable[[str], MetaClient] | None = None
) -> str:
    account = _resolve_account(target, accounts_config)
    if account.platform != target.platform:
        raise NonRetryableUploadError(
            f"Target platform {target.platform} does not match account platform {account.platform}", status_code=400
        )
    token = _get_token(account)
    client = client_factory(token) if client_factory else MetaClient(token)

    caption = f"{job.title}\n{job.description}" if job.description else job.title
    if target.platform == "instagram":
        if not account.ig_user_id:
            raise ManualRequiredUploadError(
                "Instagram account missing ig_user_id. Ensure the IG Business/Creator account is linked to a Page."
            )
        logger.info(
            "Uploading Instagram reel account_id=%s ig_user_id=%s", target.account_id, account.ig_user_id
        )
        media_id = publish_instagram_reel(client, job.file_path, caption, account.ig_user_id)
        logger.info("Instagram reel published media_id=%s", media_id)
        return media_id

    if target.platform == "facebook":
        if not account.page_id:
            raise ManualRequiredUploadError("Facebook account missing page_id for upload")
        logger.info("Uploading Facebook reel account_id=%s page_id=%s", target.account_id, account.page_id)
        video_id = publish_facebook_reel(client, job.file_path, caption, account.page_id)
        logger.info("Facebook reel published video_id=%s", video_id)
        return video_id

    raise NonRetryableUploadError(f"Unsupported Meta platform: {target.platform}", status_code=400)


def publish_instagram_reel(client: MetaClient, file_path: Path, caption: str, ig_user_id: str) -> str:
    if not file_path.exists():
        raise NonRetryableUploadError(f"File not found for Instagram upload: {file_path}")

    with open(file_path, "rb") as video_file:
        creation = client.api_post(
            f"{ig_user_id}/media",
            data={"caption": caption, "media_type": "REELS"},
            files={"video": video_file},
        )
    creation_id = creation.get("id")
    if not creation_id:
        raise NonRetryableUploadError("Instagram media creation failed: missing id")

    start = time.monotonic()
    timeout = 600
    while True:
        status_resp = client.api_get(f"{creation_id}", params={"fields": "status,status_code"})
        status_code = status_resp.get("status_code") or status_resp.get("status")
        if status_code in {"FINISHED", "READY"}:
            break
        if status_code in {"ERROR", "FAILED"}:
            raise NonRetryableUploadError(f"Instagram media processing failed: {status_code}")
        if time.monotonic() - start > timeout:
            raise RetryableUploadError("Instagram media processing timeout", status_code=504)
        time.sleep(5)

    publish_resp = client.api_post(f"{ig_user_id}/media_publish", data={"creation_id": creation_id})
    media_id = publish_resp.get("id")
    if not media_id:
        raise NonRetryableUploadError("Instagram publish failed: missing media id")
    return media_id


def publish_facebook_reel(client: MetaClient, file_path: Path, description: str, page_id: str) -> str:
    if not file_path.exists():
        raise NonRetryableUploadError(f"File not found for Facebook upload: {file_path}")
    with open(file_path, "rb") as video_file:
        upload_resp = client.api_post(
            f"{page_id}/videos",
            data={"description": description},
            files={"file": video_file},
        )
    video_id = upload_resp.get("id")
    if not video_id:
        raise NonRetryableUploadError("Facebook reel upload failed: missing video id")
    return video_id

