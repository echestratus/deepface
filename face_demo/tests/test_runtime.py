import sys
from types import SimpleNamespace

import pytest

from deepface.commons import onnx_utils


@pytest.fixture
def fake_ort(monkeypatch):
    class Options:
        def __init__(self):
            self.entries = {}

        def add_session_config_entry(self, key, value):
            self.entries[key] = value

    fake = SimpleNamespace(
        SessionOptions=Options,
        ExecutionMode=SimpleNamespace(ORT_SEQUENTIAL="sequential"),
        get_available_providers=lambda: ["CPUExecutionProvider"],
        InferenceSession=lambda model, **kwargs: kwargs,
    )
    monkeypatch.setitem(sys.modules, "onnxruntime", fake)
    monkeypatch.setattr(onnx_utils.weight_utils, "download_weights_if_necessary", lambda **kwargs: "model.onnx")


def test_thread_limit_reaches_all_onnx_sessions(fake_ort, monkeypatch):
    monkeypatch.setenv("DEEPFACE_ONNX_THREADS", "2")
    result = onnx_utils.build_session("model.onnx", "unused")
    options = result["sess_options"]
    assert options.intra_op_num_threads == 2
    assert options.inter_op_num_threads == 1
    assert options.entries["session.intra_op.allow_spinning"] == "0"
    assert result["providers"] == ["CPUExecutionProvider"]


@pytest.mark.parametrize("value", ["0", "-1", "invalid"])
def test_invalid_thread_limit_fails_clearly(fake_ort, monkeypatch, value):
    monkeypatch.setenv("DEEPFACE_ONNX_THREADS", value)
    with pytest.raises(ValueError, match="positive integer"):
        onnx_utils.build_session("model.onnx", "unused")


def test_without_limit_preserves_existing_library_defaults(fake_ort, monkeypatch):
    monkeypatch.delenv("DEEPFACE_ONNX_THREADS", raising=False)
    options = onnx_utils.build_session("model.onnx", "unused")["sess_options"]
    assert not hasattr(options, "intra_op_num_threads")
