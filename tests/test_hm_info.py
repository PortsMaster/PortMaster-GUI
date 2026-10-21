# SPDX-License-Identifier: MIT
#
# HarbourMaster.load_info(): the PortMaster-Info files (ports_info.json, porters.json,
# port stats, featured ports), fetched through the GitHub tree API.

import io
import json
import zipfile

import pytest

from harbourmaster import hm_info
from harbourmaster.util import calculate_git_blob_sha_data, calculate_git_blob_sha_file


class FakeInfoRepo:
    """PortMaster-Info as the tree API and raw downloads see it."""
    def __init__(self, monkeypatch, temp_dir):
        self.files = {}
        self.tree_text = None
        self.fetched = []
        self.downloaded = []
        self.corrupt = set()
        self.temp_dir = temp_dir

        monkeypatch.setattr(hm_info, "fetch_text", self.fetch_text)
        monkeypatch.setattr(hm_info, "fetch_data", self.fetch_data)
        monkeypatch.setattr(hm_info, "download", self.download)

    def add(self, path, data):
        if isinstance(data, str):
            data = data.encode()

        self.files[path] = data

    def _path(self, url):
        return url.split("/raw/main/", 1)[1]

    def fetch_text(self, url):
        self.fetched.append(url)
        if self.tree_text is not None:
            return self.tree_text

        return json.dumps({'tree': [{'type': 'tree', 'path': 'images', 'sha': 'x', 'size': 0}, {'type': 'blob', 'path': '.github/x.yml', 'sha': 'x', 'size': 1}] + [
            {'type': 'blob', 'path': path, 'sha': calculate_git_blob_sha_data(data), 'size': len(data)}
            for path, data in self.files.items()]})

    def _data(self, path):
        data = self.files.get(path)
        if data is not None and path in self.corrupt:
            data = data + b"corrupted"

        return data

    def fetch_data(self, url):
        self.fetched.append(url)
        return self._data(self._path(url))

    def download(self, file_name, url, callback=None, no_check=False):
        self.downloaded.append(url)
        data = self._data(self._path(url))
        if data is None:
            return None

        file_name.write_bytes(data)
        return file_name


@pytest.fixture
def info_repo(monkeypatch, hm_dirs):
    return FakeInfoRepo(monkeypatch, hm_dirs['temp_dir'])


@pytest.fixture
def info_hm(make_hm):
    """An offline HarbourMaster, switched online for load_info() calls."""
    hm = make_hm()
    hm.config['offline'] = False
    hm.config['no-check'] = False
    hm.cfg_data.pop('last-info-check', None)
    return hm


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for name, data in files.items():
            zf.writestr(name, data)

    return buffer.getvalue()


################################################################################
## The local files
def test_base_files_are_created(hm):
    cfg_dir = hm.cfg_dir

    assert json.loads((cfg_dir / "ports_info.json").read_text()) == {"items": {}, "md5": {}, "ports": {}, "portsmd_fix": {}}
    assert json.loads((cfg_dir / "porters.json").read_text()) == {}
    assert json.loads((cfg_dir / "port_stats.json").read_text()) == {"ports": {}, "total_downloads": 0}
    assert json.loads((cfg_dir / "featured_ports.json").read_text()) == []
    assert not (cfg_dir / "featured_images.zip").exists()
    assert (cfg_dir / "featured_ports").is_dir()


def test_existing_files_are_kept(hm):
    (hm.cfg_dir / "porters.json").write_text('{"klops": {}}')
    hm.load_info()

    assert json.loads((hm.cfg_dir / "porters.json").read_text()) == {"klops": {}}


def test_old_config_keys_are_dropped(hm):
    hm.cfg_data.update({"featured_ports_checked": 1, "porters_checked": 2, "ports_info_checked": 3, "keep": 4})
    hm.load_info()

    assert hm.cfg_data["keep"] == 4
    for key in ("featured_ports_checked", "porters_checked", "ports_info_checked"):
        assert key not in hm.cfg_data


@pytest.mark.parametrize("contents", ["", "not json", "null"])
def test_bad_ports_info_falls_back_to_empty(hm, contents):
    (hm.cfg_dir / "ports_info.json").write_text(contents)
    hm._PORTS_INFO = None

    assert hm.ports_info() == {"items": {}, "md5": {}, "ports": {}, "portsmd_fix": {}}


