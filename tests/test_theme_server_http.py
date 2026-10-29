# SPDX-License-Identifier: MIT
#
# The theme server without renderers: its web API (pylibs/theme_server/serve.py's Handler)
# against a fake render pool, the themes it lists and their versions, the translation
# saves, the languages, and --export. No SDL: test_theme_server.py renders for real.

import json
import os
import shutil
import threading
import time
import urllib.error
import urllib.request

import pytest

from conftest import PM_DIR

from theme_server import serve


class FakePool:
    """What the Handler uses of a RenderPool: render(), status(), translations."""
    def __init__(self):
        self.calls = []
        self.missing = None
        self.error = None
        self.translations = serve.Translations()

    def render(self, theme_id, scheme, resolution, lang, shot):
        self.calls.append((theme_id, scheme, resolution, lang, shot))
        if self.error:
            raise serve.WorkerError(self.error)
        if self.missing:
            return None, {'missing': self.missing, 'errors': []}
        return b"\x89PNG fake", {'shot': shot, 'theme': theme_id, 'resolution': resolution, 'errors': []}

    def status(self):
        return {'starting': [], 'loading': [], 'rendering': [], 'running': ["640x480"]}

    def shots(self):
        return [["main_menu", "Main menu"], ["options", "Options"]]


@pytest.fixture
def locales(tmp_path, monkeypatch):
    locales = tmp_path / "locales"
    shutil.copytree(str(PM_DIR / "pylibs" / "locales"), str(locales))
    monkeypatch.setattr(serve.i18n_tool, "LOCALES_DIR", locales)
    return locales


@pytest.fixture
def themes_dir(tmp_path):
    themes = tmp_path / "themes"
    (themes / "good").mkdir(parents=True)
    (themes / "good" / "theme.json").write_text(json.dumps({
        "#info": {"name": "Good Theme", "creator": "me", "default-scheme": "Dark"},
        "#schemes": {"#base": {}, "Light": {}, "Dark": {}},
        }))
    (themes / "broken").mkdir()
    (themes / "broken" / "theme.json").write_text("{ not json")
    (themes / "not_a_theme").mkdir()
    return themes


@pytest.fixture
def server(locales, themes_dir):
    """(base url, the fake pool) of a server on a free local port."""
    pool = FakePool()
    server = serve.Server(("127.0.0.1", 0), serve.Handler)
    server.themes, server.pool, server.shots, server.verbose = serve.Themes(themes_dir), pool, pool.shots(), False
    server.editor = serve.ThemeEditor(server.themes, themes_dir.parent / "work", serve.DEFAULT_THEME_DIR)
    ## (Polled often, so shutting it down after each test is quick.)
    threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", pool
    server.shutdown()
    server.server_close()


def get(base, path):
    try:
        with urllib.request.urlopen(base + path, timeout=30) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as error:
        return error.code, error.read(), dict(error.headers)


