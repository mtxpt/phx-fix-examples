#!/bin/bash

SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
ROOT="$(dirname "$SCRIPT_DIR")"

# https://stackoverflow.com/questions/74895819/quickfix-for-python-library-installation-fails-in-macos

BUILD_DIR="$ROOT/build-quickfix"
QUICKFIX=quickfix-1.15.1
QUICKFIX_FILE=${QUICKFIX}.tar.gz
QUICKFIX_URL=https://files.pythonhosted.org/packages/62/b0/caf2dfae8779551f6e1d2bc78668d8f5a2303d21311fdd54345722b68cbc
QUICKFIX_SOURCE=$QUICKFIX_URL/$QUICKFIX_FILE

mkdir -p "$BUILD_DIR"
curl -L -o "$BUILD_DIR/$QUICKFIX_FILE" $QUICKFIX_SOURCE
tar -zxf "$BUILD_DIR/$QUICKFIX_FILE" --directory "$BUILD_DIR"
cp "$ROOT/quickfix-patch/AtomicCount.h" "$BUILD_DIR/$QUICKFIX/C++/AtomicCount.h"

source ./opt/conda/bin/activate dev
cd "$BUILD_DIR/$QUICKFIX"
pip3 install .

conda list | grep quickfix
