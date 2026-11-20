"""A single-process loopback server so the demo stays local and CPU bounded."""

from .config import settings  # configure the process before importing the runtime

import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="Cari Kerja Face Lab (CPU / localhost)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("Port harus antara 1 dan 65535.")
    print(f"Face Lab: http://127.0.0.1:{args.port}")
    print(f"CPU only | {settings.threads} threads | anti-spoof: {settings.anti_spoofing}")
    print("Startup pertama mengunduh model. Tunggu 'Application startup complete'.")
    uvicorn.run("face_demo.app:app", host="127.0.0.1", port=args.port, workers=1,
                access_log=False, proxy_headers=False)


if __name__ == "__main__":
    main()
