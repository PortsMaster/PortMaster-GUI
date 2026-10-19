# SPDX-License-Identifier: MIT
#
# A port's links (its PortMaster website page and its stores) with QR codes: the list
# port_links() makes from port.json "store" entries, and the screen X opens on port info.

import pytest


def links(store, website=False, name="game.zip"):
    from pugwash.app_ports import port_links
    return port_links(name, {'attr': {'store': store}}, website=website)


def test_store_links():
    result = links([
        {'name': 'Steam', 'gameurl': 'https://store.steampowered.com/app/1/', 'developerurl': 'https://dev.example/'},
        {'name': 'Itch', 'gameurl': 'https://dev.itch.io/game', 'developerurl': ''},
        {'name': 'GoG ', 'url': 'https://www.gog.com/game/game'},
        ])

    assert result == [
        ("Steam", 'store', 'https://store.steampowered.com/app/1/'),
        ("Steam: developer", 'developer', 'https://dev.example/'),
        ("itch.io", 'store', 'https://dev.itch.io/game'),
        ("GOG", 'store', 'https://www.gog.com/game/game'),
        ]


def test_website_link_first():
    ## The port's name as PortMaster cleans it, which is the name the website uses.
    result = links([{'name': 'Steam', 'gameurl': 'https://store.steampowered.com/app/1/'}], website=True, name="Cave Story+.zip")
    assert result[0] == ("PortMaster website", 'website', "https://portmaster.games/detail.html?name=cave.story")
    assert result[1][0] == "Steam"


def test_bad_store_entries():
    result = links([
        "Steam",
        None,
        {'name': 'Steam', 'gameurl': ''},
        {'name': 'Steam', 'gameurl': 'store.steampowered.com/app/1/'},
        {'name': 'Steam', 'gameurl': 'javascript:alert(1)'},
        {'name': 'Steam', 'gameurl': 42},
        {'name': '', 'gameurl': 'https://www.example.com/game'},
        {'name': 'Unknown Shop', 'gameurl': 'https://www.example.com/game'},
        {'name': 'Mine', 'gameurl': 'https://mine.example/game'},
        ])

    ## Unknown names as they are, no name: the host, a link only once.
    assert result == [
        ("example.com", 'store', 'https://www.example.com/game'),
        ("Mine", 'store', 'https://mine.example/game'),
        ]

    assert links("not a list") == []
    from pugwash.app_ports import port_links
    assert port_links("game.zip", None) == []
    assert port_links("game.zip", {'attr': {}}) == []


def test_store_names():
    from pugwash.app_ports import store_name
    for name in ("itch", "Itch.io", "ITCH.IO", " itch "):
        assert store_name(name, "") == "itch.io"

    assert store_name("GameJolt", "") == "Game Jolt"
    assert store_name("Play Store", "") == "Google Play"
    assert store_name("STEAM", "") == "Steam"


################################################################################
## The screen.
@pytest.fixture
def links_gui(gui, online_hm):
    gui.hm = online_hm
    yield gui
    while len(gui.scenes) > 1:
        gui.pop_scene()

    gui.hm = None


def port_info_scene(gui, port_name):
    from pugwash import scenes
    list_scene = scenes.PortsListScene(gui, {'mode': 'install', 'base_filters': [], 'name': None})
    gui.push_scene('ports', list_scene)
    info_scene = scenes.PortInfoScene(gui, port_name, 'install', list_scene)
    gui.push_scene('port_info', info_scene)
    return info_scene


def bar_labels(scene):
    """The button bar's labels, it keeps them as (rect, label) once laid out."""
    return [item[1] if isinstance(item, tuple) else item for item in scene.tags['button_bar'].bar]


def press(gui, monkeypatch, button):
    with monkeypatch.context() as patch:
        patch.setattr(gui.events, "was_pressed", lambda pressed: pressed == button)
        gui.do_loop(no_delay=True)

    gui.do_loop(no_delay=True)


@pytest.mark.sdl
def test_links_screen(links_gui, monkeypatch):
    gui = links_gui
    info_scene = port_info_scene(gui, "sprout.zip")

    ## The official source: the website, then Steam (game and developer).
    assert gui.get_data("port_info.links") == "3"
    assert "Links" in bar_labels(info_scene)

    press(gui, monkeypatch, 'X')
    assert gui.scene_list()[-1] == "port_links"

    scene = gui.scenes[-1][1][-1]
    assert scene.tags['links_list'].list == ["PortMaster website", "Steam", "Steam: developer"]
    assert gui.get_data("port_links.url") == "https://portmaster.games/detail.html?name=sprout"
    assert gui.images.load("qr:" + gui.get_data("port_links.url")) is not None

    press(gui, monkeypatch, 'DOWN')
    assert gui.get_data("port_links.name") == "Steam"
    assert gui.get_data("port_links.url") == "https://store.steampowered.com/app/1336340/SPROUT/"

    press(gui, monkeypatch, 'B')
    assert gui.scene_list()[-1] == "port_info"


