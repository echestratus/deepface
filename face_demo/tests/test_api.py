"""Exercise identity binding, state resets, storage, consent and local API boundaries."""

import io
import copy
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from face_demo.app import create_app
from face_demo.engine import FaceError, Sample

HEADERS = {"X-Face-Demo": "local"}


def image_file():
    data = io.BytesIO()
    Image.new("RGB", (160, 160), (120, 100, 90)).save(data, format="JPEG")
    return ("photo.jpg", data.getvalue(), "image/jpeg")


class FakeEngine:
    ready = True

    def __init__(self):
        self.embedding = np.eye(128, dtype=np.float32)[0]
        self.error = None
        self.live_calls = []
        self.guide_result = {"ready": True, "status": "ready", "message": "Ready",
                             "face": {"x": 100, "y": 100, "w": 180, "h": 230},
                             "frame": {"width": 640, "height": 480}, "checks": []}

    def load(self):
        pass

    def guide(self, image):
        return copy.deepcopy(self.guide_result)

    def extract(self, image, *, live):
        self.live_calls.append(live)
        if self.error:
            raise self.error
        return Sample(self.embedding.copy(), image_file()[1], {"x": 1, "y": 1, "w": 100, "h": 100},
                      160, 160, 100, 0.9 if live else None)


@pytest.fixture
def setup(tmp_path):
    engine = FakeEngine()
    app = create_app(engine=engine, data_dir=tmp_path)
    with TestClient(app, base_url="http://127.0.0.1:8000", headers=HEADERS) as client:
        yield client, app, engine


def enroll(client, email="demo@example.test", **changes):
    payload = {"name": "Demo User", "email": email, "consent": "true", **changes}
    return client.post("/api/users", data=payload, files={"photo": image_file()})


def session_for(client, user_id):
    response = client.post("/api/sessions", json={"user_id": user_id})
    assert response.status_code == 201
    return response.json()["session_id"]


def frame(client, app, session_id):
    # Advance only the rate limiter; no sleeps and no changing verification state.
    app.state.sessions.items[session_id].last_frame = time.monotonic() - 1
    return client.post(f"/api/sessions/{session_id}/frames", files={"photo": image_file()})


def test_enrollment_persistence_duplicate_and_delete(setup, tmp_path):
    client, app, engine = setup
    response = enroll(client, email="DEMO@EXAMPLE.TEST")
    assert response.status_code == 201
    user = response.json()["user"]
    assert user["email"] == "demo@example.test"
    assert "embedding" not in user and "photo" not in user
    assert client.get("/api/users").json()["users"] == [user]
    assert engine.live_calls == [False]
    assert client.get(f"/api/users/{user['id']}/photo").headers["content-type"] == "image/jpeg"
    assert enroll(client).status_code == 409
    from face_demo.storage import Store
    assert len(Store(tmp_path / "users.sqlite3").list_users()) == 1
    token = session_for(client, user["id"])
    assert client.delete(f"/api/users/{user['id']}").status_code == 204
    assert app.state.sessions.items.get(token) is None
    assert client.get("/api/users").json() == {"users": []}
    assert client.get(f"/api/users/{user['id']}/photo").status_code == 404


@pytest.mark.parametrize("changes", [{"consent": "false"}, {"name": " "}, {"email": "broken"}])
def test_invalid_enrollment_never_stores_data(setup, changes):
    client, _, _ = setup
    assert enroll(client, **changes).status_code == 422
    assert client.get("/api/users").json() == {"users": []}


def test_three_matches_required_and_mismatch_revokes_verification(setup):
    client, app, engine = setup
    user = enroll(client).json()["user"]
    token = session_for(client, user["id"])
    for index in range(1, 4):
        result = frame(client, app, token).json()
        assert result["consecutive_matches"] == index
        assert result["verified"] is (index == 3)
        assert result["matched"] is True
    engine.embedding = np.eye(128, dtype=np.float32)[1]
    result = frame(client, app, token).json()
    assert result["status"] == "mismatch"
    assert result["verified"] is False
    assert result["consecutive_matches"] == 0
    assert result["distance"] == 1.0
    assert all(engine.live_calls[1:])


@pytest.mark.parametrize("code", ["no_face", "multiple_faces", "low_quality", "spoof_detected"])
def test_bad_frame_resets_streak_and_never_verifies(setup, code):
    client, app, engine = setup
    user = enroll(client).json()["user"]
    token = session_for(client, user["id"])
    assert frame(client, app, token).json()["consecutive_matches"] == 1
    engine.error = FaceError(code, "Rejected")
    result = frame(client, app, token).json()
    assert result["status"] == code
    assert not result["verified"] and not result["matched"]
    assert result["consecutive_matches"] == 0
    engine.error = None
    assert frame(client, app, token).json()["consecutive_matches"] == 1


def test_session_is_bound_to_one_identity_and_expires(setup):
    client, app, engine = setup
    first = enroll(client).json()["user"]
    engine.embedding = np.eye(128, dtype=np.float32)[1]
    second = enroll(client, email="other@example.test").json()["user"]
    first_token = session_for(client, first["id"])
    assert frame(client, app, first_token).json()["status"] == "mismatch"
    second_token = session_for(client, second["id"])
    assert frame(client, app, second_token).json()["matched"] is True
    app.state.sessions.items[second_token].expires_at = time.monotonic() - 1
    assert client.post(f"/api/sessions/{second_token}/frames", files={"photo": image_file()}).status_code == 404