@pytest.mark.parametrize("contents", ["", "{]", "null"])
def test_bad_porters_falls_back_to_empty(hm, contents):
    (hm.cfg_dir / "porters.json").write_text(contents)
    hm._PORTERS = None

    assert hm.porters() == {}
    assert hm.porters_list() == []


def test_porters_list(hm):
    (hm.cfg_dir / "porters.json").write_text('{"klops": {}, "Cebion": {}}')
    hm._PORTERS = None

    assert hm.porters_list() == ["klops", "Cebion"]


@pytest.mark.parametrize("contents, expected", [
    ('{"ports": {"sprout.zip": 12}}', 12),
    ('{"ports": {}}', 0),
    ('{"total_downloads": 5}', 0),
    ('[1, 2]', 0),
    ('garbage', 0),
    (None, 0),
    ])
def test_port_downloads(hm, contents, expected):
    stats = hm.cfg_dir / "port_stats.json"
    if contents is None:
        stats.unlink()
    else:
        stats.write_text(contents)

    hm._PORTS_DOWNLOAD = None
    assert hm.port_downloads("sprout.zip") == expected
    assert hm.port_downloads("other.zip") == 0


################################################################################
## Fetching
def test_offline_does_not_fetch(hm, info_repo):
    hm.load_info()
    assert info_repo.fetched == []


def test_fetch_new_files(info_hm, info_repo):
    info_repo.add("ports_info.json", '{"items": {"a.sh": ["a.zip"]}, "md5": {}, "ports": {}, "portsmd_fix": {}}')
    info_repo.add("porters.json", '{"klops": {}}')
    info_repo.add("README.md", "not wanted")

    info_hm.load_info()

    cfg_dir = info_hm.cfg_dir
    assert json.loads((cfg_dir / "porters.json").read_text()) == {"klops": {}}
    assert "a.sh" in json.loads((cfg_dir / "ports_info.json").read_text())['items']
    ## Only the files PortMaster uses.
    assert not (cfg_dir / "README.md").exists()
    assert info_hm.cfg_data['last-info-check']


def test_unchanged_files_are_not_fetched(info_hm, info_repo):
    info_repo.add("porters.json", (info_hm.cfg_dir / "porters.json").read_bytes())
    info_hm.load_info()

    assert info_repo.fetched == [info_hm.PORT_INFO_JSON]


def test_checked_recently_does_not_fetch(info_hm, info_repo):
    import datetime
    info_hm.cfg_data['last-info-check'] = datetime.datetime.now().isoformat()
    info_hm.load_info()

    assert info_repo.fetched == []


def test_checked_long_ago_fetches(info_hm, info_repo):
    info_hm.cfg_data['last-info-check'] = "2020-01-01T00:00:00"
    info_hm.load_info()

    assert info_repo.fetched == [info_hm.PORT_INFO_JSON]


def test_tree_unavailable_goes_offline(info_hm, monkeypatch):
    ## A failed tree fetch (no network, or the API's rate limit) switches the whole
    ## session to offline: the port sources don't update either.
    monkeypatch.setattr(hm_info, "fetch_text", lambda url: None)
    info_hm.load_info()

    assert info_hm.config['offline'] is True
    assert 'last-info-check' not in info_hm.cfg_data


@pytest.mark.parametrize("tree_text", ["not json", "[]", '{"no": "tree"}', "null"])
def test_bad_tree_is_ignored(info_hm, info_repo, tree_text, log_errors):
    info_repo.tree_text = tree_text
    info_hm.load_info()

    assert info_hm.config['offline'] is False
    assert 'last-info-check' not in info_hm.cfg_data
    assert any("Unable to fetch a sensible version" in message for message in log_errors)


def test_failed_small_download_keeps_the_old_file(info_hm, info_repo, callback):
    info_repo.add("porters.json", '{"new": {}}')
    info_repo.corrupt.add("porters.json")
    info_hm.load_info()

    assert json.loads((info_hm.cfg_dir / "porters.json").read_text()) == {}
    assert "Download validation failed." in callback.messages


def test_missing_small_download(info_hm, info_repo, callback, monkeypatch):
    info_repo.add("porters.json", '{"new": {}}')
    monkeypatch.setattr(hm_info, "fetch_data", lambda url: None)
    info_hm.load_info()

    assert json.loads((info_hm.cfg_dir / "porters.json").read_text()) == {}
    assert "Unable to download file." in callback.messages


