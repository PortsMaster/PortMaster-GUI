# SPDX-License-Identifier: MIT
#
# hardware.py's helpers and its quick CFW/device probe, against a fake device root.

from pathlib import Path

import pytest

from harbourmaster import hardware


class Root:
    def __init__(self, tmp_path):
        self.base = tmp_path
        self.root = tmp_path / "root"
        self.root.mkdir()

    def __call__(self, *args):
        path = Path(*args)
        if path.is_absolute() and self.base not in path.parents:
            return self.root / path.relative_to("/")
        return path

    def home(self):
        return self.root / "home"

    def write(self, absolute, text=""):
        path = self.root / absolute.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path


@pytest.fixture
def root(tmp_path, monkeypatch):
    fake = Root(tmp_path)
    monkeypatch.setattr(hardware, "Path", fake)
    monkeypatch.delenv("FLATPAK_ID", raising=False)
    return fake


def probe(tmp_path):
    return hardware.HardwareDetector(tmp_path)._quick_probe_identity()


@pytest.mark.parametrize("marker, cfw", [
    ("/app/bin/retrodeck", "retrodeck"),
    ("/etc/rocknix-release", "rocknix"),
    ("/storage/.config/rocknix", "rocknix"),
    ("/etc/jelos-release", "jelos"),
    ("/opt/muos/config/system/version", "muos"),
    ("/boot/boot/knulli.board", "knulli"),
    ("/etc/arkos_version", "arkos"),
    ("/etc/darkos_version", "arkos"),
    ])
def test_probe_cfw(root, tmp_path, marker, cfw):
    root.write(marker, "board\n")
    assert probe(tmp_path)[0] == cfw


def test_probe_retrodeck_flatpak(root, tmp_path, monkeypatch):
    monkeypatch.setenv("FLATPAK_ID", "net.retrodeck.retrodeck")
    assert probe(tmp_path)[0] == "retrodeck"


@pytest.mark.parametrize("text, cfw", [
    ("title=dArkOS\n", "darkos"),
    ("title=Thera\n", "thera"),
    ("title=ArkOS (wummle)\n", "arkos"),
    ("title=Something else\n", "unknown"),
    ])
def test_probe_plymouth(root, tmp_path, text, cfw):
    root.write("/usr/share/plymouth/themes/text.plymouth", text)
    assert probe(tmp_path)[0] == cfw


def test_probe_nothing(root, tmp_path):
    assert probe(tmp_path) == ("unknown", "unknown")


def test_probe_device_name_order(root, tmp_path):
    root.write("/proc/device-tree/model", "Generic Board\x00")
    assert probe(tmp_path)[1] == "generic_board"

    root.write("/etc/board", "\n")
    ## An empty first line is skipped.
    assert probe(tmp_path)[1] == "generic_board"

    root.write("/home/.config/.DEVICE", "RG353V\nextra\n")
    assert probe(tmp_path)[1] == "rg353v"

    root.write("/opt/muos/device/config/board/name", "rg-vita-pro")
    assert probe(tmp_path)[1] == "rg-vita-pro"


def test_probe_dmi_product_name(root, tmp_path):
    root.write("/sys/devices/virtual/dmi/id/product_name", "Steam Deck\n")
    assert probe(tmp_path)[1] == "steam_deck"


def test_probe_names_are_file_safe(root, tmp_path):
    root.write("/etc/board", "Debian GNU/Linux\n")
    assert probe(tmp_path)[1] == "debian_gnu_linux"


################################################################################
## Helpers
@pytest.mark.parametrize("value, expected", [
    (None, ""),
    ('"quoted"', "quoted"),
    ("'single' \r\n", "single"),
    ("nul\x00l", "null"),
    (5, "5"),
    ])
def test_clean_str(value, expected):
    assert hardware._clean_str(value) == expected


@pytest.mark.parametrize("value, expected", [
    (None, 7),
    ("", 7),
    ('"12"', 12),
    ("twelve", 7),
    ("1.5", 7),
    (3, 3),
    ])
def test_safe_int(value, expected):
    assert hardware._safe_int(value, 7) == expected


@pytest.mark.parametrize("text, expected", [
    ('export DEVICE_INFO_VERSION="0.2.6"\n', "0.2.6"),
    ('  DEVICE_INFO_VERSION=0.3.0\n', "0.3.0"),
    ('# nothing\nexport OTHER=1\n', None),
    ('', None),
    ])
def test_script_version(tmp_path, text, expected):
    script = tmp_path / "device_info.txt"
    script.write_text(text)
    assert hardware._script_version(script) == expected


def test_script_version_missing(tmp_path):
    assert hardware._script_version(tmp_path / "missing.txt") is None


def test_read_env_file_unreadable(tmp_path):
    assert hardware._read_env_file(tmp_path) == {}


def test_find_control_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("controlfolder", f'"{tmp_path}"')
    assert hardware._find_control_dir() == tmp_path

    monkeypatch.delenv("controlfolder")
    monkeypatch.setenv("PORTMASTER_HOME", str(tmp_path / "pm"))
    assert hardware._find_control_dir() == tmp_path / "pm"

    monkeypatch.delenv("PORTMASTER_HOME")
    ## From a checkout: the PortMaster folder this file is in.
    assert hardware._find_control_dir().name == "PortMaster"


