#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT="$(dirname "$SCRIPT_DIR")"

source "$ROOT"/../opt/conda/bin/activate dev

export PYTHONPATH="$ROOT"/../:"$PYTHONPATH"

cd "$ROOT"/random_strategy || (echo "Wrong path!" && exit); python3 main.py fix-settings.cfg strategy.yaml
