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
