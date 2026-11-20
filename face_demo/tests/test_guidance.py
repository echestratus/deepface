import pytest

from face_demo.enrollment import Enrollments
from face_demo.guidance import assess_framing


def framing(**changes):
    area = {"x": 230, "y": 100, "w": 180, "h": 230, "left_eye": (275, 170), "right_eye": (365, 170)}
    blur, brightness = changes.pop("blur", 100), changes.pop("brightness", 120)
    area.update(changes)
    return assess_framing(area, 640, 480, blur, brightness)


def test_good_framing_is_ready():
    result = framing()
    assert result["ready"]
    assert all(check["passed"] for check in result["checks"])


@pytest.mark.parametrize("changes, status", [
    ({"w": 50, "h": 80}, "too_far"),
    ({"h": 360}, "too_close"),
    ({"x": 4}, "too_close"),
    ({"x": 80}, "off_center"),
    ({"x": 380}, "off_center"),
    ({"left_eye": None}, "pose"),
    ({"left_eye": (275, 130)}, "pose"),
    ({"brightness": 20}, "lighting"),
    ({"brightness": 240}, "lighting"),
    ({"blur": 10}, "blurred"),
])
def test_guidance_targets_the_relevant_correction(changes, status):
    result = framing(**changes)
    assert not result["ready"]
    assert result["status"] == status


def test_horizontal_directions_match_the_mirrored_preview():
    assert "kiri layar" in framing(x=80)["message"]
    assert "kanan layar" in framing(x=380)["message"]


def test_enrollment_drafts_are_bounded():
    drafts = Enrollments()
    for _ in range(50):
        drafts.create("Demo", "demo@example.test")
    with pytest.raises(ValueError):
        drafts.create("Demo", "demo@example.test")
