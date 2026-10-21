# SPDX-License-Identifier: MIT
#
# pugwash.theme: requirement tags in theme keys, merging, the installed and
# downloadable themes list, and broken custom themes (they must never stop
# PortMaster from starting).

import json
import shutil
from types import SimpleNamespace

import pytest

import harbourmaster

from conftest import PM_DIR


pytestmark = pytest.mark.sdl


@pytest.fixture
def theme(pugwash):
    from pugwash import theme
    return theme


################################################################################
## Requirements and merging
@pytest.mark.parametrize("text, strict, expected", [
    ("area", False, ("area", [])),
    ("area", True, ("area", None)),
    ("area[640x480]", False, ("area", ["640x480"])),
    ("area[ 640x480 , power ]", True, ("area", ["640x480", "power"])),
    ("area[a][b]", False, ("area_bad", [])),
    ("area[a]x", True, ("area_bad", None)),
    ])
def test_extract_requirements(theme, text, strict, expected):
    assert theme.extract_requirements(text, strict=strict) == expected


def test_theme_update_follows_requirements(theme):
    ## The test device: aarch64, 640x480, power, opengl.
    result = theme.theme_update({"keep": 1}, {
        "font-size": 10,
        "font-size[640x480]": 20,
        "font-size[1280x720]": 30,
        "fill[!opengl]": [1, 2, 3],
        "list": [1, 2],
        "nested": {"a": 1, "b[power]": 2},
        })

    assert result == {"keep": 1, "font-size": 20, "list": [1, 2], "nested": {"a": 1, "b": 2}}


def test_theme_update_copies_lists(theme):
    source = {"list": [1, 2]}
    result = theme.theme_update({}, source)
    result["list"].append(3)

    assert source == {"list": [1, 2]}


def test_theme_merge_leaves_both_alone(theme):
    target = {"a": {"b": 1}}
    source = {"a": {"c": 2}}

    assert theme.theme_merge(target, source) == {"a": {"b": 1, "c": 2}}
    assert target == {"a": {"b": 1}} and source == {"a": {"c": 2}}


################################################################################
## The themes list
@pytest.fixture
def engine(theme, hm, monkeypatch):
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", hm.tools_dir)
    (hm.tools_dir / "PortMaster" / "themes").mkdir(parents=True, exist_ok=True)
    return theme.ThemeEngine(SimpleNamespace(hm=hm))


def add_theme(hm, folder, name=None, data=None, text=None, md5=None, screenshot=None):
    theme_dir = hm.tools_dir / "PortMaster" / "themes" / folder
    theme_dir.mkdir(parents=True, exist_ok=True)
    if text is None:
        text = json.dumps(data if data is not None else {"#info": {"name": name or folder, "creator": "me", "description": "A theme."}})

    (theme_dir / "theme.json").write_text(text)
    if md5 is not None:
        (theme_dir / "theme.md5").write_text(md5 + "\n")
    if screenshot is not None:
        (theme_dir / screenshot).write_bytes(b"img")

    return theme_dir


def test_themes_list_order(engine, hm):
    add_theme(hm, "zeta", "Zeta")
    add_theme(hm, "alpha", "alpha")

    assert list(engine.get_themes_list()) == ["default_theme", "alpha", "zeta"]


def test_theme_info(engine, hm):
    theme_dir = add_theme(hm, "mine", "Mine", md5="abc", screenshot="screenshot.png")

    info = engine.get_theme_info("mine")
    assert info['name'] == "Mine" and info['creator'] == "me" and info['description'] == "A theme."
    assert info['md5'] == "abc"
    assert info['image'] == theme_dir / "screenshot.png"
    assert info['status'] == "Installed" and info['url'] is None

    assert engine.get_theme_info("default_theme")['md5'] == "d41d8cd98f00b204e9800998ecf8427e"


def test_themes_list_with_downloads(engine, hm):
    add_theme(hm, "same", "Same", md5="111")
    add_theme(hm, "old", "Old", md5="222")
    add_theme(hm, "noshot", "No Shot", md5="333")

    downloads = {
        "same": {"name": "Same", "url": "https://x/same.zip", "md5": "111", "image": None},
        "old": {"name": "Old", "url": "https://x/old.zip", "md5": "999", "image": None},
        "noshot": {"name": "No Shot", "url": "https://x/noshot.zip", "md5": "333", "image": "/cache/noshot.png"},
        "new": {"name": "New", "url": "https://x/new.zip", "md5": "444", "image": None},
        }

    themes = engine.get_themes_list(downloads)

    assert themes["same"]['status'] == "Installed" and themes["same"]['url'] == "https://x/same.zip"
    assert themes["old"]['status'] == "Update Available"
    assert themes["noshot"]['image'] == "/cache/noshot.png"
    assert themes["new"]['status'] == "Not Installed"
    ## Its own copy.
    assert 'status' not in downloads["new"]


