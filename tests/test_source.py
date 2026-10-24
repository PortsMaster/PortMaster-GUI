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
## raw_download: "?md5=<hex>" on the url is the md5 the download must have.
ZIP_DATA = b"PK\x05\x06" + b"\x00" * 18


class FakeDownload:
    status_code = 200
    headers = {}

    def __init__(self, data):
        self.data = data

    def iter_content(self, chunk_size=1, decode_unicode=False):
        yield self.data


@pytest.fixture
def served(monkeypatch):
    """The urls downloaded and md5 files fetched; every download is ZIP_DATA, every md5 file `served.md5_file`."""
    import hashlib
    served = type("Served", (), {})()
    served.got = []
    served.fetched = []
    served.md5 = hashlib.md5(ZIP_DATA).hexdigest()
    served.md5_file = served.md5 + "  port.zip\n"

    def get(url, **kwargs):
        served.got.append(url)
        return FakeDownload(ZIP_DATA)

    def fetch_text(url):
        served.fetched.append(url)
        return served.md5_file

    monkeypatch.setattr(hm_net.requests, "get", get)
    monkeypatch.setattr(hm_net, "fetch_text", fetch_text)
    return served


def test_raw_download_md5_query(tmp_path, callback, served):
    url = f"https://example.com/files/port.zip?md5={served.md5}"
    result = hm_source.raw_download(tmp_path, url, callback=callback)

    assert result['zip_file'] == tmp_path / "port.zip" and result['zip_file'].read_bytes() == ZIP_DATA
    assert result['status']['md5'] == served.md5 and result['status']['url'] == url
    ## The md5 isn't sent to the server.
    assert served.got == ["https://example.com/files/port.zip"]
    assert "Passed file validation." in callback.messages


@pytest.mark.parametrize("query, sent", [
    ("token=abc&md5={md5}", "?token=abc"),
    ("md5={md5}&token=abc&x=", "?token=abc&x="),
    ("MD5={MD5}", ""),
    ])
def test_raw_download_md5_query_keeps_the_rest(tmp_path, callback, served, query, sent):
    url = "https://example.com/port.zip?" + query.format(md5=served.md5, MD5=served.md5.upper())
    assert hm_source.raw_download(tmp_path, url, callback=callback) is not None
    assert served.got == ["https://example.com/port.zip" + sent]


def test_raw_download_md5_query_wrong(tmp_path, callback, served):
    result = hm_source.raw_download(tmp_path, f"https://example.com/port.zip?md5={'0' * 32}", callback=callback)

    assert result is None
    assert callback.message_boxes == ["Download validation failed."]
    assert not (tmp_path / "port.zip").exists()


@pytest.mark.parametrize("md5", ["", "abc", "z" * 32, "0" * 31, "0" * 33, "0" * 32 + "%00"])
def test_raw_download_md5_query_not_an_md5(tmp_path, callback, served, md5):
    result = hm_source.raw_download(tmp_path, f"https://example.com/port.zip?md5={md5}", callback=callback)

    assert result is None and served.got == []
    assert callback.message_boxes == ["Unable to download file, its md5 is not valid."]


def test_raw_download_md5_file(tmp_path, callback, served):
    ## The .md5 file form: as before, and an upper case md5sum is fine too.
    served.md5_file = served.md5.upper() + "\tport.zip\n"
    result = hm_source.raw_download(tmp_path, "https://example.com/port.zip.md5", callback=callback)

    assert result is not None and result['name'] == "port.zip"
    assert served.fetched == ["https://example.com/port.zip.md5"] and served.got == ["https://example.com/port.zip"]


def test_raw_download_md5_file_and_query(tmp_path, callback, served):
    url = f"https://example.com/port.zip.md5?md5={served.md5}"
    assert hm_source.raw_download(tmp_path, url, callback=callback) is not None
    assert served.got == ["https://example.com/port.zip"]


def test_raw_download_md5_file_and_query_disagree(tmp_path, callback, served):
    ## Which one is right? Neither is trusted: nothing is downloaded.
    result = hm_source.raw_download(tmp_path, f"https://example.com/port.zip.md5?md5={'0' * 32}", callback=callback)

    assert result is None and served.got == []
    assert callback.message_boxes == ["Download validation failed."]


def test_raw_download_no_md5(tmp_path, callback, served):
    assert hm_source.raw_download(tmp_path, "https://example.com/port.zip?x=1", callback=callback) is not None
    assert served.got == ["https://example.com/port.zip?x=1"]
    assert "Unable to validate download." in callback.messages


