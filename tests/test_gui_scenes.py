# SPDX-License-Identifier: MIT
#
# The GUI's menus driven a button at a time on the shared headless GUI, with the
# PortMaster source from tests/data/ports.json: main menu, ports lists, filters,
# featured ports, options, language and the on screen keyboard.

import json

import pytest

import harbourmaster


pytestmark = pytest.mark.sdl


@pytest.fixture
def scene_gui(gui, online_hm, monkeypatch):
    """The GUI on the root scene with a HarbourMaster; message boxes answer `gui.answer`."""
    from pugwash import scenes

    gui.hm = online_hm
    gui.boxes = []
    gui.answer = True
    cancelled = []

    def message_box(text, *args, **kwargs):
        gui.boxes.append(text)
        return gui.answer

    monkeypatch.setattr(gui, "message_box", message_box)
    monkeypatch.setattr(gui, "do_cancel", lambda: cancelled.append(True))
    gui.cancelled = cancelled
    gui.scenes_mod = scenes

    sounds = (gui.sounds.music_is_disabled, gui.sounds.sound_is_disabled)
    yield gui

    while len(gui.scenes) > 1:
        gui.pop_scene()

    gui.sounds.music_is_disabled, gui.sounds.sound_is_disabled = sounds
    gui.events.running = True
    gui.hm = None


def top(gui):
    return gui.scenes[-1][1][-1]


def press(gui, monkeypatch, button):
    with monkeypatch.context() as patch:
        patch.setattr(gui.events, "was_pressed", lambda pressed: pressed == button)
        patch.setattr(gui.events, "any_pressed", lambda: True)
        gui.do_loop(no_delay=True)

    gui.do_loop(no_delay=True)


def select(scene, option, tag='option_list'):
    region = scene.tags[tag]
    region.list_select(region.options.index(option))


def choose(gui, monkeypatch, option, tag='option_list'):
    select(top(gui), option, tag)
    gui.do_loop(no_delay=True)
    press(gui, monkeypatch, 'A')


def push(gui, name, scene):
    gui.push_scene(name, scene)
    gui.do_loop(no_delay=True)
    return scene


def list_titles(scene):
    return list(scene.tags['ports_list'].list)


################################################################################
## Main menu
@pytest.fixture
def main_menu(scene_gui):
    return push(scene_gui, 'main', scene_gui.scenes_mod.MainMenuScene(scene_gui))


@pytest.mark.parametrize("option, mode, base_filters", [
    ("install", "install", []),
    ("install-rtr", "install", ["rtr"]),
    ("uninstall", "uninstall", ["installed"]),
    ])
def test_main_menu_port_lists(scene_gui, main_menu, monkeypatch, option, mode, base_filters):
    choose(scene_gui, monkeypatch, option)

    scene = top(scene_gui)
    assert isinstance(scene, scene_gui.scenes_mod.PortsListScene)
    assert scene.options['mode'] == mode
    assert scene.options['base_filters'] == base_filters

    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is main_menu


def test_main_menu_tooltip_follows_the_selection(scene_gui, main_menu):
    select(main_menu, 'options')
    scene_gui.do_loop(no_delay=True)

    assert scene_gui.get_data('menu.selected') == 'options'


def test_main_menu_options(scene_gui, main_menu, monkeypatch):
    choose(scene_gui, monkeypatch, 'options')
    assert isinstance(top(scene_gui), scene_gui.scenes_mod.OptionScene)


def test_main_menu_exit(scene_gui, main_menu, monkeypatch):
    choose(scene_gui, monkeypatch, 'exit')
    assert scene_gui.cancelled == [True]


@pytest.mark.parametrize("answer", [True, False])
def test_main_menu_back_asks_first(scene_gui, main_menu, monkeypatch, answer):
    scene_gui.answer = answer
    press(scene_gui, monkeypatch, 'B')

    assert "exit PortMaster" in scene_gui.boxes[-1]
    assert scene_gui.cancelled == ([True] if answer else [])


def test_main_menu_featured_without_any(scene_gui, main_menu, monkeypatch):
    choose(scene_gui, monkeypatch, 'featured-ports')

    assert "No featured ports found" in scene_gui.boxes[-1]
    assert top(scene_gui) is main_menu


