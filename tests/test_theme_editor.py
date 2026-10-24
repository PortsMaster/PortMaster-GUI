# SPDX-License-Identifier: MIT
#
# The theme server's Edit view, server side: what it knows about theme.json (theme_server/
# schema.py, read from pugwash's code), and its files (theme_server/editor.py): reading and
# saving theme.json, drafts for the preview, copying a theme. The HTTP side is in
# test_theme_server_http.py.

import json
import os
import re

import pytest

from conftest import PM_DIR

from theme_server import editor as theme_editor, schema, serve


################################################################################
## schema: region keys from region.py
@pytest.fixture(scope="module")
def keys():
    return schema.region_keys()


def test_region_key_types(keys):
    assert keys['font-size'] == {'type': "int"}
    assert keys['font-scale']['type'] == "float"
    assert keys['area'] == {'type': "rect"}
    assert keys['font-color'] == {'type': "color"}
    assert keys['text-wrap'] == {'type': "bool"}
    assert keys['image-size'] == {'type': "ints", 'count': 2}
    assert keys['patch'] == {'type': "ints", 'count': 4}
    assert keys['click-sound-volume'] == {'type': "int", 'min': 0, 'max': 128}
    assert keys['list-columns'] == {'type': "int", 'min': 1, 'max': 6}
    assert keys['image'] == {'type': "image"} and keys['pointer'] == {'type': "image"}


def test_region_key_options(keys):
    ## Rect.POINTS and BLEND_MODES, found by name.
    assert keys['align']['options'][:3] == ["topleft", "midtop", "topcenter"] and "bottomright" in keys['align']['options']
    assert keys['pointer-align']['count'] == 2 and keys['pointer-align']['options'] == keys['align']['options']
    assert set(keys['blend-mode']['options']) == {"none", "blend", "add", "mod", "mul"}
    assert keys['image-mode']['options'] == ["fit", "fit-horizontal", "fit-vertical", "stretch", "repeat"]
    assert keys['autoscroll']['options'] == ["slide", "marquee"]


def test_every_verified_key_is_known(keys):
    text = (PM_DIR / "pylibs" / "pugwash" / "sdl" / "region.py").read_text(encoding="utf-8")
    verified = set(re.findall(r"_verify_\w+\(\s*'([a-z-]+)'", text))
    assert len(verified) > 60
    assert verified <= set(keys)


def test_sections():
    sections = schema.sections()
    assert "option_list" in sections["main_menu"]
    assert "links_list" in sections["port_links"]
    ## A scene's section that the default theme doesn't have still counts.
    assert "disclaimer_text" in sections["disclaimer"]


def test_template_tags():
    tags = schema.template_tags()
    assert {"system.time_24hr", "port_info.title", "port_links.url", "theme_server.url", "ports_list.total_ports"} <= set(tags)
    assert all(re.match(r"^[a-z_]+\.[a-z0-9_]+$", tag) for tag in tags)


def test_capabilities(tmp_path):
    theme = tmp_path / "theme.json"
    theme.write_text('{"main_menu": {"r": {"area[!opengl]": [0, 0, 1, 1], "font-size[rg35xx|ko_KR, hires]": 5}}}')
    found = schema.capabilities([theme])
    assert {"4:3", "16:9", "ja_JP", "opengl", "rg35xx", "ko_KR", "hires"} <= set(found)
    assert not any(cap.startswith("!") for cap in found)


def test_theme_files(tmp_path):
    (tmp_path / "images").mkdir()
    for name in ("a.png", "images/b.JPG", "font.ttf", "click.ogg", "notes.txt"):
        (tmp_path / name).write_bytes(b"x")

    files = schema.theme_files(tmp_path)

    assert files['image'] == ["a.png", "images/b.JPG"]
    assert files['sound'] == ["click.ogg"]
    ## The theme's fonts, then PortMaster's (the Noto fonts even before they're unpacked).
    assert files['font'][0] == "font.ttf" and "DejaVuSans.ttf" in files['font'] and "NotoSansJP-Regular.ttf" in files['font']


def test_theme_names():
    data = {
        "#pallet": {"top": [1, 2, 3]},
        "#resources": {"buttons.png": {"atlas": {"_A": [0, 0, 1, 1]}}, "click.ogg": {"name": "click"}},
        "#schemes": {"#base": {"#pallet": {"base_color": "#fff"}}, "Dark": {"#pallet": {"dark": "#000"}}, "Light": {}},
        "#elements": {"left_pane": {}, "right_pane": {}},
        }
    names = schema.theme_names(data)
    assert names['colors'] == ["base_color", "dark", "top"]
    assert names['resources'] == ["_A", "buttons.png", "click", "click.ogg"]
    assert names['elements'] == ["left_pane", "right_pane"]
    assert names['schemes'] == ["Dark", "Light"]