@pytest.mark.sdl
def test_no_links(links_gui, monkeypatch):
    gui = links_gui
    from pugwash.app_ports import port_links

    ## starfighter has no stores; not from an official source, so no website link either.
    for source in gui.hm.sources.values():
        monkeypatch.setitem(source._config, 'url', "https://example.com/ports.json")

    info_scene = port_info_scene(gui, "starfighter.zip")
    assert port_links("starfighter.zip", info_scene.port_info) == []
    assert gui.get_data("port_info.links") == ""
    assert "Links" not in bar_labels(info_scene)

    press(gui, monkeypatch, 'X')
    assert gui.scene_list()[-1] == "port_info"


@pytest.mark.sdl
def test_theme_without_links_section(links_gui, monkeypatch, tmp_path):
    ## Themes made before port_links get a plain built-in screen.
    gui = links_gui
    from pugwash import scenes

    info_scene = port_info_scene(gui, "sprout.zip")
    monkeypatch.delitem(gui.theme_data, "port_links")
    gui.push_scene('port_links', scenes.PortLinksScene(gui, "sprout.zip", info_scene.port_info))

    for _ in range(3):
        gui.updated = True
        gui.do_loop(no_delay=True)

    gui.create_screenshot(str(tmp_path / "links.png"))
    assert (tmp_path / "links.png").stat().st_size > 0
    from pugwash.scenes.base import plain_font
    assert gui.theme_data["port_links"]["links_list"]["font"] == plain_font()
    assert gui.scenes[-1][1][-1].tags['links_list'].list[0] == "PortMaster website"


################################################################################
## Themes made before these screens: theirs are made from the theme's themes list.
THEMES_LIST = {
    "background": {"area": [0, 0, 1.0, 1.0], "fill": "background"},
    "themes_list": {"parent": "port_info_list_area", "area": [0, 0, 1.0, 1.0], "font": "List.ttf",
                    "font[ja_JP]": "NotoSansJP-Regular.ttf", "font-size": 20, "select-fill": "selection",
                    "autoscroll": "slide", "list": []},
    "theme_general_info": {"parent": "port_info_text_area", "area": [0, 0, 1.0, 0.3],
                           "text": "Creator: {theme_info.creator}\nStatus: {theme_info.status}"},
    "theme_general_info_back": {"parent": "port_info_text_area", "area": [0, 0, 1.0, 0.3], "image": "panel.png"},
    "theme_desc": {"parent": "port_info_text_area", "area": [0, 0.3, 1.0, 1.0], "font": "Display.ttf",
                   "text": "{theme_info.description}", "autoscroll": "marquee"},
    "theme_name": {"parent": "port_info_title_area", "area": [0, 0, 1.0, 1.0], "text": "{theme_info.name}"},
    "theme_image": {"parent": "port_info_image_area", "area": [0, 0, 1.0, 1.0], "image": "{theme_info.image}",
                    "image[hires]": "{theme_info.image}", "image-mode": "stretch"},
    "button_bar": {"area": [0, 0.9, 1.0, 1.0], "bar": []},
    }


def test_links_section_from_themes_list():
    from pugwash.theme import section_from_themes_list
    section = section_from_themes_list(THEMES_LIST, 'links')

    assert set(section) == {"background", "links_list", "link_info", "links_title", "link_qr", "button_bar"}

    ## The list as it was, the screenshot is the QR code (square, not stretched).
    assert section["links_list"]["select-fill"] == "selection"
    assert section["link_qr"]["image"] == "qr:{port_links.url}" and section["link_qr"]["image-mode"] == "fit"
    assert "image[hires]" not in section["link_qr"]
    assert section["links_title"]["text"] == "{port_info.title}"
    ## The address where the description was, in its font, not scrolling.
    assert section["link_info"]["text"] == "{port_links.name}\n{port_links.url}"
    assert section["link_info"]["font"] == "Display.ttf" and "autoscroll" not in section["link_info"]
    ## The theme's own data isn't changed.
    assert THEMES_LIST["theme_image"]["image"] == "{theme_info.image}"


