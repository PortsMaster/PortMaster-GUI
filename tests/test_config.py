# SPDX-License-Identifier: MIT
#
# harbourmaster.config resolves its directories at import time, so these run in
# a fresh interpreter each time.

import json
import os
import subprocess
import sys

from pathlib import Path

import pytest

from conftest import EXLIB_PATH, PYLIB_PATH


SCRIPT = f"""
import json, sys
sys.path.insert(0, {str(EXLIB_PATH)!r})
sys.path.insert(0, {str(PYLIB_PATH)!r})
from loguru import logger
logger.remove()
from harbourmaster import config
print(json.dumps({{
    'tools': str(config.HM_TOOLS_DIR),
    'ports': str(config.HM_PORTS_DIR),
    'scripts': str(config.HM_SCRIPTS_DIR),
    'testing': config.HM_TESTING,
    }}))
"""


def run_config(cwd, **env):
    run_env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HM_")}

    run_env.update(env)

    output = subprocess.check_output([sys.executable, "-c", SCRIPT], cwd=str(cwd), env=run_env)
    return json.loads(output.decode().strip().split("\n")[-1])


def test_env_overrides(tmp_path):
    result = run_config(
        tmp_path,
        HM_TOOLS_DIR=str(tmp_path / "tools"),
        HM_PORTS_DIR=str(tmp_path / "ports"),
        HM_SCRIPTS_DIR=str(tmp_path / "scripts"))

    assert result['tools'] == str(tmp_path / "tools")
    assert result['ports'] == str((tmp_path / "ports").resolve())
    assert result['scripts'] == str(tmp_path / "scripts")
    assert result['testing'] is False


def test_git_checkout_is_testing_mode(tmp_path):
    (tmp_path / ".git").mkdir()

    result = run_config(tmp_path)

    assert result['testing'] is True
    assert result['tools'] == str(tmp_path)
    assert result['ports'] == str(tmp_path / "ports")
    assert result['scripts'] == str(tmp_path / "ports")


def test_git_checkout_from_subdir_is_testing_mode(tmp_path):
    ## Running from PortMaster/ inside a checkout chdirs up a level.
    (tmp_path / ".git").mkdir()
    (tmp_path / "PortMaster").mkdir()

    result = run_config(tmp_path / "PortMaster")

    assert result['testing'] is True
    assert result['tools'] == str(tmp_path)


################################################################################
## detect_paths() against fake filesystems
from harbourmaster.config import detect_paths  # noqa: E402


def make_dirs(root, *paths):
    for path in paths:
        (root / path.lstrip("/")).mkdir(parents=True, exist_ok=True)


def detect(root, **kwargs):
    kwargs.setdefault("cwd", root / "somewhere")
    kwargs.setdefault("environ", {"XDG_DATA_HOME": "/home/user/.local/share"})
    kwargs.setdefault("home", root / "home")
    kwargs.setdefault("df_output", lambda: "")
    return detect_paths(root=root, **kwargs)


def test_detect_default(tmp_path):
    paths = detect(tmp_path)
    assert paths == (Path("/roms/ports"), Path("/roms/ports"), Path("/roms/ports"), False)


def test_detect_git_checkout(tmp_path):
    make_dirs(tmp_path, "/checkout/.git")
    paths = detect(tmp_path, cwd=tmp_path / "checkout")
    assert paths == (tmp_path / "checkout", tmp_path / "checkout" / "ports", tmp_path / "checkout" / "ports", True)


def test_detect_spruce(tmp_path):
    make_dirs(tmp_path, "/mnt/SDCARD/spruce")
    assert detect(tmp_path)[:3] == (
        Path("/mnt/SDCARD/Persistent/portmaster"), Path("/mnt/SDCARD/Roms/ports"), Path("/mnt/SDCARD/Roms/ports"))


def test_detect_trimui(tmp_path):
    make_dirs(tmp_path, "/mnt/SDCARD/Apps/PortMaster")
    assert detect(tmp_path)[:3] == (
        Path("/mnt/SDCARD/Apps/PortMaster"), Path("/mnt/SDCARD/Data/ports"), Path("/mnt/SDCARD/Data/ports"))


def test_detect_batocera(tmp_path):
    make_dirs(tmp_path, "/userdata/roms/ports")
    assert detect(tmp_path)[:3] == (
        Path("/home/user/.local/share"), Path("/userdata/roms/ports"), Path("/userdata/roms/ports"))


def test_detect_muos_internal_card(tmp_path):
    make_dirs(tmp_path, "/opt/muos")
    assert detect(tmp_path)[:3] == (Path("/mnt/mmc/MUOS"), Path("/mnt/mmc/ports"), Path("/mnt/mmc/ROMS/Ports"))


def test_detect_muos_second_card(tmp_path):
    make_dirs(tmp_path, "/opt/muos")
    paths = detect(tmp_path, df_output=lambda: "/dev/mmcblk1p1 ... /mnt/sdcard")
    assert paths[:3] == (Path("/mnt/mmc/MUOS"), Path("/mnt/sdcard/ports"), Path("/mnt/sdcard/ROMS/Ports"))