@pytest.mark.parametrize("data", [{}, {"#schemes": [1]}, {"#pallet": "x", "#resources": {"a": 5}, "#elements": None}])
def test_theme_names_odd_themes(data):
    schema.theme_names(data)


def test_schema_is_json(tmp_path):
    whole = schema.schema(PM_DIR / "pylibs" / "default_theme")
    assert json.loads(json.dumps(whole)) == whole
    assert "Light Mode" in whole['names']['schemes'] and "general_font" in whole['names']['colors']
    assert "#info" in whole['top'] and "default-scheme" in whole['info']
    ## No theme: still everything but the theme's own names.
    assert schema.schema()['names']['colors'] == []


def region_key_problems(theme_data):
    """[(section, region, key)] of keys PortMaster doesn't know, as the editor's checks find them."""
    known = schema.region_keys()
    found = []

    def check(section, region, data):
        for key in data:
            if key.split("[", 1)[0] not in known:
                found.append((section, region, key))

    check("#base", "", theme_data.get("#base", {}))
    for name, region in theme_data.get("#elements", {}).items():
        check("#elements", name, region)
    for section, regions in theme_data.items():
        if section.startswith("#") or not isinstance(regions, dict):
            continue
        for name, region in regions.items():
            if name != "#config" and isinstance(region, dict):
                check(section, name, region)
    return found


def test_default_theme_keys_are_known():
    data = json.loads((PM_DIR / "pylibs" / "default_theme" / "theme.json").read_text(encoding="utf-8"))
    problems = region_key_problems(data)
    ## Known: typos PortMaster ignores. Fixing them changes how the default theme looks.
    known = [("on_screen_keyboard", "keyboard", "barwidth"), ("filter_list", "filter_list", "list-spacer")]
    assert [problem for problem in problems if problem not in known] == []


@pytest.mark.xfail(strict=True, reason="the default theme has barwidth (bar-width) and list-spacer, which PortMaster ignores")
def test_default_theme_has_no_unknown_keys():
    data = json.loads((PM_DIR / "pylibs" / "default_theme" / "theme.json").read_text(encoding="utf-8"))
    assert region_key_problems(data) == []


################################################################################
## editor: checking and renaming theme.json text
@pytest.mark.parametrize("text, error", [
    ('{"a": 1}', None),
    ('{}', None),
    ('[]', "has to be a JSON object"),
    ('5', "has to be a JSON object"),
    ('{"a": 1,}', "Expecting property name"),
    ('{"a": 1', "Expecting"),
    ('', "Expecting value"),
    ])
def test_check_text(text, error):
    problem = theme_editor.check_text(text)
    if error is None:
        assert problem is None
    else:
        assert error in problem['error'] and problem['line'] >= 1


def test_check_text_position():
    problem = theme_editor.check_text('{\n  "a": 1,\n  "b": 2,\n}')
    assert problem['line'] == 4 and problem['column'] == 1


def test_rename_keeps_the_layout():
    text = '{\n    "#info": {\n        "version": 1,\n        "name":   "Old \\"one\\"",\n        "creator": "me"\n    },\n    "main_menu": { "r": { "area": [ 0, 0, 1, 1 ] } }\n}\n'
    renamed = theme_editor.rename_text(text, 'New "two"')

    assert json.loads(renamed)["#info"]["name"] == 'New "two"'
    assert renamed.replace('New \\"two\\"', 'Old \\"one\\"') == text


def test_rename_only_info_name():
    ## A "name" deeper in #info, or before #info, isn't the theme's name.
    text = '{"x": {"name": "not this"}, "#info": {"extra": {"name": "nor this"}, "creator": "name", "name": "Old"}}'
    renamed = json.loads(theme_editor.rename_text(text, "New"))
    assert renamed["#info"] == {"extra": {"name": "nor this"}, "creator": "name", "name": "New"}
    assert renamed["x"] == {"name": "not this"}


@pytest.mark.parametrize("text", ['{"main_menu": {}}', '{"#info": {"creator": "me"}}', '{"#info": "odd"}'])
def test_rename_without_a_name(text):
    assert json.loads(theme_editor.rename_text(text, "New"))["#info"]["name"] == "New"


################################################################################
## editor: files
@pytest.fixture
def themes(tmp_path):
    root = tmp_path / "themes"
    (root / "mine" / "images").mkdir(parents=True)
    (root / "mine" / "theme.json").write_text('{\n    "#info": {"name": "Mine"}\n}\n')
    (root / "mine" / "images" / "bg.png").write_bytes(b"png")
    (root / "mine" / "font.ttf").write_bytes(b"ttf")
    return serve.Themes(root)


