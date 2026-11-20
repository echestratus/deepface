"""Process-local settings. Import before NumPy, OpenCV or DeepFace."""

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    threads: int = 2
    threshold: float = 0.593
    anti_spoofing: bool = True
    required_matches: int = 3
    frame_interval_ms: int = 1000
    guide_interval_ms: int = 500
    capture_matches: int = 3
    max_image_bytes: int = 5 * 1024 * 1024
    max_pixels: int = 12_000_000
    max_side: int = 640
    min_face_size: int = 72
    min_blur: float = 25.0

    @classmethod
    def from_env(cls):
        threads = int(os.environ.get("FACE_DEMO_THREADS", "2"))
        threshold = float(os.environ.get("FACE_DEMO_THRESHOLD", "0.593"))
        if not 1 <= threads <= 8:
            raise ValueError("FACE_DEMO_THREADS harus antara 1 dan 8.")
        if not 0 < threshold < 1:
            raise ValueError("FACE_DEMO_THRESHOLD harus antara 0 dan 1.")
        anti_spoof = os.environ.get("FACE_DEMO_ANTI_SPOOF", "true").lower()
        if anti_spoof not in {"true", "false"}:
            raise ValueError("FACE_DEMO_ANTI_SPOOF harus true atau false.")
        return cls(
            data_dir=Path(os.environ.get("FACE_DEMO_DATA_DIR", str(Path(__file__).parent / "data"))).resolve(),
            threads=threads,
            threshold=threshold,
            anti_spoofing=anti_spoof == "true",
        )


settings = Settings.from_env()
# DeepFace's download logs contain emoji; Windows redirected consoles may use cp1252.
for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")
# Enforce these even when the parent shell requests a GPU or another framework.
os.environ["DEEPFACE_BACKEND_ENGINE"] = "onnx"
os.environ["DEEPFACE_ONNX_PROVIDERS"] = "cpu"
os.environ["DEEPFACE_ONNX_THREADS"] = str(settings.threads)
os.environ["DEEPFACE_HOME"] = str(settings.data_dir / "models")
os.environ["OMP_NUM_THREADS"] = str(settings.threads)
os.environ["OPENBLAS_NUM_THREADS"] = str(settings.threads)
