#!/bin/bash
#
# SPDX-License-Identifier: MIT
#

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
echo "Installing PortMaster to $controlfolder" | tee -a $CUR_TTY

$ESUDO mkdir temp_runtimes
$ESUDO mv PortMaster/libs/*.squashfs temp_runtimes/

$ESUDO rm -fRv "PortMaster" "PortMaster.sh" | tee -a $CUR_TTY

if [[ "${OS_NAME}" == "JELOS" ]]; then
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

  # These are our changes
  ## Create our own Start PortMaster.sh and Uninstall PortMaster which restores the default JELOS portmaster stuff.
  echo "Creating new Start PortMaster.sh" | tee -a $CUR_TTY
  cat << __END_FILE__ > /storage/.config/modules/Start\ PortMaster.sh
#!/bin/bash

# SPDX-License-Identifier: MIT
# Copyright (C) 2023-present PortMaster (https://github.com/PortsMaster)

source /etc/profile

/roms/ports/PortMaster/PortMaster.sh
__END_FILE__

  echo "Creating new Restore JELOS PortMaster.sh" | tee -a $CUR_TTY
  cat << __END_FILE__ > /storage/.config/modules/Restore\ JELOS\ PortMaster.sh
#!/bin/bash

# SPDX-License-Identifier: MIT
# Copyright (C) 2023-present PortMaster (https://github.com/PortsMaster)

source /etc/profile

mv -fv /usr/config/modules/Start\ PortMaster.sh /storage/.config/modules
rm -fv /storage/.config/modules/Restore\ JELOS\ PortMaster.sh
systemctl restart emustation
__END_FILE__

  chmod +x /storage/.config/modules/Restore\ JELOS\ PortMaster.sh

  cd "$controlfolder"
fi

$ESUDO unzip -o "$TEMP_DIR/PortMaster.zip" | tee -a $CUR_TTY
if [ ! -z "$RELOCATE_PM" ]; then
  $ESUDO mv -vf PortMaster/PortMaster.sh PortMaster.sh | tee -a $CUR_TTY
fi

$ESUDO mv temp_runtimes/*.squashfs PortMaster/libs/
$ESUDO rm -fR temp_runtimes/

if [ -f "$TEMP_DIR/runtimes.zip" ]; then
  cd PortMaster/libs/
  $ESUDO unzip "$TEMP_DIR/runtimes.zip" | tee -a $CUR_TTY
fi

cd "/$directory/ports"

$ESUDO rm -vf Install*PortMaster.sh | tee -a $CUR_TTY

echo "Finished installing PortMaster" | tee -a $CUR_TTY
sleep 2

if [ ! -f "$HOME/no_es_restart" ]; then
  $ESUDO systemctl restart $ES_NAME
else
  $ESUDO rm -f "$HOME/no_es_restart"
fi
