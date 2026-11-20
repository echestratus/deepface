"""Opt in with FACE_DEMO_MODEL_TESTS=1 after preparing the model cache."""

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

from face_demo.config import settings
from face_demo.engine import FaceEngine, FaceError, cosine_distance, decode_image

pytestmark = pytest.mark.skipif(os.environ.get("FACE_DEMO_MODEL_TESTS") != "1", reason="Set FACE_DEMO_MODEL_TESTS=1 for real CPU model tests")
DATASET = Path(__file__).resolve().parents[2] / "tests" / "unit" / "dataset"


@pytest.fixture(scope="module")
def engine():
    instance = FaceEngine()
    instance.load()
    return instance


def test_real_same_and_different_person(engine):
    first = engine.extract(decode_image((DATASET / "img1.jpg").read_bytes()), live=False)
    same = engine.extract(decode_image((DATASET / "img2.jpg").read_bytes()), live=False)
    other = engine.extract(decode_image((DATASET / "img20.jpg").read_bytes()), live=False)
    assert cosine_distance(first.embedding, same.embedding) < settings.threshold
    assert cosine_distance(first.embedding, other.embedding) > settings.threshold
    assert all(model.model.get_providers() == ["CPUExecutionProvider"] for model in engine.models)
    assert all(model.model.get_session_options().intra_op_num_threads == settings.threads for model in engine.models)


def test_real_no_face(engine):
    with pytest.raises(FaceError) as err:
        engine.extract(np.zeros((480, 640, 3), dtype=np.uint8), live=True)
    assert err.value.code == "no_face"


def test_real_multiple_faces(engine):
    image = decode_image((DATASET / "img1.jpg").read_bytes())
    image = cv2.resize(image, (240, 300))
    composite = np.concatenate([image, np.zeros((300, 50, 3), dtype=np.uint8), image], axis=1)
    with pytest.raises(FaceError) as err:
        engine.extract(composite, live=True)
    assert err.value.code == "multiple_faces"


def test_spoof_filter_is_loaded_on_cpu(engine):
    assert engine.spoof_model is not None
    for model in (engine.spoof_model.first_model, engine.spoof_model.second_model):
        assert model.get_providers() == ["CPUExecutionProvider"]


def test_live_frame_is_not_encoded_or_retained(engine):
    image = decode_image((DATASET / "img1.jpg").read_bytes())
    sample = engine.extract(image, live=True)
    assert sample.photo == b""
    assert sample.spoof_score is not None


def test_real_guided_capture_then_verify_another_photo(engine, tmp_path):
    import time
    from fastapi.testclient import TestClient
    from face_demo.app import create_app

    application = create_app(engine=engine, data_dir=tmp_path)
    with TestClient(application, base_url="http://127.0.0.1:8000", headers={"X-Face-Demo": "local"}) as client:
        response = client.post("/api/enrollments", json={"name": "Fixture", "email": "fixture@example.test", "consent": True})
        assert response.status_code == 201
        token = response.json()["enrollment_id"]
        for index in range(3):
            application.state.enrollments.items[token].last_frame = time.monotonic() - .6
            response = client.post(f"/api/enrollments/{token}/frames",
                                   files={"photo": ("frame.jpg", (DATASET / "img1.jpg").read_bytes(), "image/jpeg")})
            assert response.status_code == 200
            assert response.json()["captured"] is (index == 2)
        response = client.post(f"/api/enrollments/{token}/complete")
        assert response.status_code == 201
        user_id = response.json()["user"]["id"]
        token = client.post("/api/sessions", json={"user_id": user_id}).json()["session_id"]
        for index in range(3):
            application.state.sessions.items[token].last_frame = time.monotonic() - 1
            result = client.post(f"/api/sessions/{token}/frames", files={
                "photo": ("frame.jpg", (DATASET / "img2.jpg").read_bytes(), "image/jpeg")}).json()
            assert result["verified"] is (index == 2)
        client.delete(f"/api/users/{user_id}")
        assert application.state.enrollments.items == {}
