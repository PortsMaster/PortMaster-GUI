#!/bin/bash

awk -F"'" '/PORTMASTER_VERSION = / {print $2}' PortMaster/pugwash > PortMaster/version

cp PortMaster/version version

rm -vf PortMaster.zip
rm -fRv PortMaster/themes
rm -fRv PortMaster/config
rm -fRv PortMaster/pugwash.txt
rm -fRv PortMaster/harbourmaster.txt

find . -iname '.DS_Store' -or -iname '._*' -delete -print

for name in $(find . -iname '__pycache__');
do
    rm -fRv "$name"
done

zip -9r PortMaster.zip PortMaster/
