# SPDX-License-Identifier: MIT
#
# The harbourmaster CLI is called by PortMaster.sh and other shell scripts, so
# its commands and exit codes are part of the device contract.

import json
import os
import subprocess
import sys

import pytest

from conftest import PM_DIR, basic_port_files, write_port_zip


@pytest.fixture
def cli(hm_dirs, tmp_path):
    env = dict(os.environ)
    env.update({
        'HM_TOOLS_DIR': str(hm_dirs['tools_dir']),
        'HM_PORTS_DIR': str(hm_dirs['ports_dir']),
        'HM_SCRIPTS_DIR': str(hm_dirs['scripts_dir']),
        })

    def run(*args):
        result = subprocess.run(
            [sys.executable, str(PM_DIR / "harbourmaster"), "--offline", "--no-colour", *args],
            cwd=str(tmp_path), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)

        result.output = result.stdout.decode()
        return result

    return run


def test_help(cli):
    result = cli("help")

    assert result.returncode == 0, result.output
    assert "All available commands:" in result.output
    for command in ("install", "uninstall", "list", "runtime_check", "ports.json"):
        assert command in result.output


def test_help_for_command(cli):
    result = cli("help", "install")

    assert result.returncode == 0, result.output
    assert "Install a port" in result.output


def test_no_command_shows_help(cli):
    result = cli()

    assert result.returncode == 1
    assert "All available commands:" in result.output


def test_unknown_command(cli):
    result = cli("frobnicate")

    assert result.returncode == 2
    assert "Command frobnicate not found." in result.output


def test_nothing_command(cli):
    assert cli("nothing").returncode == 0


def test_list_offline(cli):
    result = cli("list")

    assert result.returncode == 0, result.output
    assert "Available ports:" in result.output


def test_install_and_uninstall_local_zip(cli, hm_dirs, tmp_path):
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())

    result = cli("install", "./testport.zip")
    assert result.returncode == 0, result.output
    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()

    result = cli("uninstall", "testport.zip")
    assert result.returncode == 0, result.output
    assert not (hm_dirs['ports_dir'] / "Test Port.sh").exists()
    assert not (hm_dirs['ports_dir'] / "testport").exists()


def test_install_missing_args(cli):
    result = cli("install")
    assert "Missing arguments." in result.output


def test_install_bad_zip_fails(cli, tmp_path):
    write_port_zip(tmp_path / "bad.zip", {"Bad.sh": "#!/bin/bash\n"})

    assert cli("install", "./bad.zip").returncode == 255


def test_portsjson(cli, tmp_path):
    result = cli("ports.json", str(tmp_path / "out.json"))

    assert result.returncode == 0, result.output
    assert isinstance(json.loads((tmp_path / "out.json").read_text()), dict)


def test_runtime_list(cli):
    assert cli("runtime_list").returncode == 0


def test_device_info(cli):
    result = cli("device_info")

    assert result.returncode == 0, result.output
    assert result.output.strip().endswith("{}")


@pytest.fixture(scope="module")
def hm_script():
    """The harbourmaster commands, for calling them directly."""
    from harbourmaster import cli
    return cli


@pytest.mark.xfail(strict=True, reason="BUG: `ports.json` command expects pre-V3 port_info keys ('status', 'files') and crashes with PortMasterV3 sources")
def test_portsjson_with_utils(hm_script, online_hm, tmp_path):
    out_file = tmp_path / "out.json"

    assert hm_script.do_portsjson(online_hm, [str(out_file)]) == 0

    ports_json = json.loads(out_file.read_text())
    assert "100liljumps.zip" in [port['name'] for port in ports_json['ports']]
    assert ports_json['utils']['ags_3.6.squashfs']['name'] == "Adventure Game Studio 3.6"


def test_install_failure_reason_printed(cli, tmp_path):
    (tmp_path / "garbage.zip").write_bytes(b"not a zip")

    result = cli("install", "./garbage.zip")

    assert result.returncode == 255
    assert "Installation failed:" in result.output
