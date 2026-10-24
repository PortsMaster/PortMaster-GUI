# SPDX-License-Identifier: MIT
#
# pugwash.theme.theme_load / theme_apply: a theme's JSON to the sections the scenes draw:
# "#base", "#elements", "#pallet", "#resources", colour schemes, requirement tags on
# sections, regions and elements ("[640x480]", "[ja_JP|zh_CN]", "[!opengl]"), a theme's own
# "#translations", and the sections PortMaster adds itself. A fake GUI records what's loaded.

import json
from types import SimpleNamespace

import pytest

import harbourmaster
from harbourmaster import i18n


pytestmark = pytest.mark.sdl


class FakeGUI:
    def __init__(self):
        from pugwash.sdl import geometry
        self.loaded_images, self.loaded_sounds, self.animations_added = [], [], []
        self.images = SimpleNamespace(
            load_data=lambda name, data: self.loaded_images.append((name, data)) or object(),
            load_data_lazy=lambda name, data: self.loaded_images.append((name, None)) or object())
        self.sounds = SimpleNamespace(load=lambda name, set_name: self.loaded_sounds.append((name, set_name)) or object())
        self.animations = SimpleNamespace(add_animation=lambda name, options: self.animations_added.append(name))
        self.default_rects = geometry.NamedRects((0, 0, 640, 480))
        self.pallet = {}
        self.override = {}


@pytest.fixture
def load(pugwash, tmp_path):
    """load(theme_dict, scheme=None) -> (sections, gui)"""
    from pugwash import theme

    def _load(data, scheme=None):
        base = {
            "option_menu": {"option_list": {"area": [0, 0, 1.0, 1.0]}},
            "ports_list": {"ports_list": {"area": [0, 0, 1.0, 1.0]}},
            }
        base.update(data)
        path = tmp_path / "theme.json"
        path.write_text(json.dumps(base), encoding="utf-8")
        gui = FakeGUI()
        return theme.theme_load(gui, path, scheme), gui

    yield _load
    i18n.set_theme_translations({})


@pytest.fixture
def capabilities(monkeypatch):
    """add(*caps): the test device's capabilities (aarch64 640x480 power opengl) and these."""
    caps = list(harbourmaster.device_info()['capabilities'])

    def add(*extra):
        monkeypatch.setattr(harbourmaster, "device_info", lambda *a, **k: {'capabilities': caps + list(extra)})

    add()
    return add


################################################################################
## Sections, #base and region requirements
def test_base_applies_to_every_region(load, capabilities):
    sections, _ = load({
        "#base": {"font": "Base.ttf", "font-size": 20},
        "main_menu": {"title": {"area": [0, 0, 1.0, 0.1], "font-size": 30}, "list": {"area": [0, 0.1, 1.0, 1.0]}},
        })

    assert sections["main_menu"]["title"] == {"font": "Base.ttf", "font-size": 30, "area": [0, 0, 1.0, 0.1]}
    assert sections["main_menu"]["list"]["font"] == "Base.ttf"


def test_section_base_overrides_the_themes(load, capabilities):
    sections, _ = load({
        "#base": {"font": "Base.ttf"},
        "main_menu": {"#base": {"font": "Menu.ttf"}, "title": {"area": [0, 0, 1, 1]}},
        "options": {"title": {"area": [0, 0, 1, 1]}},
        })

    assert sections["main_menu"]["title"]["font"] == "Menu.ttf"
    assert sections["options"]["title"]["font"] == "Base.ttf"
    assert "#base" not in sections["main_menu"]


def test_key_requirements(load, capabilities):
    sections, _ = load({"main_menu": {"title": {
        "font-size": 10, "font-size[640x480]": 20, "font-size[1280x720]": 30,
        "fill[!opengl]": [1, 2, 3], "fill[opengl]": [4, 5, 6],
        "image[power|battery]": "a.png", "image[nothing|else]": "b.png",
        "border[aarch64,640x480]": 3, "border[aarch64,1280x720]": 9,
        }}})

    assert sections["main_menu"]["title"] == {"font-size": 20, "fill": [4, 5, 6], "image": "a.png", "border": 3}


def test_language_requirements(load, capabilities):
    ## The GUI adds the current language to the capabilities: font[ja_JP] & co.
    capabilities("ja_JP")
    sections, _ = load({"#base": {
        "font": "DejaVuSans.ttf", "font[ja_JP]": "NotoSansJP.ttf",
        "line-height[ja_JP|zh_CN|ko_KR]": 0.8}, "main_menu": {"title": {}}})

    assert sections["main_menu"]["title"] == {"font": "NotoSansJP.ttf", "line-height": 0.8}


def test_region_requirements(load, capabilities):
    sections, _ = load({"main_menu": {
        "title": {"area": [0, 0, 1, 1]},
        "title[1280x720]": {"area": [0, 0, 0.5, 0.5]},
        "title[640x480]": {"font-size": 40},
        "extra[!power]": {"area": [0, 0, 1, 1]},
        }})

    assert sections["main_menu"]["title"] == {"area": [0, 0, 1, 1], "font-size": 40}
    assert "extra" not in sections["main_menu"]


