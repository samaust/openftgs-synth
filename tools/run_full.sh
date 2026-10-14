#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-or-later
# Full render chain (resumable): build/render/package then validate each scene in turn.
# Stops if free space on the dataset filesystem drops below MIN_FREE_GB.
set -u
cd "$(dirname "$0")/.."
MIN_FREE_GB=${MIN_FREE_GB:-25}
for s in "$@"; do
  free=$(df --output=avail -BG ~/datasets | tail -1 | tr -dc 0-9)
  if [ "$free" -lt "$MIN_FREE_GB" ]; then echo "STOP: only ${free} GB free"; exit 2; fi
  echo "=== $s start $(date -Is)"
  if [ ! -f ~/datasets/openftgs-synth-work/$s/scene.blend ]; then
    .venv/bin/python tools/run_scene.py configs/$s.yaml build || { echo "FAILED build $s"; exit 1; }
  fi
  ( while sleep 300; do f=$(df --output=avail -BG ~/datasets | tail -1 | tr -dc 0-9);
      if [ "$f" -lt "$MIN_FREE_GB" ]; then echo "STOP: only ${f} GB free"; pkill -f "run_scene.py configs/$s.yaml"; pkill -f blender-5.2.2; fi; done ) &
  guard=$!
  .venv/bin/python tools/run_scene.py configs/$s.yaml render package; rc=$?
  kill $guard 2>/dev/null
  [ $rc -eq 0 ] || { echo "FAILED render $s"; exit 1; }
  .venv/bin/python validate/run_all.py configs/$s.yaml; echo "=== $s done rc=$? $(date -Is)"
done
echo "CHAIN COMPLETE $(date -Is)"
