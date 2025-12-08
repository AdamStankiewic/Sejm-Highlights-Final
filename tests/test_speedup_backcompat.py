"""Regresyjny test dla apply_speedup bez metody speedx w AudioFileClip."""

import numpy as np
import pytest

moviepy = pytest.importorskip("moviepy")
from moviepy.audio.AudioClip import AudioArrayClip
from moviepy.video.VideoClip import ColorClip

from utils.video import apply_speedup


def test_apply_speedup_handles_missing_speedx_audio():
    """Powinno zwrócić klip z audio nawet gdy speedx nie istnieje na AudioClip."""

    fps = 44100
    samples = np.zeros(int(fps * 1), dtype=np.float32)
    audio = AudioArrayClip(samples.reshape(-1, 1), fps=fps)
    clip = ColorClip((64, 64), color=(255, 0, 0), duration=1).set_audio(audio)

    sped = apply_speedup(clip, 1.2)

    assert sped.audio is not None
    assert sped.duration > 0
