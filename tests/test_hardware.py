# SPDX-License-Identifier: MIT

import pytest

import harbourmaster
from harbourmaster import hardware


def test_device_info_from_environment():
    info = harbourmaster.device_info()

    assert info['name'] == "default"
    assert info['device'] == "testing"
    assert info['model'] == "Testing"
    assert info['resolution'] == (640, 480)
    assert info['primary_arch'] == "aarch64"
    assert info['capabilities'] == ["aarch64", "640x480", "power", "opengl"]
    assert info['ram'] == 1024
    assert info['glibc'] == "2.30"
    assert info['analogsticks'] == 2


def test_device_info_is_cached(monkeypatch):
    first = harbourmaster.device_info()
    monkeypatch.setenv("DISPLAY_WIDTH", "1280")
    assert harbourmaster.device_info() is first


def test_device_info_defaults(monkeypatch):
    for key in ("DISPLAY_WIDTH", "DISPLAY_HEIGHT", "DEVICE_RAM", "CFW_GLIBC", "DEVICE_CAPABILITIES"):
        monkeypatch.delenv(key)

    info = harbourmaster.device_info()

    assert info['resolution'] == (640, 480)
    assert info['ram'] == 1024
    assert info['glibc'] == "0.0.0"
    assert info['capabilities'] == []


def test_device_info_from_env_file(tmp_path, monkeypatch):
    for key in ("DEVICE_NAME", "DEVICE_CPU", "CFW_NAME"):
        monkeypatch.delenv(key)

    for key in ("DISPLAY_WIDTH", "DISPLAY_HEIGHT", "DEVICE_ARCH", "DEVICE_CAPABILITIES"):
        monkeypatch.delenv(key)

    (tmp_path / "device_info_muos_rg35xx.env").write_text(
        "# comment\n"
        "DEVICE_NAME='RG35XX'\n"
        "CFW_NAME=\"muOS\"\n"
        "DISPLAY_WIDTH=640\n"
        "DISPLAY_HEIGHT=480\n"
        "DEVICE_ARCH=armhf\n"
        "DEVICE_CAPABILITIES=armhf 640x480\n"
        "padding_to_get_past_the_size_check=xxxxxxxxxxxxxxxx\n")

    info = hardware.HardwareDetector(tmp_path).get_info()

    assert info['name'] == "muos"
    assert info['model'] == "RG35XX"
    assert info['primary_arch'] == "armhf"
    assert info['capabilities'] == ["armhf", "640x480"]


def test_read_env_file(tmp_path):
    env_file = tmp_path / "test.env"
    env_file.write_text("A=1\n# skip=me\n\nNo equals here\nB = 'two' \nC=x=y\n")

    assert hardware._read_env_file(env_file) == {'a': '1', 'b': 'two', 'c': 'x=y'}
    assert hardware._read_env_file(tmp_path / "missing.env") == {}


@pytest.mark.parametrize("raw, expected", [
    ("2.30", "2.30"),
    ("231", "2.31"),
    ("", "0.0.0"),
    ("unknown", "0.0.0"),
    ("0", "0.0.0"),
    ])
def test_normalize_glibc(raw, expected):
    assert hardware._normalize_glibc(raw) == expected


def test_expand_info_override_resolution():
    info = harbourmaster.expand_info({'name': 'x'}, override_resolution=(1280, 720))

    assert info['name'] == 'x'
    assert info['resolution'] == (1280, 720)
    assert "1280x720" in info['capabilities']
    assert "640x480" not in info['capabilities']
    assert "aarch64" in info['capabilities']


def test_find_device_by_resolution():
    assert harbourmaster.find_device_by_resolution((640, 480)) == "testing"
    assert harbourmaster.find_device_by_resolution((1, 1)) == "default"


def _no_device_env(monkeypatch):
    for key in ("DEVICE_NAME", "DEVICE_CPU", "CFW_NAME", "DISPLAY_WIDTH", "DISPLAY_HEIGHT", "DEVICE_ARCH", "DEVICE_CAPABILITIES"):
        monkeypatch.delenv(key, raising=False)


def _cache(folder, version, model, name="device_info_rocknix_rp5.env"):
    (folder / name).write_text(
        f'DEVICE_INFO_VERSION="{version}"\nCFW_NAME="ROCKNIX"\nDEVICE_NAME="{model}"\n'
        'DEVICE_CAPABILITIES="aarch64 1920x1080"\n')


