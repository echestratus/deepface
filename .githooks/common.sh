#!/bin/sh
run_workflow() {
    if [ -x .venv/Scripts/python.exe ]; then
        .venv/Scripts/python.exe scripts/git_workflow.py "$@"
    elif [ -x .venv/bin/python ]; then
        .venv/bin/python scripts/git_workflow.py "$@"
    elif command -v python3 >/dev/null 2>&1; then
        python3 scripts/git_workflow.py "$@"
    else
        python scripts/git_workflow.py "$@"
    fi
}
