# SPDX-License-Identifier: MIT
#
# device_info.txt itself, run on this machine. Ports run it through whatever
# /bin/bash is, and on some firmwares (TrimUI Smart Pro 1.0.4) that's BusyBox.

import re
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


def run_version_block(command, root, cfw_name):
    ## Just the CFW_VERSION section, with its absolute paths moved under root.
    text = (PM_DIR / "device_info.txt").read_text()
    block = text[text.index('export CFW_VERSION="Unknown"'):text.index("# 3c.")]
    block = re.sub(r'(?<=[\s"])/(etc|usr|boot|userdata|opt|var|mnt)/', lambda m: f"{root}/{m.group(1)}/", block)
    script = f'CFW_NAME="{cfw_name}"\n{block}\necho "$CFW_VERSION"\n'
    result = subprocess.run(command + ["-c", script], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)
    assert result.returncode == 0, result.stdout
    return result.stdout.strip()


KNULLI_OS_RELEASE = 'NAME=Batocera.linux\nPRETTY_NAME=\\"Batocera.linux {0}\\"\nVERSION={0}\nID=buildroot\nVERSION_ID=2024.11\nOS_NAME="knulli"\n'


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
@pytest.mark.parametrize("cfw_name", ["knulli", "Batocera.linux"])
@pytest.mark.parametrize("version", ["gladiator", "42", "44-dev"])
def test_knulli_version_from_os_release(shell, cfw_name, version, tmp_path):
    ## knulli has no knulli.version file: the version is Batocera's VERSION=, not
    ## Buildroot's VERSION_ID, and never a made-up "scarab".
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "os-release").write_text(KNULLI_OS_RELEASE.format(version))

    assert run_version_block(shell_or_skip(shell), tmp_path, cfw_name) == version


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
def test_knulli_version_files(shell, tmp_path):
    command = shell_or_skip(shell)
    (tmp_path / "usr" / "share" / "batocera").mkdir(parents=True)
    (tmp_path / "usr" / "share" / "batocera" / "batocera.version").write_text("41 2024/12/10 12:00\n")
    assert run_version_block(command, tmp_path, "knulli") == "41"

    (tmp_path / "etc").mkdir()
    (tmp_path / "etc" / "knulli.version").write_text("scarab\r\n")
    assert run_version_block(command, tmp_path, "knulli") == "scarab"


@pytest.mark.parametrize("shell", SHELLS, ids=["bash", "busybox"])
def test_knulli_version_unknown(shell, tmp_path):
    assert run_version_block(shell_or_skip(shell), tmp_path, "knulli") == "Unknown"
