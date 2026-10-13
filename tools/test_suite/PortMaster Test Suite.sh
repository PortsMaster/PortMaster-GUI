#!/bin/bash
# PORTMASTER: pmtest.zip, PortMaster Test Suite.sh
#
# SPDX-License-Identifier: MIT
#
# Installs the PortMaster build in pmtest/PortMaster.zip, runs every test on this
# device, shows a summary and saves a report zip in pmtest/reports/.

XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

if [ -d "/opt/system/Tools/PortMaster/" ]; then
  controlfolder="/opt/system/Tools/PortMaster"
elif [ -d "/opt/tools/PortMaster/" ]; then
  controlfolder="/opt/tools/PortMaster"
elif [ -d "$XDG_DATA_HOME/PortMaster/" ]; then
  controlfolder="$XDG_DATA_HOME/PortMaster"
else
  controlfolder="/roms/ports/PortMaster"
fi

source $controlfolder/control.txt
[ -f "${controlfolder}/mod_${CFW_NAME}.txt" ] && source "${controlfolder}/mod_${CFW_NAME}.txt"
get_controls

## Where the port's folder is: next to this script on most CFWs, in the ports folder otherwise.
GAMEDIR="$(cd "$(dirname "$0")" && pwd)/pmtest"
[ -d "$GAMEDIR" ] || GAMEDIR="/$directory/ports/pmtest"
cd "$GAMEDIR" || exit 1

## The python PortMaster itself uses on this CFW.
if [ -d "/opt/python/bin" ]; then
  ## muOS
  export PATH="/opt/python/bin:$PATH"
  export LD_LIBRARY_PATH="/opt/python/lib:$LD_LIBRARY_PATH"
fi

PY=""
for candidate in "$PM_PYTHON" python3 python; do
  if [ -n "$candidate" ] && command -v "$candidate" > /dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done

if [ -z "$PY" ]; then
  pm_message "PortMaster Test Suite: no python3 found on this device."
  sleep 5
  pm_finish
  exit 1
fi

export controlfolder
mkdir -p "$GAMEDIR/reports"

pm_platform_helper "$PY"
"$PY" "$GAMEDIR/suite.py" 2>&1 | tee "$GAMEDIR/reports/last-run.txt"

pm_finish
