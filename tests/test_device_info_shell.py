# SPDX-License-Identifier: MIT
#
# device_info.txt itself, run on this machine. Ports run it through whatever
# /bin/bash is, and on some firmwares (TrimUI Smart Pro 1.0.4) that's BusyBox.

import shutil
import subprocess

import pytest

from conftest import PM_DIR

SHELLS = [("bash",), ("busybox", "sh")]


def shell_or_skip(shell):
    if shutil.which(shell[0]) is None:
        pytest.skip(f"needs {shell[0]}")

    return list(shell)


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
def test_device_info_parses(shell):
    command = shell_or_skip(shell)
    result = subprocess.run(command + ["-n", str(PM_DIR / "device_info.txt")], stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert result.returncode == 0, result.stdout


def run_device_info(command, tmp_path):
    folder = tmp_path / command[0]
    folder.mkdir()
    shutil.copy(str(PM_DIR / "device_info.txt"), str(folder / "device_info.txt"))
    env = {'PATH': "/usr/bin:/bin:/usr/sbin:/sbin", 'controlfolder': str(folder), 'HOME': str(tmp_path)}
    result = subprocess.run(
        command + [str(folder / "device_info.txt"), "-f"], cwd=str(folder), env=env, timeout=120,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    ## Probes may grumble on stderr on a device; a shell that can't run it says so.
    assert result.returncode == 0, result.stderr
    assert "syntax error" not in result.stderr, result.stderr

    cached = list(folder.glob("device_info_*.env"))
    assert len(cached) == 1, (result.stdout, list(folder.iterdir()))
    return cached[0].name, cached[0].read_text()


def test_device_info_same_in_busybox(tmp_path):
    ## The same answers, and a cache file, whichever shell runs it.
    bash = run_device_info(shell_or_skip(SHELLS[0]), tmp_path)
    busybox = run_device_info(shell_or_skip(SHELLS[1]), tmp_path)

    assert bash == busybox
    assert "DEVICE_CAPABILITIES=" in bash[1] and "analog_0" in bash[1]
    assert "/" not in bash[0]
