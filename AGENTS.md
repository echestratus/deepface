# Repository instructions

Read [CONTRIBUTING.md](CONTRIBUTING.md) before Git operations.

- Use GitHub Flow. Start a short-lived branch from `origin/master`; branch names use
  `feat/`, `fix/`, `docs/`, `refactor/`, `perf/`, `test/`, `build/`, `ci/`, `chore/`,
  `style/`, or `revert/` and a lowercase kebab-case description.
- Use Conventional Commits for new commits and PR titles. Keep the subject at most
  72 characters; use a lowercase imperative description. Mark breaking changes.
- A user request to push authorizes committing and pushing the scoped changes and
  opening a reviewable PR. Do not ask again for those actions. Merge a PR only when
  the user explicitly asks to merge; a push request alone does not authorize merge.
- Keep commits cohesive and independently usable. Preserve unrelated user changes.
  Do not amend or rewrite published history or force-push without explicit user intent.
- Install the repository-local hooks with `git config --local core.hooksPath .githooks`.
  Do not change global Git configuration or bypass failing hooks/checks.
- Before pushing, run `python scripts/git_workflow.py verify` using the project venv.
  Fix relevant failures and report any verification limits accurately.
- Never commit runtime photos, embeddings, local databases, model weights, `.env`
  files, secrets, virtual environments, or generated test/benchmark results.
- Use `origin` (`echestratus/deepface`) for this fork. Do not push to upstream.
- Follow PR review and required CI checks. Prefer squash merge with a Conventional
  Commit PR title. Keep `master` protected and its history linear.

Do not create sub-agents unless the user explicitly requests delegation.
