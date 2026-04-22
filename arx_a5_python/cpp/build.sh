#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$SCRIPT_DIR/build" && cd "$SCRIPT_DIR/build" && cmake -DPYTHON_EXECUTABLE=/usr/bin/python3 .. && make && make install
echo "Build complete. .so files installed to $SCRIPT_DIR/../arx_a5_python/lib/"
