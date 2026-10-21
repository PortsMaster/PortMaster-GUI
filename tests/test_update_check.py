# SPDX-License-Identifier: MIT
#
# pugwash.update.portmaster_check_update(): PortMaster's self-update check, and
# config files broken by a power off while saving.

import datetime
import json

import pytest

import harbourmaster
from harbourmaster import util

from conftest import RecordingCallback


@pytest.fixture
def update(pugwash, monkeypatch, tmp_path):
    import pugwash.update as update

    tools = tmp_path / "updtools"
    (tools / "PortMaster" / "config").mkdir(parents=True)
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", tools)
    monkeypatch.setattr(update, "PORTMASTER_VERSION", "2026.06.23-1000")
    monkeypatch.setattr(update, "PORTMASTER_RELEASE_CHANNEL", "stable")
    monkeypatch.setattr(update, "PORTMASTER_MIN_VERSION", "2024.01.01-0000")
    monkeypatch.setattr(update, "HarbourMaster", lambda *args, **kwargs: "hm")
    update.cfg_file = tools / "PortMaster" / "config" / "config.json"
    update.tools = tools
    return update


class FakePM:
    def __init__(self, release_info, answer=True):
        self.release_info = release_info
        self.answer = answer
        self.hm = None
        self.boxes = []
        self.installs = []
        self.fetched = []

    def run_task(self, func, *args, **kwargs):
        if func is harbourmaster.fetch_json:
            self.fetched.append(args[0])
            if isinstance(self.release_info, BaseException):
                raise self.release_info

            return self.release_info

        return func(*args, **kwargs)

    def apply_button_mapping(self):
        pass

    def message_box(self, text, want_cancel=False):
        self.boxes.append(text)
        return self.answer

    def do_install(self, name, url, allow_cancel=True, md5_source=None):
        self.installs.append((name, url, md5_source))


def release(version, channel="stable"):
    return {channel: {"version": version, "url": f"https://example.com/{version}/PortMaster.zip", "md5": "abc"}}


def write_config(update, data):
    update.cfg_file.write_text(json.dumps(data) if not isinstance(data, str) else data)


def config(update):
    return json.loads(update.cfg_file.read_text())


def check(update, pm, **config_values):
    cfg = {'no-check': False, 'offline': False, **config_values}
    return update.portmaster_check_update(pm, cfg, None), cfg


def test_newer_version_installs(update):
    pm = FakePM(release("2026.10.18-0059"))

    result, cfg = check(update, pm)

    assert result is True
    assert "new version of PortMaster (2026.10.18-0059)" in pm.boxes[0]
    assert pm.installs == [("PortMaster", "https://example.com/2026.10.18-0059/PortMaster.zip", "abc")]
    assert (update.tools / "PortMaster" / ".pugwash-reboot").is_file()
    assert config(update)['update_checked']
    ## Asked under no-check, so the HarbourMaster made for it doesn't update sources.
    assert cfg['no-check'] is True


def test_newer_version_declined(update):
    pm = FakePM(release("2026.10.18-0059"), answer=False)

    result, cfg = check(update, pm)

    assert result is False
    assert pm.installs == []
    assert pm.hm is None
    assert cfg['no-check'] is False


def test_same_version_does_nothing(update):
    pm = FakePM(release("2026.06.23-1000"))

    assert check(update, pm)[0] is False
    assert pm.boxes == []


def test_checked_recently_doesnt_fetch(update):
    write_config(update, {"update_checked": datetime.datetime.now().isoformat()})
    pm = FakePM(release("2099.01.01-0000"))

    assert check(update, pm)[0] is False
    assert pm.fetched == []


def test_checked_long_ago_fetches(update):
    write_config(update, {"update_checked": "2020-01-01T00:00:00"})
    pm = FakePM(release("2026.06.23-1000"))

    check(update, pm)
    assert len(pm.fetched) == 1


def test_fetch_error(update):
    pm = FakePM(OSError("no network"))
    assert check(update, pm)[0] is None


def test_nothing_fetched(update):
    assert check(update, FakePM(None))[0] is False
    ## Tried again next time.
    assert not update.cfg_file.exists()


def test_channel_missing_from_version_json(update):
    pm = FakePM(release("2099.01.01-0000", channel="beta"))
    assert check(update, pm)[0] is False
    assert pm.boxes == []


def test_wont_go_below_the_minimum_version(update):
    write_config(update, {"release_channel": "stable", "change_channel": True})
    pm = FakePM(release("2020.01.01-0000"))

    assert check(update, pm)[0] is False
    assert pm.boxes == []