def test_device_info_current_cache_skips_the_probe(tmp_path, monkeypatch):
    _no_device_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.2"\n')
    _cache(tmp_path, "0.2.2", "Retroid Pocket 5")

    def no_probe(*args, **kwargs):
        raise AssertionError("probed although the cache is current")

    monkeypatch.setattr(hardware.subprocess, "run", no_probe)
    assert hardware.HardwareDetector(tmp_path).get_info()['model'] == "Retroid Pocket 5"


def test_device_info_stale_cache_is_probed_again(tmp_path, monkeypatch):
    ## ROCKNIX 20250517's own control.txt never sources device_info.txt, so only
    ## harbourmaster can notice a cache an older device_info.txt wrote.
    _no_device_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.2"\n')
    _cache(tmp_path, "0.2.1", "Old Answer")
    probes = []

    def probe(command, **kwargs):
        probes.append(command)
        _cache(tmp_path, "0.2.2", "New Answer")

    monkeypatch.setattr(hardware.subprocess, "run", probe)
    assert hardware.HardwareDetector(tmp_path).get_info()['model'] == "New Answer"
    assert probes and probes[0][-1] == "-f"


def test_device_info_stale_cache_when_the_probe_fails(tmp_path, monkeypatch):
    _no_device_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.2"\n')
    _cache(tmp_path, "0.2.1", "Old Answer")

    def probe(command, **kwargs):
        raise hardware.subprocess.TimeoutExpired(command, 60)

    monkeypatch.setattr(hardware.subprocess, "run", probe)
    assert hardware.HardwareDetector(tmp_path).get_info()['model'] == "Old Answer"


def _old_launcher_env(monkeypatch):
    """What the 2026.06 launcher's device_info.txt (0.1.15) exported: no DEVICE_CAPABILITIES."""
    _no_device_env(monkeypatch)
    monkeypatch.setenv("DEVICE_INFO_VERSION", "0.1.15")
    monkeypatch.setenv("CFW_NAME", "muOS")
    monkeypatch.setenv("DEVICE_NAME", "rg-vita-pro")
    monkeypatch.setenv("DEVICE_CPU", "Cortex-A53")


def test_device_info_ignores_an_older_scripts_environment(tmp_path, monkeypatch):
    ## PortMaster updated itself and restarted under the old launcher: every port was
    ## "incompatible", the capabilities were only the language.
    _old_launcher_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.6"\n')
    _cache(tmp_path, "0.2.6", "Retroid Pocket 5")

    info = hardware.HardwareDetector(tmp_path).get_info()

    assert info['model'] == "Retroid Pocket 5"
    assert info['capabilities'] == ["aarch64", "1920x1080"]
    ## Nothing from the old environment fills in what the cache hasn't.
    assert info['cpu'] == "Unknown"


def test_device_info_older_environment_and_no_cache_probes(tmp_path, monkeypatch):
    _old_launcher_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.6"\n')
    probes = []

    def probe(*args, **kwargs):
        probes.append(kwargs['env']['controlfolder'])
        _cache(tmp_path, "0.2.6", "Probed")

    monkeypatch.setattr(hardware.subprocess, "run", probe)
    info = hardware.HardwareDetector(tmp_path).get_info()

    assert probes == [str(tmp_path)]
    assert info['model'] == "Probed" and "aarch64" in info['capabilities']


def test_device_info_current_environment_is_used(tmp_path, monkeypatch):
    ## The launcher sourced the current device_info.txt: no disk reads.
    _no_device_env(monkeypatch)
    (tmp_path / "device_info.txt").write_text('export DEVICE_INFO_VERSION="0.2.6"\n')
    for key, value in (("DEVICE_INFO_VERSION", "0.2.6"), ("CFW_NAME", "muOS"), ("DEVICE_NAME", "RG35XX-H"),
                       ("DEVICE_CAPABILITIES", "aarch64 640x480")):
        monkeypatch.setenv(key, value)

    def no_probe(*args, **kwargs):
        raise AssertionError("probed although the environment is current")

    monkeypatch.setattr(hardware.subprocess, "run", no_probe)
    info = hardware.HardwareDetector(tmp_path).get_info()

    assert info['model'] == "RG35XX-H" and info['capabilities'] == ["aarch64", "640x480"]
