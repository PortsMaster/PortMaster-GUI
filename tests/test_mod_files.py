# SPDX-License-Identifier: MIT
#
# mod_<CFW>.txt files, which ports source after control.txt.

import shutil
import subprocess
from pathlib import Path

import pytest

PM_DIR = Path(__file__).resolve().parent.parent / "PortMaster"

## get_controls as control.txt's, with no device GUID: the whole gamecontrollerdb.
FAKE_GET_CONTROLS = 'get_controls() { sdl_controllerconfig="$(printf "%0${SDL_SIZE}d" 0)"; }\n'


def run_bash(script, size=200000):
    result = subprocess.run(
        ## (No core file if bash does crash.)
        ["bash", "-c", f'ulimit -c 0\ncontrolfolder="{PM_DIR}"\nSDL_SIZE={size}\n' + FAKE_GET_CONTROLS + script],
        capture_output=True, text=True, timeout=30)
    return result


@pytest.mark.parametrize("sources", [1, 2, 3])
def test_emuelec_get_controls_clears_the_whole_db(sources):
    ## Some ports (Mystik Belle, The Flayed Man, The Sphinx of Time) source it twice: wrapping
    ## the wrapper made get_controls call itself until bash crashed.
    result = run_bash(
        'source "$controlfolder/mod_EmuELEC.txt"\n' * sources +
        'get_controls\necho "len=${#sdl_controllerconfig}"\n')

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "len=0"


def test_emuelec_get_controls_keeps_a_small_config():
    ## One device's mappings, as SDL_GAMECONTROLLERCONFIG should have.
    result = run_bash('source "$controlfolder/mod_EmuELEC.txt"\nget_controls\necho "len=${#sdl_controllerconfig}"\n', size=300)

    assert result.stdout.strip() == "len=300"


## get_controls as control.txt's: SDL reads PortMaster's copy in /tmp.
FAKE_GET_CONTROLS_FILE = ('get_controls() { export SDL_GAMECONTROLLERCONFIG_FILE=/tmp/gamecontrollerdb.txt; '
                          'sdl_controllerconfig="$(printf "%0${SDL_SIZE}d" 0)"; }\n')


def emuelec_db_file(tmp_path, user_db):
    """SDL_GAMECONTROLLERCONFIG_FILE after get_controls on EmuELEC, with this user database (None: none)."""
    home = tmp_path / "home"
    db = home / ".config" / "SDL-GameControllerDB" / "gamecontrollerdb.txt"
    db.parent.mkdir(parents=True)
    if user_db is not None:
        db.write_text(user_db)
    result = run_bash(f'HOME="{home}"\n' + FAKE_GET_CONTROLS_FILE +
                      'source "$controlfolder/mod_EmuELEC.txt"\nget_controls\necho "$SDL_GAMECONTROLLERCONFIG_FILE"\n')
    assert result.returncode == 0, result.stderr
    return result.stdout.strip(), str(db)


def test_emuelec_uses_the_users_mappings(tmp_path):
    ## EmuELEC's own database has the buttons the user mapped.
    used, db = emuelec_db_file(tmp_path, "03000000aaaa,My pad,a:b0,platform:Linux,\n")
    assert used == db


@pytest.mark.parametrize("user_db", [None, ""])
def test_emuelec_without_user_mappings_keeps_portmasters(tmp_path, user_db):
    ## No database of its own (or an empty one): PortMaster's, or SDL would have no mappings at all.
    used, _ = emuelec_db_file(tmp_path, user_db)
    assert used == "/tmp/gamecontrollerdb.txt"


