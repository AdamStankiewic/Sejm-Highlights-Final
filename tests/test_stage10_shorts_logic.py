import sys
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

cv2_stub = types.SimpleNamespace(
    COLOR_BGR2RGB=0,
    CascadeClassifier=lambda *_, **__: types.SimpleNamespace(detectMultiScale=lambda *__, **___: []),
    data=types.SimpleNamespace(haarcascades=""),
    imread=lambda *_, **__: np.zeros((100, 100, 3), dtype=np.uint8),
    cvtColor=lambda frame, *_: frame,
)
sys.modules.setdefault("cv2", cv2_stub)

# Stub moviepy to avoid heavy imports during unit tests
editor_mod = types.ModuleType("moviepy.editor")

class _DummyClip:
    def __init__(self, *args, **kwargs):
        self.w = kwargs.get("w", 1080)
        self.h = kwargs.get("h", 1920)
        self.duration = kwargs.get("duration", 1)

    def set_duration(self, *_):
        return self

    def resize(self, *_ , **__):
        return self

    def fx(self, *_ , **__):
        return self

editor_mod.ColorClip = _DummyClip
editor_mod.CompositeVideoClip = _DummyClip
editor_mod.VideoClip = _DummyClip
editor_mod.VideoFileClip = _DummyClip
editor_mod.TextClip = _DummyClip

moviepy_mod = sys.modules.setdefault("moviepy", types.ModuleType("moviepy"))
moviepy_mod.ColorClip = _DummyClip
moviepy_mod.VideoClip = _DummyClip
moviepy_mod.VideoFileClip = _DummyClip
sys.modules.setdefault("moviepy.editor", editor_mod)
sys.modules.setdefault("moviepy.video", types.ModuleType("moviepy.video"))

video_fx = types.ModuleType("moviepy.video.fx")
video_fx_all = types.ModuleType("moviepy.video.fx.all")
video_fx_all.speedx = lambda clip, *_ , **__: clip
video_fx_all.crop = lambda clip, *_ , **__: clip
video_fx.MultiplySpeed = lambda clip, factor=1.0: clip
video_fx.resize = lambda clip, *_ , **__: clip

sys.modules.setdefault("moviepy.video.fx", video_fx)
sys.modules.setdefault("moviepy.video.fx.all", video_fx_all)
sys.modules.setdefault("moviepy.video.fx.resize", video_fx)
sys.modules.setdefault("moviepy.video.fx.crop", video_fx)
audio_mod = types.ModuleType("moviepy.audio")
audio_clip_mod = types.ModuleType("moviepy.audio.AudioClip")

class _DummyAudioClip:
    pass

audio_clip_mod.AudioClip = _DummyAudioClip
audio_mod.AudioClip = _DummyAudioClip

sys.modules.setdefault("moviepy.audio", audio_mod)
sys.modules.setdefault("moviepy.audio.AudioClip", audio_clip_mod)
sys.modules.setdefault("moviepy.audio.fx", types.ModuleType("moviepy.audio.fx"))
sys.modules.setdefault("moviepy.audio.fx.all", types.ModuleType("moviepy.audio.fx.all"))

# Stub pipeline dependency fan-out to avoid importing heavy stages
dummy_modules = {
    "pipeline.processor": "PipelineProcessor",
    "pipeline.stage_01_ingest": "IngestStage",
    "pipeline.stage_02_vad": "VADStage",
    "pipeline.stage_03_transcribe": "TranscribeStage",
    "pipeline.stage_04_features": "FeaturesStage",
    "pipeline.stage_05_scoring_gpt": "ScoringStage",
    "pipeline.stage_06_selection": "SelectionStage",
    "pipeline.stage_07_export": "ExportStage",
    "pipeline.stage_09_youtube": "YouTubeStage",
}

for module_name, attr_name in dummy_modules.items():
    mod = types.ModuleType(module_name)
    setattr(mod, attr_name, type(attr_name, (), {}))
    sys.modules.setdefault(module_name, mod)

from pipeline.stage_10_shorts import ShortsStage
from shorts.config import ShortsConfig


class DummyConfig:
    def __init__(self, face_detection=True):
        self.shorts = ShortsConfig(face_detection=face_detection)


class FakeCV2:
    COLOR_BGR2RGB = 0

    @staticmethod
    def imread(path):
        return np.zeros((100, 100, 3), dtype=np.uint8)

    @staticmethod
    def cvtColor(frame, flag):
        return frame


class FakeDetection:
    def __init__(self, xmin, ymin, width, height, score=0.9):
        bbox = types.SimpleNamespace(xmin=xmin, ymin=ymin, width=width, height=height)
        location_data = types.SimpleNamespace(relative_bounding_box=bbox)
        self.location_data = location_data
        self.score = [score]


class FakeDetector:
    def __init__(self, detections_per_call):
        self.detections_per_call = detections_per_call
        self.call_idx = 0

    def process(self, frame):
        idx = min(self.call_idx, len(self.detections_per_call) - 1)
        detections = self.detections_per_call[idx]
        self.call_idx += 1
        return types.SimpleNamespace(detections=detections)


