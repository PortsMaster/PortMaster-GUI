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
