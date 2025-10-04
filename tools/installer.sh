#!/bin/bash
#
# SPDX-License-Identifier: MIT
#

XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"

NO_SUDO="N"
ESUDO=""
CUR_TTY=/dev/tty0

# RetroDECK
if [ -f "/app/bin/retrodeck.sh" ]; then
  export LD_PRELOAD=""
  # loading the RetroDECK framework that even give access to variables such as roms_folder
  source /app/libexec/global.sh
  CUR_TTY=/dev/null

  if [ -z "$ports_folder" ]; then
    ports_folder="$rdhome/PortMaster"
  fi

  if [ -z "$roms_folder" ]; then
    roms_folder="$rdhome/roms"
  fi

  export controlfolder="/var/data"
  export directory="$ports_folder"
  OS_NAME_OVERRIDE="retrodeck"
  NO_SUDO="Y"
  touch "$HOME/no_es_restart"
elif [ -f "/var/config/retrodeck/retrodeck.cfg" ]; then
  export LD_PRELOAD=""
  # Fallback
  ports_folder="$(grep "ports_folder" /var/config/retrodeck/retrodeck.cfg | awk -F= '{print $2}')"
  roms_folder="$(grep "roms_folder" /var/config/retrodeck/retrodeck.cfg | awk -F= '{print $2}')"
  rdhome="$(grep "rdhome" /var/config/retrodeck/retrodeck.cfg | awk -F= '{print $2}')"
  CUR_TTY=/dev/null

  if [ -z "$ports_folder" ]; then
    ports_folder="$rdhome/PortMaster"
  fi

  if [ -z "$roms_folder" ]; then
    roms_folder="$rdhome/roms"
  fi

  export controlfolder="/var/data"
  export directory="$ports_folder"
  OS_NAME_OVERRIDE="retrodeck"
  NO_SUDO="Y"
  touch "$HOME/no_es_restart"
elif [ -f ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg ]; then
  export CUR_TTY=/dev/null
  LD_PRELOAD=""
  # Another Fallback
  ports_folder="$(grep "ports_folder" ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg | awk -F= '{print $2}')"
  roms_folder="$(grep "roms_folder" ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg | awk -F= '{print $2}')"
  rdhome="$(grep "rdhome" ~/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg | awk -F= '{print $2}')"

  if [ -z "$ports_folder" ]; then
    ports_folder="$rdhome/PortMaster"
  fi

  if [ -z "$roms_folder" ]; then
    roms_folder="$rdhome/roms"
  fi

  export controlfolder="$HOME/.var/app/net.retrodeck.retrodeck/data"
  export directory="$ports_folder"
  OS_NAME_OVERRIDE="retrodeck"
  NO_SUDO="Y"
  touch "$HOME/no_es_restart"
else
  # Fallback to non RetroDECK settings
  if [ -d "/opt/system/Tools/" ]; then
    controlfolder="/opt/system/Tools"
  elif [ -d "/mnt/mmc/MUOS" ]; then
    controlfolder="/mnt/mmc/MUOS"
    OS_NAME_OVERRIDE="muOS"
    CUR_TTY=/dev/null
  elif [ -d "/opt/tools/" ]; then
    controlfolder="/opt/tools"
  elif [ -d "/userdata/system" ]; then
    controlfolder="$XDG_DATA_HOME"
    mkdir -pv "$controlfolder/PortMaster"
    OS_NAME="batocera"
  else
    controlfolder="/roms/ports"
  fi

  if [[ -e "/usr/share/plymouth/themes/text.plymouth" ]]; then
    if [ ! -z "$(cat /etc/fstab | grep roms2 | tr -d '\0')" ]; then
      directory="roms2"
    else
      directory="roms"
    fi
  elif [ -d "/mnt/sdcard/ROMS/Ports/" ]; then
    directory="/mnt/sdcard/ROMS/"
  elif [ -d "/mnt/mmc/ROMS/Ports/" ]; then
    directory="/mnt/mmc/ROMS/"
  elif [ -d "/userdata/roms/ports" ]; then
    directory="userdata/roms"
  else
    directory="roms"
  fi
fi