def test_detect_muos_second_card_with_toggle(tmp_path):
    make_dirs(tmp_path, "/opt/muos", "/mnt/mmc/MUOS/PortMaster/config")
    (tmp_path / "mnt/mmc/MUOS/PortMaster/config/muos_mmc_master_race.txt").write_text("")
    paths = detect(tmp_path, df_output=lambda: "/mnt/sdcard")
    assert paths[:3] == (Path("/mnt/mmc/MUOS"), Path("/mnt/mmc/ports"), Path("/mnt/mmc/ROMS/Ports"))


@pytest.mark.parametrize("roms2, expected_tools", [(True, "/roms2/tools"), (False, "/roms/tools")])
def test_detect_arkos(tmp_path, roms2, expected_tools):
    make_dirs(tmp_path, "/opt/system/Tools")
    if roms2:
        make_dirs(tmp_path, "/roms2/tools")

    assert detect(tmp_path)[0] == Path(expected_tools)


def test_detect_jelos_style_ports_scripts(tmp_path):
    make_dirs(tmp_path, "/storage/roms/ports_scripts")
    assert detect(tmp_path)[:3] == (
        Path("/storage/roms/ports"), Path("/storage/roms/ports"), Path("/storage/roms/ports_scripts"))


def test_detect_retrodeck_json(tmp_path):
    make_dirs(tmp_path, "/var/config/retrodeck")
    (tmp_path / "var/config/retrodeck/retrodeck.json").write_text(json.dumps(
        {"paths": {"rd_home_path": "/home/deck/retrodeck", "roms_path": "/media/roms"}}))

    assert detect(tmp_path)[:3] == (
        Path("/var/data"), Path("/home/deck/retrodeck/PortMaster/ports"), Path("/media/roms/portmaster"))


def test_detect_retrodeck_json_portmaster_path(tmp_path):
    ## Newer RetroDECK writes portmaster_path, not ports_path.
    make_dirs(tmp_path, "/var/config/retrodeck")
    (tmp_path / "var/config/retrodeck/retrodeck.json").write_text(json.dumps(
        {"paths": {"rd_home_path": "/home/deck/retrodeck", "portmaster_path": "/media/pm"}}))

    assert detect(tmp_path)[1] == Path("/media/pm/ports")


def test_detect_trimui_miyoo_ex(tmp_path):
    make_dirs(tmp_path, "/mnt/SDCARD/MIYOO_EX/PortMaster")
    assert detect(tmp_path)[:3] == (
        Path("/mnt/SDCARD/MIYOO_EX/PortMaster"), Path("/mnt/SDCARD/MIYOO_EX/ports"), Path("/mnt/SDCARD/MIYOO_EX/ports"))


def test_detect_retrodeck_json_in_home(tmp_path):
    ## The flatpak keeps it under ~/.var.
    config = tmp_path / "home/.var/app/net.retrodeck.retrodeck/config/retrodeck"
    config.mkdir(parents=True)
    (config / "retrodeck.json").write_text(json.dumps(
        {"paths": {"rd_home_path": "/rd", "ports_path": "/rd/pm"}}))

    assert detect(tmp_path)[:3] == (
        tmp_path / "home/.var/app/net.retrodeck.retrodeck/data", Path("/rd/pm/ports"), Path("/rd/roms/portmaster"))


@pytest.mark.parametrize("text", ["{", "[]", '{"paths": {}}', '{"other": 1}'])
def test_detect_retrodeck_json_broken_exits(tmp_path, text):
    make_dirs(tmp_path, "/var/config/retrodeck")
    (tmp_path / "var/config/retrodeck/retrodeck.json").write_text(text)

    with pytest.raises(SystemExit) as exc:
        detect(tmp_path)

    assert exc.value.code == 255


def test_detect_retrodeck_cfg(tmp_path):
    make_dirs(tmp_path, "/var/config/retrodeck")
    (tmp_path / "var/config/retrodeck/retrodeck.cfg").write_text(
        "[paths]\nrdhome=/rd\nports_folder=/media/pm\nroms_folder=/media/roms\n")

    assert detect(tmp_path)[:3] == (Path("/var/data"), Path("/media/pm/ports"), Path("/media/roms/portmaster"))


def test_detect_retrodeck_cfg_in_home_defaults(tmp_path):
    config = tmp_path / "home/.var/app/net.retrodeck.retrodeck/config/retrodeck"
    config.mkdir(parents=True)
    (config / "retrodeck.cfg").write_text("rdhome=/rd\n")

    assert detect(tmp_path)[:3] == (
        tmp_path / "home/.var/app/net.retrodeck.retrodeck/data", Path("/rd/PortMaster/ports"), Path("/rd/roms/portmaster"))


def test_detect_retrodeck_cfg_without_rdhome_exits(tmp_path):
    make_dirs(tmp_path, "/var/config/retrodeck")
    (tmp_path / "var/config/retrodeck/retrodeck.cfg").write_text("roms_folder=/r\n")

    with pytest.raises(SystemExit):
        detect(tmp_path)
