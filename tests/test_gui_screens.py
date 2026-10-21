# SPDX-License-Identifier: MIT
#
# The GUI's other screens a button at a time: startup (disclaimer, unsupported
# firmware warnings), port info, the runtime manager, themes and colour schemes.

import json
from pathlib import Path

import pytest

import harbourmaster

from test_gui_scenes import choose, press, push, select, top


pytestmark = pytest.mark.sdl


@pytest.fixture
def screen_gui(gui, online_hm, monkeypatch):
    from pugwash import scenes

    saved_scenes = list(gui.scenes)
    gui.hm = online_hm
    gui.boxes = []
    gui.answer = True
    gui.cancelled = []
    gui.scenes_mod = scenes

    def message_box(text, *args, **kwargs):
        gui.boxes.append(text)
        return gui.answer

    monkeypatch.setattr(gui, "message_box", message_box)
    monkeypatch.setattr(gui, "do_cancel", lambda: gui.cancelled.append(True))

    yield gui

    gui.scenes = saved_scenes
    gui.events.running = True
    gui.hm = None


def bar(scene):
    return [item[1] if isinstance(item, tuple) else item for item in scene.tags['button_bar'].bar]


################################################################################
## Startup warnings
class Root:
    def __init__(self, tmp_path):
        self.root = tmp_path / "root"
        self.root.mkdir()

    def __call__(self, *args):
        path = Path(*args)
        return self.root / path.relative_to("/") if path.is_absolute() else path

    def write(self, absolute, data=""):
        path = self.root / absolute.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data)


@pytest.fixture
def device_root(pugwash, tmp_path, monkeypatch):
    from pugwash.scenes import startup
    root = Root(tmp_path)
    monkeypatch.setattr(startup, "Path", root)
    return root


def warnings_for(ram=4096):
    from pugwash.scenes.startup import get_startup_warnings
    return [keyword for keyword, reason, suggestion in get_startup_warnings({'ram': ram})]


def test_no_warnings(device_root):
    assert warnings_for() == []


@pytest.mark.parametrize("files, expected", [
    ({"/mnt/SDCARD/spruce/x": ""}, ["spruce"]),
    ({"/mnt/SDCARD/autorun.inf": "[autorun]\nlabel=CrossMix-OS\n"}, ["crossmix"]),
    ({"/mnt/SDCARD/.system/version.txt": "NextUI 6.0\n"}, ["nextui"]),
    ({"/etc/trimui_device.txt": "tg5040"}, ["trimui"]),
    ## A known firmware is named, not the generic TrimUI one.
    ({"/etc/trimui_device.txt": "tg5040", "/mnt/SDCARD/.system/version.txt": "NextUI"}, ["nextui"]),
    ({"/mnt/SDCARD/autorun.inf": b"\xff\xfe binary"}, []),
    ({"/mnt/SDCARD/autorun.inf": "other"}, []),
    ])
def test_firmware_warnings(device_root, files, expected):
    for path, data in files.items():
        device_root.write(path, data)

    assert warnings_for() == expected


def test_low_ram_warning(device_root):
    assert warnings_for(ram=512) == ["lowram"]
    assert warnings_for(ram=1024) == []


def test_next_warning_time(pugwash):
    import datetime
    from pugwash.scenes.startup import get_next_warning_time

    days = (datetime.date.fromisoformat(get_next_warning_time()) - datetime.date.today()).days
    assert days in (5, 7, 11, 13)


@pytest.fixture
def waited(screen_gui, monkeypatch):
    """The disclaimer and warning timers have run out."""
    monkeypatch.setattr(screen_gui.timers, "since", lambda name: 60_000)
    return screen_gui


def root_scene(gui):
    return gui.scenes[0][1][-1]


