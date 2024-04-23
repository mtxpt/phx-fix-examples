#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT="$(dirname "$SCRIPT_DIR")"

source "$ROOT"/../../../opt/conda/bin/activate dev

export PYTHONPATH="$ROOT"/../../../:"$PYTHONPATH"
cd "$ROOT"/random || (echo "Wrong path!" && exit); python main.py