def test_section_requirements(load, capabilities):
    sections, _ = load({
        "main_menu": {"title": {"font-size": 10}, "list": {"font-size": 12}},
        "main_menu[640x480]": {"title": {"font-size": 20}},
        "main_menu[1280x720]": {"title": {"font-size": 30}},
        ## A section that isn't defined yet can't be added to.
        "options[640x480]": {"title": {"font-size": 99}},
        })

    assert sections["main_menu"]["title"]["font-size"] == 20
    assert sections["main_menu"]["list"]["font-size"] == 12
    assert "options" not in sections


def test_config_section_is_kept_apart(load, capabilities):
    sections, _ = load({"main_menu": {"#config": {"buttons": {"A": "select"}}, "title": {}}})
    assert sections["main_menu"]["#config"] == {"buttons": {"A": "select"}}


def test_images_in_regions_are_preloaded(load, capabilities):
    _, gui = load({"main_menu": {
        "logo": {"image": "logo.png"},
        "shot": {"image": "{port_info.image}"},      ## a template: loaded when drawn
        "bg": {"pimage": "bg.png"},
        "n": {"image": 5},
        }})

    names = [name for name, _ in gui.loaded_images]
    assert "logo.png" in names and "bg.png" in names
    assert not any("{" in str(name) for name in names)


################################################################################
## Elements
def test_elements(load, capabilities):
    sections, gui = load({
        "#elements": {
            "panel": {"parent": "root", "area": [0.0, 0.0, 0.5, 1.0], "fill": [1, 1, 1]},
            "panel_wide[1280x720]": {"area": [0, 0, 1, 1]},
            },
        "main_menu": {
            "#element:panel": {"border": 4},
            "#element:panel:left_panel": {"border": 8},
            "#element:panel:wide_only[1280x720]": {},
            "#element:missing": {"border": 1},
            },
        })

    assert sections["main_menu"]["panel"] == {"parent": "root", "area": [0.0, 0.0, 0.5, 1.0], "fill": [1, 1, 1], "border": 4}
    assert sections["main_menu"]["left_panel"]["border"] == 8
    assert "wide_only" not in sections["main_menu"] and "missing" not in sections["main_menu"]
    ## An element's area is a named area other regions can use as a parent.
    assert gui.default_rects._rects["panel"].tuple() == (0, 0, 320, 480)
    assert "panel_wide" not in gui.default_rects._rects


def test_element_area_requirements(load, capabilities):
    _, gui = load({"#elements": {"panel": {"area": [0, 0, 1.0, 1.0], "area[640x480]": [0, 0, 0.5, 0.5], "area[1280x720]": [0, 0, 0.25, 0.25]}}})
    assert gui.default_rects._rects["panel"].tuple() == (0, 0, 320, 240)


################################################################################
## Resources, pallet, overrides, animations
def test_resources(load, capabilities):
    _, gui = load({"#resources": {
        "bg.png": {"name": "BACKGROUND"}, "logo.jpg": {}, "pic.svg": {},
        "click.wav": {"name": "click"}, "music.ogg": {}, "song.mp3": {}, "tune.mod": {},
        "notes.txt": {},
        }})

    assert [name for name, _ in gui.loaded_images[:3]] == ["bg.png", "logo.jpg", "pic.svg"]
    assert gui.loaded_sounds == [("click.wav", "click"), ("music.ogg", "music.ogg"), ("song.mp3", "song.mp3"), ("tune.mod", "tune.mod")]


def test_pallet_override_and_animations(load, capabilities):
    _, gui = load({
        "#pallet": {"accent": [1, 2, 3]},
        "#override": {"main_menu.title": "Hi"},
        "#animations": {"fade": {"duration": 100}},
        })

    assert gui.pallet == {"accent": [1, 2, 3]}
    assert gui.override == {"main_menu.title": "Hi"}
    assert gui.animations_added == ["fade"]


################################################################################
## Colour schemes
SCHEMES = {
    "#info": {"default-scheme": "Dark"},
    "#schemes": {
        "#base": {"#pallet": {"text": [0, 0, 0], "background": [255, 255, 255]}},
        "Light": {"#pallet": {"background": [250, 250, 250]}},
        "Dark": {"#pallet": {"text": [255, 255, 255], "background": [0, 0, 0]}, "#base": {"font-size": 18}},
        },
    "main_menu": {"title": {}},
    }


def test_default_scheme(load, capabilities):
    sections, gui = load(SCHEMES)

    assert gui.pallet == {"text": [255, 255, 255], "background": [0, 0, 0]}
    assert sections["main_menu"]["title"] == {"font-size": 18}


def test_chosen_scheme_merges_with_the_scheme_base(load, capabilities):
    _, gui = load(SCHEMES, "Light")
    assert gui.pallet == {"text": [0, 0, 0], "background": [250, 250, 250]}


