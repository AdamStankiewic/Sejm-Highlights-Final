import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Stub heavy deps (cv2, moviepy) to keep unit test lightweight
class _DummyCascade:
    def detectMultiScale(self, *_, **__):
        return []

class _DummyVideo:
    def __init__(self, *_, **__):
        self._opened = False
    def isOpened(self):
        return False
    def release(self):
        return None
    def get(self, *_):
        return 0
    def set(self, *_, **__):
        return None
    def read(self):
        return False, None

cv2_stub = types.SimpleNamespace(
    CascadeClassifier=lambda *_, **__: _DummyCascade(),
    data=types.SimpleNamespace(haarcascades=""),
    COLOR_BGR2GRAY=0,
    VideoCapture=lambda *_, **__: _DummyVideo(),
    cvtColor=lambda *_, **__: None,
)
sys.modules.setdefault("cv2", cv2_stub)

class _DummyClip:
    def __init__(self, *_, **__):
        self.w, self.h = 1080, 1920
        self.duration = 1
        self.audio = None
    @property
    def size(self):
        return (self.w, self.h)
    def fx(self, func, *args, **kwargs):
        return self
    def subclip(self, *_):
        return self
    def resize(self, *_ , **__):
        return self
    def set_audio(self, *_ , **__):
        return self
    def set_position(self, *_ , **__):
        return self
    def set_start(self, *_ , **__):
        return self
    def set_end(self, *_ , **__):
        return self
    def set_duration(self, *_ , **__):
        return self
    def write_videofile(self, *_ , **__):
        return None
    def close(self):
        return None

editor = types.ModuleType("moviepy.editor")
editor.VideoFileClip = _DummyClip
editor.CompositeVideoClip = _DummyClip
editor.TextClip = _DummyClip
editor.ImageClip = _DummyClip
editor.ColorClip = _DummyClip

video_fx = types.ModuleType("moviepy.video.fx")
resize_mod = types.SimpleNamespace(resize=lambda clip, *_, **__: clip)
crop_mod = types.SimpleNamespace(crop=lambda clip, *_, **__: clip)
video_fx.resize = resize_mod

audio_fx_all = types.SimpleNamespace(time_stretch=lambda audio, factor: audio, speedx=lambda audio, factor: audio)
audio_fx = types.ModuleType("moviepy.audio.fx")
audio_fx.all = audio_fx_all

sys.modules.setdefault("moviepy", types.ModuleType("moviepy"))
sys.modules.setdefault("moviepy.editor", editor)
sys.modules.setdefault("moviepy.video", types.ModuleType("moviepy.video"))
sys.modules.setdefault("moviepy.video.fx", video_fx)
sys.modules.setdefault("moviepy.video.fx.resize", resize_mod)
sys.modules.setdefault("moviepy.video.fx.crop", crop_mod)
sys.modules.setdefault("moviepy.audio", types.ModuleType("moviepy.audio"))
sys.modules.setdefault("moviepy.audio.fx", audio_fx)
sys.modules.setdefault("moviepy.audio.fx.all", audio_fx_all)

from shorts.generator import Segment, ShortsGenerator


def test_generate_returns_empty_when_no_segments(tmp_path: Path):
    gen = ShortsGenerator(output_dir=tmp_path)
    result = gen.generate(Path("/tmp/nonexistent.mp4"), [], template="universal")
    assert result == []


def test_segment_duration_property():
    seg = Segment(start=0, end=5, score=0.5)
    assert seg.duration == 5
