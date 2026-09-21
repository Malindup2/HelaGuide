#!/usr/bin/env bash
# One-time local setup for a single component. Usage: scripts/dev-setup.sh c2-knowledge-graph
set -euo pipefail
name="${1:?usage: scripts/dev-setup.sh <component-folder>}"
root="$(cd "$(dirname "$0")/.." && pwd)"
svc="$root/components/$name/service"
[ -d "$svc" ] || { echo "no such component: $name"; exit 1; }
cd "$svc"
python -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -e "$root/shared"
pip install -e ".[dev]"
[ -f "$root/.env" ] || cp "$root/.env.example" "$root/.env"
echo "ready: cd components/$name/service && source .venv/bin/activate && pytest"