def test_konami_code(scene_gui, main_menu, monkeypatch):
    for button in main_menu.KONAMI_CODE[:-1]:
        press(scene_gui, monkeypatch, button)

    assert scene_gui.hm.cfg_data['konami'] is True
    assert scene_gui.boxes[-1] == "Secret Mode Enabled"
    ## Still on the main menu: B, A and START were swallowed.
    assert top(scene_gui) is main_menu

    for button in main_menu.KONAMI_CODE[:-1]:
        press(scene_gui, monkeypatch, button)

    assert scene_gui.hm.cfg_data['konami'] is False
    assert scene_gui.boxes[-1] == "Secret Mode Disabled"


def test_konami_code_broken_off(scene_gui, main_menu, monkeypatch):
    for button in ('UP', 'UP', 'DOWN', 'X'):
        press(scene_gui, monkeypatch, button)

    assert main_menu.detecting_konami == 0
    assert 'konami' not in scene_gui.hm.cfg_data


################################################################################
## Ports lists and filters
@pytest.fixture
def ports_list(scene_gui):
    return push(scene_gui, 'ports', scene_gui.scenes_mod.PortsListScene(scene_gui, {'mode': 'install', 'name': None}))


def test_ports_list(scene_gui, ports_list):
    assert list_titles(ports_list) == ["-SPROUT-", "100 Lil Jumps", "2048 Plus"]
    assert scene_gui.get_data('ports_list.total_ports') == "3"
    assert scene_gui.get_data('port_info.title') == "-SPROUT-"
    ## Install lists never offer broken ports as a filter.
    assert 'broken' in ports_list.options['skip_genres']


def test_ports_list_moving(scene_gui, ports_list):
    assert ports_list.select_next_port() == "100liljumps.zip"
    assert ports_list.select_next_port() == "2048plus.zip"
    assert ports_list.select_next_port() == "sprout.zip"
    assert ports_list.select_prev_port() == "2048plus.zip"
    assert scene_gui.get_data('port_info.title') == "2048 Plus"


def test_ports_list_selection_shows_the_port(scene_gui, ports_list):
    ports_list.tags['ports_list'].list_select(2)
    scene_gui.do_loop(no_delay=True)

    assert scene_gui.get_data('ports_list.position') == "3"
    assert scene_gui.get_data('port_info.title') == "2048 Plus"
    assert ports_list.selected_port() == "2048plus.zip"


def test_ports_list_try_to_select(scene_gui, ports_list):
    ports_list.try_to_select("2048plus.zip", "")
    assert ports_list.tags['ports_list'].selected == 2

    ## Gone: the port before where it would be.
    ports_list.try_to_select("missing.zip", "101 Something")
    assert ports_list.tags['ports_list'].selected == 1

    ports_list.try_to_select("missing.zip", "zzz")
    assert ports_list.tags['ports_list'].selected == 1


def test_ports_list_a_opens_port_info(scene_gui, ports_list, monkeypatch):
    press(scene_gui, monkeypatch, 'A')

    scene = top(scene_gui)
    assert isinstance(scene, scene_gui.scenes_mod.PortInfoScene)
    assert scene_gui.get_data('port_info.title') == "-SPROUT-"


def test_ports_list_without_harbourmaster(scene_gui):
    scene_gui.hm = None
    scene = push(scene_gui, 'ports', scene_gui.scenes_mod.PortsListScene(scene_gui, {'mode': 'install'}))

    assert list_titles(scene) == ["NO PORTS"]
    assert scene_gui.get_data('port_info.title') == "** NO PORTS FOUND **"


def test_manage_ports_empty(scene_gui, monkeypatch):
    scene = push(scene_gui, 'ports', scene_gui.scenes_mod.PortsListScene(
        scene_gui, {'mode': 'uninstall', 'base_filters': ['installed']}))

    assert list_titles(scene) == ["NO PORTS"]
    assert scene_gui.get_data('port_info.description') == "Download ports first."

    ## Nothing to filter: X does nothing, A does nothing.
    press(scene_gui, monkeypatch, 'X')
    press(scene_gui, monkeypatch, 'A')
    assert top(scene_gui) is scene


