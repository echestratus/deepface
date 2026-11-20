import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from git_workflow import PolicyError, forbidden_path, validate_branch, validate_file, validate_message


class WorkflowRules(unittest.TestCase):
    def test_conventional_messages(self):
        for value in ["feat(face-lab): add camera guidance", "fix: reset sessions",
                      "feat(api)!: require authentication\n\nBREAKING CHANGE: tokens are required"]:
            with self.subTest(value=value):
                validate_message(value)

    def test_invalid_messages(self):
        for value in ["update code", "feat: Uppercase", "feat: trailing period.",
                      "fix: missing body separator\nBody", "feat: " + "x" * 70, "", "feat(): invalid scope"]:
            with self.subTest(value=value), self.assertRaises(PolicyError):
                validate_message(value)

    def test_branch_conventions(self):
        for branch in ["feat/cpu-face-lab", "fix/api/session-reset", "chore/sync-upstream"]:
            validate_branch(branch)
        for branch in ["master", "main", "feature/Capture", "feat/bad_name", "fix/../master", "feat/"]:
            with self.subTest(branch=branch), self.assertRaises(PolicyError):
                validate_branch(branch)

    def test_runtime_and_private_files(self):
        for path in ["face_demo/data/users.sqlite3", "face_demo/data/photo.jpg", "face_demo/test-results/result.json",
                     ".venv/Scripts/python.exe", ".env", ".env.production", "server.key", "weights/model.onnx"]:
            with self.subTest(path=path):
                self.assertTrue(forbidden_path(path))
        for path in [".env.example", "face_demo/README.md", "tests/unit/dataset/img1.jpg", "scripts/git_workflow.py"]:
            with self.subTest(path=path):
                self.assertFalse(forbidden_path(path))

    def test_credential_error_does_not_echo_the_secret(self):
        samples = [b"ghp_" + b"a" * 36, b"AKIA" + b"A" * 16,
                   b"sk-proj-" + b"a" * 48, b"-----BEGIN " + b"RSA PRIVATE KEY-----"]
        for sample in samples:
            with self.subTest(kind=sample[:5]), self.assertRaises(PolicyError) as context:
                validate_file("settings.txt", sample)
            self.assertNotIn(sample.decode(), str(context.exception))

    def test_plain_source_is_allowed(self):
        validate_file("face_demo/app.py", b"print('hello')\n")


if __name__ == "__main__":
    unittest.main()