@pytest.mark.parametrize("cfg, warnings, expected", [
    ({}, [], "DisclaimerScene"),
    ({'disclaimer': True}, [], "MainMenuScene"),
    ({'disclaimer': True}, [('lowram', "Low RAM", None)], "StartupWarningScene"),
    ({'disclaimer': True, 'warning_time': "2999-01-01"}, [('lowram', "Low RAM", None)], "MainMenuScene"),
    ({'disclaimer': True, 'warning_time': "2000-01-01"}, [('lowram', "Low RAM", None)], "StartupWarningScene"),
    ])
def test_temp_menu_routes(screen_gui, monkeypatch, cfg, warnings, expected):
    from pugwash.scenes import startup
    monkeypatch.setattr(startup, "get_startup_warnings", lambda info: warnings)
    for key in ('disclaimer', 'warning_time'):
        screen_gui.hm.cfg_data.pop(key, None)
    screen_gui.hm.cfg_data.update(cfg)

    screen_gui.scenes = [('root', [startup.TempMenuScene(screen_gui)])]
    screen_gui.do_loop(no_delay=True)

    assert type(root_scene(screen_gui)).__name__ == expected


@pytest.mark.parametrize("warnings, expected", [([], "MainMenuScene"), ([('lowram', "Low RAM", None)], "StartupWarningScene")])
def test_disclaimer_accept(waited, monkeypatch, warnings, expected):
    from pugwash.scenes import startup
    monkeypatch.setattr(startup, "get_startup_warnings", lambda info: warnings)
    waited.scenes = [('root', [startup.DisclaimerScene(waited)])]
    root_scene(waited).do_draw()

    assert "Accept" in bar(root_scene(waited))

    press(waited, monkeypatch, 'A')
    assert waited.hm.cfg_data['disclaimer'] is True
    assert type(root_scene(waited)).__name__ == expected


def test_disclaimer_must_wait(screen_gui, monkeypatch):
    from pugwash.scenes import startup
    monkeypatch.setattr(screen_gui.timers, "since", lambda name: 3_000)
    screen_gui.scenes = [('root', [startup.DisclaimerScene(screen_gui)])]
    root_scene(screen_gui).do_draw()

    assert bar(root_scene(screen_gui)) == ["Wait 12 seconds"]

    press(screen_gui, monkeypatch, 'A')
    assert 'disclaimer' not in screen_gui.hm.cfg_data
    assert type(root_scene(screen_gui)).__name__ == "DisclaimerScene"


@pytest.mark.parametrize("answer", [True, False])
def test_disclaimer_quit(waited, monkeypatch, answer):
    from pugwash.scenes import startup
    waited.answer = answer
    waited.scenes = [('root', [startup.DisclaimerScene(waited)])]

    press(waited, monkeypatch, 'B')
    assert waited.cancelled == ([True] if answer else [])


def test_warning_screen(waited, monkeypatch):
    from pugwash.scenes import startup
    warnings = [
        ('spruce', "SpruceOS is not supported by PortMaster.", "Switch."),
        ('lowram', "Low RAM.", None),
        ('other', "Other.", "Switch."),
        ]
    waited.scenes = [('root', [startup.StartupWarningScene(waited, warnings)])]
    root_scene(waited).do_draw()

    text = root_scene(waited).tags['disclaimer_text'].text
    ## Each reason, then each suggestion once.
    assert text == "SpruceOS is not supported by PortMaster.\nLow RAM.\nOther.\nMany ports will not work.\n\nSwitch."
    assert "I Understand" in bar(root_scene(waited))

    press(waited, monkeypatch, 'A')
    assert waited.hm.cfg_data['warning_time'] > "2000"
    assert type(root_scene(waited)).__name__ == "MainMenuScene"


def test_warning_screen_waits(screen_gui, monkeypatch):
    from pugwash.scenes import startup
    monkeypatch.setattr(screen_gui.timers, "since", lambda name: 0)
    screen_gui.scenes = [('root', [startup.StartupWarningScene(screen_gui, [('lowram', "Low RAM.", None)])])]
    root_scene(screen_gui).do_draw()

    assert bar(root_scene(screen_gui)) == ["Wait 10 seconds"]
    press(screen_gui, monkeypatch, 'A')
    assert type(root_scene(screen_gui)).__name__ == "StartupWarningScene"


