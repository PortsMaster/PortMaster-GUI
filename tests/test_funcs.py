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

    def run(script, with_portmsg=False, **extra_env):
        portmsg = pm / "portmsg.aarch64"
        if with_portmsg:
            portmsg.write_text("#!/bin/bash\n" + LOG)
            portmsg.chmod(portmsg.stat().st_mode | stat.S_IXUSR)

        env = dict(os.environ, FAKE_CALLS=str(calls), DEVICE_ARCH="aarch64", ESUDO="")
        env.pop("LD_LIBRARY_PATH", None)
        env.update(extra_env)
        result = subprocess.run(
            ["bash", "-c", f'controlfolder="{pm}"; source "$controlfolder/funcs.txt"\n{script}\nwait'],
            env=env, cwd=str(tmp_path), timeout=60,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        assert result.returncode == 0, result.stdout
        return result.stdout, calls.read_text().splitlines() if calls.is_file() else []

    return run


def test_funcs_version(funcs):
    ## 4: pm_message / pm_show_error take portmsg options, pm_message_close.
    ## 5: PM_LIBRARY_PATH.
    output, _ = funcs('echo "version=$PM_FUNCS_VERSION"; type pm_message_close > /dev/null && echo has-close; '
                      'echo "libs=${PM_LIBRARY_PATH:+set}"')
    assert "version=5" in output
    assert "has-close" in output
    assert "libs=set" in output


@pytest.mark.parametrize("arch, port_32bit, ld_path, expected_libs, expected_ld", [
    ## aarch64 devices get armhf's too, for 32-bit ports; after the system's paths.
    ("aarch64", None, "/usr/lib/extra", "libs.aarch64:libs.armhf", "/usr/lib/extra:{libs}"),
    ## Set before control.txt: armhf's first.
    ("aarch64", "Y", "", "libs.armhf:libs.aarch64", "{libs}"),
    ("x86_64", None, None, "libs.x86_64", "{libs}"),
    ("armhf", None, "/a:/b", "libs.armhf", "/a:/b:{libs}"),
    ])
def test_pm_library_path(funcs, arch, port_32bit, ld_path, expected_libs, expected_ld):
    env = {'DEVICE_ARCH': arch}
    if port_32bit is not None:
        env['PORT_32BIT'] = port_32bit
    if ld_path is not None:
        env['LD_LIBRARY_PATH'] = ld_path

    output, _ = funcs('echo "PM=$PM_LIBRARY_PATH"; echo "LD=$LD_LIBRARY_PATH"', **env)
    pm = output.split("PM=", 1)[1].split("\n", 1)[0]
    ld = output.split("LD=", 1)[1].split("\n", 1)[0]

    ## In the controlfolder (the fixture's fake PortMaster folder).
    folder = pm.split(":")[0].rsplit("/", 1)[0]
    assert folder.endswith("/PortMaster")
    libs = ":".join(f"{folder}/{name}" for name in expected_libs.split(":"))
    assert pm == libs
    ## No empty entry (which would mean the current folder) when LD_LIBRARY_PATH was empty.
    assert ld == expected_ld.format(libs=libs) and "::" not in ld and not ld.startswith(":")


def test_pm_library_path_folders_ship():
    ## The folders are in the checkout (and so in PortMaster.zip) for every architecture.
    for arch in ("aarch64", "armhf", "x86_64"):
        assert (PM_DIR / f"libs.{arch}").is_dir()


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


################################################################################
## LD_LIBRARY_PATH appends in the shell files every port sources
def _shipped_shell_files():
    for path in sorted(PM_DIR.rglob("*")):
        if not path.is_file() or "runtimes" in path.parts or path.suffix not in (".txt", ".sh"):
            continue

        try:
            yield path, path.read_text(errors="replace")
        except OSError:
            pass


def test_no_bare_ld_library_path_appends():
    ## $LD_LIBRARY_PATH:/x with LD_LIBRARY_PATH empty leaves an empty entry, which makes the
    ## loader search the current folder (control.txt did that on JELOS/AmberELEC & co).
    import re
    ## $LD_LIBRARY_PATH: or ${LD_LIBRARY_PATH}:, not the guarded ${LD_LIBRARY_PATH:+...}.
    bare = re.compile(r'LD_LIBRARY_PATH="?\$(LD_LIBRARY_PATH|\{LD_LIBRARY_PATH\}):')

    found = [
        f"{path.relative_to(PM_DIR)}:{number}: {line.strip()}"
        for path, text in _shipped_shell_files()
        for number, line in enumerate(text.splitlines(), 1)
        if bare.search(line) and not line.lstrip().startswith("#")]

    assert found == []


@pytest.mark.parametrize("before, expected", [
    (None, "/usr/lib32"),
    ("", "/usr/lib32"),
    ("/opt/lib", "/opt/lib:/usr/lib32"),
    ])
def test_guarded_append(before, expected):
    ## The form control.txt uses now.
    env = {key: value for key, value in os.environ.items() if key != "LD_LIBRARY_PATH"}
    if before is not None:
        env["LD_LIBRARY_PATH"] = before

    result = subprocess.run(
        ["bash", "-c", 'export LD_LIBRARY_PATH=${LD_LIBRARY_PATH:+$LD_LIBRARY_PATH:}/usr/lib32; printf %s "$LD_LIBRARY_PATH"'],
        env=env, stdout=subprocess.PIPE, check=True)

    assert result.stdout.decode() == expected
