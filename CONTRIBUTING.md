# Contributing to this fork

This fork uses [GitHub Flow](https://docs.github.com/en/get-started/using-github/github-flow)
and [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/).
The default branch is `master`. Existing upstream history is preserved.

## Branches, commits, and review

1. Fetch `origin`, then create a short-lived branch from `origin/master`:

   ```bash
   git fetch origin --prune
   git switch -c feat/describe-the-change origin/master
   ```

2. Use one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`,
   `ci`, `chore`, or `revert` as the branch prefix and commit type. Branch names
   are lowercase with words separated by hyphens; nested scope segments are allowed.

3. Make cohesive commits using `<type>(optional-scope): <description>`. Examples:

   ```text
   feat(face-lab): add guided camera enrollment
   fix(verification): reset matches after a rejected frame
   ci(git): enforce the pull request workflow
   feat(api)!: require authenticated interview sessions
   ```

   Repository conventions additionally require a subject of at most 72 characters,
   a lowercase description without a trailing period, and a blank line before the
   body. Describe the change in imperative form. Use `!` or a `BREAKING CHANGE:`
   footer for incompatible changes. These formatting choices supplement the standard.

4. Validate, commit, push the feature branch, and open a PR targeting `master`:

   ```bash
   python scripts/git_workflow.py verify
   git add <specific-files>
   git diff --cached --stat
   git commit -m "feat(face-lab): describe the change"
   git push -u origin feat/describe-the-change
   ```

5. Wait for required checks and address review conversations. The owner merges
   explicitly with **squash merge**; the PR title becomes the Conventional Commit
   subject on `master`. Delete the feature branch after merging. Do not push directly
   to `master`/`main`, force-push, or rewrite published history.

A request to push does not mean merge. Contributors and coding agents may create
the PR as part of an authorized push; merging requires a separate explicit instruction.

## Local setup and checks

Use Python 3.12 and the repository virtual environment. On Windows:

```powershell
.\.venv\Scripts\python.exe -m pip install -r face_demo/requirements-dev.txt -c face_demo/constraints.txt
git config --local core.hooksPath .githooks
.\.venv\Scripts\python.exe scripts/git_workflow.py verify
```

The hooks select `.venv/Scripts/python.exe` on Windows, `.venv/bin/python` on Unix,
or an installed Python when no project venv exists. Hook shell scripts use LF endings.
Only this checkout's Git configuration is changed. Node.js 24 is needed for the
JavaScript development checks; running Face Lab itself does not require Node.js.

- `pre-commit`: checks the branch name, staged paths, large files, common credential
  patterns, and whitespace. It inspects the **index**, including partially staged files.
- `commit-msg`: validates the Conventional Commit message.
- `pre-push`: rejects protected branch pushes and non-fast-forward updates, checks
  new first-parent commit messages and changed content, and runs the full verification.
- `verify`: runs workflow rule unit tests, Face Lab tests with real CPU models,
  isolated DirectML provider regression tests, Python/JavaScript syntax checks,
  camera lifecycle tests, dependency consistency, and whitespace checks.

The first model test run needs internet to download the model cache. A quick local
run can use `verify --skip-models`; the pre-push hook and required CI always include
the model tests. Lightweight credential checks are a basic guard, not a full secret
scanner. Never commit real credentials, even if a pattern is not detected.

Keep `face_demo/data/`, `face_demo/test-results/`, virtual environments, model
weights, private keys, environment secrets, and personal face images out of commits.
The existing public upstream test fixtures remain available for testing.

## GitHub checks and protection

Tracked workflows provide two stable required check names:

- `Git workflow checks`: validates PR branch/title, new first-parent commit messages,
  changed paths/content, and rule unit tests. It does not relint upstream history.
- `Face Lab CPU tests`: runs the full verification on Windows/Python 3.12/Node 24.

PR checks run for every PR targeting `master`, including documentation-only PRs,
so required checks do not remain pending because of path filters. Workflows use
read-only permissions, pinned action commit SHAs, timeouts, and concurrency controls.
The upstream library workflow is retained separately.

Repository settings are managed through GitHub, not automatically activated by
these files. The intended settings are:

- Require a PR and both checks above before updating `master`; require the branch
  to be current and all review conversations resolved.
- Enforce protection for administrators; require linear history; disallow force
  pushes and deletion of `master`.
- Enable squash merge only, use the PR title/body for the squash commit, and delete
  merged feature branches automatically.
- This personal fork has one maintainer, so external approving reviews are optional
  to avoid an unmergeable self-authored PR. When a second maintainer is available,
  require at least one independent approving review.

If upstream changes are imported, keep their commits intact. Use a clearly named
`chore/sync-upstream` branch, resolve conflicts, give your integration commit a
Conventional Commit title, and submit a PR. Never rewrite upstream history just to
change its commit messages. CI validates the new first-parent integration history.