@pytest.fixture
def editor(themes, tmp_path):
    return theme_editor.ThemeEditor(themes, tmp_path / "work", serve.DEFAULT_THEME_DIR)


def test_read(editor):
    file = editor.read("mine")
    assert file['text'].startswith('{\n    "#info"') and file['writable'] and file['can_copy']
    assert file['version'] == theme_editor.text_version(file['text'].encode())


def test_default_theme_is_read_only(editor):
    file = editor.read("default_theme")
    assert not file['writable'] and file['can_copy']
    with pytest.raises(theme_editor.EditorError) as error:
        editor.save("default_theme", file['text'], file['version'])
    assert error.value.status == 403


@pytest.mark.parametrize("theme_id", ["nope", "", None, 5, "mine~draft", "../mine"])
def test_no_such_theme(editor, theme_id):
    with pytest.raises(theme_editor.EditorError) as error:
        editor.read(theme_id)
    assert error.value.status == 404


def test_save(editor, themes):
    file = editor.read("mine")
    answer = editor.save("mine", '{"#info": {"name": "Saved"}}', file['version'])

    theme_dir = themes.get("mine")
    assert json.loads((theme_dir / "theme.json").read_text()) == {"#info": {"name": "Saved"}}
    assert (theme_dir / "theme.json.bak").read_text() == file['text']
    assert answer == {'ok': True, 'version': editor.read("mine")['version']}
    assert not (theme_dir / "theme.json.tmp").exists()


def test_save_unchanged_keeps_the_backup(editor, themes):
    file = editor.read("mine")
    editor.save("mine", file['text'], file['version'])
    assert not (themes.get("mine") / "theme.json.bak").exists()


def test_save_changed_on_disk(editor, themes):
    file = editor.read("mine")
    (themes.get("mine") / "theme.json").write_text('{"#info": {"name": "Theirs"}}')

    with pytest.raises(theme_editor.EditorError) as error:
        editor.save("mine", '{"#info": {"name": "Mine"}}', file['version'])

    assert error.value.status == 409
    assert error.value.extra['text'] == '{"#info": {"name": "Theirs"}}'
    ## Saved over theirs, given the version they have now.
    editor.save("mine", '{"a": 1}', error.value.extra['version'])
    assert (themes.get("mine") / "theme.json.bak").read_text() == '{"#info": {"name": "Theirs"}}'


@pytest.mark.parametrize("text, status", [("{ nope", 400), ("[1]", 400), ("{}" + " " * theme_editor.MAX_THEME_SIZE, 413)])
def test_save_refuses(editor, themes, text, status):
    file = editor.read("mine")
    with pytest.raises(theme_editor.EditorError) as error:
        editor.save("mine", text, file['version'])
    assert error.value.status == status
    assert (themes.get("mine") / "theme.json").read_text() == file['text']


def test_save_read_only_file(editor, themes):
    os.chmod(str(themes.get("mine") / "theme.json"), 0o444)
    try:
        if os.access(str(themes.get("mine") / "theme.json"), os.W_OK):
            pytest.skip("running as root")
        assert not editor.read("mine")['writable']
    finally:
        os.chmod(str(themes.get("mine") / "theme.json"), 0o644)


def test_single_theme_folder(tmp_path):
    ## --themes naming one theme: it can be changed, but there's no folder to copy into.
    (tmp_path / "solo").mkdir()
    (tmp_path / "solo" / "theme.json").write_text("{}")
    editor = theme_editor.ThemeEditor(serve.Themes(tmp_path / "solo"), tmp_path / "work", serve.DEFAULT_THEME_DIR)

    file = editor.read("solo")
    assert file['writable'] and not file['can_copy']
    with pytest.raises(theme_editor.EditorError) as error:
        editor.copy("solo", "Other")
    assert error.value.status == 403


def test_no_themes_folder(tmp_path):
    editor = theme_editor.ThemeEditor(serve.Themes(None), tmp_path / "work", serve.DEFAULT_THEME_DIR)
    file = editor.read("default_theme")
    assert not file['writable'] and not file['can_copy']


################################################################################
## Drafts
def test_draft(editor, themes):
    answer = editor.draft("mine", '{"#info": {"name": "Draft"}}')

    assert answer == {'ok': True, 'theme': "mine~draft"}
    draft_dir = themes.get("mine~draft")
    assert json.loads((draft_dir / "theme.json").read_text()) == {"#info": {"name": "Draft"}}
    ## The rest of the theme is there, as links: the theme itself is untouched.
    assert (draft_dir / "images" / "bg.png").read_bytes() == b"png"
    assert (draft_dir / "font.ttf").is_symlink()
    assert json.loads((themes.get("mine") / "theme.json").read_text()) == {"#info": {"name": "Mine"}}
    ## Drafts aren't listed.
    assert "mine~draft" not in themes.all()


