#!/bin/sh

# Set library path for aarch64
export LD_LIBRARY_PATH="$(dirname "$0")/innoextract/libs.aarch64:$LD_LIBRARY_PATH"

# Call innoextract with passed arguments
"$(dirname "$0")/innoextract/innoextract" "$@"
