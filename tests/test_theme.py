# SPDX-License-Identifier: MIT

import json

from types import SimpleNamespace

import pytest

from conftest import PYLIB_PATH


pytestmark = pytest.mark.sdl


@pytest.fixture(scope="module")
def pugtheme():
    from pugwash import theme as pugtheme
    return pugtheme


@pytest.mark.parametrize("text, expected", [
    ("element", ("element", [])),
    ("element[opengl]", ("element", ["opengl"])),
    ("element[opengl, !power]", ("element", ["opengl", "!power"])),
    ("element[a][b]", ("element_bad", [])),
    ("element[a", ("element_bad", [])),
    ])
def test_extract_requirements(pugtheme, text, expected):
    assert pugtheme.extract_requirements(text) == expected


def test_extract_requirements_strict(pugtheme):
    assert pugtheme.extract_requirements("element", strict=True) == ("element", None)


def test_theme_update_applies_requirements(pugtheme):
    ## Test device capabilities are "aarch64 640x480 power opengl".
    source = {
        "font": "base",
        "font[640x480]": "small",
        "font[1280x720]": "large",
        "colour[!opengl]": "never",
        "nested": {"a": 1, "list": [1, 2]},
        }

    result = pugtheme.theme_update({"nested": {"b": 2}}, source)

    assert result == {
        "font": "small",
        "nested": {"a": 1, "b": 2, "list": [1, 2]},
        }

    ## Lists are copied, not shared.
    assert result["nested"]["list"] is not source["nested"]["list"]


def test_theme_merge_does_not_modify_inputs(pugtheme):
    target = {"a": {"x": 1}}
    source = {"a": {"y": 2}}

    assert pugtheme.theme_merge(target, source) == {"a": {"x": 1, "y": 2}}
    assert target == {"a": {"x": 1}}


def test_default_theme(pugtheme):
    theme = pugtheme.Theme(PYLIB_PATH / "default_theme")

    assert theme.name != ""
    assert isinstance(theme.schemes, list)
    for scene in ("main_menu", "option_menu", "ports_list"):
        assert scene in theme.theme_data, scene


def test_missing_theme(pugtheme, tmp_path):
    with pytest.raises(ValueError):
        pugtheme.Theme(tmp_path)


################################################################################
## ThemeDownloader: the list of downloadable themes from the PortMaster-Themes release.
THEMES_JSON = {
    "themes": {
        "default_theme": {"name": "Default", "creator": "PortMaster", "file": "default_theme.theme.zip",
                          "md5": "0" * 32, "image": None},
        "zelda": {"name": "Zelda", "creator": "someone", "description": "LTTP", "file": "Zelda.theme.zip",
                  "md5": "1" * 32, "image": "zelda.png"},
        "basic": {"name": "Basic", "creator": "someone else", "file": "basic.theme.zip",
                  "md5": "2" * 32, "image": None},
        }
    }


@pytest.fixture
def theme_release(monkeypatch, tmp_path):
    import harbourmaster
    from harbourmaster.util import net

    images_zip = tmp_path / "theme_images.zip"
    import zipfile
    with zipfile.ZipFile(str(images_zip), "w") as zf:
        zf.writestr("images/zelda.png", b"png data")

    base = "https://github.com/PortsMaster/PortMaster-Themes/releases/download/2026"
    release = {"assets": [
        {"name": name, "size": 10, "browser_download_url": f"{base}/{name}"}
        for name in ("themes.json", "Zelda.theme.zip", "basic.theme.zip", "images.zip", "images.zip.md5")]}

    fetched = []

    def fetch_json(url):
        fetched.append(url)
        return json.loads(json.dumps(THEMES_JSON if url.endswith("themes.json") else release))

    def fetch_text(url):
        return "abc123  images.zip\n"

    def download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        fetched.append(file_url)
        file_name.write_bytes(images_zip.read_bytes())
        return file_name

    ## ThemeDownloader has used both the net module and harbourmaster's re-exports.
    for module in (net, harbourmaster):
        monkeypatch.setattr(module, "fetch_json", fetch_json)
        monkeypatch.setattr(module, "fetch_text", fetch_text)
        monkeypatch.setattr(module, "download", download)

    return SimpleNamespace(base=base, fetched=fetched)


@pytest.fixture
def downloader(pugtheme, hm, tmp_path):
    def _downloader():
        gui = SimpleNamespace(hm=hm)
        engine = SimpleNamespace(get_theme_dir=lambda name: tmp_path / "themes" / name)
        return pugtheme.ThemeDownloader(gui, engine)

    return _downloader


def test_theme_downloader_update(downloader, theme_release, tmp_path):
    themes_downloader = downloader()
    themes_downloader.update()

    themes = themes_downloader.get_theme_list()

    assert sorted(themes) == ["basic", "zelda"]
    zelda = themes["zelda"]
    assert zelda["name"] == "Zelda"
    assert zelda["creator"] == "someone"
    assert zelda["description"] == "LTTP"
    assert zelda["url"] == f"{theme_release.base}/Zelda.theme.zip"
    assert zelda["md5"] == "1" * 32
    assert zelda["directory"] == tmp_path / "themes" / "zelda"
    assert zelda["image"] is not None and zelda["image"].read_bytes() == b"png data"
    assert themes["basic"]["image"] is None
    assert themes["basic"]["description"] == ""


def test_theme_downloader_loads_cached_list_offline(downloader, theme_release, hm):
    downloader().update()
    fetched = len(theme_release.fetched)

    ## The hm fixture is offline, so a new downloader only reads themes.json from the config dir.
    themes = downloader().get_theme_list()

    assert len(theme_release.fetched) == fetched
    assert sorted(themes) == ["basic", "zelda"]
    assert (hm.cfg_dir / "themes.json").is_file()


def test_theme_image_with_capitals(downloader, theme_release, monkeypatch):
    ## themes.json names images like "Zelda.png", they are extracted lowercased.
    themes_json = json.loads(json.dumps(THEMES_JSON))
    themes_json["themes"]["zelda"]["image"] = "Zelda.png"
    monkeypatch.setitem(THEMES_JSON, "themes", themes_json["themes"])

    themes_downloader = downloader()
    themes_downloader.update()

    image = themes_downloader.get_theme_list()["zelda"]["image"]
    assert image is not None and image.read_bytes() == b"png data"