def test_server_section_from_themes_list():
    from pugwash.theme import section_from_themes_list
    section = section_from_themes_list(THEMES_LIST, 'server')

    assert set(section) == {"background", "server_info", "server_url", "server_title", "server_qr", "button_bar"}
    ## The list area has the instructions, a size smaller, with no list keys.
    info = section["server_info"]
    assert info["text"] == "{theme_server.status}" and info["text-wrap"] is True
    assert info["font-size"] == 15 and info["font"] == "List.ttf"
    assert not any(key.startswith(("select", "list", "autoscroll")) for key in info)
    assert section["server_qr"]["image"] == "qr:{theme_server.url}"
    assert section["server_url"]["text"] == "{theme_server.url}"
    assert section["server_title"]["text"] == "{scene.title}"


def test_section_from_other_themes_lists():
    from pugwash.theme import section_from_themes_list

    ## hiviz: one text with the creator and the description, the address goes there.
    hiviz = {
        "themes_list": {"area": [0, 0, 0.5, 1.0], "list": []},
        "theme_general_info": {"area": [0.5, 0.5, 1.0, 1.0], "text": "Creator: {theme_info.creator}\n{theme_info.description}"},
        "theme_image": {"area": [0.5, 0, 1.0, 0.5], "image": "{theme_info.image}"},
        }
    assert section_from_themes_list(hiviz, 'links')["link_info"]["area"] == [0.5, 0.5, 1.0, 1.0]

    ## Elements applied: the list is found by its tag.
    tagged = {
        "menu": {"area": [0, 0, 0.5, 1.0], "list": [], "tag": "themes_list"},
        "side_image": {"area": [0.5, 0, 1.0, 0.5], "image": "{theme_info.image}", "tag": "theme_image"},
        }
    section = section_from_themes_list(tagged, 'links')
    assert "links_list" in section and "tag" not in section["links_list"] and "tag" not in section["link_qr"]

    ## Doom: a font with capitals only, the address in the list's font.
    doom = {
        "themes_list": {"area": [0, 0, 0.5, 1.0], "list": [], "font": "DooM.ttf"},
        "theme_desc": {"area": [0.5, 0.5, 1.0, 1.0], "font": "AmazDooMLeft.ttf", "text": "{theme_info.description}"},
        "theme_image": {"area": [0.5, 0, 1.0, 0.5], "image": "{theme_info.image}"},
        }
    assert section_from_themes_list(doom, 'links')["link_info"]["font"] == "DooM.ttf"

    ## Nothing to make the QR code from (basic_theme's list is the options menu's): None,
    ## the scene's plain screen is used.
    assert section_from_themes_list({"themes_list": {"list": []}}, 'links') is None
    assert section_from_themes_list({"theme_image": {"image": "{theme_info.image}"}}, 'links') is None


@pytest.fixture
def old_theme(links_gui):
    """The default theme without the port links and theme editor sections, as themes made before."""
    import json
    import shutil
    import harbourmaster
    from conftest import PM_DIR

    theme_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "themes" / "Old Theme"
    shutil.copytree(str(PM_DIR / "pylibs" / "default_theme"), str(theme_dir))
    data = json.loads((theme_dir / "theme.json").read_text())
    data["#info"]["name"] = "Old Theme"
    del data["port_links"], data["theme_server"]
    (theme_dir / "theme.json").write_text(json.dumps(data))

    links_gui.themes.force_theme = "Old Theme"
    links_gui.reload_theme()
    yield links_gui

    links_gui.themes.force_theme = "default_theme"
    links_gui.reload_theme()
    shutil.rmtree(str(theme_dir))


@pytest.mark.sdl
def test_old_theme_gets_themed_screens(old_theme, monkeypatch, tmp_path):
    gui = old_theme
    from pugwash import scenes

    for name in ("port_links", "theme_server"):
        section = gui.theme_data[name]
        assert any(region.get("parent") == "port_info_list_area" for region in section.values() if isinstance(region, dict)), name

    assert gui.theme_data["port_links"]["link_qr"]["image"] == "qr:{port_links.url}"

    port_info_scene(gui, "sprout.zip")
    press(gui, monkeypatch, 'X')
    assert gui.scene_list()[-1] == "port_links"
    assert gui.scenes[-1][1][-1].tags['links_list'].list[0] == "PortMaster website"

    gui.push_scene('theme-editor', scenes.ThemeServerScene(gui, start=False))
    gui.do_loop(no_delay=True)
    gui.create_screenshot(str(tmp_path / "editor.png"))
    assert (tmp_path / "editor.png").stat().st_size > 0
