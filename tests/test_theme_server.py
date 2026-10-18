# SPDX-License-Identifier: MIT
#
# tools/theme_server: the theme dev server. Its renderer (worker.py, a headless pugwash)
# draws every screen of a theme; serve.py runs renderers, serves the page and exports.
# These use an empty ports cache, so no network.

import json
import sys
import threading
import urllib.error
import urllib.request

import pytest

from conftest import PM_DIR, REPO_DIR

sys.path.insert(0, str(REPO_DIR / "tools" / "theme_server"))
import serve  # noqa: E402
import worker  # noqa: E402


DEFAULT_THEME = PM_DIR / "pylibs" / "default_theme"

## The renderers rely on harbourmaster's testing mode (windowed, PM_PRETEND_RESOLUTION),
## which needs a git checkout: not the Test Suite's copy on a device.
needs_checkout = pytest.mark.skipif(not (REPO_DIR / ".git").exists(), reason="the theme server runs from a git checkout")


@pytest.mark.parametrize("size, expected, absent", [
    ((640, 480), {"640x480", "4:3"}, {"hires", "lowres", "wide", "square"}),
    ((1280, 720), {"1280x720", "16:9", "hires", "wide"}, {"lowres", "square"}),
    ((720, 720), {"720x720", "1:1", "hires", "square"}, {"wide"}),
    ((480, 320), {"480x320", "3:2", "lowres", "wide"}, {"hires"}),
    ((1280, 800), {"1280x800", "16:10", "16:9", "hires", "wide"}, set()),
    ((720, 480), {"720x480", "3:2", "wide"}, {"hires", "lowres"}),
    ])
def test_screen_capabilities_match_device_info(size, expected, absent):
    ## The same rules as device_info.txt, so a theme's [hires] / [4:3] overrides apply.
    caps = set(worker.screen_capabilities(*size))
    assert expected <= caps and not (absent & caps)


def test_prepare_tools_dir(tmp_path):
    cache_config = tmp_path / "cache" / "tools" / "PortMaster" / "config"
    (cache_config / "images_pm").mkdir(parents=True)
    (cache_config / "020_portmaster.source.json").write_text("{}")
    (cache_config / "config.json").write_text(json.dumps({'version': 2, 'theme': "other"}))
    theme = tmp_path / "My Theme"
    theme.mkdir()
    (theme / "theme.json").write_text("{}")

    work = tmp_path / "work"
    assert worker.prepare_tools_dir(work, tmp_path / "cache", theme, "Dark") == "My Theme"
    config = work / "tools" / "PortMaster" / "config"
    ## The cache is linked, not copied; config.json is the renderer's own, with the cache's
    ## version (else harbourmaster "upgrades" it by deleting the image folders).
    assert (config / "images_pm").is_symlink() and (config / "020_portmaster.source.json").is_symlink()
    cfg = json.loads((config / "config.json").read_text())
    assert (cfg['version'], cfg['theme'], cfg['theme-scheme'], cfg['disclaimer']) == (2, "My Theme", "Dark", True)
    assert (work / "tools" / "PortMaster" / "themes" / "My Theme").resolve() == theme.resolve()

    ## The built-in theme isn't linked, pugwash finds it by name.
    assert worker.prepare_tools_dir(work, tmp_path / "cache", DEFAULT_THEME, None) == "default_theme"
    assert not any((work / "tools" / "PortMaster" / "themes").iterdir())


def test_ensure_fonts(tmp_path, monkeypatch):
    ## A fresh checkout has only NotoSans.tar.xz: the PortMaster/pugwash script unpacks
    ## it, and the workers don't run that script.
    import io
    import tarfile

    resources = tmp_path / "pylibs" / "resources"
    resources.mkdir(parents=True)
    with tarfile.open(str(resources / "NotoSans.tar.xz"), "w:xz") as tar:
        for name in ("NotoSansJP-Regular.ttf", "NotoSansTC-Regular.ttf"):
            info = tarfile.TarInfo(name)
            info.size = 4
            tar.addfile(info, io.BytesIO(b"font"))

    monkeypatch.setattr(serve, "PM_DIR", tmp_path)
    serve.ensure_fonts()
    assert (resources / "NotoSansJP-Regular.ttf").read_bytes() == b"font"

    ## Unpacked already: left alone.
    (resources / "NotoSansJP-Regular.ttf").write_bytes(b"mine")
    serve.ensure_fonts()
    assert (resources / "NotoSansJP-Regular.ttf").read_bytes() == b"mine"


