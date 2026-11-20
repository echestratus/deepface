"""The same DeepFace SFace/YuNet pipeline for enrollment and verification."""

from .config import settings

import io
import threading
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError
from deepface import DeepFace
from deepface.modules import detection
from deepface.modules.exceptions import FaceNotDetected

from .guidance import assess_framing, empty_checks

PIPELINE = "deepface-sface-yunet-base-l2-v1"
Image.MAX_IMAGE_PIXELS = settings.max_pixels
cv2.setNumThreads(settings.threads)
cv2.ocl.setUseOpenCL(False)


class FaceError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass
class Sample:
    embedding: np.ndarray
    photo: bytes
    face: dict
    width: int
    height: int
    blur: float
    spoof_score: float | None


def decode_image(content: bytes) -> np.ndarray:
    if len(content) > settings.max_image_bytes:
        raise FaceError("image_too_large", "Ukuran foto maksimal 5 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.format not in {"JPEG", "PNG"}:
                raise FaceError("invalid_image", "Gunakan foto JPG atau PNG.")
            if source.width * source.height > settings.max_pixels:
                raise FaceError("image_too_large", "Resolusi foto maksimal 12 megapiksel.")
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((settings.max_side, settings.max_side))
            return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as err:
        if isinstance(err, FaceError):
            raise
        raise FaceError("invalid_image", "Foto tidak dapat dibaca. Gunakan JPG atau PNG yang valid.") from err


class FaceEngine:
    def __init__(self):
        # DeepFace caches model instances; serialize inference and model creation.
        self.lock = threading.Lock()
        self.ready = False
        self.spoof_model = None
        self.models = []

    def load(self):
        with self.lock:
            if self.ready:
                return
            self.models = [
                DeepFace.build_model("SFace"),
                DeepFace.build_model("yunet", task="face_detector"),
            ]
            if settings.anti_spoofing:
                self.spoof_model = DeepFace.build_model("Fasnet", task="spoofing")
            sessions = [model.model for model in self.models]
            if self.spoof_model:
                sessions += [self.spoof_model.first_model, self.spoof_model.second_model]
            if any(session.get_providers() != ["CPUExecutionProvider"] for session in sessions):
                raise RuntimeError("Demo ini hanya boleh menggunakan CPUExecutionProvider.")
            self.ready = True

    @staticmethod
    def _detect(image):
        try:
            faces = detection.extract_faces(
                image, detector_backend="yunet", enforce_detection=True,
                align=True, color_face="bgr", normalize_face=False, max_faces=2,
            )
        except FaceNotDetected as err:
            raise FaceError("no_face", "Wajah belum terlihat. Hadapkan wajah ke kamera dengan cahaya yang cukup.") from err
        if len(faces) != 1:
            raise FaceError("multiple_faces", "Pastikan hanya satu wajah berada di dalam gambar.")
        return faces[0]

    def guide(self, image: np.ndarray):
        """Inspect a preview without computing/storing a recognition embedding."""
        if not self.ready:
            self.load()
        frame = {"width": image.shape[1], "height": image.shape[0]}
        with self.lock:
            try:
                face = self._detect(image)
            except FaceError as err:
                checks = empty_checks()
                checks[0]["passed"] = False
                return {"ready": False, "status": err.code, "message": str(err),
                        "checks": checks, "face": None, "frame": frame}
            area = face["facial_area"]
            gray = cv2.cvtColor(face["face"], cv2.COLOR_BGR2GRAY)
            blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            brightness = float(gray.mean())
            result = assess_framing(area, image.shape[1], image.shape[0], blur, brightness)
            result.update(face={key: int(area[key]) for key in ("x", "y", "w", "h")},
                          frame=frame, blur=round(blur, 1), brightness=round(brightness, 1))
            if self.spoof_model:
                passed = None
                if result["ready"]:
                    passed, _ = self.spoof_model.analyze(image, tuple(result["face"].values()))
                    passed = bool(passed)
                    if not passed:
                        result.update(ready=False, status="spoof_detected",
                                      message="Filter anti-spoof menolak frame. Gunakan wajah langsung dengan cahaya merata.")
                result["checks"].append({"id": "anti_spoof", "label": "Frame diterima filter anti-spoof", "passed": passed})
            return result

    def extract(self, image: np.ndarray, *, live: bool) -> Sample:
        if not self.ready:
            self.load()
        with self.lock:
            face = self._detect(image)
            area = face["facial_area"]
            box = {key: int(area[key]) for key in ("x", "y", "w", "h")}
            if min(box["w"], box["h"]) < settings.min_face_size:
                raise FaceError("low_quality", "Wajah terlalu kecil. Dekatkan wajah ke kamera.")
            gray = cv2.cvtColor(face["face"], cv2.COLOR_BGR2GRAY)
            blur = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if blur < settings.min_blur:
                raise FaceError("low_quality", "Foto terlalu buram. Tahan posisi dan bersihkan lensa kamera.")
            if not 35 <= float(gray.mean()) <= 225:
                raise FaceError("low_quality", "Pencahayaan wajah terlalu gelap atau terlalu terang.")
            spoof_score = None
            if live and self.spoof_model:
                is_real, spoof_score = self.spoof_model.analyze(image, tuple(box.values()))
                if not is_real:
                    raise FaceError("spoof_detected", "Filter anti-spoof menolak frame ini. Gunakan wajah langsung dengan cahaya merata.")
            result = DeepFace.represent(
                face["face"], model_name="SFace", detector_backend="skip",
                enforce_detection=True, normalization="base", l2_normalize=True,
            )[0]
            embedding = np.asarray(result["embedding"], dtype=np.float32).reshape(-1)
            if embedding.shape != (128,) or not np.isfinite(embedding).all():
                raise RuntimeError("Embedding SFace tidak valid.")
            photo = b""
            if not live:
                ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not ok:
                    raise RuntimeError("Foto tidak dapat disimpan.")
                photo = encoded.tobytes()
            return Sample(embedding, photo, box, image.shape[1], image.shape[0], blur,
                          float(spoof_score) if spoof_score is not None else None)


def cosine_distance(first: np.ndarray, second: np.ndarray) -> float:
    denominator = float(np.linalg.norm(first) * np.linalg.norm(second))
    if denominator <= 0:
        raise ValueError("Embedding kosong.")
    return float(np.clip(1.0 - np.dot(first, second) / denominator, 0, 2))
