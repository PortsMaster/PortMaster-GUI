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

mkdir -p $HOME/RD_PM/

cd $HOME/RD_PM/

unzip $RESTORE_DIR/PortMaster.zip


cd PortMaster
cp retrodeck/control.txt control.txt
#cp retrodeck/control.txt $RESTORE_DIR/muos_build/roms/ports/PortMaster/control.txt
cp retrodeck/PortMaster.txt PortMaster.sh
rm tasksetter
touch tasksetter


cd $HOME/RD_PM

#zip -9r ../update.portmaster.zip roms/ mnt/
cd $HOME

rm -fRv RD_PM
