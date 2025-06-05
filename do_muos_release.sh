#!/bin/bash
#
# SPDX-License-Identifier: MIT
#

RESTORE_DIR=$PWD

rm muos.portmaster.zip

mkdir muos_build

cd muos_build

if [[ "$1" == "stable" ]]; then
    wget "https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/version.json"

    if [[ ! -f "version.json" ]]; then
        echo "Missing version.json file."
        exit 255
    fi

    wget "$(jq -r '.stable.url' 'version.json')"
fi

if [[ -f "$PWD/PortMaster.zip" ]]; then
    PORTMASTER_ZIP="$PWD/PortMaster.zip"
elif [[ -f "$RESTORE_DIR/PortMaster.zip" ]]; then
    PORTMASTER_ZIP="$RESTORE_DIR/PortMaster.zip"
else
    echo "Missing PortMaster.zip file."
    exit 255
fi

mkdir -p mnt/mmc/MUOS/
mkdir -p roms/ports/PortMaster/

cd mnt/mmc/MUOS/

unzip "$PORTMASTER_ZIP"

cd PortMaster
cp muos/control.txt control.txt
cp muos/control.txt "$RESTORE_DIR/muos_build/roms/ports/PortMaster/control.txt"
cp muos/PortMaster.txt PortMaster.sh
rm tasksetter
touch tasksetter

cd "$RESTORE_DIR/muos_build"

zip -9r "$RESTORE_DIR/muos.portmaster.zip" roms/ mnt/
cd $RESTORE_DIR

rm -fRv muos_build/