def test_manage_ports_lists_installed(scene_gui, monkeypatch):
    assert scene_gui.hm.install_port("2048plus.zip") == 0
    scene_gui.hm.load_ports()

    scene = push(scene_gui, 'ports', scene_gui.scenes_mod.PortsListScene(
        scene_gui, {'mode': 'uninstall', 'base_filters': ['installed']}))
    assert list_titles(scene) == ["2048 Plus"]

    press(scene_gui, monkeypatch, 'A')
    assert isinstance(top(scene_gui), scene_gui.scenes_mod.PortInfoScene)


@pytest.fixture
def filters(scene_gui, ports_list, monkeypatch):
    press(scene_gui, monkeypatch, 'X')
    scene = top(scene_gui)
    assert isinstance(scene, scene_gui.scenes_mod.FiltersScene)
    return scene


def test_filters_options(scene_gui, filters):
    options = filters.tags['filter_list'].options

    for option in harbourmaster.HM_SORT_ORDER + ['puzzle', 'platformer', 'rtr', '!rtr', 'not installed']:
        assert option in options, option

    ## No ports: not offered.
    assert 'rpg' not in options
    assert 'broken' not in options
    assert 'clear-filters' not in options


def test_filters_genre(scene_gui, filters, ports_list, monkeypatch):
    choose(scene_gui, monkeypatch, 'puzzle', tag='filter_list')

    assert list_titles(ports_list) == ["2048 Plus"]
    assert scene_gui.get_data('ports_list.filters') == "puzzle"
    assert 'clear-filters' in filters.tags['filter_list'].options

    ## Again: off.
    choose(scene_gui, monkeypatch, 'puzzle', tag='filter_list')
    assert len(list_titles(ports_list)) == 3

    choose(scene_gui, monkeypatch, 'platformer', tag='filter_list')
    choose(scene_gui, monkeypatch, 'rtr', tag='filter_list')
    assert list_titles(ports_list) == ["100 Lil Jumps"]

    choose(scene_gui, monkeypatch, 'clear-filters', tag='filter_list')
    assert len(list_titles(ports_list)) == 3
    assert filters.selected_genres == []


def test_filters_sorting(scene_gui, filters, ports_list, monkeypatch):
    ## Pressing the current sort again reverses it.
    choose(scene_gui, monkeypatch, 'alphabetical', tag='filter_list')
    assert ports_list.options['sort_by'] == "alphabetical_rev"
    assert list_titles(ports_list) == ["2048 Plus", "100 Lil Jumps", "-SPROUT-"]

    choose(scene_gui, monkeypatch, 'alphabetical', tag='filter_list')
    assert ports_list.options['sort_by'] == "alphabetical"

    choose(scene_gui, monkeypatch, 'recently_added', tag='filter_list')
    assert ports_list.options['sort_by'] == "recently_added"
    assert len(list_titles(ports_list)) == 3


def test_filters_header_rows_do_nothing(scene_gui, filters, monkeypatch):
    region = filters.tags['filter_list']
    before = list(region.options)
    region.selected = region.options.index(None)

    press(scene_gui, monkeypatch, 'A')
    assert region.options == before


@pytest.mark.parametrize("button", ['B', 'X'])
def test_filters_back(scene_gui, filters, ports_list, monkeypatch, button):
    press(scene_gui, monkeypatch, button)
    assert top(scene_gui) is ports_list


def test_filters_down_to_nothing(scene_gui, filters, ports_list, monkeypatch):
    ports_list.options['filters'] = ['puzzle', 'platformer']
    ports_list.update_ports()

    assert list_titles(ports_list) == ["NO PORTS"]
    assert scene_gui.get_data('port_info.description') == "Try removing some filters."


def test_filters_porters(scene_gui, ports_list, monkeypatch):
    (scene_gui.hm.cfg_dir / "porters.json").write_text(json.dumps({"saitamasahil": {}, "nobody": {}}))
    scene_gui.hm._PORTERS = None

    press(scene_gui, monkeypatch, 'X')
    options = top(scene_gui).tags['filter_list'].options

    assert 'saitamasahil' in options
    ## No ports by them: not offered.
    assert 'nobody' not in options