TEMP_DIR=$(pwd)

if [ -f "/etc/os-release" ]; then
  source /etc/os-release
fi

if [ -n "$OS_NAME_OVERRIDE" ]; then
  OS_NAME="$OS_NAME_OVERRIDE"
fi

echo "-- Installing on $OS_NAME --"

if [ "$NO_SUDO" = "N" ]; then
  sudo echo "Testing for sudo..." > /dev/null 2>&1
  if [ $? != 0 ]; then
    ESUDO=""
  else
    ESUDO="sudo"
  fi
fi

if [[ -e "/usr/share/plymouth/themes/text.plymouth" ]]; then
  ES_NAME="emulationstation"
elif [ -d "/userdata/roms/ports" ]; then
  ES_NAME="batocera-es-swissknife"
else
  ES_NAME="emustation"
fi

RELOCATE_PM=""
if [ "${OS_NAME}" != "JELOS" ] && [ "${OS_NAME}" != "UnofficialOS" ] && [ "${OS_NAME}" != "ROCKNIX" ] && [ "${OS_NAME}" != "muOS" ] && [ "${OS_NAME}" != "retrodeck" ]; then
  RELOCATE_PM="Y"
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

if [ "$OS_NAME" = "retrodeck" ]; then
    $ESUDO mv -vf PortMaster/PortMaster.sh "/${roms_folder}/portmaster/PortMaster.sh" | tee -a $CUR_TTY
fi

if [ "$OS_NAME" = "muOS" ]; then
  mkdir -p /roms/ports/PortMaster
  cp -f "$controlfolder/PortMaster/control.txt" "/roms/ports/PortMaster/control.txt"
fi

$ESUDO mv temp_runtimes/*.squashfs PortMaster/libs/
$ESUDO rm -fR temp_runtimes/

if [ -f "$TEMP_DIR/runtimes.zip" ]; then
  cd PortMaster/libs/
  $ESUDO unzip -o "$TEMP_DIR/runtimes.zip" | tee -a $CUR_TTY
fi

if [ "$OS_NAME" = "retrodeck" ]; then
  $ESUDO rm -vf /$roms_folder/portmaster/Install*PortMaster*.sh | tee -a $CUR_TTY
  $ESUDO rm -vf /$roms_folder/portmaster/Restore*PortMaster*.sh | tee -a $CUR_TTY
else
  $ESUDO rm -vf /$directory/port_scripts/Install*PortMaster*.sh | tee -a $CUR_TTY
  $ESUDO rm -vf /$directory/port_scripts/Restore*PortMaster*.sh | tee -a $CUR_TTY
  $ESUDO rm -vf /$directory/ports/Install*PortMaster*.sh | tee -a $CUR_TTY
  $ESUDO rm -vf /$directory/ports/Restore*PortMaster*.sh | tee -a $CUR_TTY
fi

echo "Finished installing PortMaster" | tee -a $CUR_TTY
sleep 2

if [ ! -f "$HOME/no_es_restart" ]; then
  if [ "$OS_NAME" = "muOS" ]; then
    # YEET
    /opt/muos/script/mux/quit.sh reboot frontend &
    sleep 3
  elif [ "$OS_NAME" = "ROCKNIX" ]; then
    ## This is for the best.
    shutdown -r now
  elif [[ "$ES_NAME" == "batocera-es-swissknife" ]]; then
    ## Broken
    # batocera-es-swissknife --restart
    curl http://localhost:1234/reloadgames

    # Install our own shGenerator.py
    if ! grep 'gamecontrollerdb.txt' /usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py; then
      cp -f /usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py /usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py.bak

      if ! grep 'from generators.Generator import Generator' /usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py; then
        # New style relative imports
        cp -f $controlfolder/batocera/shGenerator.py /usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py
      else
        # Old style absolute imports
        cp -f $controlfolder/knulli/shGenerator.py /usr/lib/python3.11/site-packages/configgen/generators/sh/shGenerator.py
      fi

      batocera-save-overlay
    fi
  else
    $ESUDO systemctl restart $ES_NAME
  fi
else
  $ESUDO rm -f "$HOME/no_es_restart"
fi
