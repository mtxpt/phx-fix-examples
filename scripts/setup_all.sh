#!/usr/bin/env bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT="$(dirname "$SCRIPT_DIR")"

case "$1" in
  clean)
    echo "removing existing conda environment $ROOT/opt"
    rm -rf "$ROOT/opt"
    ;;
  *)
    echo "using existing conda environment $ROOT/opt"
    ;;
esac

if [ ! -d "$ROOT/opt/conda" ]; then
    echo "creating new conda environment $ROOT/opt"
    "$SCRIPT_DIR/create_conda_env.sh"
fi

source "$ROOT/opt/conda/bin/activate" dev

if [[ -n "$ROOT_CERTIFICATE" ]]; then
  echo "pip config for root certificate $ROOT_CERTIFICATE"
  pip3 config set global.cert "$ROOT_CERTIFICATE"
else
  echo "no root certificate configured in env variable ROOT_CERTIFICATE"
fi

pip3 install -r requirements.txt

ARCH="$(uname -m)"

case "$ARCH" in
  x86_64)
    ;;
  aarch64)
    ;;
  arm64)
    QUICKFIX_DIR="$ROOT/build-quickfix/quickfix-1.15.1"
    if [ ! -d "$QUICKFIX_DIR" ]; then
      echo "building custom QuickFix version for $ARCH"
      "$SCRIPT_DIR/build_quickfix_arm64.sh"
    fi
    echo "installing custom QuickFix build for $ARCH"
    "$SCRIPT_DIR/install_pre_built_quickfix_arm64.sh"
    ;;
  *)
    (>&2 echo -e "\033[1;31mERROR: Unknown architecture.\033[0m") && exit 1
esac

conda list