def post(base, path, body=None, headers=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(base + path, data=data, method="POST", headers=headers if headers is not None else {
        "Content-Type": "application/json", "X-Theme-Server": "1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


################################################################################
## Pages and info
@pytest.mark.parametrize("path", ["/", "/index.html"])
def test_page(server, path):
    status, body, headers = get(server[0], path)
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    assert b"<html" in body.lower()


@pytest.mark.parametrize("path", ["/nope", "/static/../serve.py", "/api", "/api/render", "/../../etc/passwd"])
def test_not_found(server, path):
    assert get(server[0], path)[0] == 404


def test_info(server):
    status, body, _ = get(server[0], "/api/info")
    info = json.loads(body)

    assert status == 200
    themes = {theme['id']: theme for theme in info['themes']}
    assert list(themes) == ["default_theme", "broken", "good"]
    assert themes["good"]["name"] == "Good Theme" and themes["good"]["default_scheme"] == "Dark"
    assert themes["good"]["schemes"] == ["Light", "Dark"]
    assert themes["broken"]["error"] and themes["broken"]["schemes"] == []
    assert info['resolutions'] == list(serve.RESOLUTIONS)
    assert info['shots'] == FakePool().shots()
    assert ["de_DE", "German"] in info['languages']


def test_status(server):
    status, body, headers = get(server[0], "/api/status")
    assert status == 200 and json.loads(body)['running'] == ["640x480"]
    assert headers["Cache-Control"] == "no-store"


################################################################################
## Renders
def test_render_defaults(server):
    base, pool = server
    status, body, headers = get(base, "/api/render.png")

    assert status == 200 and body == b"\x89PNG fake" and headers["Content-Type"] == "image/png"
    assert pool.calls == [("default_theme", None, "640x480", "en_US", "main_menu")]
    ## No version in the URL: not cached.
    assert headers["Cache-Control"] == "no-store"


def test_render_parameters(server):
    base, pool = server
    status, _, headers = get(base, "/api/render.png?theme=good&scheme=Dark&res=1280x720&lang=de_DE&shot=options&v=abc")

    assert status == 200
    assert pool.calls[-1] == ("good", "Dark", "1280x720", "de_DE", "options")
    ## The URL carries the version: cacheable.
    assert headers["Cache-Control"] == "max-age=3600"


def test_render_json(server):
    base, pool = server
    status, body, headers = get(base, "/api/render.json?shot=options")
    assert status == 200 and json.loads(body)['shot'] == "options" and headers["Content-Type"] == "application/json"


def test_render_missing_section(server):
    base, pool = server
    pool.missing = "this theme has no options section"
    status, body, _ = get(base, "/api/render.png?shot=options")
    assert status == 404 and json.loads(body)['error'] == pool.missing


def test_render_worker_error(server):
    base, pool = server
    pool.error = "the renderer died"
    status, body, _ = get(base, "/api/render.png")
    assert status == 500 and json.loads(body)['error'] == "the renderer died"


@pytest.mark.parametrize("query", [
    "res=99999x10", "res=640", "res=0x0", "res=abc", "res=640x480x2",
    "lang=de", "lang=../xx", "lang=de_de", "lang=%C3%A9%C3%A9_%C3%A9%C3%A9", "lang=de_DE_x",
    "shot=nope", "shot=../main_menu",
    ])
def test_render_bad_parameters(server, query):
    base, pool = server
    assert get(base, "/api/render.png?" + query)[0] == 400
    assert pool.calls == []


@pytest.mark.parametrize("theme", ["nope", "../good", "not_a_theme", "default_theme/.."])
def test_render_unknown_theme(server, theme):
    base, pool = server
    assert get(base, "/api/render.png?theme=" + theme)[0] == 404
    assert pool.calls == []


################################################################################
## Versions: what a render depends on
def test_version(server, themes_dir):
    base, _ = server
    status, body, _ = get(base, "/api/version?theme=good&lang=de_DE")
    first = json.loads(body)['version']
    assert status == 200 and len(first) == 12

    ## Saving the theme changes it.
    time.sleep(0.01)
    (themes_dir / "good" / "theme.json").write_text((themes_dir / "good" / "theme.json").read_text() + " ")
    assert json.loads(get(base, "/api/version?theme=good&lang=de_DE")[1])['version'] != first


def test_version_changes_with_the_translations(server, locales):
    base, _ = server
    before = json.loads(get(base, "/api/version?theme=default_theme&lang=de_DE")[1])['version']
    status, _ = post(base, "/api/translate", {'lang': "de_DE", 'domain': "messages", 'text': "Options", 'translation': "Einstellungen"})
    after = json.loads(get(base, "/api/version?theme=default_theme&lang=de_DE")[1])['version']
    other = json.loads(get(base, "/api/version?theme=default_theme&lang=fr_FR")[1])['version']

    assert status == 200 and before != after
    ## Other languages' renders don't depend on it.
    assert other == json.loads(get(base, "/api/version?theme=default_theme&lang=fr_FR")[1])['version']


@pytest.mark.parametrize("query, code", [("theme=nope", 404), ("theme=good&lang=xx", 400), ("", 404)])
def test_version_bad(server, query, code):
    assert get(server[0], "/api/version?" + query)[0] == code


################################################################################
## Translations
def test_strings(server):
    status, body, _ = get(server[0], "/api/strings?lang=de_DE")
    data = json.loads(body)

    assert status == 200 and data['lang'] == "de_DE"
    entries = {entry['text']: entry for entry in data['domains']['messages']}
    assert entries["Options"]['translation'] == "Optionen" and entries["Options"]['sources']
    assert all(entry['problems'] == [] for entry in entries.values())
    assert "{port_links.name}\n{port_links.url}" in {entry['text'] for entry in data['domains']['themes']}


@pytest.mark.parametrize("query", ["", "lang=de", "lang=../de_DE", "lang=de_DE%00"])
def test_strings_bad_language(server, query):
    assert get(server[0], "/api/strings?" + query)[0] == 400


def test_new_language_has_every_string_untranslated(server):
    entries = json.loads(get(server[0], "/api/strings?lang=da_DK")[1])['domains']['messages']
    assert entries and all(entry['translation'] == "" for entry in entries)


def test_save_and_remove(server, locales):
    base, _ = server
    body = {'lang': "de_DE", 'domain': "messages", 'text': "Options", 'translation': "Einstellungen"}

    assert post(base, "/api/translate", body) == (200, {'ok': True, 'problems': []})
    assert json.loads((locales / "de_DE.json").read_text(encoding="utf-8"))["Options"] == "Einstellungen"

    ## Problems come back with the save.
    status, answer = post(base, "/api/translate", dict(body, text="Music: ", translation="Musik:"))
    assert status == 200 and answer['problems'] == ["English ends with a space, this doesn't"]

    ## "" removes it.
    post(base, "/api/translate", dict(body, translation=""))
    assert "Options" not in json.loads((locales / "de_DE.json").read_text(encoding="utf-8"))


def test_save_a_theme_string(server, locales):
    base, _ = server
    text = "{system.free_space} free"
    assert post(base, "/api/translate", {'lang': "de_DE", 'domain': "themes", 'text': text, 'translation': "{system.free_space} übrig"})[0] == 200
    assert json.loads((locales / "de_DE.themes.json").read_text(encoding="utf-8"))[text] == "{system.free_space} übrig"


def test_saves_at_once_all_land(server, locales):
    ## The page saves as you type, several at once: the lock keeps them all.
    base, _ = server
    texts = ["Options", "Back", "Select", "Install", "Uninstall", "Exit", "Quit", "Filters", "Links", "Warning"]
    threads = [threading.Thread(target=post, args=(base, "/api/translate", {
        'lang': "nl_NL", 'domain': "messages", 'text': text, 'translation': f"T-{text}"})) for text in texts]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    saved = json.loads((locales / "nl_NL.json").read_text(encoding="utf-8"))
    assert {text: saved[text] for text in texts} == {text: f"T-{text}" for text in texts}


@pytest.mark.parametrize("body, code", [
    ({'lang': "de_DE", 'domain': "messages", 'text': "Options", 'translation': "{x}"}, 400),
    ({'lang': "de_DE", 'domain': "messages", 'text': "Options", 'translation': "Opt {"}, 400),
    ({'lang': "en_US", 'domain': "messages", 'text': "Options", 'translation': "x"}, 400),
    ({'lang': "de_DE", 'domain': "nope", 'text': "Options", 'translation': "x"}, 400),
    ({'lang': "de_DE", 'domain': "messages", 'text': 5, 'translation': "x"}, 400),
    ({'lang': "de_DE", 'domain': "messages", 'text': "Options", 'translation': None}, 400),
    ({'lang': "de_DE", 'domain': "messages", 'text': "Not a PortMaster string", 'translation': "x"}, 404),
    ([1, 2], 400),
    ("text", 400),
    ])
def test_save_refused(server, locales, body, code):
    before = (locales / "de_DE.json").read_text(encoding="utf-8")
    assert post(server[0], "/api/translate", body)[0] == code
    assert (locales / "de_DE.json").read_text(encoding="utf-8") == before


@pytest.mark.parametrize("headers", [
    {"Content-Type": "application/json"},
    {"Content-Type": "text/plain", "X-Theme-Server": "1"},
    {"Content-Type": "application/x-www-form-urlencoded", "X-Theme-Server": "1"},
    {"Content-Type": "application/json", "X-Theme-Server": "0"},
    {"Content-Type": "application/json", "X-Theme-Server": "1", "Host": "rebound.example.com"},
    ])
def test_save_forbidden(server, headers):
    body = {'lang': "de_DE", 'domain': "messages", 'text': "Options", 'translation': "x"}
    assert post(server[0], "/api/translate", body, headers)[0] == 403


@pytest.mark.parametrize("raw", [b"", b"{ not json", b"\xff\xfe\x00", b"x" * (256 * 1024 + 1)])
def test_save_bad_bodies(server, raw):
    assert post(server[0], "/api/translate", raw=raw)[0] == 400


def test_post_elsewhere(server):
    assert post(server[0], "/api/nope", {})[0] == 404


################################################################################
## Themes and languages
def test_themes_folder_of_themes(themes_dir):
    themes = serve.Themes(themes_dir)
    assert list(themes.all()) == ["default_theme", "broken", "good"]
    assert themes.get("good") == (themes_dir / "good").resolve() and themes.get("nope") is None


def test_themes_one_theme(themes_dir):
    ## --themes can be a theme folder itself.
    assert list(serve.Themes(themes_dir / "good").all()) == ["default_theme", "good"]


def test_themes_none_or_missing(tmp_path):
    assert list(serve.Themes(None).all()) == ["default_theme"]
    assert list(serve.Themes(tmp_path / "missing").all()) == ["default_theme"]


@pytest.mark.parametrize("data, expected", [
    ({}, {'name': "t", 'schemes': [], 'default_scheme': None}),
    ({"#info": {"name": "Mine"}, "#schemes": {"A": {}, "B": {}}}, {'name': "Mine", 'schemes': ["A", "B"], 'default_scheme': "A"}),
    ({"#info": {"default-scheme": "Nope"}, "#schemes": {"A": {}}}, {'name': "t", 'schemes': ["A"], 'default_scheme': "A"}),
    ({"#schemes": {"#base": {}}}, {'name': "t", 'schemes': [], 'default_scheme': None}),
    ])
def test_theme_info(tmp_path, data, expected):
    (tmp_path / "theme.json").write_text(json.dumps(data))
    info = serve.Themes(None).info("t", tmp_path)
    assert {key: info[key] for key in expected} == expected and info['error'] is None


def test_theme_info_unreadable(tmp_path):
    info = serve.Themes(None).info("t", tmp_path / "missing")
    assert info['error'] and info['schemes'] == []


def test_fingerprint(tmp_path):
    (tmp_path / "theme.json").write_text("{}")
    first = serve.Themes.fingerprint(tmp_path)

    assert serve.Themes.fingerprint(tmp_path) == first
    (tmp_path / "image.png").write_bytes(b"x")
    second = serve.Themes.fingerprint(tmp_path)
    assert second != first
    (tmp_path / "image.png").unlink()
    assert serve.Themes.fingerprint(tmp_path) == first
    ## An extra file that isn't there is left out, not an error.
    assert serve.Themes.fingerprint(tmp_path, [tmp_path / "nope.json"]) == first


def test_languages():
    codes = dict(serve.languages())
    files = {path.name[:-5] for path in (PM_DIR / "pylibs" / "locales").glob("??_??.json")}

    assert set(codes) == files | {"en_US"}
    assert codes["de_DE"] == "German" and codes["zh_CN"] == "Chinese Simplified"


def test_all_languages():
    languages = {code: (name, has) for code, name, has in serve.all_languages()}
    assert languages["de_DE"] == ("German", True)
    ## Ones PortMaster has a name for but no translation yet: offered as new.
    assert languages["da_DK"] == ("Danish", False) and languages["fi_FI"] == ("Finnish", False)


@pytest.mark.parametrize("text, valid", [
    ("640x480", True), ("4096x4096", True), ("10x10", True), ("4097x10", False), ("0x480", False),
    ("640x0", False), ("1x1", False), ("640X480", False), (" 640x480", False), ("640x480 ", False),
    ("", False), (None, False), ("12345x12", False)])
def test_valid_resolution(text, valid):
    assert serve.valid_resolution(text) is valid


def test_default_cache(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    assert serve.default_cache() == tmp_path / "portmaster-theme-server"
    monkeypatch.delenv("XDG_CACHE_HOME")
    assert serve.default_cache().name == "portmaster-theme-server"


################################################################################
## --export
def test_export(tmp_path, capsys):
    pool = FakePool()
    themes = serve.Themes(None)

    code = serve.export(pool, themes, tmp_path / "out", ["default_theme"], ["640x480", "480x320"], [], ["en_US", "de_DE"], pool.shots())

    assert code == 0
    folder = tmp_path / "out" / "default_theme" / "640x480" / "Light Mode" / "de_DE"
    assert (folder / "main_menu.png").read_bytes() == b"\x89PNG fake"
    assert json.loads((folder / "options.json").read_text())['shot'] == "options"
    ## Every theme x size x scheme x language: the theme's default scheme only, unless asked.
    assert len(pool.calls) == 2 * 2 * 2


def test_export_all_schemes(tmp_path):
    pool = FakePool()
    serve.export(pool, serve.Themes(None), tmp_path / "out", ["default_theme"], ["640x480"], ["all"], ["en_US"], pool.shots())
    schemes = {call[1] for call in pool.calls}
    assert {"Light Mode", "Dark Mode", "Dracula"} <= schemes


def test_export_failures(tmp_path, capsys):
    pool = FakePool()
    pool.error = "it broke"

    assert serve.export(pool, serve.Themes(None), tmp_path / "out", ["default_theme"], ["640x480"], [], ["en_US"], pool.shots()) == 1
    assert "FAIL default_theme 640x480" in capsys.readouterr().err


def test_export_missing_section(tmp_path):
    pool = FakePool()
    pool.missing = "no section"

    assert serve.export(pool, serve.Themes(None), tmp_path / "out", ["default_theme"], ["640x480"], [], ["en_US"], pool.shots()) == 0
    folder = tmp_path / "out" / "default_theme" / "640x480" / "Light Mode" / "en_US"
    assert not (folder / "main_menu.png").exists() and (folder / "main_menu.json").is_file()


################################################################################
## The Edit view
@pytest.mark.parametrize("path, content_type, cached", [
    ("/static/codemirror.js", "text/javascript", True),
    ("/static/codemirror.css", "text/css", True),
    ("/static/editor.js", "text/javascript", False),
    ])
def test_static_files(server, path, content_type, cached):
    status, body, headers = get(server[0], path)
    assert status == 200 and headers["Content-Type"].startswith(content_type) and len(body) > 1000
    assert ("max-age" in headers["Cache-Control"]) == cached


@pytest.mark.parametrize("path", ["/static/", "/static/index.html", "/static/codemirror/LICENSE", "/static/codemirror/codemirror.js", "/static/../editor.py"])
def test_static_only_the_listed_files(server, path):
    assert get(server[0], path)[0] == 404


def test_page_loads_the_editor(server):
    body = get(server[0], "/")[1].decode()
    assert '<script src="/static/editor.js">' in body and 'data-view="edit"' in body
    ## Everything the page asks for is served.
    for path in serve.STATIC_FILES:
        assert (serve.HERE / "static" / serve.STATIC_FILES[path][0]).is_file()


def test_codemirror_licence():
    folder = serve.HERE / "static" / "codemirror"
    assert "MIT License" in (folder / "LICENSE").read_text()
    for name in ("codemirror.js", "codemirror.css"):
        assert "MIT License, see LICENSE" in (folder / name).read_text(encoding="utf-8")[:300]


def test_schema(server):
    status, body, _ = get(server[0], "/api/schema?theme=good")
    data = json.loads(body)
    assert status == 200 and data['keys']['font-size'] == {'type': "int"}
    assert data['names']['schemes'] == ["Light", "Dark"]
    assert get(server[0], "/api/schema?theme=nope")[0] == 404


def test_theme_file(server, themes_dir):
    status, body, _ = get(server[0], "/api/theme_file?theme=good")
    file = json.loads(body)
    assert status == 200 and file['text'] == (themes_dir / "good" / "theme.json").read_text()
    assert file['writable'] and file['can_copy']
    assert json.loads(get(server[0], "/api/theme_file?theme=default_theme")[1])['writable'] is False
    assert get(server[0], "/api/theme_file?theme=nope")[0] == 404
    assert get(server[0], "/api/theme_file")[0] == 404


def test_save_theme_file(server, themes_dir):
    version = json.loads(get(server[0], "/api/theme_file?theme=good")[1])['version']

    status, answer = post(server[0], "/api/theme_file", {'theme': "good", 'text': '{"#info": {"name": "New"}}', 'version': version})

    assert status == 200 and answer['ok']
    assert json.loads((themes_dir / "good" / "theme.json").read_text()) == {"#info": {"name": "New"}}
    assert (themes_dir / "good" / "theme.json.bak").is_file()
    ## The version it sent is old now.
    status, answer = post(server[0], "/api/theme_file", {'theme': "good", 'text': "{}", 'version': version})
    assert status == 409 and answer['text'] == '{"#info": {"name": "New"}}' and answer['version'] != version


@pytest.mark.parametrize("body, status", [
    ({'theme': "good", 'text': "{ nope", 'version': "x"}, 400),
    ({'theme': "good", 'text': 5, 'version': "x"}, 400),
    ({'theme': "good", 'text': "{}"}, 400),
    ({'theme': "default_theme", 'text': "{}", 'version': "x"}, 403),
    ({'theme': "nope", 'text': "{}", 'version': "x"}, 404),
    ({'theme': ["good"], 'text': "{}", 'version': "x"}, 404),
    ])
def test_save_theme_file_refused(server, themes_dir, body, status):
    before = (themes_dir / "good" / "theme.json").read_text()
    assert post(server[0], "/api/theme_file", body)[0] == status
    assert (themes_dir / "good" / "theme.json").read_text() == before


def test_save_theme_file_syntax_error_says_where(server):
    version = json.loads(get(server[0], "/api/theme_file?theme=good")[1])['version']
    status, answer = post(server[0], "/api/theme_file", {'theme': "good", 'text': '{\n  "a": 1\n  "b": 2\n}', 'version': version})
    assert status == 400 and answer['line'] == 3 and answer['column'] == 3 and "valid JSON" in answer['error']


@pytest.mark.parametrize("path", ["/api/theme_file", "/api/theme_draft", "/api/theme_copy"])
def test_editor_posts_need_the_page(server, path):
    ## Without the header (another site's page): refused before anything is read.
    body = {'theme': "good", 'text': "{}", 'version': "x", 'name': "Evil"}
    assert post(server[0], path, body, headers={"Content-Type": "application/json"})[0] == 403
    assert post(server[0], path, body, headers={"Content-Type": "text/plain", "X-Theme-Server": "1"})[0] == 403


def test_draft_renders(server, themes_dir):
    base, pool = server
    status, answer = post(base, "/api/theme_draft", {'theme': "good", 'text': '{"#info": {"name": "Draft"}}'})
    assert status == 200 and answer['theme'] == "good~draft"

    status, body, _ = get(base, "/api/render.json?theme=good~draft&shot=main_menu")
    assert status == 200 and pool.calls[-1][0] == "good~draft"
    assert json.loads(get(base, "/api/version?theme=good~draft")[1])['version']
    ## Not listed, and the theme itself is as it was.
    assert "good~draft" not in [theme['id'] for theme in json.loads(get(base, "/api/info")[1])['themes']]
    assert "Draft" not in (themes_dir / "good" / "theme.json").read_text()


@pytest.mark.parametrize("body", [{'theme': "good", 'text': "["}, {'theme': "good"}, {'theme': "nope", 'text': "{}"}, {'theme': "good~draft", 'text': "{}"}])
def test_draft_refused(server, body):
    assert post(server[0], "/api/theme_draft", body)[0] in (400, 404)


def test_big_theme_file(server, themes_dir):
    ## Bigger than a translation may be, as theme.json files are.
    version = json.loads(get(server[0], "/api/theme_file?theme=good")[1])['version']
    text = json.dumps({"main_menu": {f"region_{n}": {"text": "x" * 100} for n in range(3000)}})
    assert len(text) > 256 * 1024
    assert post(server[0], "/api/theme_file", {'theme': "good", 'text': text, 'version': version})[0] == 200


def test_copy_theme(server, themes_dir):
    status, answer = post(server[0], "/api/theme_copy", {'theme': "good", 'name': "Good Copy"})

    assert status == 200 and answer['theme'] == "Good_Copy"
    assert json.loads((themes_dir / "Good_Copy" / "theme.json").read_text())["#info"]["name"] == "Good Copy"
    assert "Good_Copy" in [theme['id'] for theme in json.loads(get(server[0], "/api/info")[1])['themes']]

    status, answer = post(server[0], "/api/theme_copy", {'theme': "good", 'name': "Good Copy"})
    assert status == 409


def test_copy_theme_with_changes(server, themes_dir):
    status, answer = post(server[0], "/api/theme_copy", {'theme': "default_theme", 'name': "Mine", 'text': '{"#info": {"name": "x"}, "main_menu": {}}'})
    assert status == 200
    assert json.loads((themes_dir / "Mine" / "theme.json").read_text()) == {"#info": {"name": "Mine"}, "main_menu": {}}


################################################################################
## Stopping while a renderer starts
class SlowZygote:
    """A zygote that takes `delay` seconds to start, and says when it was stopped."""
    delay = 0.5
    made = []

    def __init__(self, ports_config, work):
        time.sleep(self.delay)
        self.stopped = False
        SlowZygote.made.append(self)

    def alive(self):
        return not self.stopped

    def stop(self):
        self.stopped = True


class FakeWorker:
    made = []

    def __init__(self, *args, **kwargs):
        self.stopped = False
        FakeWorker.made.append(self)

    def alive(self):
        return not self.stopped

    def stop(self):
        self.stopped = True


@pytest.fixture
def slow_pool(tmp_path, themes_dir, monkeypatch):
    SlowZygote.made, FakeWorker.made = [], []
    monkeypatch.setattr(serve, "Zygote", SlowZygote)
    monkeypatch.setattr(serve, "Worker", FakeWorker)
    return serve.RenderPool(serve.Themes(themes_dir), tmp_path / "config", tmp_path / "work")


def test_stop_waits_for_a_start(slow_pool):
    ## warm() is still starting the first renderer when PortMaster stops the server: stop()
    ## waits for it and stops what it started, or it would carry on in the removed folder.
    warm = threading.Thread(target=slow_pool.warm)
    warm.start()
    time.sleep(0.1)

    slow_pool.stop()
    warm.join()

    assert len(SlowZygote.made) == 1 and SlowZygote.made[0].stopped
    assert len(FakeWorker.made) == 1 and FakeWorker.made[0].stopped
    assert slow_pool.workers == {} and slow_pool.zygote is None


def test_nothing_starts_after_stop(slow_pool):
    slow_pool.stop()
    with pytest.raises(serve.WorkerError):
        slow_pool.warm()
    assert SlowZygote.made == [] and FakeWorker.made == []


def test_stop_gives_up_waiting(slow_pool, monkeypatch):
    ## A start that never ends: stop() still returns (PortMaster kills the server at 15 s).
    monkeypatch.setattr(SlowZygote, "delay", 3)
    warm = threading.Thread(target=slow_pool.warm, daemon=True)
    warm.start()
    time.sleep(0.1)

    began = time.monotonic()
    slow_pool.stop(start_timeout=0.3)
    assert time.monotonic() - began < 2


def test_renderer_folders_need_the_servers(tmp_path):
    ## A renderer starting after serve.py removed its folder fails, rather than making it again.
    from theme_server import worker

    gone = tmp_path / "pm-theme-server-x" / "zygote"
    with pytest.raises(FileNotFoundError):
        worker.prepare_tools_dir(gone, tmp_path / "config", serve.DEFAULT_THEME_DIR, None)
    assert not (tmp_path / "pm-theme-server-x").exists()
