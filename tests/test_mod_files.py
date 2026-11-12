# SPDX-License-Identifier: MIT
#
# mod_<CFW>.txt files, which ports source after control.txt.

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
