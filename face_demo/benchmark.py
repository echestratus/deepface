"""Measure real CPU inference at the same one-frame-per-second demo cadence."""

from .config import settings

import argparse
import importlib.metadata
import json
import os
import platform
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .engine import FaceEngine, FaceError, decode_image


def cpu_seconds(process):
    value = process.cpu_times()
    return value.user + value.system


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, default=Path("tests/unit/dataset/img1.jpg"))
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--mode", choices=["verify", "guide"], default="verify")
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--output", type=Path, default=Path("face_demo/test-results/benchmark.json"))
    args = parser.parse_args()
    if args.frames < 3 or args.interval < 0:
        parser.error("Gunakan minimal 3 frame dan interval >= 0.")
    process = psutil.Process()
    engine = FaceEngine()
    start = time.perf_counter()
    engine.load()
    model_load_ms = (time.perf_counter() - start) * 1000
    image = decode_image(args.image.read_bytes())
    # Enrollment does not run the spoof filter. Warm up the recognizer too.
    engine.extract(image, live=False)
    durations, statuses = [], Counter()
    start = time.perf_counter()
    cpu_start = cpu_seconds(process)
    for index in range(args.frames):
        frame_start = time.perf_counter()
        try:
            if args.mode == "guide":
                result = engine.guide(image)
                statuses[result["status"]] += 1
            else:
                engine.extract(image, live=True)
                statuses["processed"] += 1
        except FaceError as err:
            statuses[err.code] += 1
        durations.append((time.perf_counter() - frame_start) * 1000)
        if index < args.frames - 1:
            time.sleep(max(0, args.interval - (time.perf_counter() - frame_start)))
    elapsed = time.perf_counter() - start
    core_percent = (cpu_seconds(process) - cpu_start) / elapsed * 100
    memory = process.memory_info()
    weights = settings.data_dir / "models" / ".deepface" / "weights"
    report = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "os": platform.platform(),
        "logical_cpus": os.cpu_count(), "threads_per_session": settings.threads,
        "provider": "CPUExecutionProvider", "anti_spoofing": settings.anti_spoofing,
        "fixture": args.image.as_posix(), "image_size": [image.shape[1], image.shape[0]],
        "frames": args.frames, "interval_seconds": args.interval,
        "mode": args.mode,
        "elapsed_seconds": round(elapsed, 2), "statuses": dict(statuses),
        "model_load_ms": round(model_load_ms, 1),
        "latency_median_ms": round(statistics.median(durations), 1),
        "latency_p95_ms": round(sorted(durations)[int((len(durations) - 1) * .95)], 1),
        "latency_max_ms": round(max(durations), 1),
        "cpu_percent_one_core": round(core_percent, 2),
        "cpu_percent_entire_machine": round(core_percent / (os.cpu_count() or 1), 2),
        "rss_mib": round(memory.rss / 1024 ** 2, 1),
        "peak_rss_mib": round(getattr(memory, "peak_wset", memory.rss) / 1024 ** 2, 1),
        "model_files_mib": round(sum(path.stat().st_size for path in weights.glob("*.onnx")) / 1024 ** 2, 1),
        "packages": {name: importlib.metadata.version(name) for name in
                     ("deepface", "onnxruntime", "opencv-contrib-python-headless", "numpy", "fastapi")},
        "heavy_frameworks_imported": [name for name in ("tensorflow", "torch") if name in sys.modules],
        "limitation": "Repeated repository photo fixture; measures runtime, not live-camera accuracy or spoof resistance. Includes image inference but excludes browser, HTTP and JPEG decode overhead.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
