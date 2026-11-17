#!/usr/bin/env bash
set -euo pipefail
WII_PROJECT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd -- "$WII_PROJECT_ROOT"
if [[ ! -x .venv-linux/bin/python ]]; then
    python3 -m venv .venv-linux
fi
.venv-linux/bin/python -m pip install -r configs/requirements-linux.txt
.venv-linux/bin/python scripts/prepare_linux_environment.py "$@"