@pytest.fixture
def stage(monkeypatch):
    monkeypatch.setattr(ShortsStage, "_check_ffmpeg", lambda self: None)
    monkeypatch.setattr(ShortsStage, "_init_gpt", lambda self: None)
    monkeypatch.setattr(ShortsStage, "_init_face_detection", lambda self: None)
    cfg = DummyConfig(face_detection=True)
    stg = ShortsStage(cfg)
    stg.cv2 = FakeCV2()
    return stg


@pytest.fixture
def no_subprocess_run(monkeypatch):
    def _fake_run(*args, **kwargs):
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr("pipeline.stage_10_shorts.subprocess.run", _fake_run)


def test_classify_to_side_zone(stage):
    assert stage._classify_to_side_zone({"x": 5, "y": 80, "w": 10, "h": 10}, 100, 100) == "left_bottom"
    assert stage._classify_to_side_zone({"x": 60, "y": 60, "w": 10, "h": 10}, 100, 100) == "center_ignored"
    assert stage._classify_to_side_zone({"x": 80, "y": 5, "w": 10, "h": 10}, 100, 100) == "right_top"

    # Boundary: exactly at 1/3 should be treated as center_ignored
    assert stage._classify_to_side_zone({"x": 33, "y": 10, "w": 1, "h": 1}, 100, 100) == "center_ignored"


@pytest.mark.usefixtures("no_subprocess_run")
def test_detect_webcam_region_left_bottom(stage):
    detections = [[FakeDetection(0.05, 0.75, 0.1, 0.1)] for _ in range(5)]
    stage.face_detector = FakeDetector(detections)
    result = stage._detect_webcam_region(Path("input.mp4"), start_time=0.0, duration=5.0, num_samples=5)
    assert result["type"] == "face_detected"
    assert result["zone"] == "left_bottom"
    assert pytest.approx(result["detection_rate"], rel=1e-3) == 1.0


@pytest.mark.usefixtures("no_subprocess_run")
def test_detect_webcam_region_right_top(stage):
    detections = [[FakeDetection(0.8, 0.1, 0.1, 0.1)] for _ in range(5)]
    stage.face_detector = FakeDetector(detections)
    result = stage._detect_webcam_region(Path("input.mp4"), start_time=0.0, duration=5.0, num_samples=5)
    assert result["zone"] == "right_top"
    assert result["type"] == "face_detected"


@pytest.mark.usefixtures("no_subprocess_run")
def test_detect_webcam_region_none(stage):
    detections = [[] for _ in range(5)]
    stage.face_detector = FakeDetector(detections)
    result = stage._detect_webcam_region(Path("input.mp4"), start_time=0.0, duration=5.0, num_samples=5)
    assert result["type"] == "none"
    assert result["zone"] is None
    assert result["detection_rate"] == 0.0


@pytest.mark.usefixtures("no_subprocess_run")
def test_detect_webcam_region_mixed_consensus(stage):
    # Two left_bottom, one right_bottom, two empty → dominant left_bottom with 0.4 rate
    detections = [
        [FakeDetection(0.05, 0.8, 0.1, 0.1)],
        [FakeDetection(0.05, 0.82, 0.1, 0.1)],
        [FakeDetection(0.8, 0.8, 0.1, 0.1)],
        [],
        [],
    ]
    stage.face_detector = FakeDetector(detections)
    result = stage._detect_webcam_region(Path("input.mp4"), start_time=0.0, duration=5.0, num_samples=5)
    assert result["zone"] == "left_bottom"
    assert result["type"] == "face_detected"
    assert pytest.approx(result["detection_rate"], rel=1e-3) == 0.4


def test_select_template_manual_override(stage):
    result = stage._select_template({"zone": "left_bottom", "detection_rate": 1.0, "type": "face_detected"}, "big_face_reaction")
    assert result == "big_face_reaction"


def test_select_template_low_confidence(stage):
    det = {"zone": "left_bottom", "detection_rate": 0.2, "type": "face_detected"}
    assert stage._select_template(det) == "simple_game_only"


def test_select_template_zone_based(stage):
    assert stage._select_template({"zone": "left_bottom", "detection_rate": 0.8, "type": "face_detected"}) == "game_top_face_bottom_bar"
    assert stage._select_template({"zone": "right_top", "detection_rate": 0.9, "type": "face_detected"}) == "full_game_with_floating_face"
    assert stage._select_template({"zone": "center_ignored", "detection_rate": 0.9, "type": "face_detected"}) == "simple_game_only"


@pytest.mark.usefixtures("no_subprocess_run")
def test_global_template_override_skip_detection(monkeypatch):
    cfg = DummyConfig(face_detection=True)
    cfg.shorts.template = "simple_game_only"

    monkeypatch.setattr(ShortsStage, "_check_ffmpeg", lambda self: None)
    monkeypatch.setattr(ShortsStage, "_init_gpt", lambda self: None)
    monkeypatch.setattr(ShortsStage, "_init_face_detection", lambda self: None)

    stage = ShortsStage(cfg)
    stage.cv2 = FakeCV2()

    detection = {"type": "none"}
    assert stage._select_template(detection, manual_override="simple_game_only") == "simple_game_only"
