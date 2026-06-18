#!/usr/bin/env bash
# Set up the TASTELESS engine from a clone, into an isolated .venv.
#   ./setup.sh              core audit (light, fast)
#   ./setup.sh --hierarchy  + the DINOv2 visual-hierarchy heatmap (torch/timm/opencv)
set -euo pipefail

PY="${PYTHON:-python3}"   # pyenv & most systems expose python3, not python
command -v "$PY" >/dev/null 2>&1 || { echo "✗ need python3 on PATH"; exit 1; }

"$PY" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install -q --upgrade pip

EXTRA=""
[ "${1:-}" = "--hierarchy" ] && EXTRA="[hierarchy]"
python -m pip install -e ".${EXTRA}"
python -m playwright install chromium

echo
echo "✓ TASTELESS ready in .venv${EXTRA:+ (with hierarchy)}."
echo "  source .venv/bin/activate"
echo "  tasteless-shoot --url http://localhost:3000 --out /tmp/tl --full-page && tasteless-audit /tmp/tl.json"
