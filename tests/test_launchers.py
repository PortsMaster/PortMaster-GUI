# SPDX-License-Identifier: MIT
#
# The launchers: PortMaster.sh and <cfw>/PortMaster.txt are stubs that find
# $controlfolder and source utils/pm_launch.txt (with <cfw>/launch_hooks.txt).
#
# pm_launch.txt runs here against a fake controlfolder: control.txt, pugwash,
# PortMasterDialog.txt and the system tools (systemctl, sudo, ...) are fakes that
# write what they were asked to do into calls.txt.

import os
import shutil
import stat
import subprocess

import pytest

from conftest import PM_DIR

## stub file -> hooks folder it passes to pm_launch.txt (None: generic)
STUBS = {
    "PortMaster.sh": None,
    "muos/PortMaster.txt": "muos",
    "miyoo/PortMaster.txt": "miyoo",
    "spruce/PortMaster.txt": "spruce",
    "trimui/PortMaster.txt": "trimui",
    "retrodeck/PortMaster.txt": "retrodeck",
    }

SHELL_FILES = [
    "utils/pm_launch.txt",
    *STUBS,
    *(f"{cfw}/launch_hooks.txt" for cfw in STUBS.values() if cfw is not None),
    ]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def write_exe(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


LOG = 'echo "$(basename "$0") $*" >> "$FAKE_CALLS"\n'


class Launcher:
    def __init__(self, tmp_path):
        self.root = tmp_path
        self.pm = tmp_path / "data" / "PortMaster"
        self.calls_file = tmp_path / "calls.txt"
        self.ports_dir = tmp_path / "roms" / "ports"
        self.bin = tmp_path / "bin"

        pm = self.pm
        (pm / "utils").mkdir(parents=True)
        shutil.copy(PM_DIR / "utils" / "pm_launch.txt", pm / "utils" / "pm_launch.txt")
        for cfw in STUBS.values():
            if cfw is not None:
                (pm / cfw).mkdir()
                shutil.copy(PM_DIR / cfw / "launch_hooks.txt", pm / cfw / "launch_hooks.txt")

        (pm / "utils" / "pmsplash.txt").write_text("")
        control = (
            f'directory="{tmp_path / "roms"}"\n'
            'CFW_NAME="Test"\n'
            'ESUDO=""\n'
            'get_controls() { echo "get_controls" >> "$FAKE_CALLS"; }\n'
            'pm_message() { echo "pm_message $*" >> "$FAKE_CALLS"; }\n'
            )
        (pm / "control.txt").write_text(control)
        (pm / "retrodeck" / "control.txt").write_text(control)
        (pm / "device_info.txt").write_text(control)

        ## The GUI: leaves the markers the test asks for, and asks for a restart once if told to.
        write_exe(pm / "pugwash", LOG + (
            'for marker in $FAKE_MARKERS; do touch "$marker"; done\n'
            'if [ -f "$FAKE_REBOOT_ONCE" ]; then rm -f "$FAKE_REBOOT_ONCE"; touch .pugwash-reboot; fi\n'
            ))

        (pm / "PortMasterDialog.txt").write_text(
            'PortMasterIPCheck() { echo "$FAKE_GW"; }\n'
            'PortMasterDialogInit() { echo "PortMasterDialogInit $*" >> "$FAKE_CALLS"; }\n'
            'PortMasterDialog() { echo "PortMasterDialog $*" >> "$FAKE_CALLS"; }\n'
            'PortMasterDialogExit() { echo "PortMasterDialogExit" >> "$FAKE_CALLS"; }\n'
            )

        write_exe(pm / "muos" / "image_smash.txt", LOG)
        write_exe(pm / "trimui" / "image_smash.txt", LOG)
        write_exe(pm / "trimui" / "update.txt", LOG)

        for tool in ("systemctl", "sudo", "curl", "pkill", "mount", "umount", "df"):
            write_exe(self.bin / tool, LOG)

        self.env = {
            'PATH': f"{self.bin}:{os.environ['PATH']}",
            'HOME': str(tmp_path / "home"),
            'XDG_DATA_HOME': str(tmp_path / "data"),
            'PM_CUR_TTY': str(tmp_path / "tty"),
            'FAKE_CALLS': str(self.calls_file),
            'FAKE_GW': "192.168.1.1",
            'FAKE_MARKERS': "",
            'FAKE_REBOOT_ONCE': str(tmp_path / "reboot-once"),
            }

    def run(self, cfw=None, stub=None, **env):
        """Runs `stub` (a launcher file), or sources pm_launch.txt for `cfw` as its stub would."""
        run_env = dict(self.env)
        run_env.update(env)

        if stub is not None:
            command = ["bash", str(PM_DIR / stub)]
        else:
            command = ["bash", "-c", f'controlfolder="{self.pm}"; source "$controlfolder/utils/pm_launch.txt" {cfw or ""}']

        result = subprocess.run(
            command, env=run_env, cwd=str(self.root), timeout=60,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        self.output = result.stdout
        assert result.returncode == 0, result.stdout
        return self.calls()

    def calls(self):
        if not self.calls_file.is_file():
            return []

        return self.calls_file.read_text().splitlines()

    def markers(self, *names):
        return " ".join(str(self.pm / name) for name in names)


@pytest.fixture
def launcher(tmp_path):
    return Launcher(tmp_path)


## -- the files themselves

@pytest.mark.parametrize("name", SHELL_FILES)
def test_bash_syntax(name):
    subprocess.run(["bash", "-n", str(PM_DIR / name)], check=True)


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="needs shellcheck")
def test_shellcheck_errors():
    result = subprocess.run(
        ["shellcheck", "-s", "bash", "--severity=error", *SHELL_FILES],
        cwd=str(PM_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("stub, cfw", STUBS.items())
def test_stub_sources_shared_launcher(stub, cfw):
    lines = [line.strip() for line in (PM_DIR / stub).read_text().splitlines() if line.strip()]

    expected = 'source "$controlfolder/utils/pm_launch.txt"'
    if cfw is not None:
        expected += f" {cfw}"
        assert (PM_DIR / cfw / "launch_hooks.txt").is_file()

    assert lines[-1] == expected
    assert sum(1 for line in lines if not line.startswith('#')) < 15, "stubs only find $controlfolder"


## -- generic launcher (ArkOS, ROCKNIX, ...)

def test_generic_stub_runs_gui(launcher):
    calls = launcher.run(stub="PortMaster.sh")

    assert calls == ["get_controls", "pugwash ", "systemctl restart oga_events"]
    assert (launcher.pm / "log.txt").is_file()


def test_generic_restarts_gui_on_request(launcher):
    (launcher.root / "reboot-once").touch()

    calls = launcher.run()

    assert calls.count("pugwash ") == 2
    assert not (launcher.pm / ".pugwash-reboot").exists()


def test_generic_portmaster_cmds(launcher):
    assert "pugwash --debug" in launcher.run(PORTMASTER_CMDS="--debug")


@pytest.mark.parametrize("marker, command", [
    (".emulationstation-refresh", "systemctl restart emulationstation"),
    (".emustation-refresh", "systemctl restart emustation"),
    (".weston-refresh", "systemctl restart weston.service"),
    (".batocera-es-refresh", "curl http://localhost:1234/reloadgames"),
    ])
def test_generic_frontend_refresh(launcher, marker, command):
    calls = launcher.run(FAKE_MARKERS=launcher.markers(marker), UI_SERVICE="weston.service")

    assert calls[-1] == command
    assert not (launcher.pm / marker).exists()


def test_generic_no_autoinstall_files(launcher):
    (launcher.pm / "autoinstall").mkdir()
    (launcher.pm / "autoinstall" / "readme.txt").write_text("not a port")

    calls = launcher.run()

    assert not any(call.startswith("PortMasterDialog") for call in calls)
    ## Both directories exist afterwards, so users can find them.
    assert (launcher.ports_dir / "autoinstall").is_dir()


def test_generic_autoinstall(launcher):
    (launcher.ports_dir / "autoinstall").mkdir(parents=True)
    (launcher.ports_dir / "autoinstall" / "Port.ZIP").write_bytes(b"zip")

    calls = launcher.run()

    pm_dir = launcher.pm / "autoinstall"
    ports_dir = "/" + str(launcher.ports_dir / "autoinstall")
    assert calls[1:4] == [
        "PortMasterDialogInit no-check",
        f"PortMasterDialog autoinstall {pm_dir} {ports_dir}",
        "PortMasterDialogExit",
        ]
    assert "pugwash " in calls[4:]


def test_generic_autoinstall_offline_skips_gui(launcher):
    (launcher.pm / "autoinstall").mkdir()
    (launcher.pm / "autoinstall" / "godot.squashfs").write_bytes(b"squash")

    calls = launcher.run(FAKE_GW="", FAKE_MARKERS="")
    ## Autoinstall leaves the marker itself, the frontend is still refreshed.
    assert "pugwash " not in calls
    assert calls[-1] == "systemctl restart oga_events"

    (launcher.pm / ".emulationstation-refresh").touch()
    launcher.calls_file.unlink()
    calls = launcher.run(FAKE_GW="")
    assert calls[-1] == "systemctl restart emulationstation"


## -- each CFW's hooks

def test_muos(launcher):
    calls = launcher.run("muos", FAKE_MARKERS=launcher.markers(".muos-refresh"))

    assert "get_controls" not in calls
    assert "pugwash " in calls
    assert "systemctl restart oga_events" not in calls
    assert calls[-1] == "image_smash.txt "
    assert not (launcher.pm / ".muos-refresh").exists()


def test_trimui(launcher):
    calls = launcher.run("trimui", FAKE_MARKERS=launcher.markers(".trimui-refresh"))

    assert calls[0] == "update.txt "
    assert "pugwash --debug" in calls
    assert calls[-1] == "image_smash.txt "


def test_spruce_runs_once_with_one_autoinstall_dir(launcher):
    (launcher.root / "reboot-once").touch()
    (launcher.pm / "autoinstall").mkdir()
    (launcher.pm / "autoinstall" / "port.zip").write_bytes(b"zip")

    calls = launcher.run("spruce")

    assert f"PortMasterDialog autoinstall {launcher.pm / 'autoinstall'}" in calls
    assert calls.count("pugwash ") == 1


def test_miyoo(launcher):
    calls = launcher.run("miyoo")

    assert "pm_message Starting PortMaster." in calls
    assert calls.count("pugwash ") == 1


def test_retrodeck(launcher):
    calls = launcher.run("retrodeck", FAKE_MARKERS=launcher.markers(".es-de-refresh"))

    assert calls == ["get_controls", "pugwash ", "pkill -f es-de"]


def test_retrodeck_reload_disabled(launcher):
    calls = launcher.run("retrodeck", FAKE_MARKERS=launcher.markers(".es-de-refresh"), portmaster_reload_esde="false")

    assert "pkill -f es-de" not in calls
