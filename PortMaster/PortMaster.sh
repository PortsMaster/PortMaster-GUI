#!/bin/bash
#
# SPDX-License-Identifier: MIT
#

export XDG_DATA_HOME=${XDG_DATA_HOME:-$HOME/.local/share}

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

## TODO: Change to PortMaster/tty when Johnnyonflame merges the changes in,
CUR_TTY=/dev/tty0

cd "$controlfolder"

> "$controlfolder/log.txt" && exec > >(tee "$controlfolder/log.txt") 2>&1

export TERM=linux
$ESUDO chmod 666 $CUR_TTY
printf "\033c" > $CUR_TTY

source "$controlfolder/utils/pmsplash.txt"

echo "Starting PortMaster." > $CUR_TTY

$ESUDO chmod -R +x .

## Autoinstallation Code
# This will automatically install zips found within the `PortMaster/autoinstall` / `ports/autoinstall` directory using harbourmaster
AUTOINSTALL_DIR_1="$controlfolder/autoinstall"
AUTOINSTALL_DIR_2="/$directory/ports/autoinstall"

if [ ! -d "$AUTOINSTALL_DIR_2" ]; then
  mkdir -p "$AUTOINSTALL_DIR_2"
fi

# Check if there are any files to process before starting the dialog
AUTOINSTALL_FILES=$(find "$AUTOINSTALL_DIR_1" "$AUTOINSTALL_DIR_2" -type f \( -name "*.zip" -o -name "*.squashfs" \) 2>/dev/null)

if [ -n "$AUTOINSTALL_FILES" ]; then
  source "$controlfolder/PortMasterDialog.txt"

  GW=$(PortMasterIPCheck)
  PortMasterDialogInit "no-check"

  PortMasterDialog "messages_begin"
  PortMasterDialog "message" "Auto-installation"

  # 1. Install PortMaster.zip first
  for autoinstall_dir in "$AUTOINSTALL_DIR_1" "$AUTOINSTALL_DIR_2"; do
    if [ -f "$autoinstall_dir/PortMaster.zip" ]; then
      if [ "$(PortMasterDialogResult "install" "$autoinstall_dir/PortMaster.zip")" = "OKAY" ]; then
        $ESUDO rm -f "$autoinstall_dir/PortMaster.zip"
        PortMasterDialog "message" "- SUCCESS: PortMaster.zip"
      else
        PortMasterDialog "message" "- FAILURE: PortMaster.zip"
      fi
      break # Stop after finding and processing the first one
    fi
  done

  # 2. Install runtimes.zip and/or runtimes.${DEVICE_ARCH}.zip
  RUNTIME_FILE_1="runtimes.zip"
  RUNTIME_FILE_2="runtimes.${DEVICE_ARCH}.zip"

  for autoinstall_dir in "$AUTOINSTALL_DIR_1" "$AUTOINSTALL_DIR_2"; do
    for runtime_zip in "$RUNTIME_FILE_1" "$RUNTIME_FILE_2"; do
      if [ -f "$autoinstall_dir/$runtime_zip" ]; then
        PortMasterDialog "message" "- Installing $runtime_zip, this could take a minute or two."
        $ESUDO unzip -o "$autoinstall_dir/$runtime_zip" -d "$controlfolder/libs"
        $ESUDO rm -f "$autoinstall_dir/$runtime_zip"
        PortMasterDialog "message" "- SUCCESS: $runtime_zip"
      fi
    done

    if ls "$autoinstall_dir"/runtimes*.zip >/dev/null 2>&1; then
      for file_name in "$autoinstall_dir"/runtimes*.zip; do
        if [ -f "$file_name" ]; then
            $ESUDO rm -f "$file_name"
            PortMasterDialog "message" "- Removing invalid runtimes.zip: $(basename "$file_name")"
        fi
      done
    fi
  done

  # 3. Install *.squashfs files
  for autoinstall_dir in "$AUTOINSTALL_DIR_1" "$AUTOINSTALL_DIR_2"; do
    if ls "$autoinstall_dir"/*.squashfs >/dev/null 2>&1; then
      for file_name in "$autoinstall_dir"/*.squashfs; do
        if [ -f "$file_name" ]; then
            $ESUDO mv -f "$file_name" "$controlfolder/libs"
            PortMasterDialog "message" "- SUCCESS: $(basename "$file_name")"
        fi
      done
    fi
  done

  # 4. Install remaining *.zip files
  for autoinstall_dir in "$AUTOINSTALL_DIR_1" "$AUTOINSTALL_DIR_2"; do
    if ls "$autoinstall_dir"/*.zip >/dev/null 2>&1; then
      for file_name in "$autoinstall_dir"/*.zip; do
        # Skip files we've already processed
        base_file=$(basename "$file_name")
        if [ "$base_file" = "PortMaster.zip" ]; then
          continue
        fi

        if [ -f "$file_name" ]; then
            if [ "$(PortMasterDialogResult "install" "$file_name")" = "OKAY" ]; then
              $ESUDO rm -f "$file_name"
              PortMasterDialog "message" "- SUCCESS: $base_file"
            else
              PortMasterDialog "message" "- FAILURE: $base_file"
            fi
        fi
      done
    fi
  done

  PortMasterDialog "messages_end"
  if [ -z "$GW" ]; then
    PortMasterDialogMessageBox "Finished running autoinstall.\n\nNo internet connection present so exiting."
    PortMasterDialogExit
    exit 0
  else
    PortMasterDialogMessageBox "Finished running autoinstall."
    PortMasterDialogExit
  fi
fi

## To help with testing.
# export PORTMASTER_CMDS="--debug"
# export HM_PERFTEST="Y"

export PYSDL2_DLL_PATH="/usr/lib"
$ESUDO rm -f "${controlfolder}/.pugwash-reboot"
while true; do
  $ESUDO ./pugwash $PORTMASTER_CMDS

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
elif [ -f "${controlfolder}/.weston-refresh" ]; then
  $ESUDO rm -f "${controlfolder}/.weston-refresh"
  $ESUDO systemctl restart ${UI_SERVICE}
elif [ -f "${controlfolder}/.emulationstation-refresh" ]; then
  $ESUDO rm -f "${controlfolder}/.emulationstation-refresh"
  $ESUDO systemctl restart emulationstation
elif [ -f "${controlfolder}/.batocera-es-refresh" ]; then
  $ESUDO rm -f "${controlfolder}/.batocera-es-refresh"
  # BROKEN :(
  # batocera-es-swissknife --restart
  curl http://localhost:1234/reloadgames
fi
