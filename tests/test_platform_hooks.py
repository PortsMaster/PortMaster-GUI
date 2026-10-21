# SPDX-License-Identifier: MIT
#
# The per-CFW platform hooks (harbourmaster/platform/), against a fake device root:
# each module's Path is swapped for one that puts absolute device paths under tmp.

import json
import os
from pathlib import Path

import pytest

from harbourmaster import platform as hm_platform
from harbourmaster.platform import arkos, base, batocera, emuelec, jelos, miyoo, muos, retrodeck, trimui
from harbourmaster.util import CancelEvent

from conftest import basic_port_files, write_port_zip


class DeviceRoot:
    """Absolute paths outside tmp_path land in `root`, `Path.home()` is root/home."""
    def __init__(self, tmp_path):
        self.tmp_path = tmp_path
        self.root = tmp_path / "root"
        self.root.mkdir()

    def __call__(self, *args):
        path = Path(*args)
        if path.is_absolute() and self.tmp_path not in path.parents:
            return self.root / path.relative_to("/")

        return path

    def home(self):
        return self.root / "home"

    def path(self, absolute):
        return self.root / absolute.lstrip("/")

    def write(self, absolute, text=""):
        path = self.path(absolute)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def mkdir(self, absolute):
        path = self.path(absolute)
        path.mkdir(parents=True, exist_ok=True)
        return path


@pytest.fixture
def device(tmp_path, monkeypatch):
    fake = DeviceRoot(tmp_path)
    for module in (muos, trimui, miyoo, jelos, batocera, retrodeck):
        monkeypatch.setattr(module, "Path", fake)

    return fake


@pytest.fixture
def pm_dir(hm):
    """PortMaster's own folder with every CFW's control.txt and launcher stub."""
    pm_dir = hm.tools_dir / "PortMaster"
    for cfw in ("muos", "trimui", "miyoo", "spruce", "batocera", "knulli", "retrodeck"):
        (pm_dir / cfw).mkdir(parents=True, exist_ok=True)
        (pm_dir / cfw / "control.txt").write_text(f"# {cfw} control\n")
        (pm_dir / cfw / "PortMaster.txt").write_text(f"# {cfw} launcher\n")

    return pm_dir


GAMEINFO = """<?xml version="1.0"?>
<gameList>
  <game>
    <path>./Test Port.sh</path>
    <name>Test Port</name>
    <desc>First line of the description.
Second line.</desc>
    <image>./testport/cover.png</image>
  </game>
</gameList>
"""


@pytest.fixture
def gameinfo(hm):
    ports_dir = hm.ports_dir
    (ports_dir / "testport").mkdir(exist_ok=True)
    (ports_dir / "testport" / "cover.png").write_bytes(b"cover")
    (ports_dir / "testport" / "screenshot.png").write_bytes(b"shot")
    (ports_dir / "Test Port.sh").write_text("#!/bin/bash\n")

    path = ports_dir / "testport" / "gameinfo.xml"
    path.write_text(GAMEINFO)
    return path


################################################################################
## The registry
def test_every_platform_is_a_platform(hm):
    for name, platform_class in hm_platform.HM_PLATFORMS.items():
        assert name == name.lower()
        assert issubclass(platform_class, base.PlatformBase)


def use_cfw(monkeypatch, cfw):
    from harbourmaster import hardware
    monkeypatch.setenv("CFW_NAME", cfw)
    hardware._CACHED_DICT = None


@pytest.mark.parametrize("cfw, expected", [
    ("muOS", muos.PlatformmuOS),
    ("TrimUI", trimui.PlatformTrimUI),
    ("spruce", miyoo.PlatformSpruce),
    ("darkosre", arkos.PlatformdArkOS),
    ("unofficialos", emuelec.PlatformUOS),
    ("something new", base.PlatformBase),
    ])
def test_platform_by_cfw_name(make_hm, monkeypatch, cfw, expected, device, pm_dir, hm_dirs):
    ## A fresh config folder, so first_run runs too: against the fake root.
    import shutil
    shutil.rmtree(str(pm_dir / "config"))
    use_cfw(monkeypatch, cfw)

    hm = make_hm()
    assert type(hm.platform) is expected
    assert hm.platform_name == (cfw.lower() if expected is not base.PlatformBase else "default")