@pytest.mark.parametrize("answer", [True, False])
def test_warning_screen_quit(waited, monkeypatch, answer):
    from pugwash.scenes import startup
    waited.answer = answer
    waited.scenes = [('root', [startup.StartupWarningScene(waited, [('lowram', "Low RAM.", None)])])]

    press(waited, monkeypatch, 'B')
    assert waited.cancelled == ([True] if answer else [])


################################################################################
## Port info
@pytest.fixture
def info(screen_gui):
    scenes = screen_gui.scenes_mod
    list_scene = push(screen_gui, 'ports', scenes.PortsListScene(screen_gui, {'mode': 'install', 'name': None}))
    scene = push(screen_gui, 'port_info', scenes.PortInfoScene(screen_gui, "2048plus.zip", 'install', list_scene))
    scene.list_scene = list_scene
    return scene


def test_port_info_install(screen_gui, info, monkeypatch):
    assert screen_gui.get_data('port_info.title') == "2048 Plus"
    assert "Install" in bar(info) and "Uninstall" not in bar(info)

    installs = []
    monkeypatch.setattr(screen_gui, "do_install", lambda name: installs.append(name))
    press(screen_gui, monkeypatch, 'A')

    assert installs == ["2048plus.zip"]
    assert top(screen_gui) is info.list_scene


def test_port_info_installed(screen_gui, monkeypatch):
    assert screen_gui.hm.install_port("2048plus.zip") == 0
    screen_gui.hm.load_ports()
    scenes = screen_gui.scenes_mod
    list_scene = push(screen_gui, 'ports', scenes.PortsListScene(screen_gui, {'mode': 'uninstall', 'base_filters': ['installed']}))
    info = push(screen_gui, 'port_info', scenes.PortInfoScene(screen_gui, "2048plus.zip", 'uninstall', list_scene))

    assert "Reinstall" in bar(info) and "Uninstall" in bar(info)

    uninstalls = []
    monkeypatch.setattr(screen_gui, "do_uninstall", lambda name: uninstalls.append(name))

    screen_gui.answer = False
    press(screen_gui, monkeypatch, 'Y')
    assert uninstalls == []
    assert "uninstall 2048 Plus" in screen_gui.boxes[-1]

    screen_gui.answer = True
    press(screen_gui, monkeypatch, 'Y')
    assert uninstalls == ["2048plus.zip"]
    assert top(screen_gui) is list_scene


def test_port_info_y_when_not_installed(screen_gui, info, monkeypatch):
    press(screen_gui, monkeypatch, 'Y')
    assert screen_gui.boxes == []
    assert top(screen_gui) is info


def test_port_info_back(screen_gui, info, monkeypatch):
    press(screen_gui, monkeypatch, 'B')
    assert top(screen_gui) is info.list_scene


def test_port_info_next_and_previous(screen_gui, info, monkeypatch):
    ## The default theme has a popup: LEFT and RIGHT move between ports.
    buttons = info.config['buttons']
    next_button = [button for button, action in buttons.items() if action == 'next_port'][0]
    prev_button = [button for button, action in buttons.items() if action == 'prev_port'][0]

    info.list_scene.tags['ports_list'].list_select(2)
    info.list_scene.last_port = 2

    press(screen_gui, monkeypatch, next_button)
    assert info.port_name == "sprout.zip"
    assert screen_gui.get_data('port_info.title') == "-SPROUT-"

    press(screen_gui, monkeypatch, prev_button)
    assert info.port_name == "2048plus.zip"


@pytest.fixture
def popup_theme(screen_gui, monkeypatch):
    """A theme with the port info popup (the default theme has none)."""
    monkeypatch.setitem(screen_gui.theme_data, 'port_info_popup', dict(screen_gui.theme_data['port_info']))
    return screen_gui