def test_themes(tmp_path):
    for name, data in (("Alpha", {"#info": {"name": "Alpha Theme"}, "#schemes": {"#base": {}, "Dark": {}, "Light": {}}}),
                       ("Beta", {"#info": {"name": "Beta", "default-scheme": "Light"}, "#schemes": {"Dark": {}, "Light": {}}})):
        (tmp_path / name).mkdir()
        (tmp_path / name / "theme.json").write_text(json.dumps(data))
    (tmp_path / "Broken").mkdir()
    (tmp_path / "Broken" / "theme.json").write_text("{ not json")
    (tmp_path / "not-a-theme").mkdir()

    themes = serve.Themes(tmp_path)
    assert list(themes.all()) == ["default_theme", "Alpha", "Beta", "Broken"]
    alpha = themes.info("Alpha", tmp_path / "Alpha")
    assert (alpha['name'], alpha['schemes'], alpha['default_scheme']) == ("Alpha Theme", ["Dark", "Light"], "Dark")
    assert themes.info("Beta", tmp_path / "Beta")['default_scheme'] == "Light"
    assert themes.info("Broken", tmp_path / "Broken")['error']

    ## A single theme folder works too.
    assert list(serve.Themes(tmp_path / "Alpha").all()) == ["default_theme", "Alpha"]

    ## The fingerprint changes when a file is saved or added.
    before = serve.Themes.fingerprint(tmp_path / "Alpha")
    assert serve.Themes.fingerprint(tmp_path / "Alpha") == before
    (tmp_path / "Alpha" / "image.png").write_bytes(b"x")
    assert serve.Themes.fingerprint(tmp_path / "Alpha") != before


def test_languages_and_resolutions():
    codes = dict(serve.languages())
    assert codes["en_US"] == "English" and "de_DE" in codes
    assert serve.valid_resolution("640x480") and serve.valid_resolution("1920x1152")
    for bad in ("640", "640x", "x480", "0x480", "640x480; rm", "99999x10", "../x"):
        assert not serve.valid_resolution(bad)


