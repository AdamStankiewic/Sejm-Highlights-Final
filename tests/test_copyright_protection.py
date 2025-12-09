import pytest
from pathlib import Path

moviepy = pytest.importorskip("moviepy")
from moviepy.editor import ColorClip, AudioClip

from utils.copyright_protection import CopyrightProtector, CopyrightSettings


def _make_dummy_video(tmp_path: Path) -> Path:
    audio = AudioClip(lambda t: 0 * t, duration=1, fps=44100)
    clip = ColorClip(size=(2, 2), color=(0, 0, 0), duration=1).set_audio(audio)
    out = tmp_path / "dummy.mp4"
    clip.write_videofile(out.as_posix(), fps=24, codec="libx264", audio_codec="aac", verbose=False, logger=None)
    clip.close()
    audio.close()
    return out


def test_scan_skipped_when_disabled(tmp_path):
    video = _make_dummy_video(tmp_path)
    protector = CopyrightProtector(CopyrightSettings(enable_protection=False))
    path, status = protector.scan_and_fix(video.as_posix())
    assert Path(path) == video
    assert status == "skipped"


def test_scan_clean_when_no_model(tmp_path, monkeypatch):
    video = _make_dummy_video(tmp_path)
    protector = CopyrightProtector(CopyrightSettings(enable_protection=True))
    monkeypatch.setattr(protector, "_load_model", lambda: None)
    path, status = protector.scan_and_fix(video.as_posix())
    assert Path(path) == video
    assert status == "clean"
