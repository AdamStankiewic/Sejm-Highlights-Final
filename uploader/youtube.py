from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
DEFAULT_SECRETS_PATH = Path("secrets/youtube_client_secret.json")


class YouTubeUploadError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class YouTubeAccount:
    credential_profile: str
    default_privacy: str = "unlisted"
    category_id: Optional[str] = None
    tags: list[str] | None = None
    client_secret_path: Path = DEFAULT_SECRETS_PATH


class _Progress:
    def __init__(self, total: int):
        self.total = max(total, 1)
        self.last_logged = 0

    def maybe_log(self, uploaded: int):
        percent = int(uploaded / self.total * 100)
        if percent // 5 > self.last_logged // 5:
            self.last_logged = percent
            logger.info("YouTube upload progress: %s%%", percent)


def get_youtube_client(credential_profile: str, client_secret_path: Path | str = DEFAULT_SECRETS_PATH):
    token_path = Path(f"secrets/youtube_token_{credential_profile}.json")
    creds: Credentials | None = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), SCOPES)
        creds = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as token_file:
            token_file.write(creds.to_json())
        logger.info("Saved new YouTube token at %s", token_path)
    return build("youtube", "v3", credentials=creds)


def _build_video_body(
    *,
    title: str,
    description: str,
    tags: list[str] | None,
    category_id: str | None,
    privacy_status: str,
    publish_at_iso: str | None,
):
    body = {
        "snippet": {
            "title": title,
            "description": description,
        },
        "status": {"privacyStatus": privacy_status},
    }
    if tags:
        body["snippet"]["tags"] = list(dict.fromkeys(tags))
    if category_id:
        body["snippet"]["categoryId"] = category_id
    if publish_at_iso:
        body["status"]["publishAt"] = publish_at_iso
        body["status"]["selfDeclaredMadeForKids"] = False
    return body


def _append_shorts_metadata(description: str, tags: Iterable[str]) -> tuple[str, list[str]]:
    updated_description = description if "#shorts" in description.lower() else f"{description}\n#shorts"
    tag_list = list(tags)
    if "shorts" not in {t.lower() for t in tag_list}:
        tag_list.append("shorts")
    return updated_description, tag_list


def upload_video(
    youtube,
    file_path: Path,
    *,
    title: str,
    description: str,
    tags: list[str] | None,
    category_id: str | None,
    privacy_status: str,
    publish_at_iso: str | None = None,
    chunk_retries: int = 3,
) -> str:
    if publish_at_iso:
        try:
            datetime.fromisoformat(publish_at_iso)
        except Exception as exc:  # pragma: no cover - defensive
            raise ValueError("publish_at_iso must be ISO datetime string") from exc

    total_size = file_path.stat().st_size
    progress = _Progress(total_size)

    media = MediaFileUpload(str(file_path), chunksize=8 * 1024 * 1024, resumable=True)
    body = _build_video_body(
        title=title,
        description=description,
        tags=tags,
        category_id=category_id,
        privacy_status=privacy_status,
        publish_at_iso=publish_at_iso,
    )

    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    attempts = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                progress.maybe_log(status.resumable_progress)
        except HttpError as exc:  # pragma: no cover - network handling
            attempts += 1
            status_code = getattr(exc, "status_code", None) or getattr(exc.resp, "status", None)
            logger.warning("YouTube chunk error (status=%s): %s", status_code, exc)
            if attempts > chunk_retries or status_code not in {429, 500, 502, 503, 504}:
                raise YouTubeUploadError(str(exc), status_code=status_code) from exc
            sleep_time = min(2 ** attempts, 30)
            time.sleep(sleep_time)
            continue
    if not response or "id" not in response:
        raise YouTubeUploadError("Missing video id in upload response")
    logger.info("YouTube upload finished video_id=%s", response["id"])
    return response["id"]


def upload_thumbnail(youtube, video_id: str, thumbnail_path: Path):
    if not thumbnail_path.exists():
        raise FileNotFoundError(f"Thumbnail not found: {thumbnail_path}")
    request = youtube.thumbnails().set(videoId=video_id, media_body=str(thumbnail_path))
    request.execute()
    logger.info("YouTube thumbnail set for %s", video_id)


def _resolve_account(account_id: str, accounts_config: dict | None) -> YouTubeAccount:
    youtube_accounts = (accounts_config or {}).get("youtube", {}) if accounts_config else {}
    account_cfg = youtube_accounts.get(account_id, {})
    credential_profile = account_cfg.get("credential_profile") or account_id or "default"
    default_privacy = account_cfg.get("default_privacy", "unlisted")
    category_id = account_cfg.get("category_id")
    tags = account_cfg.get("tags") or []
    client_secret_path = Path(account_cfg.get("client_secret_path") or DEFAULT_SECRETS_PATH)
    return YouTubeAccount(
        credential_profile=credential_profile,
        default_privacy=default_privacy,
        category_id=str(category_id) if category_id is not None else None,
        tags=list(tags),
        client_secret_path=client_secret_path,
    )


def upload_target(job, target, accounts_config: dict | None = None, youtube_client=None) -> str:
    account = _resolve_account(target.account_id, accounts_config)
    youtube = youtube_client or get_youtube_client(account.credential_profile, account.client_secret_path)

    is_short = (job.kind or "").lower() == "short" or target.platform == "youtube_shorts"
    base_tags = list(account.tags or []) + list(job.tags or [])
    description = job.description
    if is_short:
        description, base_tags = _append_shorts_metadata(description, base_tags)

    publish_at_iso = None
    privacy_status = account.default_privacy
    if target.mode == "NATIVE_SCHEDULE":
        if not target.scheduled_at:
            raise ValueError("scheduled_at is required for NATIVE_SCHEDULE")
        if target.scheduled_at.tzinfo is None:
            raise ValueError("scheduled_at must be timezone-aware for YouTube scheduling")
        publish_at_iso = target.scheduled_at.astimezone(ZoneInfo("UTC")).isoformat()
        privacy_status = "private"

    video_id = upload_video(
        youtube,
        job.file_path,
        title=job.title,
        description=description,
        tags=base_tags,
        category_id=account.category_id,
        privacy_status=privacy_status,
        publish_at_iso=publish_at_iso,
    )

    if job.thumbnail_path:
        try:
            upload_thumbnail(youtube, video_id, job.thumbnail_path)
        except Exception as exc:  # pragma: no cover - best effort
            logger.warning("Thumbnail upload failed for %s: %s", video_id, exc)

    if publish_at_iso:
        logger.info("Uploaded video_id=%s with publishAt=%s", video_id, publish_at_iso)
    else:
        logger.info("Uploaded video_id=%s for immediate publish (privacy=%s)", video_id, privacy_status)
    return video_id
