from __future__ import annotations

"""Utilities for deriving public URLs for uploaded content."""


def build_public_url(platform: str, result_id: str, account_cfg: dict | None = None) -> str | None:
    """
    Map platform + result_id (and optional account configuration) to a public URL.

    Returns None when a reliable public URL cannot be derived (e.g., Instagram
    without a permalink, TikTok without a returned share URL).
    """

    if not result_id:
        return None

    normalized = platform.split("_")[0] if "_" in platform else platform

    if normalized == "youtube":
        return f"https://www.youtube.com/watch?v={result_id}"

    if normalized == "facebook":
        return f"https://www.facebook.com/watch/?v={result_id}"

    # Instagram and TikTok often require a permalink/share URL returned from the API.
    # If the caller already has one (e.g., stored in account_cfg or target), it
    # should be provided separately rather than guessed.
    if account_cfg:
        maybe_url = account_cfg.get("result_url") or account_cfg.get("permalink")
        if maybe_url:
            return maybe_url

    return None
