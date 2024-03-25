#!/bin/bash

RESTORE_DIR=$PWD

rm update.portmaster.zip

mkdir retrodeck_build

cd retrodeck_build

if [[ "$1" == "alpha" ]]; then
    wget "https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/version.json"

    if [[ ! -f "version.json" ]]; then
        echo "Missing version.json file."
        exit 255
    fi

    wget "$(jq -r '.alpha.url' 'version.json')"
fi

if [[ -f "$PWD/PortMaster.zip" ]]; then
    PORTMASTER_ZIP="$PWD/PortMaster.zip"
elif [[ -f "$RESTORE_DIR/PortMaster.zip" ]]; then
    PORTMASTER_ZIP="$RESTORE_DIR/PortMaster.zip"
else
    echo "Missing PortMaster.zip file."
    exit 255
fi

mkdir -p $HOME/RD_PM/

cd $HOME/RD_PM/

unzip "$PORTMASTER_ZIP"

cd PortMaster
cp retrodeck/control.txt control.txt
cp retrodeck/PortMaster.txt PortMaster.sh
rm tasksetter
touch tasksetter

cd $HOME/RD_PM
zip -9r ../update.portmaster.zip PortMaster/
cd $HOME

rm -fRv retrodeck_build