################################################################################
## PlatformBase
def test_base_added_and_removed_ports(hm):
    platform = base.PlatformBase(hm)
    assert not platform.ports_changed()

    platform.port_install("a.zip", {}, [], [])
    assert platform.added_ports == {"a.zip"}
    assert platform.ports_changed()

    ## Uninstalling what was installed this run cancels out.
    platform.port_uninstall("a.zip", {}, [])
    assert platform.added_ports == set() and platform.removed_ports == set()
    assert not platform.ports_changed()

    platform.port_uninstall("b.zip", {}, [])
    assert platform.removed_ports == {"b.zip"}
    platform.port_install("b.zip", {}, [], [])
    assert platform.removed_ports == set() and platform.added_ports == set()


def test_base_defaults(hm):
    platform = base.PlatformBase(hm)

    assert platform.gamelist_file() is None
    assert platform.get_gcd_modes() == ()
    assert platform.get_gcd_mode() is None
    platform.set_gcd_mode("xbox")
    platform.runtime_install("x.squashfs", [])
    platform.loaded()
    platform.do_move_ports()
    platform.first_run()
    platform.portmaster_install([])


def test_base_gamelist_add_missing_gameinfo(hm, tmp_path):
    platform = base.PlatformTesting(hm)
    platform.gamelist_add(tmp_path / "missing.xml")
    assert not (hm.scripts_dir / "gamelist.xml").exists()


@pytest.mark.parametrize("platform_class", [muos.PlatformmuOS, trimui.PlatformTrimUI])
def test_special_gamelist_errors_dont_escape(hm, platform_class, device, gameinfo, monkeypatch, log_errors):
    ## Like a real gamelist: a failure updating the frontend's own catalogue must not fail the install.
    platform = platform_class(hm)

    def boom(*args, **kwargs):
        raise OSError("no space left on device")

    device.mkdir("/opt/graphicsmagick")
    for folder in ("box", "preview", "text"):
        device.mkdir(f"/run/muos/storage/info/catalogue/External - Ports/{folder}")
    for folder in ("Imgs/PORTS", "Roms/PORTS"):
        device.mkdir(f"/mnt/SDCARD/{folder}")

    monkeypatch.setattr(base.shutil, "copy", boom)
    monkeypatch.setattr(muos.shutil, "copy", boom)
    monkeypatch.setattr(trimui.shutil, "copy", boom)

    platform.gamelist_add(gameinfo)
    assert any("no space left on device" in message for message in log_errors)


@pytest.mark.parametrize("error", [CancelEvent, KeyboardInterrupt])
def test_special_gamelist_cancel_still_escapes(hm, error):
    platform = muos.PlatformmuOS(hm)

    with pytest.raises(error):
        with platform.gamelist_backup():
            raise error()


################################################################################
## GCD modes (ArkOS, AmberELEC, ...)
@pytest.fixture
def gcd(hm):
    backup = hm.tools_dir / "PortMaster" / ".Backup"
    backup.mkdir(parents=True)
    (backup / "donottouch.txt").write_text("# Standard Layout\n")
    (backup / "donottouch_x.txt").write_text("# Xbox 360 Layout\n")
    return emuelec.PlatformAmberELEC(hm)


def test_gcd_mode_defaults_to_standard(gcd, hm):
    assert gcd.get_gcd_modes() == ('standard', 'xbox')
    assert gcd.get_gcd_mode() == 'standard'
    assert hm.cfg_data['gcd-mode'] == 'standard'


def test_gcd_mode_detected_from_the_file(gcd, hm):
    (hm.tools_dir / "PortMaster" / "gamecontrollerdb.txt").write_text("# Xbox 360 Layout\nstuff\n")
    assert gcd.get_gcd_mode() == 'xbox'

    gcd.loaded()
    assert gcd.WANT_XBOX_FIX is True


def test_gcd_mode_bad_config_value(gcd, hm):
    hm.cfg_data['gcd-mode'] = 'nonsense'
    assert gcd.get_gcd_mode() == 'standard'


def test_set_gcd_mode(gcd, hm):
    gamecontroller = hm.tools_dir / "PortMaster" / "gamecontrollerdb.txt"

    gcd.set_gcd_mode('xbox')
    assert gamecontroller.read_text() == "# Xbox 360 Layout\n"
    assert hm.cfg_data['gcd-mode'] == 'xbox'
    assert json.loads(hm.cfg_file.read_text())['gcd-mode'] == 'xbox'

    gcd.set_gcd_mode('standard')
    assert gamecontroller.read_text() == "# Standard Layout\n"


