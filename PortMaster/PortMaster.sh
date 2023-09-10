#!/bin/bash

if [ -d "/opt/system/Tools/PortMaster/" ]; then
  controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
  controlfolder="/opt/tools/PortMaster"
else
  controlfolder="/roms/ports/PortMaster"
fi

source $controlfolder/control.txt
if [ -z ${TASKSET+x} ]; then
  source $controlfolder/tasksetter
fi

get_controls

## TODO: Change to PortMaster/tty when Johnnyonflame merges the changes in,
CUR_TTY=/dev/tty0


cd "$controlfolder"

export TERM=linux
$ESUDO chmod 666 $CUR_TTY
printf "\033c" > $CUR_TTY

echo "Starting PortMaster." > $CUR_TTY

$ESUDO chmod -R +x .

export PYSDL2_DLL_PATH="/usr/lib"
$ESUDO rm -f "${controlfolder}/.pugwash-reboot"
while true; do
  $ESUDO ./pugwash 2>&1 | $ESUDO tee -a ./log.txt

  if [ ! -f "${controlfolder}/.pugwash-reboot" ]; then
    break;
  fi

  $ESUDO rm -f "${controlfolder}/.pugwash-reboot"
done

unset LD_LIBRARY_PATH
unset SDL_GAMECONTROLLERCONFIG
$ESUDO systemctl restart oga_events &
printf "\033c" > $CUR_TTY

if [ -f "${controlfolder}/.emustation-refresh" ]; then
  $ESUDO rm -f "${controlfolder}/.emustation-refresh"
  $ESUDO systemctl restart emustation
elif [ -f "${controlfolder}/.emulationstation-refresh" ]; then
  $ESUDO rm -f "${controlfolder}/.emulationstation-refresh"
  $ESUDO systemctl restart emulationstation
fi
