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
from pathlib import Path

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

        for tool in ("sudo", "curl", "pkill", "mount", "umount", "df"):
            write_exe(self.bin / tool, LOG)

        ## `systemctl cat UNIT` only finds the units in $FAKE_UNITS.
        write_exe(self.bin / "systemctl", (
            'if [ "$1" = "cat" ]; then\n'
            '  case " $FAKE_UNITS " in *" $2 "*) exit 0;; esac\n'
            '  exit 1\n'
            'fi\n') + LOG)

        self.env = {
            'PATH': f"{self.bin}:{os.environ['PATH']}",
            'HOME': str(tmp_path / "home"),
            'XDG_DATA_HOME': str(tmp_path / "data"),
            'PM_CUR_TTY': str(tmp_path / "tty"),
            'FAKE_CALLS': str(self.calls_file),
            'FAKE_GW': "192.168.1.1",
            'FAKE_MARKERS': "",
            'FAKE_REBOOT_ONCE': str(tmp_path / "reboot-once"),
            'FAKE_UNITS': "oga_events",
            }

    def run(self, cfw=None, stub=None, **env):
        """Runs `stub` (a launcher file), or sources pm_launch.txt for `cfw` as its stub would."""
        run_env = dict(self.env)
        run_env.update(env)

        if stub is not None:
            command = ["bash", str(self.sandboxed(PM_DIR / stub))]
        else:
            command = ["bash", "-c", f'controlfolder="{self.pm}"; source "$controlfolder/utils/pm_launch.txt" {cfw or ""}; exit $?']

        result = subprocess.run(
            command, env=run_env, cwd=str(self.root), timeout=60,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

        self.output = result.stdout
        assert result.returncode == 0, result.stdout
        return self.calls()

    OGA_RESTART = "systemctl restart oga_events"

    ## Where the generic stub looks before $XDG_DATA_HOME: on a real ArkOS / dArkOS
    ## device these exist, and the test would run the device's own PortMaster.
    DEVICE_PATHS = ("/opt/system/Tools/", "/opt/tools/", "/roms/ports/")

    def sandboxed(self, stub):
        """A copy of `stub` that looks for those under the fake root instead."""
        text = Path(stub).read_text()
        for device_path in self.DEVICE_PATHS:
            text = text.replace(f'"{device_path}', f'"{self.root / "device"}{device_path}')

        copy = self.root / "stubs" / Path(stub).name
        copy.parent.mkdir(exist_ok=True)
        copy.write_text(text)
        return copy

    def calls(self):
        """
        What ran, in order. The oga_events restart runs in the background, so it is
        left out (it can land anywhere), self.oga_restarted says if it happened.
        """
        if not self.calls_file.is_file():
            return []

        calls = self.calls_file.read_text().splitlines()
        self.oga_restarted = self.OGA_RESTART in calls
        return [call for call in calls if call != self.OGA_RESTART]

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

    ## Exits on the same line: bash reads scripts as it goes, nothing after it may run,
    ## even if an update replaced this file while PortMaster was running.
    assert lines[-1] == expected + "; exit $?"
    assert sum(1 for line in lines if not line.startswith('#')) < 15, "stubs only find $controlfolder"


## -- generic launcher (ArkOS, ROCKNIX, ...)

def test_generic_stub_runs_gui(launcher):
    calls = launcher.run(stub="PortMaster.sh")

    assert calls == ["get_controls", "pugwash "]
    assert launcher.oga_restarted
    assert (launcher.pm / "log.txt").is_file()


def test_generic_without_oga_events(launcher):
    ## eg: AmberELEC, ROCKNIX: no "Unit oga_events.service not found." in the log.
    calls = launcher.run(FAKE_UNITS="")

    assert calls == ["get_controls", "pugwash "]
    assert not launcher.oga_restarted


def test_stub_overwritten_while_running(launcher):
    ## An older harbourmaster updating PortMaster from the GUI overwrites the running
    ## launcher in place. Bash then reads on from where it was, in the new file.
    stub = launcher.root / "PortMaster.sh"
    shutil.copy(str(launcher.sandboxed(PM_DIR / "PortMaster.sh")), str(stub))

    write_exe(launcher.pm / "pugwash", LOG + (
        f'printf "%0{stub.stat().st_size + 100}d\\necho SHOULD-NOT-RUN >> \\"$FAKE_CALLS\\"\\n" 0 > "{stub}"\n'))

    calls = launcher.run(stub=str(stub))

    assert "SHOULD-NOT-RUN" not in calls
    assert launcher.oga_restarted


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
    assert launcher.oga_restarted

    (launcher.pm / ".emulationstation-refresh").touch()
    launcher.calls_file.unlink()
    calls = launcher.run(FAKE_GW="")
    assert calls[-1] == "systemctl restart emulationstation"


## -- each CFW's hooks

def test_muos(launcher):
    calls = launcher.run("muos", FAKE_MARKERS=launcher.markers(".muos-refresh"))

    assert "get_controls" not in calls
    assert "pugwash " in calls
    assert not launcher.oga_restarted
    assert calls[-1] == "image_smash.txt "
    assert not (launcher.pm / ".muos-refresh").exists()


def test_trimui(launcher):
    calls = launcher.run("trimui", FAKE_MARKERS=launcher.markers(".trimui-refresh"))

    assert calls[0] == "update.txt "
    assert "pugwash --debug" in calls
    assert calls[-1] == "image_smash.txt "


def test_spruce_runs_once_after_autoinstall(launcher):
    (launcher.root / "reboot-once").touch()
    (launcher.pm / "autoinstall").mkdir()
    (launcher.pm / "autoinstall" / "port.zip").write_bytes(b"zip")

    ## (On a real spruce device its python3 exists, keep the test off it.)
    calls = launcher.run("spruce", PM_PYTHON=str(launcher.root / "no-python"))

    assert f"PortMasterDialog autoinstall {launcher.pm / 'autoinstall'} {launcher.ports_dir / 'autoinstall'}" in calls
    assert calls.count("pugwash ") == 1


def test_spruce_autoinstall_from_roms_ports(launcher):
    ## Roms/ports/autoinstall too, made on the first launch like on other CFWs.
    ## ($directory comes from the fake device_info.txt, spruce's own ends in a slash.)
    roms = launcher.ports_dir.parent
    (roms / "ports").mkdir(parents=True, exist_ok=True)

    calls = launcher.run("spruce", PM_PYTHON=str(launcher.root / "no-python"))
    assert (roms / "ports" / "autoinstall").is_dir()
    assert not any(call.startswith("PortMasterDialog autoinstall") for call in calls)

    (roms / "ports" / "autoinstall" / "port.zip").write_bytes(b"zip")

    calls = launcher.run("spruce", PM_PYTHON=str(launcher.root / "no-python"))
    assert f"PortMasterDialog autoinstall {launcher.pm / 'autoinstall'} {roms / 'ports' / 'autoinstall'}" in calls


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


def test_spruce_uses_its_own_python(launcher):
    python = launcher.root / "python3"
    write_exe(python, 'echo "python3 $*" >> "$FAKE_CALLS"\n')

    calls = launcher.run("spruce", PM_PYTHON=str(python))

    assert "python3 ./pugwash" in calls
    assert "pugwash " not in calls


def test_sandboxed_stub_keeps_its_logic(launcher):
    ## Only the paths move: the copy must still be the real stub otherwise.
    copy = launcher.sandboxed(PM_DIR / "PortMaster.sh").read_text()
    original = (PM_DIR / "PortMaster.sh").read_text()

    assert copy.count("\n") == original.count("\n")
    assert "/opt/system/Tools/PortMaster/" in copy
    assert '"/opt/system/Tools/' not in copy
    assert copy.splitlines()[-1] == original.splitlines()[-1]


## -- PM_LAUNCH_ENV_ONLY: the GUI's environment, nothing run (the PortMaster Test Suite uses it)

@pytest.mark.parametrize("cfw, sdl_path", [
    (None, "/usr/lib"),
    ("muos", "/usr/lib"),
    ("trimui", "/usr/trimui/lib"),
    ("retrodeck", ""),
    ])
def test_env_only(launcher, cfw, sdl_path):
    calls = launcher.run(cfw, PM_LAUNCH_ENV_ONLY="Y", FAKE_REBOOT_ONCE="")
    assert "pugwash " not in calls
    assert not any(call.startswith("pugwash") for call in calls)

    result = subprocess.run(
        ["bash", "-c", f'controlfolder="{launcher.pm}"; source "$controlfolder/utils/pm_launch.txt" {cfw or ""}; echo "SDL=$PYSDL2_DLL_PATH"'],
        env=dict(launcher.env, PM_LAUNCH_ENV_ONLY="Y"), cwd=str(launcher.root), timeout=60,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert f"SDL={sdl_path}" in result.stdout.splitlines()


def test_spruce_gui_env_keeps_its_sdl(launcher):
    ## spruce's pm_hook_env picks the SDL2 (the card's spruce/portmaster/portmaster.txt),
    ## pm_hook_gui_env must leave it. A fake card file, so a real spruce device's doesn't count.
    card = launcher.root / "card-portmaster.txt"
    card.write_text('export PYSDL2_DLL_PATH="/card/lib/"\n')
    hooks = launcher.pm / "spruce" / "launch_hooks.txt"
    hooks.write_text(hooks.read_text().replace("/mnt/SDCARD/spruce/portmaster/portmaster.txt", str(card)))

    result = subprocess.run(
        ["bash", "-c", f'controlfolder="{launcher.pm}"; source "$controlfolder/utils/pm_launch.txt" spruce; echo "SDL=$PYSDL2_DLL_PATH"'],
        env=dict(launcher.env, PM_LAUNCH_ENV_ONLY="Y"), cwd=str(launcher.root), timeout=60,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, universal_newlines=True)

    assert "SDL=/card/lib/" in result.stdout.splitlines()