@pytest.mark.parametrize("script_name", ["device_info.sh", "PortMaster/device_info.txt"])
def test_device_info_script_names(tmp_path, script_name):
    path = tmp_path / script_name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")

    assert hardware.HardwareDetector(tmp_path)._device_info_script() == path


def test_no_device_info_script(tmp_path):
    assert hardware.HardwareDetector(tmp_path)._device_info_script() is None


################################################################################
## get_info's details
def _no_env(monkeypatch):
    for key in ("DEVICE_NAME", "DEVICE_CPU", "CFW_NAME", "DISPLAY_WIDTH", "DISPLAY_HEIGHT", "DEVICE_ARCH",
                "DEVICE_CAPABILITIES", "DEVICE_RAM", "CFW_GLIBC", "ANALOG_STICKS", "DEVICE_INFO_VERSION", "CFW_VERSION"):
        monkeypatch.delenv(key, raising=False)


def write_env(folder, text, name="device_info_x_y.env"):
    (folder / name).write_text(text + "padding=" + "x" * 40 + "\n")


def test_get_info_from_cache_details(tmp_path, monkeypatch):
    _no_env(monkeypatch)
    write_env(tmp_path, (
        "CFW_NAME=ROCKNIX\nCFW_VERSION=20250517\nDEVICE_NAME=Retroid Pocket 5\nDEVICE_SLUG=rp5\n"
        "DISPLAY_WIDTH=1920\nDISPLAY_HEIGHT=1080\nDEVICE_RAM_MB=8192\nANALOG_STICKS=2\n"
        "DEVICE_TOUCH=y\nDEVICE_HAS_RUMBLE=y\nDEVICE_ARCH=aarch64\nCFW_GLIBC=238\n"
        "DEVICE_CAPABILITIES=aarch64 1920x1080 power\n"))

    info = hardware.HardwareDetector(tmp_path).get_info()

    assert info['name'] == "rocknix"
    assert info['device'] == "rp5"
    assert info['resolution'] == (1920, 1080)
    assert info['ram'] == 8192
    assert info['glibc'] == "2.38"
    assert info['touch'] == "Y" and info['rumble'] == "Y"
    assert info['capabilities'] == ["aarch64", "1920x1080", "power"]


def test_get_info_bad_numbers_use_defaults(tmp_path, monkeypatch):
    _no_env(monkeypatch)
    write_env(tmp_path, "CFW_NAME=x\nDISPLAY_WIDTH=wide\nDISPLAY_HEIGHT=\nDEVICE_RAM=lots\nANALOG_STICKS=two\n")

    info = hardware.HardwareDetector(tmp_path).get_info()

    assert info['resolution'] == (640, 480)
    assert info['ram'] == 1024
    assert info['analogsticks'] == 0


def test_get_info_force_refresh_skips_the_memo(tmp_path, monkeypatch):
    _no_env(monkeypatch)
    write_env(tmp_path, "CFW_NAME=first\n")
    first = hardware.HardwareDetector(tmp_path).get_info()

    write_env(tmp_path, "CFW_NAME=second\n")
    assert hardware.HardwareDetector(tmp_path).get_info() is first

    monkeypatch.setattr(hardware.subprocess, "run", lambda *args, **kwargs: None)
    assert hardware.HardwareDetector(tmp_path).get_info(force_refresh=True)['name'] == "unknown"


def test_get_info_probe_error_is_survived(tmp_path, monkeypatch):
    _no_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.6"\n')

    def fail(*args, **kwargs):
        raise OSError("no bash")

    monkeypatch.setattr(hardware.subprocess, "run", fail)
    info = hardware.HardwareDetector(tmp_path).get_info()

    assert info['name'] == "unknown"
    assert info['resolution'] == (640, 480)


def test_get_info_probe_writes_another_name(tmp_path, monkeypatch):
    ## The script names its cache from what it found, not what the quick probe guessed.
    _no_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.6"\n')

    def probe(*args, **kwargs):
        write_env(tmp_path, 'DEVICE_INFO_VERSION="0.2.6"\nCFW_NAME=Found\n', name="device_info_found_it.env")

    monkeypatch.setattr(hardware.subprocess, "run", probe)
    assert hardware.HardwareDetector(tmp_path).get_info()['name'] == "found"


def test_tiny_cache_is_ignored(tmp_path, monkeypatch):
    _no_env(monkeypatch)
    (tmp_path / "device_info_x_y.env").write_text("CFW_NAME=x\n")
    monkeypatch.setattr(hardware.subprocess, "run", lambda *args, **kwargs: None)

    assert hardware.HardwareDetector(tmp_path).get_info()['name'] == "unknown"


def test_api_shims(monkeypatch):
    assert hardware.hardware_info() == hardware.device_info()
    info = hardware.expand_info(None)
    assert info == hardware.device_info() and info is not hardware.device_info()

    expanded = hardware.expand_info({"name": "x"}, override_ram=4096)
    assert expanded['ram'] == 4096
