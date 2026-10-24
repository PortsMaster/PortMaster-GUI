# SPDX-License-Identifier: MIT

import json
import shutil

import pytest

import harbourmaster
from harbourmaster import source as hm_source
from harbourmaster.util import net as hm_net
from harbourmaster import util

from conftest import basic_port_files, write_port_zip


################################################################################
## Startup
def test_first_run_creates_config(hm, hm_dirs):
    cfg_dir = hm_dirs['tools_dir'] / "PortMaster" / "config"

    assert (cfg_dir / "config.json").is_file()
    assert (cfg_dir / "ports_info.json").is_file()
    assert sorted(p.name for p in cfg_dir.glob("*.source.json")) == ["020_portmaster.source.json", "021_portmaster.multiverse.source.json"]

    config = json.loads((cfg_dir / "config.json").read_text())
    assert config['first-run'] is False
    assert config['theme'] == "default_theme"
    assert config['version'] == harbourmaster.HarbourMaster.CONFIG_VERSION


def test_platform_from_cfw_name(hm):
    assert hm.platform_name == "default"
    assert type(hm.platform) is harbourmaster.HM_PLATFORMS['default']


def test_offline_startup_does_not_fetch(make_hm, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("fetched while offline")

    monkeypatch.setattr(hm_net, "fetch_json", fail)
    make_hm()


################################################################################
## Local installs
@pytest.fixture
def port_zip(tmp_path):
    return write_port_zip(tmp_path / "testport.zip", basic_port_files())


def test_install_local_zip(hm, hm_dirs, port_zip, callback):
    assert hm.install_port(str(port_zip)) == 0

    ports_dir = hm_dirs['ports_dir']
    script = ports_dir / "Test Port.sh"

    assert script.is_file()
    assert (ports_dir / "testport" / "data.txt").read_text() == "game data"
    assert util.load_pm_signature(script) == ["testport.zip", "Test Port.sh"]

    port_json = json.loads((ports_dir / "testport" / "port.json").read_text())
    assert port_json['name'] == "testport.zip"
    assert port_json['status']['status'] == "Installed"
    assert port_json['status']['source'] == "file"
    assert port_json['status']['md5'] == util.hash_file(port_zip)
    assert port_json['files'] == {
        'port.json': "testport/port.json",
        'Test Port.sh': "Test Port.sh",
        'testport/': "testport/",
        }

    hm.load_ports()
    assert list(hm.installed_ports) == ["testport.zip"]
    assert hm.installed_ports["testport.zip"]['attr']['title'] == "Test Port"

    ## Local zips have no source info, so the zip name is used rather than the title.
    assert callback.message_boxes[-1] == "Port 'testport.zip' installed successfully."


def test_install_local_missing_file(hm, tmp_path):
    assert hm.install_port(str(tmp_path / "missing.zip")) == 255


def test_install_bad_zip_rolls_back(hm, hm_dirs, tmp_path, callback):
    zip_file = write_port_zip(tmp_path / "bad.zip", {"Bad.sh": "#!/bin/bash\n"})

    assert hm.install_port(str(zip_file)) == 255
    assert list(hm_dirs['ports_dir'].iterdir()) == []
    assert "failed to install" in callback.message_boxes[-1]


def test_install_incompatible_port_still_installs_from_cli(hm, tmp_path):
    ## Only the GUI asks before installing ports that don't match the device.
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files(arch=["x86_64"]))

    assert hm.install_port(str(zip_file)) == 0


def test_uninstall(hm, hm_dirs, port_zip, callback):
    hm.install_port(str(port_zip))
    hm.load_ports()

    assert hm.uninstall_port("testport.zip") == 0
    assert list(hm_dirs['ports_dir'].iterdir()) == []
    assert callback.message_boxes[-1] == "Successfully uninstalled Test Port"

    hm.load_ports()
    assert hm.installed_ports == {}


def test_uninstall_unknown(hm, callback):
    hm.load_ports()
    assert hm.uninstall_port("missing.zip") == 255
    assert callback.message_boxes[-1] == "Unknown port missing.zip"


def test_uninstall_error_is_reported(hm, hm_dirs, port_zip, monkeypatch):
    hm.install_port(str(port_zip))
    hm.load_ports()

    def broken_rmtree(*args, **kwargs):
        raise OSError("read-only file system")

    monkeypatch.setattr(shutil, "rmtree", broken_rmtree)

    assert hm.uninstall_port("testport.zip") == 1


################################################################################
## Installing from a source
def test_list_ports_filters_by_device(online_hm, ports_json_data):
    ports = online_hm.list_ports()

    assert set(ports) <= set(ports_json_data['ports'])
    assert "100liljumps.zip" in ports

    for port_name in ports:
        assert online_hm.match_requirements(ports[port_name])


def test_install_from_source(online_hm, ports_json_data, callback):
    assert online_hm.install_port("100liljumps.zip") == 0
    assert online_hm.downloads == [ports_json_data['ports']['100liljumps.zip']['source']['url']]

    online_hm.load_ports()
    installed = online_hm.installed_ports["100liljumps.zip"]
    assert installed['status']['source'] == "PortMaster"
    assert installed['attr']['title'] == "100 Lil Jumps"


def test_install_from_named_source(online_hm):
    assert online_hm.install_port("pmmv/100liljumps.zip") == 255
    assert online_hm.downloads == []

    assert online_hm.install_port("pm/100liljumps.zip") == 0


def test_install_unknown_port(online_hm, callback):
    assert online_hm.install_port("missing.zip") == 255
    assert callback.message_boxes[-1] == "Unable to find a source for missing.zip"


def test_install_offline_refuses_download(hm, callback):
    assert hm.install_port("https://example.com/port.zip") == 255
    assert callback.message_boxes[-1] == "Unable to download in offline mode."
