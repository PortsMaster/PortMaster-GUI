# SPDX-License-Identifier: MIT
#
# Changing theme, colour scheme or language without a restart (PortMasterGUI.reload_theme
# and reload_language): the screens after switching away and back must be the same as
# before, so nothing of the other theme or language is left behind.

import json
import shutil

import pytest

import harbourmaster

from conftest import PM_DIR


pytestmark = pytest.mark.sdl


@pytest.fixture
def app(gui, hm_dirs):
    from pugwash import lang

    gui.hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=gui, **hm_dirs)
    start_lang = lang.CURRENT_LANG
    yield gui

    ## Back as the other tests expect it.
    gui.themes.force_theme = "default_theme"
    gui.hm.cfg_data['theme-scheme'] = None
    if lang.CURRENT_LANG != start_lang:
        gui.reload_language(start_lang)
    else:
        gui.reload_theme()
    gui.hm = None


@pytest.fixture
def other_theme():
    """A copy of the default theme with other colours, installed where themes go."""
    theme_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "themes" / "Other Theme"
    shutil.copytree(str(PM_DIR / "pylibs" / "default_theme"), str(theme_dir))
    data = json.loads((theme_dir / "theme.json").read_text())
    data["#info"]["name"] = "Other Theme"
    for scheme in data["#schemes"].values():
        if isinstance(scheme, dict) and "#pallet" in scheme:
            scheme["#pallet"] = {name: [40, 120, 40] for name in scheme["#pallet"]}
    (theme_dir / "theme.json").write_text(json.dumps(data))
    yield "Other Theme"
    shutil.rmtree(str(theme_dir))


def screen(gui, tmp_path, name):
    """The screen as PNG bytes, after a few frames."""
    for _ in range(3):
        gui.updated = True
        gui.draw_counter = 0
        gui.do_loop(no_delay=True)

    out_file = tmp_path / f"{name}.png"
    gui.create_screenshot(str(out_file))
    return out_file.read_bytes()


def options(gui):
    from pugwash.scenes import OptionScene
    return [('option', OptionScene)]


def test_theme_reload(app, other_theme, tmp_path):
    app.reload_theme(then=options(app))
    before = screen(app, tmp_path, "before")

    app.themes.force_theme = other_theme
    app.reload_theme(then=options(app))
    assert app.scene_list() == ["root", "option"]
    assert app.theme_dir.name == other_theme
    other = screen(app, tmp_path, "other")
    assert other != before

    app.themes.force_theme = "default_theme"
    app.reload_theme(then=options(app))
    assert screen(app, tmp_path, "after") == before


def test_scheme_reload(app, tmp_path):
    app.reload_theme(then=options(app))
    before = screen(app, tmp_path, "before")

    app.hm.cfg_data['theme-scheme'] = "Dracula"
    app.reload_theme(then=options(app))
    assert screen(app, tmp_path, "dracula") != before

    app.hm.cfg_data['theme-scheme'] = None
    app.reload_theme(then=options(app))
    assert screen(app, tmp_path, "after") == before


def test_language_reload(app, tmp_path):
    from pugwash import lang

    app.reload_language("en_US", then=options(app))
    before = screen(app, tmp_path, "before")

    app.reload_language("de_DE", then=options(app))
    assert lang.CURRENT_LANG == "de_DE"
    option_list = app.scenes[-1][1][-1].tags['option_list']
    assert "Sprache wählen" in option_list.list
    assert "de_DE" in harbourmaster.device_info()['capabilities'] and "en_US" not in harbourmaster.device_info()['capabilities']

    ## The languages are named in the new language too.
    from pugwash.scenes import LanguageScene
    names = LanguageScene(app).tags['option_list'].list
    assert "Französisch" in names and "French" not in names

    ## The theme's font for the language: "font[ja_JP]" (the Test Suite has no Noto fonts).
    if (PM_DIR / "pylibs" / "resources" / "NotoSansJP-Regular.ttf").is_file():
        app.reload_language("ja_JP", then=options(app))
        assert app.scenes[-1][1][-1].tags['option_list'].font == "NotoSansJP-Regular.ttf"

    app.reload_language("en_US", then=options(app))
    assert screen(app, tmp_path, "after") == before


def test_choosing_a_theme_applies_it(app, other_theme, monkeypatch):
    ## The themes list: A on another theme applies it, no restart, back in the list.
    from pugwash.scenes import ThemesScene
    from pugwash import theme

    app.hm.cfg_data['theme'] = "default_theme"
    app.themes.force_theme = None
    monkeypatch.setattr(theme.ThemeDownloader, "get_theme_list", lambda self: {})
    app.theme_downloader = theme.ThemeDownloader(app, app.themes)
    app.reload_theme(then=options(app) + [('select-theme', ThemesScene)])

    scene = app.scenes[-1][1][-1]
    scene.tags['themes_list'].list_select(list(scene.themes).index(other_theme))
    monkeypatch.setattr(app.events, "was_pressed", lambda button: button == 'A')
    app.do_loop(no_delay=True)

    assert app.events.running
    assert app.hm.cfg_data['theme'] == other_theme and app.theme_dir.name == other_theme
    assert app.scene_list() == ["root", "option", "select-theme"]
    assert app.scenes[-1][1][-1].tags['themes_list'].selected_option() == other_theme

    app.hm.cfg_data['theme'] = "default_theme"
    app.theme_downloader = None
