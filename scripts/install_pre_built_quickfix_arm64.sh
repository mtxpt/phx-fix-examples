#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT="$(dirname "$SCRIPT_DIR")"

BUILD_DIR="$ROOT/build-quickfix"
QUICKFIX=quickfix-1.15.1

source "$ROOT/opt/conda/bin/activate" dev

if [[ -n "$ROOT_CERTIFICATE" ]]; then
  echo "pip config for root certificate $ROOT_CERTIFICATE"
  pip3 config set global.cert "$ROOT_CERTIFICATE"
else
  echo "no root certificate configured in env variable ROOT_CERTIFICATE"
fi

pip3 install --trusted-host pypi.org --trusted-host pypi.python.org "$BUILD_DIR/$QUICKFIX"

conda list | grep quickfix
 
