"""Small, dependency-free Git policy checks shared by hooks and GitHub Actions."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TYPES = "feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert"
SUBJECT = re.compile(rf"^(?:{TYPES})(?:\([a-z0-9][a-z0-9._/-]*\))?!?: [a-z0-9].*$")
BRANCH = re.compile(rf"^(?:{TYPES})/[a-z0-9]+(?:[/-][a-z0-9]+)*$")
ZERO_SHA = "0" * 40
MAX_FILE_BYTES = 10 * 1024 * 1024
SECRET_PATTERNS = {
    "private key": re.compile(rb"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "OpenAI key": re.compile(rb"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{40,}\b"),
}


class PolicyError(ValueError):
    """A useful error that never includes matched credential contents."""


def git(*arguments, binary=False):
    output = subprocess.check_output(["git", *arguments], cwd=ROOT)
    return output if binary else output.decode("utf-8").strip()


def validate_message(message):
    lines = [line for line in message.strip().splitlines() if not line.startswith("#")]
    subject = lines[0] if lines else ""
    if not SUBJECT.fullmatch(subject):
        raise PolicyError("Use a Conventional Commit: feat(scope): describe the change")
    if len(subject) > 72:
        raise PolicyError("Commit/PR subject must be at most 72 characters.")
    if subject.endswith("."):
        raise PolicyError("Omit the trailing period from the commit/PR subject.")
    if len(lines) > 1 and lines[1].strip():
        raise PolicyError("Separate the subject and body with a blank line.")


def validate_branch(name):
    if not BRANCH.fullmatch(name):
        raise PolicyError("Use a feature branch such as feat/camera-guidance or fix/session-reset.")


def forbidden_path(path):
    normalized = path.replace("\\", "/")
    name = normalized.rsplit("/", 1)[-1].lower()
    if normalized.startswith(("face_demo/data/", "face_demo/test-results/", ".venv/", "venv/")):
        return True
    if name.startswith(".env") and name not in {".env.example", ".env.sample"}:
        return True
    return name in {"id_rsa", "id_ed25519"} or Path(name).suffix in {
        ".pem", ".key", ".p12", ".pfx", ".onnx", ".h5", ".pt", ".pth", ".ckpt",
        ".tflite", ".sqlite", ".sqlite3", ".db", ".log",
    }


def validate_file(path, content):
    if forbidden_path(path):
        raise PolicyError(f"Runtime/private/model file cannot be committed: {path}")
    if len(content) > MAX_FILE_BYTES:
        raise PolicyError(f"File exceeds the 10 MiB repository limit: {path}")
    for label, pattern in SECRET_PATTERNS.items():
        if pattern.search(content):
            raise PolicyError(f"Possible {label} in {path}; remove it before committing.")


def scan_files(paths, revision):
    for path in paths:
        object_name = f"{revision}:{path}" if revision else f":{path}"
        size = int(git("cat-file", "-s", object_name))
        if forbidden_path(path) or size > MAX_FILE_BYTES:
            validate_file(path, b"" if size <= MAX_FILE_BYTES else b"x" * (MAX_FILE_BYTES + 1))
        validate_file(path, git("show", object_name, binary=True))


def changed_paths(*arguments):
    raw = git("diff", "--name-only", "--diff-filter=ACMR", "-z", *arguments, binary=True)
    return [path.decode("utf-8") for path in raw.split(b"\0") if path]


def check_range(base, head):
    if not re.fullmatch(r"[0-9a-f]{40,64}", base) or not re.fullmatch(r"[0-9a-f]{40,64}", head):
        raise PolicyError("Expected full Git commit IDs for the validation range.")
    for commit in git("rev-list", "--first-parent", f"{base}..{head}").splitlines():
        try:
            validate_message(git("show", "-s", "--format=%B", commit))
        except PolicyError as error:
            raise PolicyError(f"Commit {commit[:12]}: {error}") from error
    scan_files(changed_paths(base, head), head)


def run(command, env=None):
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def verify(skip_models=False):
    node = shutil.which("node")
    if not node:
        raise PolicyError("Install Node.js 24 for JavaScript development checks.")
    env = {**os.environ, "FACE_DEMO_MODEL_TESTS": "0" if skip_models else "1", "PYTHONUTF8": "1"}
    run([sys.executable, "-m", "unittest", "discover", "-s", "scripts/tests", "-v"], env)
    run([sys.executable, "-m", "pytest", "face_demo/tests", "tests/unit/test_onnx_providers.py", "-q"], env)
    # These mocks test the library's default options, independent of demo settings.
    regression_env = env.copy()
    regression_env.pop("DEEPFACE_ONNX_THREADS", None)
    run([sys.executable, "-m", "pytest", "tests/unit/test_onnx_directml_session.py", "-q"], regression_env)
    run([sys.executable, "-m", "compileall", "-q", "face_demo", "scripts"], env)
    for path in sorted((ROOT / "face_demo/static").iterdir()):
        if path.suffix in {".js", ".mjs"}:
            run([node, "--check", str(path)], env)
    run([node, "--test", "face_demo/tests/camera.test.mjs"], env)
    run([sys.executable, "-m", "pip", "check"], env)
    run(["git", "diff", "--check"])
    print("Verification passed.")


def validate_event():
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as source:
        event = json.load(source)
    if "pull_request" in event:
        pr = event["pull_request"]
        validate_branch(pr["head"]["ref"])
        validate_message(pr["title"])
        check_range(pr["base"]["sha"], pr["head"]["sha"])
    elif os.environ.get("GITHUB_EVENT_NAME") == "push":
        if event["before"] != ZERO_SHA:
            check_range(event["before"], event["after"])
    print("Git workflow policy passed.")


def pre_push():
    validate_branch(git("branch", "--show-current"))
    updates = [line.split() for line in sys.stdin.read().splitlines() if line.strip()]
    heads = []
    for _local_ref, local_sha, remote_ref, remote_sha in updates:
        if remote_ref in {"refs/heads/master", "refs/heads/main"}:
            raise PolicyError("Push a feature branch and open a PR; direct default-branch pushes are blocked.")
        if local_sha == ZERO_SHA:
            continue
        if remote_sha != ZERO_SHA:
            result = subprocess.run(["git", "merge-base", "--is-ancestor", remote_sha, local_sha], cwd=ROOT)
            if result.returncode:
                raise PolicyError("Non-fast-forward update blocked. Fetch and preserve published history.")
        base = remote_sha if remote_sha != ZERO_SHA else git("merge-base", "origin/master", local_sha)
        check_range(base, local_sha)
        heads.append(local_sha)
    if heads:
        if git("status", "--porcelain", "--untracked-files=no"):
            raise PolicyError("Commit the intended tracked changes before running push verification.")
        verify()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("pre-commit")
    message_parser = subcommands.add_parser("commit-msg")
    message_parser.add_argument("file", type=Path)
    subcommands.add_parser("pre-push")
    subcommands.add_parser("validate-event")
    verify_parser = subcommands.add_parser("verify")
    verify_parser.add_argument("--skip-models", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "pre-commit":
            validate_branch(git("branch", "--show-current"))
            scan_files(changed_paths("--cached"), "")
            run(["git", "diff", "--cached", "--check"])
        elif args.command == "commit-msg":
            validate_message(args.file.read_text(encoding="utf-8"))
        elif args.command == "pre-push":
            pre_push()
        elif args.command == "validate-event":
            validate_event()
        else:
            verify(args.skip_models)
    except (PolicyError, subprocess.CalledProcessError) as error:
        print(f"Git workflow check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
