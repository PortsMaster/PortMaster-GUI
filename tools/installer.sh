#!/bin/bash

if [ -d "/opt/system/Tools/" ]; then
  controlfolder="/opt/system/Tools"
elif [ -d "/opt/tools/" ]; then
  controlfolder="/opt/tools"
else
  controlfolder="/roms/ports"
fi

if [[ -e "/usr/share/plymouth/themes/text.plymouth" ]]; then
  if [ ! -z "$(cat /etc/fstab | grep roms2 | tr -d '\0')" ]; then
    directory="roms2"
  else
    directory="roms"
  fi
else
  directory="roms"
fi

CUR_TTY=/dev/tty0

TEMP_DIR=$(pwd)

if [ -f "/etc/os-release" ]; then
  source /etc/os-release
fi

sudo echo "Testing for sudo..." > /dev/null 2>&1
if [ $? != 0 ]; then
  ESUDO=""
else
  ESUDO="sudo"
fi

if [[ -e "/usr/share/plymouth/themes/text.plymouth" ]]; then
  ES_NAME="emulationstation"
else
  ES_NAME="emustation"
fi

RELOCATE_PM=""
if [ "${OS_NAME}" != "JELOS" ] && [ "${OS_NAME}" != "UnofficialOS" ]; then
  RELOCATE_PM="TRUE"
fi

$ESUDO chmod 666 $CUR_TTY
printf "\033c" > $CUR_TTY

cd "$controlfolder"
echo "Installing PortMaster" > $CUR_TTY

$ESUDO rm -fRv "PortMaster" "PortMaster.sh" > $CUR_TTY

$ESUDO unzip "$TEMP_DIR/PortMaster.zip" > $CUR_TTY
if [ ! -z "$RELOCATE_PM" ]; then
  $ESUDO mv -vf PortMaster/PortMaster.sh PortMaster.sh > $CUR_TTY
fi

if [ -f "$TEMP_DIR/runtimes.zip" ]; then
  cd PortMaster/libs/
  $ESUDO unzip "$TEMP_DIR/runtimes.zip" > $CUR_TTY
fi

cd "/$directory/ports"

$ESUDO rm -vf Install*PortMaster.sh > $CUR_TTY

echo "Finished installing PortMaster" > $CUR_TTY
sleep 3

$ESUDO systemctl restart $ES_NAME