@pytest.mark.parametrize("text", ['{"#info": {"name": "Bro', "", "[]", "null"])
def test_broken_theme_is_left_out_of_the_list(engine, hm, text, log_errors):
    ## A cut-off or hand-edited theme.json took the whole list (Options -> Select Theme) down.
    add_theme(hm, "good", "Good")
    add_theme(hm, "broken", text=text)

    assert list(engine.get_themes_list()) == ["default_theme", "good"]


@pytest.mark.parametrize("make", [
    lambda hm: None,
    lambda hm: (hm.tools_dir / "PortMaster" / "themes" / "chosen").mkdir(parents=True),
    lambda hm: add_theme(hm, "chosen", text='{"broken'),
    ])
def test_current_theme_falls_back(engine, hm, make, log_errors):
    make(hm)
    hm.cfg_data['theme'] = "chosen"

    assert engine.get_current_theme() == "default_theme"
    assert any("default_theme" in message for message in log_errors)


def test_current_theme(engine, hm):
    add_theme(hm, "chosen", "Chosen")
    hm.cfg_data['theme'] = "chosen"
    assert engine.get_current_theme() == "chosen"

    hm.cfg_data.pop('theme')
    assert engine.get_current_theme() == "default_theme"


def test_forced_theme_and_scheme(theme, hm):
    engine = theme.ThemeEngine(SimpleNamespace(hm=hm), force_theme="forced", force_scheme="dark")
    assert engine.get_current_theme() == "forced"
    assert engine.get_current_theme_scheme() == "dark"


def test_config_without_harbourmaster(theme, hm, monkeypatch):
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", hm.tools_dir)
    hm.cfg_data['theme-scheme'] = "Night"
    hm.save_config()

    engine = theme.ThemeEngine(SimpleNamespace(hm=None))
    assert engine.get_current_theme_scheme() == "Night"


def test_theme_schemes(engine, hm):
    add_theme(hm, "schemed", data={"#info": {"name": "S"}, "#schemes": {"#base": {}, "Day": {}, "Night": {}}})
    assert engine.get_theme_schemes_list("schemed") == ["Day", "Night"]
    assert engine.get_theme("schemed").screenshot is None


def test_theme_missing(theme, tmp_path):
    with pytest.raises(ValueError):
        theme.Theme(tmp_path / "nothing")


################################################################################
## A custom theme that loads as JSON but not as a theme
@pytest.fixture
def app(gui, hm_dirs):
    gui.hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=gui, **hm_dirs)
    yield gui

    gui.themes.force_theme = "default_theme"
    gui.hm.cfg_data['theme'] = "default_theme"
    gui.reload_theme()
    gui.hm = None


@pytest.fixture
def typo_theme():
    """A copy of the default theme with a typo: an element's area has three numbers."""
    theme_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "themes" / "Typo"
    shutil.copytree(str(PM_DIR / "pylibs" / "default_theme"), str(theme_dir))
    data = json.loads((theme_dir / "theme.json").read_text())
    data["#elements"]["left_pane"] = dict(data["#elements"]["left_pane"], area=[0, 0, 100])
    (theme_dir / "theme.json").write_text(json.dumps(data))
    yield "Typo"
    shutil.rmtree(str(theme_dir))


def test_theme_that_fails_to_load_falls_back(app, typo_theme, log_errors):
    ## It stopped PortMaster from starting until the theme was deleted by hand.
    app.themes.force_theme = None
    app.hm.cfg_data['theme'] = typo_theme

    app.reload_theme()

    assert app.themes.get_current_theme() == "default_theme"
    assert app.theme_dir == PM_DIR / "pylibs" / "default_theme"
    assert 'option_menu' in app.theme_data
    assert any("using the default theme" in message for message in log_errors)


def test_forced_theme_that_fails_to_load_raises(app, typo_theme):
    ## The theme editor shows the error rather than another theme.
    from pugwash.sdl.errors import GUIThemeError
    app.themes.force_theme = typo_theme

    with pytest.raises(GUIThemeError):
        app.reload_theme()