@pytest.mark.parametrize("mode", [None, "", "rainbow"])
def test_set_gcd_mode_ignores_bad_modes(gcd, hm, mode):
    gcd.set_gcd_mode(mode)
    assert not (hm.tools_dir / "PortMaster" / "gamecontrollerdb.txt").exists()


def test_set_gcd_mode_missing_file(gcd, hm):
    (hm.tools_dir / "PortMaster" / ".Backup" / "donottouch_x.txt").unlink()
    gcd.set_gcd_mode('xbox')
    assert 'gcd-mode' not in hm.cfg_data


def test_harbourmaster_gcd_passthrough(hm, gcd):
    hm.platform = gcd
    hm.set_gcd_mode('xbox')
    assert hm.get_gcd_mode() == 'xbox'
    assert hm.get_gcd_modes() == ('standard', 'xbox')


################################################################################
## ArkOS
@pytest.mark.parametrize("good, expected", [
    (None, "bad"),
    ("old launcher", "bad"),
    ("new pmsplash launcher", "new pmsplash launcher"),
    ])
def test_arkos_moves_a_misplaced_launcher(hm, good, expected):
    (hm.ports_dir / "PortMaster.sh").write_text("bad")
    if good is not None:
        (hm.tools_dir / "PortMaster.sh").write_text(good)

    arkos.PlatformArkOS(hm)

    assert not (hm.ports_dir / "PortMaster.sh").exists()
    assert (hm.tools_dir / "PortMaster.sh").read_text() == expected


def test_arkos_nothing_to_move(hm):
    arkos.PlatformArkOS(hm)
    assert not (hm.tools_dir / "PortMaster.sh").exists()
    assert arkos.PlatformArkOS(hm).gamelist_file() == hm.ports_dir / "gamelist.xml"


def test_emuelec_gamelists(hm):
    assert emuelec.PlatformEmuELEC(hm).gamelist_file() == hm.scripts_dir / "gamelist.xml"
    assert emuelec.PlatformUOS(hm).gamelist_file() == hm.ports_dir / "gamelist.xml"
    assert emuelec.PlatformAmberELEC(hm).gamelist_file() == hm.ports_dir / "gamelist.xml"


################################################################################
## muOS
def test_muos_portmaster_install(hm, device, pm_dir):
    bash_files = []
    (pm_dir / "tasksetter").write_text("old")

    muos.PlatformmuOS(hm).first_run()
    muos.PlatformmuOS(hm).portmaster_install(bash_files)

    assert (pm_dir / "control.txt").read_text() == "# muos control\n"
    assert device.path("/roms/ports/PortMaster/control.txt").read_text() == "# muos control\n"
    assert (pm_dir / "PortMaster.sh").read_text() == "# muos launcher\n"
    assert bash_files == [pm_dir / "PortMaster.sh"]
    assert (pm_dir / "tasksetter").read_text() == ""


def muos_port_info(name="testport.zip", script="Test Port.sh"):
    return {"name": name, "files": {"port.json": "testport/port.json", script: script, "testport/": "testport/"}}


def test_muos_port_install_application(hm, device):
    app_dir = device.mkdir("/run/muos/storage/application")
    (hm.ports_dir / "testport").mkdir()
    (hm.ports_dir / "testport" / "mux_launch.txt").write_text("#!/bin/sh\nlaunch\n")

    platform = muos.PlatformmuOS(hm)
    platform.port_install("testport.zip", muos_port_info(), [], [])

    assert (app_dir / "Test Port" / "mux_launch.sh").read_text() == "#!/bin/sh\nlaunch\n"
    assert (app_dir / "Test Port" / platform.MUOSAPP_PM_MARKER).read_text() == "Test Port"

    platform.port_uninstall("testport.zip", muos_port_info(), [])
    assert not (app_dir / "Test Port").exists()


def test_muos_port_install_without_script_uses_the_port_name(hm, device):
    app_dir = device.mkdir("/run/muos/storage/application")
    (hm.ports_dir / "testport").mkdir()
    (hm.ports_dir / "testport" / "mux_launch.txt").write_text("x")

    info = {"name": "testport.zip", "files": {"port.json": "testport/port.json"}}
    muos.PlatformmuOS(hm).port_install("testport.zip", info, [], [])

    assert (app_dir / "testport" / "mux_launch.sh").is_file()


def test_muos_port_install_not_an_application(hm, device):
    app_dir = device.mkdir("/run/muos/storage/application")
    (hm.ports_dir / "testport").mkdir()

    muos.PlatformmuOS(hm).port_install("testport.zip", muos_port_info(), [], [])
    assert list(app_dir.iterdir()) == []