@pytest.mark.parametrize("scheme", ["Nope", "#base"])
def test_unknown_scheme_is_the_default(load, capabilities, scheme):
    _, gui = load(SCHEMES, scheme)
    assert gui.pallet["text"] == [255, 255, 255]


def test_no_default_scheme_is_the_first(load, capabilities):
    data = json.loads(json.dumps(SCHEMES))
    del data["#info"]
    _, gui = load(data)
    assert gui.pallet == {"text": [0, 0, 0], "background": [250, 250, 250]}


def test_no_schemes(load, capabilities):
    _, gui = load({"#pallet": {"a": [1, 1, 1]}}, "Dark")
    assert gui.pallet == {"a": [1, 1, 1]}


################################################################################
## A theme's own translations
def test_theme_translations(load, capabilities, monkeypatch):
    monkeypatch.setattr(i18n, "LANGUAGE", "de_DE")
    load({"#translations": {"de_DE": {"Hello": "Hallo"}, "fr_FR": {"Hello": "Bonjour"}}})
    assert i18n.theme_text("Hello") == "Hallo"

    ## The next theme's (none) replace them.
    load({})
    assert i18n.theme_text("Hello") == "Hello"


################################################################################
## What PortMaster adds
def test_disclaimer_is_always_the_same(load, capabilities):
    sections, _ = load({"disclaimer": {"background": {"fill": [255, 0, 0]}}})

    disclaimer = sections["disclaimer"]
    assert set(disclaimer) == {"background", "disclaimer_text", "button_bar"}
    assert disclaimer["background"]["fill"] == [200, 200, 200, 255]


@pytest.mark.parametrize("lang, font", [
    ("en_US", "DejaVuSans.ttf"), ("ja_JP", "NotoSansJP-Regular.ttf"), ("zh_CN", "NotoSansSC-Regular.ttf"),
    ("ko_KR", "NotoSansKR-Regular.ttf"), ("zh_TW", "NotoSansTC-Regular.ttf")])
def test_disclaimer_font_for_the_language(load, capabilities, lang, font):
    ## The startup warnings are translated: DejaVu Sans would draw CJK as boxes.
    capabilities(lang)
    sections, _ = load({})
    assert {region["font"] for region in sections["disclaimer"].values()} == {font}


def test_disclaimer_bar_is_translated(load, capabilities, monkeypatch):
    from pugwash import theme
    monkeypatch.setattr(theme, "_", lambda text: "Bitte warten." if text == "Please wait." else text)
    sections, _ = load({})
    assert sections["disclaimer"]["button_bar"]["bar"] == ["Bitte warten."]


def test_sections_made_for_older_themes(load, capabilities):
    sections, _ = load({
        "option_menu": {"option_list": {"area": [0, 0, 1, 1], "font-size": 11}},
        "ports_list": {"ports_list": {"area": [0, 0, 1, 1], "font-size": 12}},
        })

    assert sections["themes_list"]["themes_list"]["font-size"] == 11 and "option_list" not in sections["themes_list"]
    assert sections["runtime_list"]["runtime_list"]["font-size"] == 11
    assert sections["featured_ports_list"]["option_list"]["font-size"] == 11
    assert sections["featured_ports"]["ports_list"]["font-size"] == 12


def test_port_links_and_editor_from_the_themes_list(load, capabilities):
    sections, _ = load({"themes_list": {
        "themes_list": {"area": [0, 0, 0.5, 1], "border-x": 12, "list": []},
        "theme_image": {"area": [0.5, 0, 1, 0.5], "image": "{theme_info.image}"},
        "theme_desc": {"area": [0.5, 0.5, 1, 1], "text": "{theme_info.description}"},
        }})

    assert sections["port_links"]["link_qr"]["image"] == "qr:{port_links.url}"
    assert sections["theme_server"]["server_info"]["border-x"] == 12


def test_own_port_links_and_editor_sections_are_kept(load, capabilities):
    sections, _ = load({
        "themes_list": {"themes_list": {"list": []}, "theme_image": {"image": "{theme_info.image}"}},
        "port_links": {"mine": {"area": [0, 0, 1, 1]}},
        })

    assert set(sections["port_links"]) == {"mine"}
    assert "server_qr" in sections["theme_server"]


def test_no_screenshot_no_made_sections(load, capabilities):
    ## Nowhere for the QR code: the scenes show their own plain screens instead.
    sections, _ = load({"themes_list": {"themes_list": {"list": []}}})
    assert "port_links" not in sections and "theme_server" not in sections


################################################################################
## Broken themes raise (the theme engine falls back to the default theme)
@pytest.mark.parametrize("data", [
    {"main_menu": {"title": "not a region"}},
    {"main_menu": ["not", "a", "section"]},
    {"#elements": {"panel": "not an element"}},
    ])
def test_broken_theme_raises(load, capabilities, data):
    with pytest.raises(Exception):
        load(data)


def test_null_theme_raises(pugwash, tmp_path):
    from pugwash import theme
    (tmp_path / "theme.json").write_text("null")
    with pytest.raises(ValueError):
        theme.theme_load(FakeGUI(), tmp_path / "theme.json")