def popup_info(gui, port_name):
    scenes = gui.scenes_mod
    list_scene = push(gui, 'ports', scenes.PortsListScene(gui, {'mode': 'install', 'name': None}))
    info = push(gui, 'port_info', scenes.PortInfoScene(gui, port_name, 'install', list_scene))
    info.list_scene = list_scene
    return info


def test_port_info_popup(popup_theme, monkeypatch):
    screen_gui = popup_theme
    info = popup_info(screen_gui, "2048plus.zip")
    assert "Show Info" in bar(info)
    assert info.config['buttons']['LEFT'] == 'prev_port'

    press(screen_gui, monkeypatch, 'UP')
    popup = top(screen_gui)
    assert isinstance(popup, screen_gui.scenes_mod.PortInfoPopup)
    assert info.popup_shown
    assert "Hide Info" in bar(popup)

    ## Only one at a time.
    info.do_update(type("Events", (), {"was_pressed": lambda self, b: b == 'UP', "any_pressed": lambda self: True})())
    assert top(screen_gui) is popup

    press(screen_gui, monkeypatch, 'DOWN')
    assert top(screen_gui) is info
    assert not info.popup_shown


def test_port_info_popup_links(popup_theme, monkeypatch):
    screen_gui = popup_theme
    popup_info(screen_gui, "sprout.zip")

    press(screen_gui, monkeypatch, 'UP')
    popup = top(screen_gui)
    assert "Links" in bar(popup)

    press(screen_gui, monkeypatch, 'X')
    assert screen_gui.scene_list()[-1] == "port_links"


def test_port_info_popup_follows_the_port(popup_theme, monkeypatch):
    screen_gui = popup_theme
    popup_info(screen_gui, "2048plus.zip")
    press(screen_gui, monkeypatch, 'UP')
    popup = top(screen_gui)
    screen_gui.set_data("port_info.name", "something else")
    screen_gui.do_loop(no_delay=True)

    assert popup.port_name == "something else"


def test_port_info_without_links(screen_gui, info, monkeypatch):
    ## 2048plus has no stores, and the website link is only for the official sources' ports.
    screen_gui.set_data("port_info.links", "")
    assert not info.has_links()
    assert info.show_links() is False


def test_port_info_without_harbourmaster(screen_gui, info):
    screen_gui.hm = None
    info.ready = False
    info.update_port()
    assert info.ready is False


################################################################################
## Runtime manager
@pytest.fixture
def runtimes(screen_gui):
    return push(screen_gui, 'runtime-manager', screen_gui.scenes_mod.RuntimesScene(screen_gui))


def test_runtime_list(screen_gui, runtimes):
    options = runtimes.tags['runtime_list'].options

    ## aarch64 builds only, by name, then "Download All".
    assert [option for option in options if option] == ['ags_3.6.squashfs', 'dotnet-8.0.12.squashfs', 'gmtoolkit.squashfs', 'all']
    assert screen_gui.get_data('runtime_info.status') == "Not Installed"
    assert screen_gui.get_data('runtime_info.disk_size') == ""


def test_runtime_selection_details(screen_gui, monkeypatch):
    (screen_gui.hm.libs_dir / "gmtoolkit.squashfs").write_bytes(b"x" * 2048)
    scene = push(screen_gui, 'runtime-manager', screen_gui.scenes_mod.RuntimesScene(screen_gui))

    select(scene, 'gmtoolkit.squashfs', tag='runtime_list')
    screen_gui.do_loop(no_delay=True)

    assert screen_gui.get_data('runtime_info.name') == "GMToolkit"
    assert screen_gui.get_data('runtime_info.status') == "Installed"
    assert screen_gui.get_data('runtime_info.disk_size') == "2.00 KB"
    assert "Uninstall" in bar(scene)