@pytest.mark.parametrize("url", ["https://example.com", "https://example.com/", "https://example.com/?md5=" + "0" * 32])
def test_raw_download_no_file_name(tmp_path, callback, served, url):
    assert hm_source.raw_download(tmp_path, url, callback=callback) is None
    assert callback.message_boxes == ["Unable to download non zip files."] and served.got == []


def test_install_md5_query(hm, callback, served, monkeypatch):
    ## harbourmaster install <url>?md5=...: the CLI and the GUI both end up here.
    monkeypatch.setitem(hm.config, 'offline', False)
    monkeypatch.setattr(hm, "callback", callback)
    installed = []
    monkeypatch.setattr(hm, "_install_portmaster", lambda zip_file, do_delete=False: installed.append(zip_file.name) or 0)

    assert hm.install_port(f"https://example.com/PortMaster.zip?md5={served.md5}") == 0
    assert installed == ["PortMaster.zip"] and served.got == ["https://example.com/PortMaster.zip"]

    assert hm.install_port(f"https://example.com/PortMaster.zip?md5={'0' * 32}") == 255
    assert len(installed) == 1


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


################################################################################
## A ports.json from any source: entries it can't use are skipped, not fatal.
def update_with(hm, monkeypatch, data):
    monkeypatch.setattr(hm_net, "fetch_json", lambda url: json.loads(json.dumps(data)))
    source = hm.sources['pm']
    source.update()
    return source


@pytest.mark.parametrize('source_block', [None, "x", [], {}, {'md5': "abc", 'size': 1}])
def test_port_without_a_download_is_skipped(hm, monkeypatch, ports_json_data, source_block):
    if source_block is None:
        del ports_json_data['ports']['sprout.zip']['source']
    else:
        ports_json_data['ports']['sprout.zip']['source'] = source_block

    source = update_with(hm, monkeypatch, ports_json_data)

    assert 'sprout.zip' not in source.ports
    assert sorted(source.ports) == sorted(set(ports_json_data['ports']) - {'sprout.zip'})


def test_port_with_bad_source_values(hm, monkeypatch, ports_json_data):
    ports_json_data['ports']['sprout.zip']['source'].update(size="big", md5=None, date_added=None)
    source = update_with(hm, monkeypatch, ports_json_data)

    assert source.port_download_size('sprout.zip', check_runtime=False) == 0
    hm.list_ports_new(sort_by='recently_added')


@pytest.mark.parametrize('entry', ["/etc/hostname", 1, None, ["x"]])
def test_port_entry_that_isnt_an_object(hm, monkeypatch, ports_json_data, entry):
    ## A string isn't read as a port.json path either.
    ports_json_data['ports']['sprout.zip'] = entry
    source = update_with(hm, monkeypatch, ports_json_data)

    assert 'sprout.zip' not in source.ports
    assert len(source.ports) == len(ports_json_data['ports']) - 1


def test_port_with_no_name_uses_its_key(hm, monkeypatch, ports_json_data):
    ports_json_data['ports']['sprout.zip']['name'] = 5
    source = update_with(hm, monkeypatch, ports_json_data)

    assert source.port_info('sprout.zip')['name'] == 'sprout.zip'
    hm.list_ports_new()


@pytest.mark.parametrize('key', ["ports", "utils"])
@pytest.mark.parametrize('value', [None, [], "x"])
def test_ports_json_with_bad_sections(hm, monkeypatch, ports_json_data, key, value, log_errors):
    ports_json_data[key] = value
    update_with(hm, monkeypatch, ports_json_data)

    assert any("Bad ports.json" in message for message in log_errors)


@pytest.mark.parametrize('data', [None, [], "x", 1])
def test_ports_json_that_isnt_an_object(hm, monkeypatch, data):
    source = update_with(hm, monkeypatch, {'x': data} if data is None else data)
    assert source.ports == []


def test_util_names_are_file_names(hm, monkeypatch, ports_json_data):
    ## Runtimes are saved in the libs folder under these names.
    good = next(iter(ports_json_data['utils'].values()))
    ports_json_data['utils']['../../escape.squashfs'] = dict(good)
    ports_json_data['utils']['named.squashfs'] = dict(good, runtime_name="../escape.squashfs", runtime_arch="aarch64")
    ports_json_data['utils']['no-url.squashfs'] = {'name': "x", 'md5': "y"}
    ports_json_data['utils']['sized.squashfs'] = dict(good, size="big", md5=7)

    source = update_with(hm, monkeypatch, ports_json_data)

    assert not any('escape' in runtime for runtime in hm.runtimes_info)
    assert 'no-url.squashfs' not in source.utils
    assert source.port_download_size('sized.squashfs') == 0
