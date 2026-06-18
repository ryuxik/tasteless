#!/usr/bin/env bash
# One-command setup for the TASTELESS engine. The Claude Code skill also runs
# this automatically on first use — see the skill's Setup step.
set -euo pipefail

# install the engine (editable from a clone, else straight from GitHub)
python -m pip install -e . 2>/dev/null \
  || python -m pip install "git+https://github.com/ryuxik/tasteless.git"

# one-time headless-browser download for rendering
python -m playwright install chromium

echo "✓ TASTELESS engine ready — try: python -m tasteless.shoot --url http://localhost:3000 --out /tmp/tl"