def test_local_request_boundaries_and_rate_limit(setup):
    client, app, _ = setup
    assert client.post("/api/sessions", headers={"X-Face-Demo": "wrong"}, json={"user_id": "x" * 36}).status_code == 403
    assert enroll(client).status_code == 201
    user_id = client.get("/api/users").json()["users"][0]["id"]
    assert client.post("/api/sessions", headers={"Origin": "https://external.example"}, json={"user_id": user_id}).status_code == 403
    token = session_for(client, user_id)
    assert frame(client, app, token).status_code == 200
    assert client.post(f"/api/sessions/{token}/frames", files={"photo": image_file()}).status_code == 429
    assert client.get("/api/users", headers={"Host": "external.example"}).status_code == 400


def test_invalid_photo_and_html_safe_names(setup):
    client, _, _ = setup
    result = client.post("/api/users", data={"name": "Demo", "email": "x@example.test", "consent": "true"},
                         files={"photo": ("photo.jpg", b"not an image", "image/jpeg")})
    assert result.status_code == 422
    assert result.json()["detail"]["code"] == "invalid_image"
    result = enroll(client, name="<script>alert(1)</script>")
    assert result.status_code == 201
    # The UI uses textContent, never innerHTML, for data returned by this endpoint.
    assert client.get("/").headers["content-security-policy"].find("script-src 'self'") >= 0


def test_serves_local_assets_and_health(setup):
    client, _, _ = setup
    for path in ["/", "/register", "/verify", "/static/app.js", "/static/camera.mjs", "/static/styles.css", "/openapi.json"]:
        assert client.get(path).status_code == 200
    health = client.get("/api/health").json()
    assert health["provider"] == "CPUExecutionProvider"
    assert health["required_matches"] == 3
    assert health["anti_spoofing"] is True
    assert health["guide_interval_ms"] == 500
    assert 'data-page="register"' in client.get("/register").text
    assert 'data-page="verify"' in client.get("/verify").text


def enrollment_for(client, **changes):
    payload = {"name": "Camera User", "email": "camera@example.test", "consent": True, **changes}
    response = client.post("/api/enrollments", json=payload)
    assert response.status_code == 201
    return response.json()["enrollment_id"]


def guide_frame(client, app, token):
    app.state.enrollments.items[token].last_frame = time.monotonic() - .6
    return client.post(f"/api/enrollments/{token}/frames", files={"photo": image_file()})


def test_camera_enrollment_only_saves_the_approved_capture(setup):
    client, app, engine = setup
    token = enrollment_for(client)
    assert client.post(f"/api/enrollments/{token}/complete").status_code == 409
    for index in range(1, 4):
        response = guide_frame(client, app, token)
        assert response.status_code == 200
        result = response.json()
        assert result["captured"] is (index == 3)
        assert result["consecutive_ready"] == index
        assert client.get("/api/users").json()["users"] == []
    assert engine.live_calls == [False]  # Embedding only after the three accepted guide frames.
    assert client.get(f"/api/enrollments/{token}/photo").status_code == 200
    completed = client.post(f"/api/enrollments/{token}/complete")
    assert completed.status_code == 201
    user = completed.json()["user"]
    assert completed.json()["verification_url"] == "/verify?user=" + user["id"]
    assert len(client.get("/api/users").json()["users"]) == 1
    assert client.post(f"/api/enrollments/{token}/complete").json()["user"] == user
    assert len(client.get("/api/users").json()["users"]) == 1
    assert app.state.enrollments.items[token].sample is None
    stored = app.state.store.get(user["id"])
    assert stored["consent_at"] == app.state.enrollments.items[token].consent_at


@pytest.mark.parametrize("status", ["no_face", "multiple_faces", "off_center", "too_far", "blurred", "lighting", "pose", "spoof_detected"])
def test_camera_guidance_failure_resets_capture_progress(setup, status):
    client, app, engine = setup
    token = enrollment_for(client)
    assert guide_frame(client, app, token).json()["consecutive_ready"] == 1
    engine.guide_result.update(ready=False, status=status)
    result = guide_frame(client, app, token).json()
    assert result["consecutive_ready"] == 0 and result["captured"] is False
    engine.guide_result.update(ready=True, status="ready")
    assert guide_frame(client, app, token).json()["consecutive_ready"] == 1
    assert engine.live_calls == []


def test_camera_motion_and_gap_require_new_stable_frames(setup):
    client, app, engine = setup
    token = enrollment_for(client)
    assert guide_frame(client, app, token).json()["consecutive_ready"] == 1
    engine.guide_result["face"]["x"] += 40
    assert guide_frame(client, app, token).json()["consecutive_ready"] == 1
    app.state.enrollments.items[token].last_frame = time.monotonic() - 3
    result = client.post(f"/api/enrollments/{token}/frames", files={"photo": image_file()}).json()
    assert result["consecutive_ready"] == 1


def test_capture_can_be_canceled_expired_and_rate_limited(setup):
    client, app, _ = setup
    token = enrollment_for(client)
    guide_frame(client, app, token)
    assert client.post(f"/api/enrollments/{token}/frames", files={"photo": image_file()}).status_code == 429
    assert client.delete(f"/api/enrollments/{token}").status_code == 204
    assert client.post(f"/api/enrollments/{token}/complete").status_code == 404
    token = enrollment_for(client)
    app.state.enrollments.items[token].expires_at = time.monotonic() - 1
    app.state.enrollments.purge()
    assert token not in app.state.enrollments.items
    assert client.get(f"/api/enrollments/{token}/photo").status_code == 404


def test_camera_enrollment_consent_and_identity_validation(setup):
    client, _, _ = setup
    for changes in [{"consent": False}, {"email": "invalid"}, {"name": " "}]:
        response = client.post("/api/enrollments", json={"name": "Demo", "email": "camera@example.test", "consent": True, **changes})
        assert response.status_code == 422
    enroll(client)
    assert client.post("/api/enrollments", json={"name": "Demo", "email": "demo@example.test", "consent": True}).status_code == 409