def test_draft_follows_the_theme(editor, themes):
    editor.draft("mine", "{}")
    (themes.get("mine") / "font.ttf").unlink()
    (themes.get("mine") / "new.png").write_bytes(b"new")

    editor.draft("mine", '{"a": 1}')

    draft_dir = themes.get("mine~draft")
    assert not os.path.lexists(str(draft_dir / "font.ttf"))
    assert (draft_dir / "new.png").read_bytes() == b"new"


def test_draft_version_changes_with_the_text(editor, themes):
    editor.draft("mine", '{"a": 1}')
    first = serve.version(themes.get("mine~draft"), "en_US")
    editor.draft("mine", '{"a": 1}')
    assert serve.version(themes.get("mine~draft"), "en_US") == first

    os.utime(str(themes.get("mine~draft") / "theme.json"), (1, 1))
    editor.draft("mine", '{"a": 2}')
    assert serve.version(themes.get("mine~draft"), "en_US") != first


def test_draft_of_the_default_theme(editor, themes):
    editor.draft("default_theme", '{"main_menu": {}}')
    draft_dir = themes.get("default_theme~draft")
    assert (draft_dir / "buttons.png").is_file()


@pytest.mark.parametrize("text", ["{ nope", "[]"])
def test_draft_bad_json(editor, text):
    with pytest.raises(theme_editor.EditorError) as error:
        editor.draft("mine", text)
    assert error.value.status == 400 and error.value.extra['line'] >= 1


################################################################################
## Copies
def test_copy(editor, themes):
    answer = editor.copy("mine", "My Copy")

    assert answer == {'ok': True, 'theme': "My_Copy"}
    copy_dir = themes.get("My_Copy")
    assert json.loads((copy_dir / "theme.json").read_text()) == {"#info": {"name": "My Copy"}}
    assert (copy_dir / "images" / "bg.png").read_bytes() == b"png"
    ## The layout of theme.json is kept.
    assert (copy_dir / "theme.json").read_text() == '{\n    "#info": {"name": "My Copy"}\n}\n'


def test_copy_with_changes(editor, themes):
    editor.copy("mine", "Changed", text='{"#info": {"name": "Mine"}, "main_menu": {}}')
    assert json.loads((themes.get("Changed") / "theme.json").read_text()) == {"#info": {"name": "Changed"}, "main_menu": {}}
    ## The original keeps its own.
    assert json.loads((themes.get("mine") / "theme.json").read_text()) == {"#info": {"name": "Mine"}}


def test_copy_the_default_theme(editor, themes):
    editor.copy("default_theme", "Mine Too")
    copy_dir = themes.get("Mine_Too")
    data = json.loads((copy_dir / "theme.json").read_text(encoding="utf-8"))
    assert data["#info"]["name"] == "Mine Too" and "main_menu" in data
    assert (copy_dir / "buttons.png").is_file()
    assert editor.read("Mine_Too")['writable']


def test_downloaded_theme(editor, themes):
    ## Downloaded from the theme list: the page says an update there replaces the changes.
    assert editor.read("mine")['downloaded'] is False
    (themes.get("mine") / "theme.md5").write_text("abc")
    assert editor.read("mine")['downloaded'] is True
    ## A copy is the user's own.
    editor.copy("mine", "Own")
    assert not (themes.get("Own") / "theme.md5").exists() and editor.read("Own")['downloaded'] is False


def test_copy_leaves_backups_behind(editor, themes):
    file = editor.read("mine")
    editor.save("mine", '{"a": 1}', file['version'])
    editor.copy("mine", "Clean")
    assert not (themes.get("Clean") / "theme.json.bak").exists()


@pytest.mark.parametrize("name, status", [
    ("mine", 409), ("Mine Theme", 200), ("", 400), ("   ", 400), ("../evil", 400), ("a/b", 400),
    (".hidden", 400), ("x" * 49, 400), (5, 400), (None, 400), ("default_theme", 409), ("x~draft", 400),
    ])
def test_copy_names(editor, name, status):
    try:
        editor.copy("mine", name)
        assert status == 200
    except theme_editor.EditorError as error:
        assert error.status == status


def test_copy_with_bad_text(editor, themes):
    with pytest.raises(theme_editor.EditorError) as error:
        editor.copy("mine", "Bad", text="{ nope")
    assert error.value.status == 400
    assert themes.get("Bad") is None
