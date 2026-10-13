# SPDX-License-Identifier: MIT
#
# PortMaster/funcs.txt, which ports source for pm_message & co.
#
# It runs against a fake controlfolder: PortMasterDialog.txt (the pugwash fallback)
# and portmsg are fakes that write what they were asked to do into calls.txt.

import os
import shutil
import stat
import subprocess

import pytest

from conftest import PM_DIR


pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")

LOG = 'echo "$(basename "$0") $*" >> "$FAKE_CALLS"\n'


@pytest.fixture
def funcs(tmp_path):
    pm = tmp_path / "PortMaster"
    pm.mkdir()
    shutil.copy(str(PM_DIR / "funcs.txt"), str(pm / "funcs.txt"))
    (pm / "version").write_text("2026-10-13_0069\n")
    (pm / "PortMasterDialog.txt").write_text(
        'PortMasterDialogInit() { echo "PortMasterDialogInit $*" >> "$FAKE_CALLS"; }\n'
        'PortMasterDialog() { echo "PortMasterDialog $*" >> "$FAKE_CALLS"; }\n'
        'PortMasterDialogExit() { echo "PortMasterDialogExit" >> "$FAKE_CALLS"; }\n')

    calls = tmp_path / "calls.txt"

    def run(script, with_portmsg=False):
        portmsg = pm / "portmsg.aarch64"
        if with_portmsg:
            portmsg.write_text("#!/bin/bash\n" + LOG)
            portmsg.chmod(portmsg.stat().st_mode | stat.S_IXUSR)

        env = dict(os.environ, FAKE_CALLS=str(calls), DEVICE_ARCH="aarch64", ESUDO="")
        result = subprocess.run(
            ["bash", "-c", f'controlfolder="{pm}"; source "$controlfolder/funcs.txt"\n{script}\nwait'],
            env=env, cwd=str(tmp_path), timeout=60,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        assert result.returncode == 0, result.stdout
        return result.stdout, calls.read_text().splitlines() if calls.is_file() else []

    return run


def test_funcs_version(funcs):
    ## 4: pm_message / pm_show_error take portmsg options, pm_message_close.
    output, _ = funcs('echo "version=$PM_FUNCS_VERSION"; type pm_message_close > /dev/null && echo has-close')
    assert "version=4" in output
    assert "has-close" in output


def test_funcs_sourced_twice_is_a_no_op(funcs):
    output, _ = funcs('PM_FUNCS_VERSION=99; source "$controlfolder/funcs.txt"; echo "version=$PM_FUNCS_VERSION"')
    assert "version=99" in output


def test_pm_message_uses_portmsg(funcs):
    _, calls = funcs('pm_message "Loading" --title "Test Port"', with_portmsg=True)
    assert calls == ["portmsg.aarch64 --wait --type info --text Loading --title Test Port"]


def test_pm_message_timeout_does_not_wait(funcs):
    _, calls = funcs('pm_message "Loading" --timeout 2', with_portmsg=True)
    assert calls == ["portmsg.aarch64 --type info --text Loading --timeout 2"]


def test_pm_show_error_uses_portmsg(funcs):
    _, calls = funcs('pm_show_error "Missing files" --title "Oops"', with_portmsg=True)
    assert calls == ["portmsg.aarch64 --text Missing files --title Oops"]


def test_pm_message_falls_back_to_pugwash(funcs):
    ## No portmsg for this device's architecture.
    output, calls = funcs('pm_message "Loading"')
    assert "Loading" in output
    assert calls == ["PortMasterDialogInit no-harbour", "PortMasterDialog messages_begin", "PortMasterDialog message Loading"]