################################################################################
## Featured ports
@pytest.fixture
def featured(scene_gui):
    (scene_gui.hm.cfg_dir / "featured_ports.json").write_text(json.dumps([
        {"name": "Collections", "type": "category", "description": "Lists of lists", "children": [
            {"name": "Puzzles", "description": "Thinky", "ports": ["2048plus.zip"]},
            ]},
        {"name": "Platformers", "description": "Jumpy", "ports": ["sprout.zip", "100liljumps.zip"]},
        ]))
    return push(scene_gui, 'featured-ports', scene_gui.scenes_mod.FeaturedPortsNavigationScene(scene_gui))


def test_featured_navigation(scene_gui, featured, monkeypatch):
    assert featured.tags['option_list'].list == ["Collections", "Platformers"]
    assert scene_gui.get_data('featured_ports.name') == "Collections"

    select(featured, 1)
    scene_gui.do_loop(no_delay=True)
    assert scene_gui.get_data('featured_ports.description') == "Jumpy"

    press(scene_gui, monkeypatch, 'A')
    ports = top(scene_gui)
    assert isinstance(ports, scene_gui.scenes_mod.FeaturedPortsScene)
    assert list_titles(ports) == ["-SPROUT-", "100 Lil Jumps"]
    assert scene_gui.get_data('ports_list.total_ports') == "2"

    press(scene_gui, monkeypatch, 'A')
    assert isinstance(top(scene_gui), scene_gui.scenes_mod.PortInfoScene)

    press(scene_gui, monkeypatch, 'B')
    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is featured


def test_featured_category(scene_gui, featured, monkeypatch):
    press(scene_gui, monkeypatch, 'A')

    nested = top(scene_gui)
    assert isinstance(nested, scene_gui.scenes_mod.FeaturedPortsNavigationScene)
    assert nested.scene_title == "Collections"
    assert nested.tags['option_list'].list == ["Puzzles"]

    press(scene_gui, monkeypatch, 'A')
    assert list_titles(top(scene_gui)) == ["2048 Plus"]

    press(scene_gui, monkeypatch, 'B')
    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is featured


def test_featured_breadcrumbs(scene_gui):
    scene = push(scene_gui, 'nav', scene_gui.scenes_mod.FeaturedPortsNavigationScene(
        scene_gui, [{"name": "Deeper", "type": "category", "description": "", "image": "", "children": []}], "Top"))
    assert scene.scene_title == "Top"


################################################################################
## Options
@pytest.fixture
def options(scene_gui, monkeypatch, tmp_path):
    ## Options that touch PortMaster's own folder use the HarbourMaster's.
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", scene_gui.hm.tools_dir)
    return push(scene_gui, 'option', scene_gui.scenes_mod.OptionScene(scene_gui))


def option_text(scene, option):
    region = scene.tags['option_list']
    return region.list[region.options.index(option)]


def test_options_list(scene_gui, options):
    ids = options.tags['option_list'].options

    for option in ('select-language', 'select-theme', 'theme-editor', 'toggle-music', 'toggle-sfx',
                   'runtime-manager', 'toggle-experimental', 'update-ports', 'update-portmaster', 'release-channel'):
        assert option in ids, option

    ## The default platform has no gamelist and no secret options yet.
    for option in ('toggle-gamelist', 'toggle-all', 'delete-config'):
        assert option not in ids


@pytest.mark.parametrize("option, key, label", [
    ('toggle-experimental', 'show_experimental', "Experimental Ports: "),
    ('toggle-music', 'music-disabled', "Music: "),
    ('toggle-sfx', 'sfx-disabled', "Sound FX: "),
    ])
def test_options_toggles(scene_gui, options, monkeypatch, option, key, label):
    before = option_text(options, option)
    choose(scene_gui, monkeypatch, option)

    after = option_text(options, option)
    assert after.startswith(label) and after != before
    assert key in json.loads(scene_gui.hm.cfg_file.read_text())

    choose(scene_gui, monkeypatch, option)
    assert option_text(options, option) == before


