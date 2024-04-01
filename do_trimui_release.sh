#!/bin/bash

RESTORE_DIR=$PWD

rm trimui.portmaster.zip

mkdir trimui_build

cd trimui_build

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

mkdir -p Apps/PortMaster

cd Apps/PortMaster

unzip "$PORTMASTER_ZIP"

cd PortMaster
rm -f PortMaster.sh

cp trimui/control.txt control.txt
cp trimui/PortMaster.txt ../launch.sh
cp trimui/config.json ../config.json
cp trimui/icon.png ../icon.png

rm tasksetter
touch tasksetter

cd "$RESTORE_DIR/trimui_build"

zip -9r "$RESTORE_DIR/trimui.portmaster.zip" Apps/
cd $RESTORE_DIR

rm -fRv trimui_build/
