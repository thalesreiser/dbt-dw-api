#!/usr/bin/env bash
# Runs once when the codespace (or local dev container) is created.
set -euo pipefail

command -v make >/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq make; }

python -m pip install --quiet --upgrade pip
python -m pip install --quiet -e ".[dev,dbt]"
pre-commit install
make deps

# Local settings only (API key, DuckDB path). Never committed.
[ -f .env ] || cp .env.example .env

echo "Dev container ready. Next: make build, then make api"