def test_options_update_portmaster(scene_gui, options, monkeypatch):
    scene_gui.hm.cfg_data['update_checked'] = "2026-01-01T00:00:00"
    choose(scene_gui, monkeypatch, 'update-portmaster')

    assert scene_gui.hm.cfg_data['update_checked'] is None
    assert scene_gui.events.running is False


@pytest.mark.parametrize("current, new", [("stable", "beta"), ("beta", "stable"), ("alpha", "beta")])
def test_options_release_channel(scene_gui, options, monkeypatch, current, new):
    scene_gui.hm.cfg_data['release_channel'] = current
    choose(scene_gui, monkeypatch, 'release-channel')

    assert f"from {current} to {new}" in scene_gui.boxes[-1]
    assert scene_gui.hm.cfg_data['release_channel'] == new
    assert scene_gui.hm.cfg_data['change_channel'] is True
    assert scene_gui.events.running is False


def test_options_release_channel_declined(scene_gui, options, monkeypatch):
    scene_gui.answer = False
    choose(scene_gui, monkeypatch, 'release-channel')

    assert scene_gui.hm.cfg_data.get('release_channel', 'stable') == 'stable'
    assert scene_gui.events.running is True


def test_options_restore_declined(scene_gui, options, monkeypatch):
    scene_gui.answer = False
    installs = []
    monkeypatch.setattr(scene_gui.hm, "install_port", lambda name: installs.append(name))

    choose(scene_gui, monkeypatch, 'restore-portmaster')
    assert installs == []
    assert scene_gui.events.running is True


def test_options_restore(scene_gui, options, monkeypatch):
    installs = []
    monkeypatch.setattr(scene_gui.hm, "install_port", lambda name: installs.append(name) or 0)

    choose(scene_gui, monkeypatch, 'restore-portmaster')
    assert installs == ["restore.portmaster.zip"]
    assert "Restore PortMaster.sh" in scene_gui.boxes[-2]
    assert scene_gui.events.running is False


def test_options_restore_failed(scene_gui, options, monkeypatch):
    monkeypatch.setattr(scene_gui.hm, "install_port", lambda name: 255)

    choose(scene_gui, monkeypatch, 'restore-portmaster')
    assert scene_gui.events.running is True


@pytest.mark.parametrize("option, scene_name", [
    ('select-language', 'LanguageScene'),
    ('select-theme', 'ThemesScene'),
    ('runtime-manager', 'RuntimesScene'),
    ])
def test_options_open_screens(scene_gui, options, monkeypatch, option, scene_name):
    choose(scene_gui, monkeypatch, option)
    assert type(top(scene_gui)).__name__ == scene_name

    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is options


def test_options_back(scene_gui, options, monkeypatch):
    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is not options


def test_options_update_ports(scene_gui, options, monkeypatch):
    updated = []
    monkeypatch.setattr(scene_gui, "do_update_ports", lambda: updated.append(True))

    choose(scene_gui, monkeypatch, 'update-ports')
    assert updated == [True]


@pytest.fixture
def secret_options(scene_gui, monkeypatch):
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", scene_gui.hm.tools_dir)
    scene_gui.hm.cfg_data['konami'] = True
    return push(scene_gui, 'option', scene_gui.scenes_mod.OptionScene(scene_gui))


def test_secret_options_listed(scene_gui, secret_options):
    ids = secret_options.tags['option_list'].options
    for option in ('release-alpha', 'toggle-all', 'toggle-cwtbe', 'toggle-debug', 'delete-config', 'delete-runtimes'):
        assert option in ids, option


def test_secret_alpha_hidden_on_alpha(scene_gui, monkeypatch):
    scene_gui.hm.cfg_data.update({'konami': True, 'release_channel': 'alpha'})
    scene = push(scene_gui, 'option', scene_gui.scenes_mod.OptionScene(scene_gui))
    assert 'release-alpha' not in scene.tags['option_list'].options


def test_secret_release_alpha(scene_gui, secret_options, monkeypatch):
    choose(scene_gui, monkeypatch, 'release-alpha')

    assert scene_gui.hm.cfg_data['release_channel'] == 'alpha'
    assert scene_gui.events.running is False