################################################################################
## Rendering: real renderers, an empty ports cache.
@pytest.fixture(scope="module")
def pool(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("theme_server")
    themes_dir = tmp / "themes"
    ## A theme with only the sections pugwash needs (it copies the rest from these): the
    ## other screens say what's missing.
    (themes_dir / "Tiny").mkdir(parents=True)
    tiny = json.loads((DEFAULT_THEME / "theme.json").read_text())
    tiny = {key: value for key, value in tiny.items() if key.startswith("#") or key in ("main_menu", "option_menu", "ports_list", "message_window")}
    (themes_dir / "Tiny" / "theme.json").write_text(json.dumps(tiny))

    themes = serve.Themes(themes_dir)
    pool = serve.RenderPool(themes, tmp / "cache", tmp / "work")
    try:
        pool.shots()
    except serve.WorkerError as error:
        pool.stop()
        pytest.skip(f"the renderer can't start here: {str(error).strip().splitlines()[-1]}")

    yield pool
    pool.stop()



@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
@pytest.mark.parametrize("resolution", ["640x480", "1280x720"])
def test_every_screen_renders(pool, resolution):
    for shot, _ in pool.shots():
        png, info = pool.render("default_theme", None, resolution, "en_US", shot)
        assert info['errors'] == [], (shot, info['errors'])
        if shot in ("port_info", "port_info_popup", "featured", "featured_list"):
            ## No ports or featured lists in an empty cache (and the default theme has no popup section).
            assert info['missing'] and png == b""
            continue

        assert png.startswith(b"\x89PNG"), shot
        assert info['regions'], shot
        width, height = (int(part) for part in resolution.split("x"))
        for region in info['regions']:
            x, y, w, h = region['rect']
            assert 0 <= x <= width and 0 <= y <= height, (shot, region['name'])
            assert region['section'] or region['scene'] == "EmptyScene"


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_png_size_and_caching(pool):
    import png as pypng

    png_bytes, info = pool.render("default_theme", "Dark Mode", "854x480", "de_DE", "main_menu")
    width, height, _, _ = pypng.Reader(bytes=png_bytes).read()
    assert (width, height) == (854, 480)
    assert info['scheme'] == "Dark Mode"
    ## Rendered once per theme version.
    assert pool.render("default_theme", "Dark Mode", "854x480", "de_DE", "main_menu")[0] is png_bytes


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_missing_sections_and_default_only_screens(pool):
    _, info = pool.render("Tiny", None, "640x480", "en_US", "main_menu")
    assert not info['missing'] and info['regions']
    _, info = pool.render("Tiny", None, "640x480", "en_US", "filters")
    assert info['missing'] == "this theme has no filter_list section"
    ## fifo_control (autoinstall, PortMasterDialog) always uses the default theme.
    _, info = pool.render("Tiny", None, "640x480", "en_US", "selection_list")
    assert "default theme" in info['missing']


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_a_saved_theme_gets_a_new_renderer(pool):
    theme_json = pool.themes.get("Tiny") / "theme.json"
    _, before = pool.render("Tiny", None, "640x480", "en_US", "main_menu")
    data = json.loads(theme_json.read_text())
    data["main_menu"]["#element:option_list"]["area"] = [0.0, 0.0, 0.5, 0.5]
    theme_json.write_text(json.dumps(data))
    _, after = pool.render("Tiny", None, "640x480", "en_US", "main_menu")

    assert after['version'] != before['version']
    rect = next(region['rect'] for region in after['regions'] if region['tag'] == "option_list")
    assert rect == [0, 0, 320, 240]
    ## The old renderer for those settings is gone.
    assert sum(1 for key in pool.workers if key[0] == "Tiny" and key[3] == "640x480") == 1


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_http_api(pool):
    server = serve.Server(("127.0.0.1", 0), serve.Handler)
    server.themes, server.pool, server.shots, server.verbose = pool.themes, pool, pool.shots(), False
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path):
        try:
            with urllib.request.urlopen(base + path, timeout=60) as response:
                return response.status, response.headers['Content-Type'], response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.headers['Content-Type'], error.read()

    try:
        status, kind, body = get("/")
        assert status == 200 and kind.startswith("text/html") and b"Theme Preview" in body

        status, _, body = get("/api/info")
        info = json.loads(body)
        assert [theme['id'] for theme in info['themes']] == ["default_theme", "Tiny"]
        assert ["main_menu", "Main menu"] in info['shots'] and "640x480" in info['resolutions']

        status, kind, body = get("/api/render.png?theme=default_theme&res=640x480&shot=options")
        assert status == 200 and kind == "image/png" and body.startswith(b"\x89PNG")
        status, _, body = get("/api/render.json?theme=default_theme&res=640x480&shot=options")
        assert json.loads(body)['regions']

        assert get("/api/render.png?theme=default_theme&res=640x480&shot=no_such_screen")[0] == 400
        assert get("/api/render.png?theme=default_theme&res=huge&shot=options")[0] == 400
        assert get("/api/render.png?theme=nope&res=640x480&shot=options")[0] == 500
        assert get("/api/render.png?theme=Tiny&res=640x480&shot=filters")[0] == 404
        assert json.loads(get("/api/version?theme=Tiny")[2])['version']
        assert get("/api/version?theme=nope")[0] == 404
        assert get("/etc/passwd")[0] == 404

    finally:
        server.shutdown()
        server.server_close()


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_export(pool, tmp_path):
    shots = [shot for shot in pool.shots() if shot[0] in ("main_menu", "filters")]
    assert serve.export(pool, pool.themes, tmp_path, ["Tiny"], ["640x480"], [], ["en_US"], shots) == 0
    ## <theme>/<resolution>/<scheme: the theme's default>/<language>
    folder = tmp_path / "Tiny" / "640x480" / pool.themes.info("Tiny", pool.themes.get("Tiny"))['default_scheme'] / "en_US"
    assert (folder / "main_menu.png").read_bytes().startswith(b"\x89PNG")
    assert json.loads((folder / "filters.json").read_text())['missing'] == "this theme has no filter_list section"
    assert not (folder / "filters.png").exists()


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_port_screens_with_port_data(online_hm, hm_dirs, tmp_path):
    ## online_hm saved tests/data/ports.json's ports into hm_dirs' config: a ports cache.
    cache = hm_dirs['tools_dir'].parent
    assert (cache / "tools" / "PortMaster" / "config" / "020_portmaster.source.json").is_file()
    pool = serve.RenderPool(serve.Themes(None), cache, tmp_path / "work")
    try:
        _, info = pool.render("default_theme", None, "640x480", "en_US", "port_info")
        assert not info['missing'] and not info['errors']
        title = next(region for region in info['regions'] if region['tag'] == "port_title")
        assert title['data']['text'] == "{port_info.title}"

        _, info = pool.render("default_theme", None, "640x480", "en_US", "ports_all")
        assert not info['errors'] and any(region['tag'] == "ports_list" for region in info['regions'])

    finally:
        pool.stop()


