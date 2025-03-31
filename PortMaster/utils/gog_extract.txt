#!/bin/bash

# Set the correct innoextract binary
INNOEXTRACT="./PortMaster/utils/innoextract_$DEVICE_ARCH"

# Check if the binary exists
if [ ! -f "$INNOEXTRACT" ]; then
    echo "Error: innoextract binary for $DEVICE_ARCH not found!"
    exit 1
fi

# Set LD_LIBRARY_PATH
export LD_LIBRARY_PATH="./PortMaster/utils/libs.$DEVICE_ARCH:$LD_LIBRARY_PATH"

# Run innoextract with provided arguments
$INNOEXTRACT "$@"