def test_runtime_check(screen_gui, runtimes, monkeypatch):
    checked = []

    def check(name, in_install=False):
        checked.append((name, in_install))
        (screen_gui.hm.libs_dir / name).write_bytes(b"data")

    monkeypatch.setattr(screen_gui, "do_runtime_check", check)
    choose(screen_gui, monkeypatch, 'dotnet-8.0.12.squashfs', tag='runtime_list')

    assert checked == [('dotnet-8.0.12.squashfs', False)]
    assert runtimes.runtimes['dotnet-8.0.12.squashfs']['installed'] is True


def test_runtime_check_failed(screen_gui, runtimes, monkeypatch):
    monkeypatch.setattr(screen_gui, "do_runtime_check", lambda name, in_install=False: None)
    choose(screen_gui, monkeypatch, 'dotnet-8.0.12.squashfs', tag='runtime_list')

    assert runtimes.runtimes['dotnet-8.0.12.squashfs']['installed'] is False


def test_runtime_download_all(screen_gui, runtimes, monkeypatch):
    checked = []

    def check(name, in_install=False):
        checked.append(name)
        if name != 'ags_3.6.squashfs':
            (screen_gui.hm.libs_dir / name).write_bytes(b"data")

    monkeypatch.setattr(screen_gui, "do_runtime_check", check)

    screen_gui.answer = False
    choose(screen_gui, monkeypatch, 'all', tag='runtime_list')
    assert checked == []

    screen_gui.answer = True
    choose(screen_gui, monkeypatch, 'all', tag='runtime_list')
    assert sorted(checked) == ['ags_3.6.squashfs', 'dotnet-8.0.12.squashfs', 'gmtoolkit.squashfs']
    assert runtimes.runtimes['all']['installed'] is False


def test_runtime_uninstall(screen_gui, monkeypatch):
    runtime = screen_gui.hm.libs_dir / "gmtoolkit.squashfs"
    runtime.write_bytes(b"x")
    scene = push(screen_gui, 'runtime-manager', screen_gui.scenes_mod.RuntimesScene(screen_gui))

    select(scene, 'gmtoolkit.squashfs', tag='runtime_list')
    screen_gui.do_loop(no_delay=True)
    press(screen_gui, monkeypatch, 'Y')

    assert not runtime.exists()
    assert screen_gui.boxes[-1] == "Deleted runtime GMToolkit"

    ## Not installed: Y does nothing.
    press(screen_gui, monkeypatch, 'Y')
    assert len(screen_gui.boxes) == 1


def test_runtime_manager_shows_ports_using_them(screen_gui, monkeypatch):
    from conftest import port_files_with, write_port_zip
    zip_file = write_port_zip(screen_gui.hm.temp_dir / "rt.zip", port_files_with(name="rt", attr={"runtime": ["gmtoolkit.squashfs"], "title": "RT Port"}))
    monkeypatch.setattr(screen_gui.hm, "check_runtime", lambda *args, **kwargs: 0)
    assert screen_gui.hm.install_port(str(zip_file)) == 0
    screen_gui.hm.load_ports()
    screen_gui.hm._port_attrs_updated = True

    scene = push(screen_gui, 'runtime-manager', screen_gui.scenes_mod.RuntimesScene(screen_gui))
    select(scene, 'gmtoolkit.squashfs', tag='runtime_list')
    screen_gui.do_loop(no_delay=True)

    assert screen_gui.get_data('runtime_info.in_use') == "Used"
    assert screen_gui.get_data('runtime_info.ports') == "RT Port"


def test_runtime_manager_back(screen_gui, runtimes, monkeypatch):
    press(screen_gui, monkeypatch, 'B')
    assert top(screen_gui) is not runtimes


################################################################################
## Themes
@pytest.fixture
def themes(screen_gui, monkeypatch):
    monkeypatch.setattr(screen_gui.hm, "config", {**screen_gui.hm.config, 'offline': True, 'no-check': True})
    monkeypatch.setattr(screen_gui, "theme_downloader", None)
    return push(screen_gui, 'select-theme', screen_gui.scenes_mod.ThemesScene(screen_gui))


