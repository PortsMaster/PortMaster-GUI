#!/bin/bash
#
# SPDX-License-Identifier: MIT
#

XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

if [ -d "/opt/system/Tools/" ]; then
  controlfolder="/opt/system/Tools"
elif [ -d "/opt/tools/" ]; then
  controlfolder="/opt/tools"
elif [ -d "/userdata/system" ]; then
  controlfolder="$XDG_DATA_HOME"
  mkdir -pv "$controlfolder/PortMaster"
  OS_NAME="Batocera"
else
  controlfolder="/roms/ports"
fi

if [[ -e "/usr/share/plymouth/themes/text.plymouth" ]]; then
  if [ ! -z "$(cat /etc/fstab | grep roms2 | tr -d '\0')" ]; then
    directory="roms2"
  else
    directory="roms"
  fi
elif [ -d "/userdata/roms/ports" ]; then
  directory="userdata/roms"
else
  directory="roms"
fi

CUR_TTY=/dev/tty0

TEMP_DIR=$(pwd)

if [ -f "/etc/os-release" ]; then
  source /etc/os-release
fi

echo "-- Installing on $OS_NAME --"

sudo echo "Testing for sudo..." > /dev/null 2>&1
if [ $? != 0 ]; then
  ESUDO=""
else
  ESUDO="sudo"
fi

if [[ -e "/usr/share/plymouth/themes/text.plymouth" ]]; then
  ES_NAME="emulationstation"
elif [ -d "/userdata/roms/ports" ]; then
  ES_NAME="batocera-es-swissknife"
else
  ES_NAME="emustation"
fi

RELOCATE_PM=""
if [ "${OS_NAME}" != "JELOS" ] && [ "${OS_NAME}" != "UnofficialOS" ] && [ "${OS_NAME}" != "ROCKNIX" ]; then
  RELOCATE_PM="TRUE"
fi

$ESUDO chmod 666 $CUR_TTY
printf "\033c" > $CUR_TTY

cd "$controlfolder"
echo "Installing PortMaster to $controlfolder" | tee -a $CUR_TTY

$ESUDO mkdir temp_runtimes
$ESUDO mv PortMaster/libs/*.squashfs temp_runtimes/

$ESUDO rm -fRv "PortMaster" "PortMaster.sh" | tee -a $CUR_TTY

if [[ "${OS_NAME}" == "JELOS" ]] || [[ "${OS_NAME}" == "ROCKNIX" ]]; then
  ## Taken from this: https://github.com/brooksytech/JELOS/blob/main/packages/apps/portmaster/scripts/start_portmaster.sh
  # Make sure PortMaster exists in .config/PortMaster
  if [ ! -d "/storage/.config/PortMaster" ]; then
      mkdir -p "/storage/.config/ports/PortMaster"
      cp -rv "/usr/config/PortMaster" "/storage/.config/"
  fi

  cd /storage/.config/PortMaster

  # Grab the latest PortMaster.sh script
  cp -v /usr/config/PortMaster/PortMaster.sh PortMaster.sh | tee -a $CUR_TTY
  cp -v /usr/config/PortMaster/control.txt control.txt | tee -a $CUR_TTY

  # Use our gamecontrollerdb.txt
  rm gamecontrollerdb.txt
  ln -svf /usr/config/SDL-GameControllerDB/gamecontrollerdb.txt gamecontrollerdb.txt | tee -a $CUR_TTY

  # Use our gptokeyb
  rm gptokeyb
  ln -svf /usr/bin/gptokeyb gptokeyb | tee -a $CUR_TTY
  cp -v /usr/config/PortMaster/portmaster.gptk portmaster.gptk | tee -a $CUR_TTY

  cd "$controlfolder"
fi

$ESUDO unzip -o "$TEMP_DIR/PortMaster.zip" | tee -a $CUR_TTY

# Overrides
if [ ! -z "$OS_NAME" ]; then
  PORTMASTER_DIR="$controlfolder/PortMaster"
  OVERRIDE_DIR="$PORTMASTER_DIR/${OS_NAME,,}"

  echo "--> $OVERRIDE_DIR <--" | tee -a $CUR_TTY
  if [ -d "$OVERRIDE_DIR" ]; then
    [ -f "$OVERRIDE_DIR/PortMaster.txt" ] && $ESUDO cp -vf "$OVERRIDE_DIR/PortMaster.txt" "$PORTMASTER_DIR/PortMaster.sh" | tee -a $CUR_TTY
    [ -f "$OVERRIDE_DIR/control.txt"    ] && $ESUDO cp -vf "$OVERRIDE_DIR/control.txt" "$PORTMASTER_DIR/" | tee -a $CUR_TTY
  fi
fi

if [ ! -z "$RELOCATE_PM" ]; then
  if [ -d "/userdata/roms/ports" ]; then
    $ESUDO mv -vf PortMaster/PortMaster.sh /$directory/ports/PortMaster.sh | tee -a $CUR_TTY
  else
    $ESUDO mv -vf PortMaster/PortMaster.sh PortMaster.sh | tee -a $CUR_TTY
  fi
fi

$ESUDO mv temp_runtimes/*.squashfs PortMaster/libs/
$ESUDO rm -fR temp_runtimes/

if [ -f "$TEMP_DIR/runtimes.zip" ]; then
  cd PortMaster/libs/
  $ESUDO unzip "$TEMP_DIR/runtimes.zip" | tee -a $CUR_TTY
fi

$ESUDO rm -vf /$directory/port_scripts/Install*PortMaster*.sh | tee -a $CUR_TTY
$ESUDO rm -vf /$directory/port_scripts/Restore*PortMaster*.sh | tee -a $CUR_TTY
$ESUDO rm -vf /$directory/ports/Install*PortMaster*.sh | tee -a $CUR_TTY
$ESUDO rm -vf /$directory/ports/Restore*PortMaster*.sh | tee -a $CUR_TTY

echo "Finished installing PortMaster" | tee -a $CUR_TTY
sleep 2

if [ ! -f "$HOME/no_es_restart" ]; then
  if [[ "$ES_NAME" == "batocera-es-swissknife" ]]; then
    if [ ! -e "/lib/ld-linux-x86-64.so.2" ]; then
      batocera-es-swissknife --restart
    fi
  else
    $ESUDO systemctl restart $ES_NAME
  fi
else
  $ESUDO rm -f "$HOME/no_es_restart"
fi