################################################################################
## The translation editor's side: which strings a screen uses, reading and saving.
@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_render_lists_the_strings_it_used(pool):
    _, info = pool.render("default_theme", None, "640x480", "de_DE", "options")
    assert "Select Theme" in info['strings']['messages']
    ## Only translatable ones: not templates like "{system.cfw_name}".
    known = serve.i18n_tool.read_strings()
    assert all(text in known['messages'] for text in info['strings']['messages'])
    assert all(text in known['themes'] for text in info['strings']['themes'])


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_language_capability_picks_the_font(pool):
    ## The default theme's "font[ja_JP]": the language reaches the theme's capabilities
    ## with a pretend resolution too.
    _, info = pool.render("default_theme", None, "1280x720", "ja_JP", "main_menu")
    fonts = {region['data'].get('font') for region in info['regions']}
    assert fonts == {"NotoSansJP-Regular.ttf"}


@pytest.fixture
def locales(tmp_path, monkeypatch):
    """The translation files, copied: saving writes there, not into the checkout."""
    import shutil as sh
    locales = tmp_path / "locales"
    sh.copytree(str(serve.i18n_tool.LOCALES_DIR), str(locales))
    monkeypatch.setattr(serve.i18n_tool, "LOCALES_DIR", locales)
    return locales


def test_translations_save(locales):
    translations = serve.Translations()
    entries = {entry['text']: entry for entry in translations.language("de_DE")['messages']}
    assert entries["Select Theme"]['translation'] and entries["Select Theme"]['sources']

    before = serve.version(serve.DEFAULT_THEME_DIR, "de_DE")
    assert translations.save("de_DE", "messages", "Select Theme", "Thema wählen") == []
    assert json.loads((locales / "de_DE.json").read_text(encoding="utf-8"))["Select Theme"] == "Thema wählen"
    ## The renders depend on it.
    assert serve.version(serve.DEFAULT_THEME_DIR, "de_DE") != before

    ## Kept in strings.json's order, so diffs stay small.
    order = list(json.loads((locales / "strings.json").read_text(encoding="utf-8")))
    saved = list(json.loads((locales / "de_DE.json").read_text(encoding="utf-8")))
    assert saved == [text for text in order if text in saved]

    ## Problems come back; "" removes a translation.
    assert translations.save("de_DE", "messages", "Music: ", "Musik:") == ["English ends with a space, this doesn't"]
    translations.save("de_DE", "messages", "Select Theme", "")
    assert "Select Theme" not in json.loads((locales / "de_DE.json").read_text(encoding="utf-8"))

    ## Only known strings; a new language gets both its files.
    with pytest.raises(KeyError):
        translations.save("de_DE", "messages", "Not a string PortMaster has", "x")
    translations.save("da_DK", "themes", next(iter(serve.i18n_tool.read_strings()['themes'])), "Dansk")
    assert (locales / "da_DK.json").is_file() and (locales / "da_DK.themes.json").is_file()


@pytest.mark.sdl
@pytest.mark.own_display
@needs_checkout
def test_translate_api(pool, locales):
    server = serve.Server(("127.0.0.1", 0), serve.Handler)
    server.themes, server.pool, server.shots, server.verbose = pool.themes, pool, pool.shots(), False
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def post(body, headers={"Content-Type": "application/json", "X-Theme-Server": "1"}):
        request = urllib.request.Request(base + "/api/translate", data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        with urllib.request.urlopen(base + "/api/strings?lang=de_DE", timeout=30) as response:
            data = json.loads(response.read())
        assert {entry['text'] for entry in data['domains']['messages']} >= {"Select Theme", "Options"}

        good = {'lang': "de_DE", 'domain': "messages", 'text': "Select Theme", 'translation': "Thema wählen"}
        ## Only from the page: another site's form or script can't send the header.
        assert post(good, {"Content-Type": "application/json"})[0] == 403
        assert post(good, {"Content-Type": "text/plain", "X-Theme-Server": "1"})[0] == 403
        assert post(dict(good, lang="en_US"))[0] == 400
        assert post(dict(good, lang="../x"))[0] == 400
        assert post(dict(good, domain="other"))[0] == 400
        assert post(dict(good, text="Nope"))[0] == 404
        status, body = post(good)
        assert status == 200 and body == {'ok': True, 'problems': []}
        assert json.loads((locales / "de_DE.json").read_text(encoding="utf-8"))["Select Theme"] == "Thema wählen"

        with urllib.request.urlopen(base + "/api/info", timeout=30) as response:
            names = {code: (name, has) for code, name, has in json.loads(response.read())['all_languages']}
        assert names["de_DE"] == ("German", True) and names["da_DK"] == ("Danish", False)

    finally:
        server.shutdown()
        server.server_close()
