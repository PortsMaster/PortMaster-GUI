# SPDX-License-Identifier: MIT

import json

import pytest

import harbourmaster
from harbourmaster import source as hm_source
from harbourmaster.util import net as hm_net

REAL_FETCH_JSON = hm_net.fetch_json


@pytest.fixture
def pm_source(hm, ports_json_data, monkeypatch):
    """The default PortMaster source, updated from tests/data/ports.json."""
    fetched = []

    def fake_fetch_json(url):
        fetched.append(url)
        return json.loads(json.dumps(ports_json_data))

    monkeypatch.setattr(hm_net, "fetch_json", fake_fetch_json)

    source = hm.sources['pm']
    source.update()
    source.fetched = fetched
    return source


def test_default_sources(hm):
    assert sorted(hm.sources) == ['pm', 'pmmv']
    assert all(isinstance(source, hm_source.PortMasterV3) for source in hm.sources.values())
    assert hm.sources['pm'].name == "PortMaster"


def test_update_loads_ports(pm_source, ports_json_data):
    assert pm_source.fetched == [pm_source._config['url']]
    assert sorted(pm_source.ports) == sorted(ports_json_data['ports'])
    ## Runtimes are keyed by runtime_name, so each arch build adds the same name again.
    assert sorted(pm_source.utils) == [
        'ags_3.6.squashfs', 'ags_3.6.squashfs', 'dotnet-8.0.12.squashfs', 'gameinfo.zip', 'gmtoolkit.squashfs']

    info = pm_source.port_info("100LilJumps.zip")
    assert info['attr']['title'] == "100 Lil Jumps"
    assert pm_source.port_info("missing.zip") == {}

    expected = ports_json_data['ports']['100liljumps.zip']['source']
    assert pm_source.port_download_size("100liljumps.zip", check_runtime=False) == expected['size']
    assert pm_source.port_download_url("100liljumps.zip") == expected['url']


def test_update_registers_runtimes_per_arch(pm_source, hm):
    ags = hm.runtimes_info['ags_3.6.squashfs']

    assert ags['name'] == "Adventure Game Studio 3.6"
    assert sorted(ags['remote']) == ['aarch64', 'x86_64']


def test_update_saves_and_reloads(pm_source, make_hm, ports_json_data):
    ## A second HarbourMaster on the same dirs loads the cached source without fetching.
    hm2 = make_hm()
    assert sorted(hm2.sources['pm'].ports) == sorted(ports_json_data['ports'])


def test_runtime_size_added_to_download_size(pm_source, hm, ports_json_data):
    port = ports_json_data['ports']['sprout.zip']
    size = pm_source.port_download_size("sprout.zip", check_runtime=False)

    assert size == port['source']['size']
    assert pm_source.port_download_size("sprout.zip") > size


def test_download_unknown_port(pm_source, callback):
    assert pm_source.download("missing.zip") is None
    assert len(callback.message_boxes) == 1


def test_update_failure_keeps_going(hm, monkeypatch):
    monkeypatch.setattr(hm_net, "fetch_json", lambda url: None)

    source = hm.sources['pm']
    source.update()

    assert source.ports == []


def test_update_again_fetches_again(pm_source, ports_json_data):
    ## "Update ports" after the startup update emptied the list until a restart. It
    ## fetches again: a release may have been made since PortMaster started.
    ports_json_data['ports']['sprout.zip']['attr']['title'] = "Sprout, the new release"
    pm_source.update()

    assert pm_source.fetched == [pm_source._config['url']] * 2
    assert sorted(pm_source.ports) == sorted(ports_json_data['ports'])
    assert pm_source.port_info("sprout.zip")['attr']['title'] == "Sprout, the new release"


def test_failed_update_keeps_the_cached_ports(pm_source, make_hm, ports_json_data, monkeypatch):
    ## Due an update, but the network isn't really there: the cache is still shown.
    config = json.loads(pm_source._file_name.read_text())
    config['last_checked'] = "2020-01-01T00:00:00"
    pm_source._file_name.write_text(json.dumps(config))

    def timeout(*args, **kwargs):
        raise hm_net.requests.exceptions.ReadTimeout("read timed out")

    monkeypatch.setattr(hm_net, "fetch_json", REAL_FETCH_JSON)
    monkeypatch.setattr(hm_net.requests, "get", timeout)
    source = make_hm(offline=False, **{'no-check': False}).sources['pm']

    assert sorted(source.ports) == sorted(ports_json_data['ports'])
    assert source.port_download_url("sprout.zip") == ports_json_data['ports']['sprout.zip']['source']['url']


class FakeResponse:
    status_code = 200

    def json(self):
        raise ValueError("Expecting value: line 1 column 1 (char 0)")


@pytest.mark.parametrize("error", [
    hm_net.requests.exceptions.ReadTimeout("read timed out"),
    hm_net.requests.exceptions.SSLError("certificate is not yet valid"),
    hm_net.requests.exceptions.ConnectionError("no route to host"),
    ])
def test_fetch_network_errors_are_none(monkeypatch, error):
    def get(*args, **kwargs):
        raise error

    monkeypatch.setattr(hm_net.requests, "get", get)
    assert hm_net.fetch_json("https://example.com/ports.json") is None


def test_fetch_json_bad_json_is_none(monkeypatch):
    monkeypatch.setattr(hm_net.requests, "get", lambda *args, **kwargs: FakeResponse())
    assert hm_net.fetch_json("https://example.com/ports.json") is None


def test_raw_download_md5_unavailable(tmp_path, callback, monkeypatch):
    ## Used to crash with NameError on the undefined `r` while reporting this.
    monkeypatch.setattr(hm_net, "fetch_text", lambda url: None)

    result = hm_source.raw_download(tmp_path, "https://example.com/port.zip.md5", callback=callback)

    assert result is None
    assert callback.message_boxes == ["Unable to download verification file."]


################################################################################
## Old source files are upgraded to PortMasterV3 when loaded.
LEGACY_SOURCES = {
    "020_portmaster.source.json": ("pm", "PortMaster",
        "https://github.com/PortsMaster/PortMaster-New/releases/latest/download/ports.json"),
    "021_portmaster.multiverse.source.json": ("pmmv", "PortMaster Multiverse",
        "https://github.com/PortsMaster-MV/PortMaster-MV-New/releases/latest/download/ports.json"),
    }


@pytest.mark.parametrize("api", ["PortMasterV1", "PortMasterV2"])
def test_legacy_sources_upgrade_to_v3(make_hm, hm_dirs, api):
    cfg_dir = make_hm().cfg_dir

    for file_name, (prefix, name, _) in LEGACY_SOURCES.items():
        (cfg_dir / file_name).write_text(json.dumps({
            "prefix": prefix, "api": api, "name": name, "url": "https://example.com/old",
            "last_checked": None, "version": 1, "data": {}}))

    hm = make_hm()

    for file_name, (prefix, name, url) in LEGACY_SOURCES.items():
        assert isinstance(hm.sources[prefix], hm_source.PortMasterV3)
        assert hm.sources[prefix]._config['url'] == url


def test_unknown_source_api_is_skipped(make_hm):
    cfg_dir = make_hm().cfg_dir
    (cfg_dir / "030_custom.source.json").write_text(json.dumps({
        "prefix": "custom", "api": "SomethingElse", "name": "Custom", "url": "https://example.com",
        "last_checked": None, "version": 1, "data": {}}))

    hm = make_hm()

    assert "custom" not in hm.sources
    assert sorted(hm.sources) == ['pm', 'pmmv']
