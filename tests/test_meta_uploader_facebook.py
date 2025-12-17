import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from uploader.meta import ManualRequiredUploadError, RetryableUploadError, upload_meta_target
from uploader.models import UploadJob, UploadTarget


class _FailingClient:
    def __init__(self, exc: Exception):
        self.exc = exc

    def api_post(self, *_, **__):
        raise self.exc


def _job_and_target(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_text("video")
    job = UploadJob(file_path=video, title="Title", description="Desc", targets=[])
    target = UploadTarget(platform="facebook", account_id="fb_page_main")
    job.targets.append(target)
    return job, target


def test_facebook_missing_page_id_manual_required(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {"meta": {"fb_page_main": {"platform": "facebook", "access_token_env": "TOKEN_ENV"}}}
    monkeypatch.setenv("TOKEN_ENV", "secret")
    with pytest.raises(ManualRequiredUploadError):
        upload_meta_target(job, target, accounts_config=accounts)


def test_facebook_retryable_error_propagates(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {
        "meta": {
            "fb_page_main": {"platform": "facebook", "page_id": "123", "access_token_env": "TOKEN_ENV"}
        }
    }
    monkeypatch.setenv("TOKEN_ENV", "secret")
    with pytest.raises(RetryableUploadError):
        upload_meta_target(
            job,
            target,
            accounts_config=accounts,
            client_factory=lambda token: _FailingClient(RetryableUploadError("429", status_code=429)),
        )


def test_facebook_permission_manual_required(monkeypatch, tmp_path):
    job, target = _job_and_target(tmp_path)
    accounts = {
        "meta": {
            "fb_page_main": {"platform": "facebook", "page_id": "123", "access_token_env": "TOKEN_ENV"}
        }
    }
    monkeypatch.setenv("TOKEN_ENV", "secret")
    with pytest.raises(ManualRequiredUploadError):
        upload_meta_target(
            job,
            target,
            accounts_config=accounts,
            client_factory=lambda token: _FailingClient(ManualRequiredUploadError("permissions")),
        )

