"""Download once and validate all CPU models without starting a server."""

from .engine import FaceEngine


def main():
    engine = FaceEngine()
    engine.load()
    print("SFace, YuNet, dan filter anti-spoof siap. Provider: CPUExecutionProvider.")


if __name__ == "__main__":
    main()