def big(text):
    ## Over 1MB: downloaded with a progress bar rather than fetched.
    return text + " " * (1024 * 1024 + 1)


def test_big_download(info_hm, info_repo):
    info_repo.add("ports_info.json", big('{"items": {}, "md5": {}, "ports": {"big.zip": {}}, "portsmd_fix": {}}'))
    info_hm.load_info()

    local = info_hm.cfg_dir / "ports_info.json"
    assert "big.zip" in json.loads(local.read_text())['ports']
    assert len(info_repo.downloaded) == 1
    ## The temp copy is cleaned up.
    assert not (info_hm.temp_dir / "ports_info.json").exists()


def test_big_download_failure(info_hm, info_repo, monkeypatch):
    info_repo.add("ports_info.json", big("{}"))
    monkeypatch.setattr(hm_info, "download", lambda *args, **kwargs: None)

    before = (info_hm.cfg_dir / "ports_info.json").read_text()
    info_hm.load_info()
    assert (info_hm.cfg_dir / "ports_info.json").read_text() == before


def test_big_download_validation_failure_keeps_the_old_file(info_hm, info_repo, callback):
    ## It deleted the bad download and then copied it over the old file: FileNotFoundError.
    info_repo.add("ports_info.json", big("{}"))
    info_repo.corrupt.add("ports_info.json")

    before = (info_hm.cfg_dir / "ports_info.json").read_text()
    info_hm.load_info()

    assert (info_hm.cfg_dir / "ports_info.json").read_text() == before
    assert "Download validation failed." in callback.messages


################################################################################
## Featured ports
def test_featured_images_zip_is_extracted(info_hm, info_repo):
    info_repo.add("featured_images.zip", zip_bytes({
        "images/one.png": b"png1",
        "images/sub/two.jpg": b"jpg2",
        "images/": b"",
        "images/readme.txt": b"skip",
        "../escape.png": b"flattened",
        }))
    info_hm.load_info()

    featured = info_hm.cfg_dir / "featured_ports"
    assert sorted(path.name for path in featured.iterdir()) == ["escape.png", "one.png", "two.jpg"]
    assert (featured / "two.jpg").read_bytes() == b"jpg2"
    assert not (info_hm.cfg_dir / "escape.png").exists()


def test_featured_images_fetched_one_by_one(info_hm, info_repo):
    info_repo.add("images/three.png", b"png3")
    info_repo.add("images/notes.txt", b"skip")
    info_hm.load_info()

    featured = info_hm.cfg_dir / "featured_ports"
    assert (featured / "three.png").read_bytes() == b"png3"
    assert not (featured / "notes.txt").exists()

    ## Up to date now: not fetched again.
    info_repo.fetched.clear()
    info_hm.cfg_data.pop('last-info-check')
    info_hm.load_info()
    assert info_repo.fetched == [info_hm.PORT_INFO_JSON]


def test_images_in_the_zip_are_not_fetched_again(info_hm, info_repo):
    info_repo.add("featured_images.zip", zip_bytes({"images/one.png": b"png1"}))
    info_repo.add("images/one.png", b"png1")
    info_hm.load_info()

    assert not any(url.endswith("images/one.png") for url in info_repo.fetched)


################################################################################
## runtimes.json
def test_runtimes_file_is_loaded(make_hm, hm_dirs):
    hm = make_hm()
    hm.runtimes_file.write_text(json.dumps({"mono.squashfs": {"name": "Mono", "status": "Unknown", "remote": {}}}))

    hm.load_info()
    assert hm.runtimes_info["mono.squashfs"]["name"] == "Mono"


def test_bad_runtimes_file(make_hm):
    hm = make_hm()
    hm.runtimes_file.write_text("garbage")

    hm.load_info()
    assert hm.runtimes_info == {}


def test_git_blob_sha():
    ## The same as `git hash-object`.
    assert calculate_git_blob_sha_data(b"") == "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert calculate_git_blob_sha_data(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_git_blob_sha_file(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"hello\n")
    assert calculate_git_blob_sha_file(path) == "ce013625030ba8dba906f756967f9e9ca394464a"
    assert calculate_git_blob_sha_file(tmp_path / "missing") is None
