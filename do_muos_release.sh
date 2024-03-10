#!/bin/bash

RESTORE_DIR=$PWD

rm update.portmaster.zip

if [[ "$1" == "stable" ]]; then
    rm PortMaster.zip
    rm version.json

    wget "https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/version.json"

    if [[ ! -f "version.json" ]]; then
        echo "Missing version.json file."
        exit 255
    fi

    wget "$(jq -r '.stable.url' 'version.json')"
fi

if [[ ! -f "PortMaster.zip" ]]; then
    echo "Missing PortMaster.zip file."
    exit 255
fi

mkdir -p muos_build/mnt/mmc/MUOS/
mkdir -p muos_build/roms/ports/PortMaster/

cd muos_build/mnt/mmc/MUOS/

unzip $RESTORE_DIR/PortMaster.zip

cd PortMaster
cp muos/control.txt control.txt
cp muos/control.txt $RESTORE_DIR/muos_build/roms/ports/PortMaster/control.txt
cp muos/PortMaster.txt PortMaster.sh
rm tasksetter
touch tasksetter

cd $RESTORE_DIR/muos_build

zip -9r ../update.portmaster.zip roms/ mnt/
cd $RESTORE_DIR

rm -fRv muos_build/