def test_secret_release_alpha_declined(scene_gui, secret_options, monkeypatch):
    scene_gui.answer = False
    choose(scene_gui, monkeypatch, 'release-alpha')
    assert scene_gui.hm.cfg_data.get('release_channel', 'stable') == 'stable'


def test_secret_toggle_all(scene_gui, secret_options, monkeypatch):
    choose(scene_gui, monkeypatch, 'toggle-all')
    assert scene_gui.hm.cfg_data['show_all'] is True
    assert option_text(secret_options, 'toggle-all') == "All Ports: Enabled"


@pytest.mark.parametrize("option, flag, label", [
    ('toggle-cwtbe', "cwtbe_flag", "CWTBE Mode: "),
    ('toggle-debug', "debug_all_the_things_flag", "Debug Mode: "),
    ])
def test_secret_flags(scene_gui, secret_options, monkeypatch, option, flag, label):
    flag_file = scene_gui.hm.tools_dir / "PortMaster" / flag

    choose(scene_gui, monkeypatch, option)
    assert flag_file.is_file()
    assert option_text(secret_options, option) == label + "Enabled"

    choose(scene_gui, monkeypatch, option)
    assert not flag_file.exists()
    assert option_text(secret_options, option) == label + "Disabled"


def test_secret_delete_runtimes(scene_gui, secret_options, monkeypatch):
    choose(scene_gui, monkeypatch, 'delete-runtimes')
    assert scene_gui.boxes[-1] == "No runtimes found."

    for name in ("a.squashfs", "b.squashfs"):
        (scene_gui.hm.libs_dir / name).write_bytes(b"x")

    choose(scene_gui, monkeypatch, 'delete-runtimes')
    assert scene_gui.boxes[-1] == "Removed 2 runtimes."
    assert list(scene_gui.hm.libs_dir.glob("*.squashfs")) == []


def test_secret_delete_config(scene_gui, secret_options, monkeypatch):
    choose(scene_gui, monkeypatch, 'delete-config')

    assert not scene_gui.hm.cfg_dir.exists()
    assert scene_gui.events.running is False


def test_secret_delete_config_already_gone(scene_gui, secret_options, monkeypatch):
    import shutil
    shutil.rmtree(str(scene_gui.hm.cfg_dir))

    choose(scene_gui, monkeypatch, 'delete-config')
    assert scene_gui.events.running is False


def test_options_gcd_toggle(scene_gui, monkeypatch):
    backup = scene_gui.hm.tools_dir / "PortMaster" / ".Backup"
    backup.mkdir(parents=True)
    (backup / "donottouch.txt").write_text("# Standard\n")
    (backup / "donottouch_x.txt").write_text("# Xbox 360 Layout\n")

    from harbourmaster.platform import PlatformAmberELEC
    monkeypatch.setattr(scene_gui.hm, "platform", PlatformAmberELEC(scene_gui.hm))
    scene = push(scene_gui, 'option', scene_gui.scenes_mod.OptionScene(scene_gui))

    assert option_text(scene, 'toggle-gcd') == "Controller Mode: standard"
    choose(scene_gui, monkeypatch, 'toggle-gcd')
    assert option_text(scene, 'toggle-gcd') == "Controller Mode: xbox"
    choose(scene_gui, monkeypatch, 'toggle-gcd')
    assert option_text(scene, 'toggle-gcd') == "Controller Mode: standard"


def test_options_gamelist(scene_gui, monkeypatch):
    from harbourmaster.platform import PlatformTesting
    monkeypatch.setattr(scene_gui.hm, "platform", PlatformTesting(scene_gui.hm))
    scene = push(scene_gui, 'option', scene_gui.scenes_mod.OptionScene(scene_gui))

    assert option_text(scene, 'toggle-gamelist') == "Metadata Update: Auto"
    choose(scene_gui, monkeypatch, 'toggle-gamelist')
    assert option_text(scene, 'toggle-gamelist') == "Metadata Update: Manual"
    assert scene_gui.hm.cfg_data['gamelist_update'] is False

    updated = []
    monkeypatch.setattr(scene_gui, "update_gamelist_xml", lambda: updated.append(True))
    scene_gui.answer = False
    choose(scene_gui, monkeypatch, 'update-gamelist')
    assert updated == []

    scene_gui.answer = True
    choose(scene_gui, monkeypatch, 'update-gamelist')
    assert updated == [True]