def test_themes_list(screen_gui, themes):
    region = themes.tags['themes_list']
    assert 'default_theme' in region.options
    assert any("(Selected)" in text for text in region.list)
    assert "Select" in bar(themes)


def test_themes_select(screen_gui, themes, monkeypatch):
    reloads = []
    monkeypatch.setattr(screen_gui, "reload_theme", lambda then=None: reloads.append([name for name, _ in then]))

    choose(screen_gui, monkeypatch, 'default_theme', tag='themes_list')

    assert reloads == [['option', 'select-theme']]
    assert screen_gui.hm.cfg_data['theme'] == 'default_theme'
    assert screen_gui.hm.cfg_data['theme-scheme'] is None


def test_themes_not_installed_cant_be_selected(screen_gui, themes, monkeypatch):
    themes.themes['remote_theme'] = dict(themes.themes['default_theme'], name="Remote", status="Not Installed", url="https://example.com/remote.theme.zip")
    ## Still listed after the download reloads the list.
    listed = dict(themes.themes)
    monkeypatch.setattr(screen_gui.themes, "get_themes_list", lambda *args: listed)
    themes.tags['themes_list'].add_option('remote_theme', "Remote")

    reloads = []
    monkeypatch.setattr(screen_gui, "reload_theme", lambda then=None: reloads.append(then))
    installs = []
    monkeypatch.setattr(screen_gui, "do_install", lambda name, url: installs.append((name, url)))

    select(themes, 'remote_theme', tag='themes_list')
    screen_gui.do_loop(no_delay=True)
    assert "Download" in bar(themes) and "Select" not in bar(themes)

    press(screen_gui, monkeypatch, 'A')
    assert reloads == []

    press(screen_gui, monkeypatch, 'X')
    assert installs == [("Remote", "https://example.com/remote.theme.zip.md5")]


def test_themes_x_without_a_url(screen_gui, themes, monkeypatch):
    installs = []
    monkeypatch.setattr(screen_gui, "do_install", lambda name, url: installs.append(name))

    press(screen_gui, monkeypatch, 'X')
    assert installs == []


def test_themes_back(screen_gui, themes, monkeypatch):
    press(screen_gui, monkeypatch, 'B')
    assert top(screen_gui) is not themes


@pytest.fixture
def schemes(screen_gui, monkeypatch):
    schemes = screen_gui.themes.get_theme_schemes_list()
    if len(schemes) < 2:
        pytest.skip("the default theme has one scheme")

    return push(screen_gui, 'select-scheme', screen_gui.scenes_mod.ThemeSchemeScene(screen_gui))


def test_schemes_list(screen_gui, schemes):
    region = schemes.tags['option_list']
    assert sum(1 for text in region.list if "(Selected)" in str(text)) == 1
    assert region.options[-1] == ('back', None)


def test_schemes_choose(screen_gui, schemes, monkeypatch):
    reloads = []
    monkeypatch.setattr(screen_gui, "reload_theme", lambda then=None: reloads.append([name for name, _ in then]))
    other = [option for option in schemes.tags['option_list'].options if isinstance(option, tuple) and option[0] == 'select-scheme'][0]

    choose(screen_gui, monkeypatch, other)

    assert screen_gui.hm.cfg_data['theme-scheme'] == other[1]
    assert reloads == [['option', 'select-scheme']]


def test_schemes_back_and_blank(screen_gui, schemes, monkeypatch):
    region = schemes.tags['option_list']
    region.selected = region.options.index(None)
    press(screen_gui, monkeypatch, 'A')
    assert top(screen_gui) is schemes

    region.selected = region.options.index((None, ''))
    press(screen_gui, monkeypatch, 'A')
    assert top(screen_gui) is schemes

    choose(screen_gui, monkeypatch, ('back', None))
    assert top(screen_gui) is not schemes


def test_schemes_b(screen_gui, schemes, monkeypatch):
    press(screen_gui, monkeypatch, 'B')
    assert top(screen_gui) is not schemes
