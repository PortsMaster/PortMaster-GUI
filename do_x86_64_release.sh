#!/bin/bash

RESTORE_DIR=$PWD

rm retrodeck.portmaster.zip
mkdir retrodeck_build
cd retrodeck_build

case "$1" in
    alpha|beta|stable)
        wget "https://github.com/PortsMaster/PortMaster-GUI/releases/latest/download/version.json"
        if [[ ! -f "version.json" ]]; then
            echo "Missing version.json file."
            exit 255
        fi
        wget "$(jq -r ".$1.url" "version.json")"
        ;;
esac

if [[ -f "$PWD/PortMaster.zip" ]]; then
    PORTMASTER_ZIP="$PWD/PortMaster.zip"
elif [[ -f "$RESTORE_DIR/PortMaster.zip" ]]; then
    PORTMASTER_ZIP="$RESTORE_DIR/PortMaster.zip"
else
    echo "Missing PortMaster.zip file."
    exit 255
fi

mkdir -p RD_PM/
mkdir -p $PMC_DIR
cd RD_PM/

unzip "$PORTMASTER_ZIP"

cd PortMaster
cp retrodeck/control.txt control.txt 
cp retrodeck/PortMaster.txt PortMaster.sh
rm tasksetter
touch tasksetter

cd ..
zip -9r "$RESTORE_DIR/retrodeck.portmaster.zip" PortMaster/
cd $RESTORE_DIR
rm -fRv retrodeck_build