def test_hippos_control_uses_the_launchers_mappings(tmp_path):
    ## HippOS's launcher passes SDL_GAMECONTROLLERCONFIG; ports read a gamecontrollerdb file.
    result = subprocess.run(
        ["bash", "-c",
         'source() { :; }\n'
         'SDL_GAMECONTROLLERCONFIG="030000005e0400008e02000014010000,Xbox 360,a:b0,platform:Linux,"\n'
         ## A scratch controlfolder: control.txt renames the bundled x86_64 binaries in it.
         f'HOME="{tmp_path}"\ncontrolfolder="{tmp_path}"\nXDG_RUNTIME_DIR="{tmp_path}"\n'
         f'. "{PM_DIR}/hippos/control.txt"\n'
         'get_controls\necho "$SDL_GAMECONTROLLERCONFIG_FILE|$sdl_controllerconfig|$ESUDO"\n'],
        capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr
    db_file, mappings, esudo = result.stdout.strip().split("|")
    assert db_file == f"{tmp_path}/gamecontrollerdb.txt"
    assert mappings.startswith("030000005e0400008e02000014010000,Xbox 360")
    assert esudo == f"{tmp_path}/hippos/esudo"


def test_hippos_control_without_a_controller_keeps_the_db_out_of_the_environment(tmp_path):
    ## No launcher mappings: get_controls must not load the whole gamecontrollerdb (E2BIG).
    result = subprocess.run(
        ["bash", "-c",
         'source() { :; }\nunset SDL_GAMECONTROLLERCONFIG\n'
         f'HOME="{tmp_path}"\ncontrolfolder="{tmp_path}"\nXDG_RUNTIME_DIR="{tmp_path}"\n'
         f'cp "{PM_DIR}/gamecontrollerdb.txt" "{tmp_path}/gamecontrollerdb.txt"\n'
         f'. "{PM_DIR}/hippos/control.txt"\n'
         'get_controls\necho "${#sdl_controllerconfig}|$SDL_GAMECONTROLLERCONFIG_FILE"\n'],
        capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"0|{tmp_path}/gamecontrollerdb.txt"


@pytest.mark.parametrize("line, runs_as", [
    ## PortMaster's own lines (PortMasterDialog.txt, funcs.txt, pm_launch.txt).
    ('$ESUDO env -u SDL_VIDEODRIVER LD_LIBRARY_PATH="" $controlfolder/pugwash --quiet fifo_control "$PM_PIPE" "$PM_DONE"', "user"),
    ('$ESUDO ./pugwash', "user"),
    ('$ESUDO mkdir -p /dev/shm/portmaster', "user"),
    ('$ESUDO tee "$PM_DONE"', "user"),
    ('$ESUDO tar -C "$controlfolder/pylibs/resources" -xf "$controlfolder/pylibs/resources/NotoSans.tar.xz"', "user"),
    ('$ESUDO env LD_LIBRARY_PATH="" "$controlfolder/portmsg.x86_64" --type info', "user"),
    ('$ESUDO kill -9 1234', "user"),
    ('$ESUDO chmod 666 /dev/uinput', "sudo"),
    ('$ESUDO systemctl restart oga_events', "sudo"),
    ## A port with runtimes (Crop and Claw 2): its game and config are the user's, the mounts need root.
    ('$ESUDO mkdir -p "$GAMEDIR/conf"', "user"),
    ('$ESUDO mkdir -p "$weston_dir"', "user"),
    ('$ESUDO mount "$controlfolder/libs/${weston_runtime}.squashfs" "$weston_dir"', "sudo"),
    ('$ESUDO env CRUSTY_BLOCK_INPUT=1 $weston_dir/westonwrap.sh headless noop kiosk crusty_x11egl', "user"),
    ('$ESUDO umount "$weston_dir"', "sudo"),
    ## File operations on system paths.
    ('echo 1 | $ESUDO tee /sys/devices/system/cpu/cpu0/online', "sudo"),
    ('$ESUDO cp -f "$controlfolder/gamecontrollerdb.txt" /etc/gamecontrollerdb.txt', "sudo"),
    ## ESUDO handed to another program as a command (the Westonpack 0.2.8 test suite's setsid launcher).
    ('setsid --wait bash -c \'exec "$@"\' session $ESUDO env WP=1 ./pugwash', "user"),
    ('setsid --wait bash -c \'exec "$@"\' session $ESUDO mount "$controlfolder/libs/${weston_runtime}.squashfs" "$weston_dir"', "sudo"),
    ])
def test_hippos_esudo_decides_by_command(tmp_path, line, runs_as):
    ## Ports run as the user, so PortMaster's files must not end up root's; the rest needs sudo.
    shutil.copytree(PM_DIR / "hippos", tmp_path / "hippos")
    stubs = tmp_path / "bin"
    stubs.mkdir()
    ## Every command only says how it was run: nothing is mounted, written or killed.
    for cmd in ("env", "pugwash", "mkdir", "rm", "tee", "tar", "cp", "kill", "chmod", "mount", "umount", "systemctl", "sudo"):
        stub = stubs / cmd
        stub.write_text(f"#!/bin/sh\necho {'sudo' if cmd == 'sudo' else 'user'}\n")
        stub.chmod(0o755)
    shutil.copy(stubs / "pugwash", tmp_path / "pugwash")

    result = subprocess.run(
        ["bash", "-c",
         'source() { :; }\n'
         f'PATH="{stubs}:$PATH"\nHOME="{tmp_path}"\ncontrolfolder="{tmp_path}"\nXDG_RUNTIME_DIR="{tmp_path}"\n'
         f'. "{PM_DIR}/hippos/control.txt" > /dev/null\n'
         'PM_PIPE=/dev/shm/portmaster/pm_input\nPM_DONE=/dev/shm/portmaster/pm_done\n'
         f'weston_runtime=weston_pkg_0.2\nweston_dir=/tmp/weston\nGAMEDIR="{tmp_path}/game"\n'
         f'cd "{tmp_path}"\n'
         f'{line}\n'],
        capture_output=True, text=True, timeout=30)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == runs_as
