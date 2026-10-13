# SPDX-License-Identifier: MIT
#
# Starts pugwash headless in fifo_control mode and drives it the same way
# PortMaster/PortMasterDialog.txt does:
#
#   printf "WAIT" > $PM_DONE
#   echo $(printf "%s\1" "$@") > $PM_PIPE
#   wait until $PM_DONE != WAIT

import json
import os

import pytest

from conftest import PM_DIR, REPO_DIR, basic_port_files, start_fifo_gui, write_port_zip


pytestmark = pytest.mark.sdl

@pytest.fixture(params=["device", "git-checkout"])
def fifo_gui(request, hm_dirs, tmp_path):
    """
    "device" runs from a plain directory, "git-checkout" runs from the repo so
    harbourmaster switches to HM_TESTING mode, like a developer running it.
    """
    cwd = tmp_path if request.param == "device" else REPO_DIR

    env = dict(os.environ)
    env.update({
        'HM_TOOLS_DIR': str(hm_dirs['tools_dir']),
        'HM_PORTS_DIR': str(hm_dirs['ports_dir']),
        'HM_SCRIPTS_DIR': str(hm_dirs['scripts_dir']),
        })

    gui = start_fifo_gui(PM_DIR, cwd, env, tmp_path)

    try:
        yield gui

    finally:
        gui.kill()


def test_messages_and_progress(fifo_gui):
    assert fifo_gui.send("messages_begin") == "DONE"
    assert fifo_gui.send("message", "Hello from the tests") == "DONE"
    assert fifo_gui.send("progress", "Working", "50", "100") == "DONE"
    assert fifo_gui.send("progress_clear") == "DONE"
    assert fifo_gui.send("messages_end") == "DONE"

    assert fifo_gui.exit() == 0


def test_bad_commands(fifo_gui):
    ## Ending messages that were never started fails.
    assert fifo_gui.send("messages_end") == "FAIL"
    assert fifo_gui.send("message") == "FAIL"
    assert fifo_gui.send("not_a_command") == "DONE"

    assert fifo_gui.exit() == 0


def test_register(fifo_gui):
    assert fifo_gui.send("register_set_info", "ports", "game", "title:Game", "size:10") == "DONE"
    assert json.loads(fifo_gui.send("register_dump", "ports")) == {"game": {"title": "Game", "size": "10"}}
    assert fifo_gui.send("register_clear", "ports") == "DONE"
    assert fifo_gui.send("register_dump", "ports") == "FAIL"

    assert fifo_gui.exit() == 0


def test_install_local_zip(fifo_gui, hm_dirs, tmp_path):
    ## Runs HarbourMaster.install_port on pugwash's worker thread.
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())

    assert fifo_gui.send("messages_begin") == "DONE"
    assert fifo_gui.send("install", str(zip_file)) == "OKAY"
    assert fifo_gui.send("messages_end") == "DONE"

    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()
    assert (hm_dirs['ports_dir'] / "testport" / "port.json").is_file()

    assert fifo_gui.exit() == 0


def test_install_bad_zip_fails(fifo_gui, tmp_path):
    zip_file = write_port_zip(tmp_path / "bad.zip", {"Bad.sh": "#!/bin/bash\n"})

    assert fifo_gui.send("install", str(zip_file)) == "FAIL"
    assert fifo_gui.exit() == 0


def test_install_garbage_then_keep_going(fifo_gui, hm_dirs, tmp_path):
    ## A broken autoinstall zip must answer FAIL and leave pugwash working.
    (tmp_path / "garbage.zip").write_bytes(b"not a zip")
    good = write_port_zip(tmp_path / "testport.zip", basic_port_files())

    assert fifo_gui.send("messages_begin") == "DONE"
    assert fifo_gui.send("install", str(tmp_path / "garbage.zip")) == "FAIL"
    assert fifo_gui.send("install", str(good)) == "OKAY"
    assert fifo_gui.send("messages_end") == "DONE"

    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()
    assert fifo_gui.exit() == 0
