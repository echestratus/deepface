"""Camera framing hints; landmark checks are heuristics, not a 3-D pose model."""

import math

from .config import settings

LABELS = {
    "single_face": "Satu wajah terlihat",
    "distance": "Jarak wajah sesuai",
    "position": "Wajah berada di tengah",
    "pose": "Wajah menghadap kamera dan kepala tegak",
    "lighting": "Pencahayaan cukup",
    "sharpness": "Gambar wajah tajam",
    "anti_spoof": "Frame diterima filter anti-spoof",
}


def empty_checks():
    return [{"id": key, "label": label, "passed": None} for key, label in LABELS.items()
            if key != "anti_spoof" or settings.anti_spoofing]


def assess_framing(area, width, height, blur, brightness):
    """Directions refer to the mirrored preview, while the input remains unmirrored."""
    x, y, w, h = (area[key] for key in ("x", "y", "w", "h"))
    center_x, center_y = (x + w / 2) / width, (y + h / 2) / height
    small = min(w, h) < settings.min_face_size or h / height < .28
    large = h / height > .72 or w / width > .62
    clipped = x < width * .02 or y < height * .02 or x + w > width * .98 or y + h > height * .98
    centered = abs(center_x - .5) <= .15 and abs(center_y - .46) <= .16
    left, right = area.get("left_eye"), area.get("right_eye")
    pose = False
    if left is not None and right is not None:
        eye_distance = math.dist(left, right)
        pose = eye_distance >= w * .22 and abs(left[1] - right[1]) <= eye_distance * .18
    values = {"single_face": True, "distance": not (small or large or clipped),
              "position": centered, "pose": pose, "lighting": 35 <= brightness <= 225,
              "sharpness": blur >= settings.min_blur}
    checks = [{"id": key, "label": LABELS[key], "passed": passed} for key, passed in values.items()]
    status, message = "ready", "Posisi sudah sesuai. Tahan wajah dan lihat ke kamera."
    if small:
        status, message = "too_far", "Dekatkan wajah ke kamera sampai mengisi panduan oval."
    elif large or clipped:
        status, message = "too_close", "Mundur sedikit agar seluruh wajah terlihat di dalam kamera."
    elif not centered:
        if abs(center_x - .5) > .15:
            message = "Geser wajah ke kiri layar." if center_x < .5 else "Geser wajah ke kanan layar."
        else:
            message = "Turunkan posisi wajah sedikit." if center_y < .46 else "Naikkan posisi wajah sedikit."
        status = "off_center"
    elif not pose:
        status, message = "pose", "Hadapkan wajah lurus ke kamera dan tegakkan kepala."
    elif not values["lighting"]:
        status = "lighting"
        message = "Tambahkan cahaya dari depan wajah." if brightness < 35 else "Kurangi cahaya langsung agar wajah tidak terlalu terang."
    elif not values["sharpness"]:
        status, message = "blurred", "Tahan posisi sebentar. Pastikan lensa bersih dan wajah tidak buram."
    return {"ready": all(values.values()), "status": status, "message": message, "checks": checks}
