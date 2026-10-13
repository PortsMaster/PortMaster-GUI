# SPDX-License-Identifier: MIT
#
# gameinfo.xml -> the frontend's gamelist.xml (PlatformBase.gamelist_add and
# gamelist_backup), and RetroDECK's ES-DE screenshot copy.

import shutil
import xml.etree.ElementTree as ET

import pytest

import harbourmaster
from harbourmaster.platform.base import PlatformBase
from harbourmaster.platform.retrodeck import PlatformRetroDECK


GAMEINFO = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Test Port.sh</path>
    <name>Test Port</name>
    <desc>A test.</desc>
    <image>./testport/screenshot.png</image>
    <genre>Puzzle</genre>
    <notmapped>dropped</notmapped>
  </game>
</gameList>
"""


def games(gamelist_xml):
    root = ET.parse(gamelist_xml).getroot()
    return {
        game.find('path').text: {child.tag: child.text for child in game}
        for game in root.findall('game')
        }


@pytest.fixture
def platform(hm, tmp_path, monkeypatch):
    platform = PlatformBase(hm)
    gamelist_xml = tmp_path / "frontend" / "gamelist.xml"
    gamelist_xml.parent.mkdir()
    monkeypatch.setattr(platform, "gamelist_file", lambda: gamelist_xml)
    platform.test_gamelist = gamelist_xml
    return platform


@pytest.fixture
def gameinfo(hm_dirs):
    port_dir = hm_dirs['ports_dir'] / "testport"
    port_dir.mkdir(parents=True)
    (port_dir / "screenshot.png").write_bytes(b"png")
    gameinfo = port_dir / "gameinfo.xml"
    gameinfo.write_text(GAMEINFO)
    return gameinfo


## -- gamelist_add

def test_add_creates_gamelist(platform, gameinfo):
    platform.gamelist_add(gameinfo)

    assert games(platform.test_gamelist) == {
        "./Test Port.sh": {
            'path': "./Test Port.sh",
            'name': "Test Port",
            'desc': "A test.",
            'image': "./testport/screenshot.png",
            'genre': "Puzzle",
            },
        }
    assert platform.ports_changed()


def test_add_updates_existing_entry(platform, gameinfo):
    platform.test_gamelist.write_text(
        "<gameList><game><path>./Test Port.sh</path><name>Old</name><playcount>3</playcount></game>"
        "<game><path>./Other.sh</path><name>Other</name></game></gameList>")

    platform.gamelist_add(gameinfo)

    result = games(platform.test_gamelist)
    assert sorted(result) == ["./Other.sh", "./Test Port.sh"]
    assert result["./Test Port.sh"]['name'] == "Test Port"
    ## What the frontend added is kept.
    assert result["./Test Port.sh"]['playcount'] == "3"


def test_add_restores_empty_gamelist_from_backup(platform, gameinfo):
    platform.test_gamelist.write_text("")
    platform.test_gamelist.with_name("gamelist.xml.bak").write_text(
        "<gameList><game><path>./Other.sh</path><name>Other</name></game></gameList>")

    platform.gamelist_add(gameinfo)

    assert sorted(games(platform.test_gamelist)) == ["./Other.sh", "./Test Port.sh"]


def test_add_with_separate_scripts_dir_uses_absolute_images(platform, gameinfo, hm, tmp_path, monkeypatch):
    ## eg: muOS / RetroDECK, the scripts are not next to the port directories.
    monkeypatch.setattr(hm, "scripts_dir", tmp_path / "scripts")

    platform.gamelist_add(gameinfo)

    image = games(platform.test_gamelist)["./Test Port.sh"]['image']
    assert image == str(hm.ports_dir / "testport" / "screenshot.png")


def test_add_no_gamelist_platform(hm, gameinfo):
    ## Platforms without a gamelist do nothing.
    PlatformBase(hm).gamelist_add(gameinfo)


## -- gamelist_backup: a failure part way restores the gamelist, and is logged

def test_broken_gameinfo_restores_and_logs(platform, gameinfo, log_errors):
    original = "<gameList><game><path>./Other.sh</path><name>Other</name></game></gameList>"
    platform.test_gamelist.write_text(original)
    gameinfo.write_text("<gameList><game><path>./Broken.sh</path>")

    ## A broken gamelist never fails the install that called it.
    platform.gamelist_add(gameinfo)

    assert platform.test_gamelist.read_text() == original
    assert any("gamelist" in error for error in log_errors), log_errors


def test_backup_restores_on_error(platform, log_errors):
    platform.test_gamelist.write_text("<gameList />")

    with platform.gamelist_backup() as gamelist_xml:
        gamelist_xml.write_text("half written")
        raise ValueError("boom")

    assert platform.test_gamelist.read_text() == "<gameList />"
    assert any("boom" in error for error in log_errors), log_errors


def test_backup_nested_restores_once(platform):
    platform.test_gamelist.write_text("<gameList />")

    with platform.gamelist_backup():
        with platform.gamelist_backup() as gamelist_xml:
            gamelist_xml.write_text("inner")

        gamelist_xml.write_text("outer")

    assert platform.test_gamelist.read_text() == "outer"
    assert platform._GAMELIST_BACKUP == 0


@pytest.mark.parametrize("error", [harbourmaster.CancelEvent, KeyboardInterrupt])
def test_backup_cancel_restores_and_propagates(platform, error):
    platform.test_gamelist.write_text("<gameList />")

    with pytest.raises(error):
        with platform.gamelist_backup() as gamelist_xml:
            gamelist_xml.write_text("half written")
            raise error()

    assert platform.test_gamelist.read_text() == "<gameList />"
    assert platform._GAMELIST_BACKUP == 0


def test_backup_without_gamelist_propagates(hm):
    with pytest.raises(harbourmaster.CancelEvent):
        with PlatformBase(hm).gamelist_backup() as gamelist_xml:
            assert gamelist_xml is None
            raise harbourmaster.CancelEvent()


## -- RetroDECK: ES-DE wants the screenshot copied into its media dir

@pytest.fixture
def retrodeck(hm, tmp_path, monkeypatch):
    platform = PlatformRetroDECK(hm)
    rdhome = tmp_path / "retrodeck"
    monkeypatch.setattr(platform, "RD_CONFIG", {
        'rdhome': rdhome,
        'roms_folder': rdhome / "roms",
        'ports_folder': rdhome / "PortMaster",
        })
    platform.test_rdhome = rdhome
    return platform


def test_retrodeck_copies_screenshot(retrodeck, gameinfo, tmp_path, monkeypatch):
    ## pugwash runs from $controlfolder, not the ports dir.
    monkeypatch.chdir(tmp_path)

    retrodeck.gamelist_add(gameinfo)

    media = retrodeck.test_rdhome / "ES-DE" / "downloaded_media" / "portmaster" / "screenshots" / "Test Port.png"
    assert media.read_bytes() == b"png"

    gamelist_xml = retrodeck.test_rdhome / "ES-DE" / "gamelists" / "portmaster" / "gamelist.xml"
    entry = games(gamelist_xml)["./Test Port.sh"]
    assert entry['name'] == "Test Port"
    ## ES-DE finds the image itself, it is not in the gamelist.
    assert 'image' not in entry


def test_retrodeck_separate_scripts_dir(retrodeck, gameinfo, hm, tmp_path, monkeypatch):
    ## A real RetroDECK install: scripts in roms/portmaster, ports in PortMaster/ports.
    monkeypatch.setattr(hm, "scripts_dir", tmp_path / "scripts")
    monkeypatch.chdir(tmp_path)

    retrodeck.gamelist_add(gameinfo)

    media = retrodeck.test_rdhome / "ES-DE" / "downloaded_media" / "portmaster" / "screenshots" / "Test Port.png"
    assert media.read_bytes() == b"png"


def test_retrodeck_missing_screenshot_still_adds_game(retrodeck, gameinfo, log_errors):
    (gameinfo.parent / "screenshot.png").unlink()

    retrodeck.gamelist_add(gameinfo)

    gamelist_xml = retrodeck.test_rdhome / "ES-DE" / "gamelists" / "portmaster" / "gamelist.xml"
    assert "./Test Port.sh" in games(gamelist_xml)


## -- PortMaster's own entry, on platforms whose ports list holds the launcher

from conftest import PM_DIR  # noqa: E402
from harbourmaster.platform.arkos import PlatformArkOS  # noqa: E402
from harbourmaster.platform.batocera import PlatformBatocera, PlatformKnulli  # noqa: E402
from harbourmaster.platform.emuelec import PlatformAmberELEC  # noqa: E402
from harbourmaster.platform.jelos import PlatformROCKNIX  # noqa: E402


@pytest.fixture
def pm_files(hm):
    """The real PortMaster/gameinfo.xml and screenshot.png, where PortMaster is installed."""
    pm_dir = hm.tools_dir / "PortMaster"
    pm_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(str(PM_DIR / "gameinfo.xml"), str(pm_dir / "gameinfo.xml"))
    shutil.copy(str(PM_DIR / "screenshot.png"), str(pm_dir / "screenshot.png"))
    return pm_dir


def ports_gamelist(hm):
    return hm.ports_dir / "gamelist.xml"


@pytest.mark.parametrize("platform_class", [PlatformBatocera, PlatformKnulli, PlatformAmberELEC])
def test_portmaster_entry_added(hm, pm_files, platform_class):
    platform_class(hm).gamelist_add_portmaster()

    entry = games(ports_gamelist(hm))["./PortMaster.sh"]
    assert entry['name'] == "PortMaster"
    assert entry['desc'].startswith("PortMaster is an open-source port manager")
    ## PortMaster isn't in the ports dir on Batocera, so the image is a full path.
    assert entry['image'] == str(pm_files / "screenshot.png")
    assert (pm_files / "screenshot.png").is_file()


def test_portmaster_entry_updates_in_place(hm, pm_files):
    ports_gamelist(hm).write_text(
        "<gameList><game><path>./PortMaster.sh</path><name>PortMaster.sh</name><playcount>7</playcount></game>"
        "<game><path>./Other.sh</path><name>Other</name></game></gameList>")
    platform = PlatformBatocera(hm)

    platform.gamelist_add_portmaster()
    platform.gamelist_add_portmaster()

    result = games(ports_gamelist(hm))
    assert sorted(result) == ["./Other.sh", "./PortMaster.sh"]
    assert result["./PortMaster.sh"]['name'] == "PortMaster"
    assert result["./PortMaster.sh"]['playcount'] == "7"


def test_portmaster_entry_retrodeck(retrodeck, hm, pm_files):
    retrodeck.gamelist_add_portmaster()

    media = retrodeck.test_rdhome / "ES-DE" / "downloaded_media" / "portmaster" / "screenshots" / "PortMaster.png"
    assert media.read_bytes() == (PM_DIR / "screenshot.png").read_bytes()

    gamelist_xml = retrodeck.test_rdhome / "ES-DE" / "gamelists" / "portmaster" / "gamelist.xml"
    entry = games(gamelist_xml)["./PortMaster.sh"]
    assert entry['name'] == "PortMaster"
    assert 'image' not in entry


def test_portmaster_entry_respects_gamelist_update(hm, pm_files):
    hm.cfg_data['gamelist_update'] = False

    PlatformBatocera(hm).gamelist_add_portmaster()

    assert not ports_gamelist(hm).exists()


@pytest.mark.parametrize("platform_class", [PlatformBase, PlatformArkOS, PlatformROCKNIX])
def test_portmaster_entry_not_where_the_launcher_lives_elsewhere(hm, pm_files, platform_class):
    ## ArkOS: Tools menu, ROCKNIX: its own start script and a hidden folder.
    platform_class(hm).gamelist_add_portmaster()

    assert not ports_gamelist(hm).exists()


@pytest.mark.parametrize("gameinfo", [None, "<gameList><game><path>"])
def test_portmaster_entry_bad_gameinfo(hm, pm_files, gameinfo):
    if gameinfo is None:
        (pm_files / "gameinfo.xml").unlink()
    else:
        (pm_files / "gameinfo.xml").write_text(gameinfo)

    PlatformBatocera(hm).gamelist_add_portmaster()

    assert not ports_gamelist(hm).exists() or "PortMaster.sh" not in ports_gamelist(hm).read_text()


def test_post_install_moves_launcher_then_adds_entry(hm, pm_files, monkeypatch, tmp_path):
    ## Batocera: the launcher arrives in PortMaster/ and moves to the ports dir.
    monkeypatch.setattr(hm, "scripts_dir", hm.ports_dir)
    (pm_files / "PortMaster.sh").write_text("launcher")
    platform = PlatformKnulli(hm)

    seen = []
    real_add = platform.gamelist_add

    def gamelist_add(gameinfo_file):
        seen.append((hm.ports_dir / "PortMaster.sh").is_file())
        real_add(gameinfo_file)

    monkeypatch.setattr(platform, "gamelist_add", gamelist_add)

    platform.portmaster_post_install()

    assert seen == [True]
    assert "./PortMaster.sh" in games(ports_gamelist(hm))