def test_options_trimui_port_mode(scene_gui, monkeypatch):
    moved = []
    monkeypatch.setattr(scene_gui.hm, "platform_name", "trimui")
    monkeypatch.setattr(scene_gui.hm.platform, "do_move_ports", lambda: moved.append(True), raising=False)
    scene = push(scene_gui, 'option', scene_gui.scenes_mod.OptionScene(scene_gui))

    assert option_text(scene, 'trimui-port-mode-toggle') == "Ports Location: Roms section"
    choose(scene_gui, monkeypatch, 'trimui-port-mode-toggle')

    assert scene_gui.hm.cfg_data['trimui-port-mode'] == 'ports'
    assert option_text(scene, 'trimui-port-mode-toggle') == "Ports Location: Ports tab"
    assert moved == [True]
    ## No restore on TrimUI.
    assert 'restore-portmaster' not in scene.tags['option_list'].options


################################################################################
## Language
@pytest.fixture
def language(scene_gui):
    return push(scene_gui, 'select-language', scene_gui.scenes_mod.LanguageScene(scene_gui))


def test_language_list(scene_gui, language):
    region = language.tags['option_list']
    assert any(text.endswith("(Selected)") for text in region.list if isinstance(text, str))
    assert region.options[-1] == ('back', None)


def test_language_back_option(scene_gui, language, monkeypatch):
    select(language, ('back', None))
    scene_gui.do_loop(no_delay=True)
    press(scene_gui, monkeypatch, 'A')

    assert top(scene_gui) is not language


def test_language_blank_row(scene_gui, language, monkeypatch):
    ## The blank row before Back holds None, which couldn't be unpacked. The d-pad
    ## skips such rows, so this guards against a theme's list that doesn't.
    region = language.tags['option_list']
    region.selected = region.options.index(None)

    press(scene_gui, monkeypatch, 'A')
    assert top(scene_gui) is language


def test_language_selected_row_does_nothing(scene_gui, language, monkeypatch):
    region = language.tags['option_list']
    region.selected = region.options.index((None, ''))

    press(scene_gui, monkeypatch, 'A')
    assert top(scene_gui) is language


def test_language_choose(scene_gui, language, monkeypatch):
    reloaded = []
    monkeypatch.setattr(scene_gui, "reload_language", lambda code, then=None: reloaded.append((code, [name for name, _ in then])))

    region = language.tags['option_list']
    others = [option for option in region.options if isinstance(option, tuple) and option[0] == 'select-language']
    assert others

    select(language, others[0])
    scene_gui.do_loop(no_delay=True)
    press(scene_gui, monkeypatch, 'A')

    code = others[0][1]
    assert reloaded == [(code, ['option', 'select-language'])]
    from pugwash import lang
    if code == lang.DEFAULT_LANG:
        assert 'language' not in scene_gui.hm.cfg_data
    else:
        assert scene_gui.hm.cfg_data['language'] == code


def test_language_b(scene_gui, language, monkeypatch):
    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is not language


################################################################################
## On screen keyboard
def test_keyboard(scene_gui, monkeypatch):
    keyboard = push(scene_gui, 'osk', scene_gui.scenes_mod.OnScreenKeyboard(scene_gui))
    region = keyboard.tags['keyboard']
    assert region.list[0][1] == ' 1 '

    press(scene_gui, monkeypatch, 'X')
    assert keyboard.mode == 'upper'
    assert region.list[0][1] == ' ! '

    press(scene_gui, monkeypatch, 'X')
    assert keyboard.mode == 'lower'

    region.list_select(3)
    scene_gui.do_loop(no_delay=True)

    ## Typing isn't hooked up yet: A and START do nothing.
    press(scene_gui, monkeypatch, 'A')
    press(scene_gui, monkeypatch, 'START')
    assert top(scene_gui) is keyboard

    press(scene_gui, monkeypatch, 'B')
    assert top(scene_gui) is not keyboard
