import io
import time

import pytest
from PIL import Image

from face_demo.engine import FaceError, decode_image
from face_demo.sessions import Sessions


def test_large_photo_is_reduced_and_exif_orientation_is_applied():
    image = Image.new("RGB", (1200, 800), "white")
    exif = image.getexif()
    exif[274] = 6
    data = io.BytesIO()
    image.save(data, format="JPEG", exif=exif)
    decoded = decode_image(data.getvalue())
    assert decoded.shape == (640, 427, 3)


def test_rejects_oversized_and_unsupported_images():
    with pytest.raises(FaceError, match="5 MB"):
        decode_image(b"x" * (5 * 1024 * 1024 + 1))
    data = io.BytesIO()
    Image.new("RGB", (20, 20)).save(data, format="GIF")
    with pytest.raises(FaceError, match="JPG atau PNG"):
        decode_image(data.getvalue())


def test_frame_gap_resets_streak_and_parallel_requests_are_rejected():
    sessions = Sessions()
    token = sessions.create("user")
    item = sessions.begin(token)
    with pytest.raises(ValueError):
        sessions.begin(token)
    sessions.finish(item, True)
    item.last_frame = time.monotonic() - 11
    item = sessions.begin(token)
    assert item.streak == 0
    sessions.finish(item, False)
    assert item.streak == 0


def test_session_count_is_bounded():
    sessions = Sessions()
    for _ in range(200):
        sessions.create("user")
    with pytest.raises(ValueError):
        sessions.create("user")
    sessions.remove_user("user")
    assert sessions.items == {}