def test_muos_port_install_without_the_application_folder(hm, device):
    (hm.ports_dir / "testport").mkdir()
    (hm.ports_dir / "testport" / "mux_launch.txt").write_text("x")

    muos.PlatformmuOS(hm).port_install("testport.zip", muos_port_info(), [], [])
    assert not device.path("/run/muos/storage/application").exists()


def test_muos_port_install_copy_error_is_logged(hm, device, monkeypatch, log_errors):
    device.mkdir("/run/muos/storage/application")
    (hm.ports_dir / "testport").mkdir()
    (hm.ports_dir / "testport" / "mux_launch.txt").write_text("x")

    def fail(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(muos.shutil, "copy2", fail)
    muos.PlatformmuOS(hm).port_install("testport.zip", muos_port_info(), [], [])

    assert any("read-only" in message for message in log_errors)


def test_muos_uninstall_leaves_apps_it_didnt_make(hm, device):
    app_dir = device.mkdir("/run/muos/storage/application/Test Port")
    (app_dir / "mux_launch.sh").write_text("someone else's")

    muos.PlatformmuOS(hm).port_uninstall("testport.zip", muos_port_info(), [])
    assert (app_dir / "mux_launch.sh").is_file()


def test_muos_uninstall_error_is_ignored(hm, device, monkeypatch):
    app_dir = device.mkdir("/run/muos/storage/application/Test Port")
    (app_dir / muos.PlatformmuOS.MUOSAPP_PM_MARKER).write_text("Test Port")

    def fail(*args, **kwargs):
        raise OSError("busy")

    monkeypatch.setattr(muos.shutil, "rmtree", fail)
    muos.PlatformmuOS(hm).port_uninstall("testport.zip", muos_port_info(), [])


@pytest.mark.parametrize("catalogue", [
    "/run/muos/storage/info/catalogue/External - Ports",
    "/mnt/mmc/MUOS/info/catalogue/External - Ports",
    ])
def test_muos_gamelist_add(hm, device, gameinfo, catalogue):
    device.write("/usr/bin/magick")
    for folder in ("box", "preview", "text"):
        device.mkdir(f"{catalogue}/{folder}")

    platform = muos.PlatformmuOS(hm)
    assert platform.gamelist_file() is base.SPECIAL_GAMELIST_CODE
    platform.gamelist_add(gameinfo)

    root = device.path(catalogue)
    assert (root / "box" / "Test Port-pre.png").read_bytes() == b"cover"
    assert (root / "preview" / "Test Port-pre.png").read_bytes() == b"shot"
    assert (root / "text" / "Test Port.txt").read_text() == "First line of the description.\n"
    assert platform.ports_changed()


def test_muos_gamelist_add_jpg_screenshot_and_missing_image(hm, device, gameinfo):
    catalogue = "/run/muos/storage/info/catalogue/External - Ports"
    device.mkdir("/opt/graphicsmagick")
    for folder in ("box", "preview", "text"):
        device.mkdir(f"{catalogue}/{folder}")

    (hm.ports_dir / "testport" / "screenshot.png").unlink()
    (hm.ports_dir / "testport" / "screenshot.jpg").write_bytes(b"jpg")

    muos.PlatformmuOS(hm).gamelist_add(gameinfo)
    ## Named after the cover's suffix.
    assert device.path(catalogue + "/preview/Test Port-pre.png").read_bytes() == b"jpg"

    (hm.ports_dir / "testport" / "cover.png").unlink()
    for path in device.path(catalogue).rglob("*.*"):
        path.unlink()

    muos.PlatformmuOS(hm).gamelist_add(gameinfo)
    assert not device.path(catalogue + "/box/Test Port-pre.png").exists()
    assert device.path(catalogue + "/text/Test Port.txt").is_file()


def test_muos_gamelist_add_needs_an_image_tool(hm, device, gameinfo):
    platform = muos.PlatformmuOS(hm)
    platform.gamelist_add(gameinfo)

    assert not platform.ports_changed()


def test_muos_gamelist_add_makes_missing_catalogue_folders(hm, device, gameinfo):
    ## A catalogue without a preview folder failed the whole port install.
    device.write("/usr/bin/magick")
    catalogue = "/run/muos/storage/info/catalogue/External - Ports"
    device.mkdir(catalogue)

    muos.PlatformmuOS(hm).gamelist_add(gameinfo)

    assert device.path(catalogue + "/box/Test Port-pre.png").is_file()
    assert device.path(catalogue + "/preview/Test Port-pre.png").is_file()


def test_muos_gamelist_add_without_a_catalogue(hm, device, gameinfo):
    device.write("/usr/bin/magick")
    muos.PlatformmuOS(hm).gamelist_add(gameinfo)

    ## None made up.
    assert not device.path("/mnt/mmc").exists()
    assert not device.path("/run/muos/storage/info").exists()


def test_muos_gamelist_add_missing_file(hm, device, tmp_path):
    muos.PlatformmuOS(hm).gamelist_add(tmp_path / "missing.xml")


################################################################################
## TrimUI
@pytest.fixture
def trimui_dirs(device):
    for folder in ("/mnt/SDCARD/Roms/PORTS", "/mnt/SDCARD/Imgs/PORTS", "/mnt/SDCARD/Ports"):
        device.mkdir(folder)

    return device


def test_trimui_portmaster_install(hm, trimui_dirs, pm_dir):
    bash_files = []
    trimui.PlatformTrimUI(hm).first_run()
    trimui.PlatformTrimUI(hm).portmaster_install(bash_files)

    assert (pm_dir / "control.txt").read_text() == "# trimui control\n"
    assert trimui_dirs.path("/roms/ports/PortMaster/control.txt").is_file()
    assert (hm.tools_dir / "launch.sh").read_text() == "# trimui launcher\n"
    assert bash_files == [hm.tools_dir / "launch.sh"]
    assert (pm_dir / "tasksetter").is_file()


def test_trimui_port_install_roms_mode(hm, trimui_dirs):
    script = hm.scripts_dir / "Test Port.sh"
    script.write_text("#!/bin/bash\n")
    nested = hm.scripts_dir / "testport" / "inner.sh"
    nested.parent.mkdir()
    nested.write_text("x")

    platform = trimui.PlatformTrimUI(hm)
    platform.port_install("testport.zip", {}, [script, nested, hm.scripts_dir / "testport" / "data.txt"], [])

    roms = trimui_dirs.path("/mnt/SDCARD/Roms/PORTS")
    assert (roms / "Test Port.sh").read_text() == "#!/bin/bash\n"
    ## Only scripts right in the scripts folder.
    assert not (roms / "inner.sh").exists()

    platform.port_uninstall("testport.zip", {}, ["Test Port.sh", "testport/"])
    assert not (roms / "Test Port.sh").exists()


def test_trimui_port_install_outside_the_scripts_dir(hm, trimui_dirs, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    script = other / "x.sh"
    script.write_text("x")

    trimui.PlatformTrimUI(hm).port_install("x.zip", {}, [script], [])
    assert not trimui_dirs.path("/mnt/SDCARD/Roms/PORTS/x.sh").exists()


def test_trimui_add_script_same_file(hm, trimui_dirs):
    ## The scripts folder *is* the roms folder: nothing to copy.
    roms = trimui_dirs.path("/mnt/SDCARD/Roms/PORTS")
    script = roms / "Same.sh"
    script.write_text("x")

    trimui.PlatformTrimUI(hm).add_port_script(script)
    assert script.read_text() == "x"


def test_trimui_ports_mode(hm, trimui_dirs):
    hm.cfg_data['trimui-port-mode'] = 'ports'
    script = hm.scripts_dir / "Test Port.sh"
    script.write_text("x")

    platform = trimui.PlatformTrimUI(hm)
    platform.add_port_script(script)

    port_dir = trimui_dirs.path("/mnt/SDCARD/Ports/portmaster-test.port")
    config = json.loads((port_dir / "config.json").read_text())
    assert config['label'] == "Test Port"
    assert config['package'] == "portmaster-test.port"
    assert config['launch'] == str(script).replace(" ", "\\ ")

    platform.remove_port_script(script)
    assert not port_dir.exists()


def test_trimui_gamelist_add_roms_mode(hm, trimui_dirs, gameinfo):
    platform = trimui.PlatformTrimUI(hm)
    platform.gamelist_add(gameinfo)

    assert trimui_dirs.path("/mnt/SDCARD/Imgs/PORTS/Test Port-pre.png").read_bytes() == b"cover"
    assert trimui_dirs.path("/mnt/SDCARD/Roms/PORTS/Test Port.sh").is_file()


def test_trimui_gamelist_add_ports_mode(hm, trimui_dirs, gameinfo):
    hm.cfg_data['trimui-port-mode'] = 'ports'
    trimui.PlatformTrimUI(hm).gamelist_add(gameinfo)

    port_dir = trimui_dirs.path("/mnt/SDCARD/Ports/portmaster-test.port")
    assert json.loads((port_dir / "config.json").read_text())['label'] == "Test Port"
    assert (port_dir / "icon-pre.png").read_bytes() == b"cover"


def test_trimui_gamelist_add_partial_entries(hm, trimui_dirs, gameinfo):
    gameinfo.write_text("""<gameList>
  <game><path>./Missing.sh</path></game>
  <game><path>./Test Port.sh</path></game>
  <game><path>./Test Port.sh</path><image>./testport/none.png</image></game>
</gameList>""")
    hm.cfg_data['trimui-port-mode'] = 'ports'

    trimui.PlatformTrimUI(hm).gamelist_add(gameinfo)

    port_dir = trimui_dirs.path("/mnt/SDCARD/Ports/portmaster-test.port")
    ## No name: the script's.
    assert json.loads((port_dir / "config.json").read_text())['label'] == "Test Port"
    assert not (port_dir / "icon-pre.png").exists()


def test_trimui_gamelist_add_missing_file(hm, trimui_dirs, tmp_path):
    platform = trimui.PlatformTrimUI(hm)
    platform.gamelist_add(tmp_path / "missing.xml")
    assert not platform.ports_changed()


@pytest.mark.parametrize("mode", ["roms", "ports"])
def test_trimui_do_move_ports(hm, trimui_dirs, gameinfo, mode):
    roms = trimui_dirs.path("/mnt/SDCARD/Roms/PORTS")
    ports = trimui_dirs.path("/mnt/SDCARD/Ports")
    (roms / "Stale.sh").write_text("x")
    (ports / "portmaster-stale").mkdir()
    (ports / "portmaster-file").write_text("not a folder")
    (ports / "someone-elses").mkdir()

    hm.cfg_data['trimui-port-mode'] = mode
    trimui.PlatformTrimUI(hm).do_move_ports()

    assert (ports / "someone-elses").is_dir()
    assert (ports / "portmaster-file").is_file()
    if mode == "roms":
        assert not (ports / "portmaster-stale").exists()
        assert (roms / "Test Port.sh").is_file()
        assert (roms / "Stale.sh").is_file()
    else:
        assert not (roms / "Stale.sh").exists()
        assert (ports / "portmaster-test.port" / "config.json").is_file()


################################################################################
## Miyoo and spruce
def test_miyoo_portmaster_install(hm, device, pm_dir):
    bash_files = []
    miyoo.PlatformMiyoo(hm).first_run()
    miyoo.PlatformMiyoo(hm).portmaster_install(bash_files)

    assert (pm_dir / "control.txt").read_text() == "# miyoo control\n"
    assert (pm_dir / "PortMaster.sh").read_text() == "# miyoo launcher\n"
    assert device.path("/root/.local/share/PortMaster/control.txt").read_text() == "# miyoo control\n"
    assert bash_files == [pm_dir / "PortMaster.sh"]


@pytest.mark.parametrize("xdg", [True, False])
def test_spruce_portmaster_install(hm, device, pm_dir, monkeypatch, tmp_path, xdg):
    if xdg:
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        control = tmp_path / "xdg" / "PortMaster" / "control.txt"
    else:
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)
        control = device.path("/home/.local/share/PortMaster/control.txt")

    platform = miyoo.PlatformSpruce(hm)
    platform.first_run()
    platform.portmaster_post_install()

    assert (pm_dir / "control.txt").read_text() == "# spruce control\n"
    assert (pm_dir / "PortMaster.sh").read_text() == "# spruce launcher\n"
    assert control.read_text() == "# spruce control\n"


################################################################################
## JELOS / ROCKNIX
def test_jelos_portmaster_install(hm, device, monkeypatch):
    system = device.mkdir("/usr/config/PortMaster")
    for name in ("control.txt", "gamecontrollerdb.txt", "mapper.txt", "oga_controls", "oga_controls_settings.txt"):
        (system / name).write_text(name)

    import shutil
    copytree = shutil.copytree
    monkeypatch.setattr(jelos.shutil, "copytree", lambda src, dst: copytree(str(device(src)), str(dst)))
    (hm.tools_dir / "PortMaster").mkdir(exist_ok=True)

    platform = jelos.PlatformROCKNIX(hm)
    platform.first_run()

    pm_dir = hm.tools_dir / "PortMaster"
    for name in ("control.txt", "gamecontrollerdb.txt", "mapper.txt", "oga_controls", "oga_controls_settings.txt"):
        assert (pm_dir / name).read_text() == name

    assert device.path("/storage/.config/PortMaster/control.txt").is_file()
    assert platform.gamelist_file() == hm.ports_dir / "gamelist.xml"
    assert platform.ES_NAME == "weston"


################################################################################
## Batocera / knulli settings
@pytest.fixture
def batocera_conf(device, monkeypatch):
    files = [str(device.path(path)) for path in batocera.PlatformBatocera.BATOCERA_CONFIG_FILES]
    monkeypatch.setattr(batocera.PlatformBatocera, "BATOCERA_CONFIG_FILES", files)
    return device


@pytest.mark.parametrize("files, key, expected", [
    ({"/userdata/system/batocera.conf": "a=1\n"}, "a", "1"),
    ({"/userdata/system/knulli.conf": "a=knulli\n", "/userdata/system/batocera.conf": "a=batocera\n"}, "a", "knulli"),
    ({"/userdata/system/system.conf": "# a=comment\n\nnonsense\n b = spaced \n"}, "b", "spaced"),
    ({"/userdata/system/batocera.conf": "a=1\n"}, "missing", "default"),
    ({}, "a", "default"),
    ])
def test_batocera_settings_get(hm, batocera_conf, files, key, expected):
    device = batocera_conf
    for path, text in files.items():
        device.write(path, text)

    platform = batocera.PlatformBatocera(hm)
    assert platform.batocera_settings_get(key, "default") == expected
    ## Remembered.
    assert platform.batocera_settings_get(key, "default") == expected


@pytest.mark.parametrize("settings, expected", [
    (None, False),
    ('<config><bool name="InvertButtons" value="true" /></config>', True),
    ('<config><bool name="InvertButtons" value="false" /></config>', False),
    ('<config><bool name="Other" value="true" /></config>', False),
    ])
def test_batocera_invert_buttons(hm, device, settings, expected):
    if settings is not None:
        device.write("/userdata/system/configs/emulationstation/es_settings.cfg", settings)

    platform = batocera.PlatformBatocera(hm)
    assert platform.get_invert_buttons_value() is expected

    platform.loaded()
    assert platform.WANT_SWAP_BUTTONS is (not expected)


@pytest.mark.parametrize("conf, invert, xbox, swap", [
    ('ports["PortMaster.sh"].xbox_layout=0\n', None, False, True),
    ('ports["PortMaster.sh"].xbox_layout=1\n', None, False, False),
    ('ports.xbox_layout=0\n', None, False, True),
    ('', "true", True, False),
    ('', "false", False, True),
    ])
def test_knulli_loaded(hm, batocera_conf, conf, invert, xbox, swap):
    device = batocera_conf
    device.write("/userdata/system/batocera.conf", conf)
    if invert is not None:
        device.write("/userdata/system/configs/emulationstation/es_settings.cfg",
                     f'<config><bool name="InvertButtons" value="{invert}" /></config>')

    platform = batocera.PlatformKnulli(hm)
    platform.loaded()

    assert platform.WANT_XBOX_FIX is xbox
    assert platform.WANT_SWAP_BUTTONS is swap


def test_batocera_first_run(hm, device, pm_dir):
    platform = batocera.PlatformBatocera(hm)
    platform.first_run()

    assert (hm.tools_dir / ".pugwash-reboot").is_file()
    assert (pm_dir / "control.txt").read_text() == "# batocera control\n"
    assert platform.gamelist_file() == hm.ports_dir / "gamelist.xml"


def test_batocera_move_launcher_error_is_logged(hm, device, pm_dir, monkeypatch, log_errors):
    (pm_dir / "PortMaster.sh").write_text("x")

    def fail(*args, **kwargs):
        raise OSError("read-only")

    monkeypatch.setattr(batocera, "replace_file", fail)
    batocera.PlatformBatocera(hm)._move_launcher()

    assert any("read-only" in message for message in log_errors)


################################################################################
## RetroDECK
def write_rd_json(device, paths, where="/var/config/retrodeck/retrodeck.json"):
    return device.write(where, json.dumps({"paths": paths}))


def test_retrodeck_json_config(hm, device, tmp_path):
    write_rd_json(device, {"rd_home_path": "/rd", "roms_path": "/roms", "ports_path": "/ports"})

    config = retrodeck.PlatformRetroDECK(hm).get_rdconfig()
    assert config == {"rdhome": device("/rd"), "roms_folder": device("/roms"), "ports_folder": device("/ports")}


def test_retrodeck_json_config_defaults(hm, device):
    write_rd_json(device, {"rd_home_path": "/rd"}, where="/home/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.json")

    config = retrodeck.PlatformRetroDECK(hm).get_rdconfig()
    assert config['roms_folder'] == device("/rd/roms")
    assert config['ports_folder'] == device("/rd/PortMaster")


@pytest.mark.parametrize("text", ['[]', '{"paths": {}}', 'garbage'])
def test_retrodeck_bad_json_config(hm, device, text, log_errors):
    device.write("/var/config/retrodeck/retrodeck.json", text)

    platform = retrodeck.PlatformRetroDECK(hm)
    assert platform.get_rdconfig() is None
    assert platform.gamelist_file() is None


def test_retrodeck_cfg_config(hm, device):
    device.write("/var/config/retrodeck/retrodeck.cfg", "[paths]\nrdhome=/rd\nroms_folder=/r\nmedia_folder=/m\n")

    config = retrodeck.PlatformRetroDECK(hm).get_rdconfig()
    assert config['rdhome'] == device("/rd")
    assert config['roms_folder'] == device("/r")
    assert config['media_folder'] == device("/m")
    assert config['ports_folder'] == device("/rd/PortMaster")


def test_retrodeck_cfg_without_rdhome(hm, device, log_errors):
    device.write("/home/.var/app/net.retrodeck.retrodeck/config/retrodeck/retrodeck.cfg", "roms_folder=/r\n")

    assert retrodeck.PlatformRetroDECK(hm).get_rdconfig() is None
    assert any("rdhome" in message for message in log_errors)


def test_retrodeck_no_config_at_all(hm, device, gameinfo):
    ## Neither file: it opened the missing .cfg anyway, failing every install with a gameinfo.xml.
    platform = retrodeck.PlatformRetroDECK(hm)

    assert platform.get_rdconfig() is None
    assert platform.gamelist_file() is None
    platform.gamelist_add(gameinfo)


def test_retrodeck_gamelist_file(hm, device, tmp_path):
    write_rd_json(device, {"rd_home_path": str(tmp_path / "rd")})

    gamelist = retrodeck.PlatformRetroDECK(hm).gamelist_file()
    assert gamelist == tmp_path / "rd" / "ES-DE" / "gamelists" / "portmaster" / "gamelist.xml"
    assert gamelist.parent.is_dir()


def test_retrodeck_portmaster_install(hm, device, pm_dir, tmp_path):
    scripts = hm.scripts_dir
    (scripts / "PortMaster.sh").symlink_to(tmp_path / "nowhere")
    bash_files = []

    platform = retrodeck.PlatformRetroDECK(hm)
    platform.first_run()
    platform.portmaster_install(bash_files)

    assert (pm_dir / "control.txt").read_text() == "# retrodeck control\n"
    assert (pm_dir / "PortMaster.sh").read_text() == "# retrodeck launcher\n"
    assert not (scripts / "PortMaster.sh").is_symlink()
    assert (scripts / "PortMaster.sh").read_text() == "# retrodeck launcher\n"
    assert bash_files == [scripts / "PortMaster.sh"]


################################################################################
## End to end: an install on muOS with the catalogue
def test_muos_install_fills_the_catalogue(make_hm, hm_dirs, device, monkeypatch, pm_dir):
    use_cfw(monkeypatch, "muOS")
    hm = make_hm()
    assert type(hm.platform) is muos.PlatformmuOS

    device.write("/usr/bin/magick")
    catalogue = "/run/muos/storage/info/catalogue/External - Ports"
    for folder in ("box", "preview", "text"):
        device.mkdir(f"{catalogue}/{folder}")

    files = basic_port_files()
    files["testport/gameinfo.xml"] = GAMEINFO
    files["testport/cover.png"] = "cover"
    zip_file = write_port_zip(hm_dirs['temp_dir'] / "testport.zip", files)

    assert hm.install_port(str(zip_file)) == 0
    assert device.path(catalogue + "/box/Test Port-pre.png").read_text() == "cover"
    assert device.path(catalogue + "/text/Test Port.txt").read_text().startswith("First line")