def test_switching_channel_downgrades(update):
    write_config(update, {"release_channel": "stable", "change_channel": True})
    pm = FakePM(release("2026.01.01-0000"))

    class Hm:
        cfg_data = {'change_channel': True}
        saved = False

        def save_config(self):
            self.saved = True

    update.HarbourMaster = lambda *args, **kwargs: Hm()

    assert check(update, pm)[0] is True
    assert "Do you want to downgrade?" in pm.boxes[0]
    assert pm.hm.cfg_data['change_channel'] is False and pm.hm.saved


def test_older_version_without_a_channel_switch(update):
    pm = FakePM(release("2026.01.01-0000"))
    assert check(update, pm)[0] is False
    assert pm.boxes == []


def test_konami_reinstall(update):
    write_config(update, {"konami": True})
    pm = FakePM(release("2026.06.23-1000"))

    assert check(update, pm)[0] is True
    assert "reinstall PortMaster" in pm.boxes[0]


def test_unknown_channel_is_reset(update):
    from pugwash import PORTMASTER_RELEASE_VALUES
    write_config(update, {"release_channel": "nightly"})
    pm = FakePM(release("2026.06.23-1000", channel=PORTMASTER_RELEASE_VALUES[-1]))

    check(update, pm)
    assert config(update)['release_channel'] == PORTMASTER_RELEASE_VALUES[-1]


@pytest.mark.parametrize("contents", ["", "{", "\x00\x00\x00", "[1]", "\xff\xfe"])
def test_broken_config_json(update, contents):
    update.cfg_file.write_bytes(contents.encode('latin-1'))
    pm = FakePM(release("2026.10.18-0059"))

    assert check(update, pm)[0] is True


@pytest.mark.parametrize("info", [
    {"stable": {}},
    {"stable": "2099"},
    {"stable": {"version": "2099.01.01-0000"}},
    ["stable"],
    ])
def test_bad_version_json(update, info):
    ## A broken version.json on the server must not stop PortMaster from starting.
    pm = FakePM(info)
    assert check(update, pm)[0] is False
    assert pm.installs == []


################################################################################
## HarbourMaster's own config files
@pytest.mark.parametrize("contents", [b"", b"{", b"\x00" * 64, b"[]", b"\xff\xfe\xfa"])
def test_broken_config_json_starts_afresh(make_hm, hm_dirs, contents, callback):
    cfg_file = hm_dirs['tools_dir'] / "PortMaster" / "config" / "config.json"
    make_hm()
    cfg_file.write_bytes(contents)

    hm = make_hm()

    assert hm.cfg_data['theme'] == "default_theme"
    assert json.loads(cfg_file.read_text())['first-run'] is False


@pytest.mark.parametrize("contents, expected", [
    (None, {}),
    (b"", {}),
    (b"{", {}),
    (b"[1, 2]", {}),
    (b"\xff\xfe", {}),
    (b'{"a": 1}', {"a": 1}),
    ])
def test_json_load_dict(tmp_path, contents, expected):
    path = tmp_path / "x.json"
    if contents is not None:
        path.write_bytes(contents)

    assert util.json_load_dict(path) == expected
    assert util.json_load_dict(path, {"d": 1}) == (expected or {"d": 1})


def test_json_load_dict_default_is_copied(tmp_path):
    default = {"a": 1}
    result = util.json_load_dict(tmp_path / "missing.json", default)
    result["a"] = 2

    assert default == {"a": 1}


def test_gui_get_config_broken(gui, monkeypatch, tmp_path):
    tools = tmp_path / "guitools"
    (tools / "PortMaster" / "config").mkdir(parents=True)
    (tools / "PortMaster" / "config" / "config.json").write_text("{")
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", tools)
    monkeypatch.setattr(gui, "hm", None)

    assert gui.get_config() == {}


def test_broken_themes_json(pugwash, hm):
    ## A themes.json missing keys took the theme list down with a KeyError.
    from types import SimpleNamespace
    from pugwash.theme import ThemeDownloader

    (hm.cfg_dir / "themes.json").write_text('{"name": "partial"}')
    downloader = ThemeDownloader(SimpleNamespace(hm=hm), None)

    assert downloader._config['prefix'] == "theme"
    assert downloader._config['name'] == "partial"


@pytest.mark.parametrize("contents", ["", "{", "[]"])
def test_unreadable_themes_json(pugwash, hm, contents):
    from types import SimpleNamespace
    from pugwash.theme import ThemeDownloader

    (hm.cfg_dir / "themes.json").write_text(contents)
    downloader = ThemeDownloader(SimpleNamespace(hm=hm), None)

    assert downloader._config['name'] == "PortMaster Themes"
