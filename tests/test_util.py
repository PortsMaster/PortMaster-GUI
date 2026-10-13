# SPDX-License-Identifier: MIT

import hashlib

import pytest
import requests

import harbourmaster
from harbourmaster import util


################################################################################
## Formatting helpers
@pytest.mark.parametrize("size, expected", [
    (0, "0 B"),
    (767, "767 B"),
    (768, "0.75 KB"),
    (1024 * 1024, "1.00 MB"),
    (5 * 1024 ** 3, "5.00 GB"),
    ])
def test_nice_size(size, expected):
    assert util.nice_size(size) == expected


@pytest.mark.parametrize("strings, expected", [
    ([], ""),
    (["a"], "a"),
    (["a", "b"], "a and b"),
    (["a", "b", "c"], "a, b, and c"),
    ])
def test_oc_join(strings, expected):
    assert util.oc_join(strings) == expected


@pytest.mark.parametrize("version, expected", [
    ("2.30", (2, 30)),
    ("1.2.3a", (1, 2, 3, 'a')),
    ("2024-01-07-1007", (2024, 1, 7, 1007)),
    ("", ()),
    ])
def test_version_parse(version, expected):
    assert util.version_parse(version) == expected


def test_version_parse_orders_glibc():
    assert util.version_parse("2.30") > util.version_parse("2.4")


@pytest.mark.parametrize("text, expected", [
    ("Half-Life.zip", "half-life.zip"),
    ("  Some Port!.zip ", "some.port.zip"),
    ("100 Lil Jumps.sh", "100.lil.jumps.sh"),
    ])
def test_name_cleaner(text, expected):
    assert util.name_cleaner(text) == expected


@pytest.mark.parametrize("runtime, expected", [
    ("frt_3.5.2.squashfs", "Godot/FRT 3.5.2"),
    ("mono-6.12.0.122-aarch64.squashfs", "Mono 6.12.0.122"),
    ("rlvm.squashfs", "RLVM"),
    ("something_else.squashfs", "something_else.squashfs"),
    (["rlvm.squashfs", "frt_3.5.2.squashfs"], "RLVM and Godot/FRT 3.5.2"),
    ])
def test_runtime_nicename(runtime, expected):
    assert util.runtime_nicename(runtime) == expected


################################################################################
## Requirements
@pytest.mark.parametrize("requirements, expected", [
    ([], True),
    ([""], True),
    (["aarch64"], True),
    (["x86_64"], False),
    (["!x86_64"], True),
    (["!aarch64"], False),
    (["x86_64|aarch64"], True),
    (["x86_64|armhf"], False),
    (["!x86_64|armhf"], True),
    (["aarch64", "opengl"], True),
    (["aarch64", "!opengl"], False),
    ])
def test_match_requirements(requirements, expected):
    capabilities = ["aarch64", "640x480", "opengl"]
    assert util.match_requirements(capabilities, requirements) is expected


################################################################################
## Dict list helpers, used for port file ownership.
def test_dict_list_helpers():
    data = {}

    util.add_dict_list_unique(data, "a", "x")
    assert data == {"a": "x"}

    util.add_dict_list_unique(data, "a", "x")
    assert data == {"a": "x"}

    util.add_dict_list_unique(data, "a", "y")
    assert data == {"a": ["x", "y"]}

    assert util.get_dict_list(data, "a") == ["x", "y"]
    assert util.get_dict_list(data, "missing") == []
    assert util.get_dict_list({"n": None}, "n") == []
    assert util.get_dict_list({"s": "v"}, "s") == ["v"]

    util.remove_dict_list(data, "a", "x")
    assert data == {"a": "y"}

    util.remove_dict_list(data, "a", "y")
    assert data == {}


def test_add_list_unique():
    items = ["a"]
    util.add_list_unique(items, "a")
    util.add_list_unique(items, "b")
    assert items == ["a", "b"]


def test_port_sort_funcs_cover_sort_order():
    assert set(harbourmaster.HM_SORT_ORDER) <= set(util.PORT_SORT_FUNCS)

    ports = [
        {'name': 'b.zip', 'attr': {'title': 'Bravo'}, 'source': {'downloads': 5, 'date_added': '2024-02-01'}},
        {'name': 'a.zip', 'attr': {'title': 'alpha'}, 'source': {'downloads': 9, 'date_added': '2024-01-01'}},
        {'name': 'c.zip', 'attr': {'title': 'Charlie'}},
        ]

    def names(sort_by):
        return [p['name'] for p in sorted(ports, key=util.PORT_SORT_FUNCS[sort_by])]

    assert names('alphabetical') == ['a.zip', 'b.zip', 'c.zip']
    assert names('total_downloads') == ['c.zip', 'b.zip', 'a.zip']
    assert names('recently_added') == ['c.zip', 'a.zip', 'b.zip']


################################################################################
## Hashing
def test_hash_file(tmp_path):
    test_file = tmp_path / "data.bin"
    test_file.write_bytes(b"hello world")

    assert util.hash_file(test_file) == hashlib.md5(b"hello world").hexdigest()
    assert util.hash_file(str(test_file)) == hashlib.md5(b"hello world").hexdigest()
    assert util.hash_file_sha(test_file) == hashlib.sha1(b"hello world").hexdigest()
    assert util.hash_file(tmp_path / "missing") is None


def test_git_blob_sha(tmp_path):
    # `printf 'hello world' | git hash-object --stdin`
    expected = "95d09f2b10159347eece71399a7e2e907ea3df4f"

    test_file = tmp_path / "data.txt"
    test_file.write_bytes(b"hello world")

    assert util.calculate_git_blob_sha_data(b"hello world") == expected
    assert util.calculate_git_blob_sha_data("hello world") == expected
    assert util.calculate_git_blob_sha_file(test_file) == expected


################################################################################
## PortMaster script signatures
def test_pm_signature_round_trip(tmp_path):
    script = tmp_path / "Game.sh"
    script.write_text("#!/bin/bash\necho hi\n")

    assert util.load_pm_signature(script) is None

    util.add_pm_signature(script, ["game.zip", "Game.sh"])
    assert util.load_pm_signature(script) == ["game.zip", "Game.sh"]
    lines = script.read_text().split("\n")
    assert lines[0] == "#!/bin/bash"
    assert lines[1] == "# PORTMASTER: game.zip, Game.sh"

    ## Re-signing replaces the old signature rather than adding another.
    util.add_pm_signature(script, ["other.zip", "Game.sh"])
    assert util.load_pm_signature(script) == ["other.zip", "Game.sh"]
    assert script.read_text().count("PORTMASTER:") == 1

    util.remove_pm_signature(script)
    assert util.load_pm_signature(script) is None
    assert "echo hi" in script.read_text()


def test_pm_signature_ignores_non_scripts(tmp_path):
    text_file = tmp_path / "readme.txt"
    text_file.write_text("hello\n")

    util.add_pm_signature(text_file, ["game.zip", "readme.txt"])
    assert text_file.read_text() == "hello\n"
    assert util.load_pm_signature(text_file) is None


@pytest.mark.parametrize("signed", [True, False])
def test_pm_signature_binary_script(tmp_path, log_errors, signed):
    ## Self-extracting installers (makeself) are .sh files with gzip data after the header.
    script = tmp_path / "installer.sh"
    header = b"#!/bin/sh\n"
    if signed:
        header += b"# PORTMASTER: game.zip, installer.sh\n"

    script.write_bytes(header + b"echo unpacking\n" + bytes(range(256)) * 8)

    assert util.load_pm_signature(script) == (["game.zip", "installer.sh"] if signed else None)
    assert log_errors == []


def test_replace_file_is_a_new_file(tmp_path):
    ## A running bash script keeps reading the old file.
    target = tmp_path / "PortMaster.sh"
    target.write_text("old launcher\n")
    source = tmp_path / "new.txt"
    source.write_text("new launcher\n")

    with open(target) as running:
        util.replace_file(source, target)

        assert running.read() == "old launcher\n"

    assert target.read_text() == "new launcher\n"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["PortMaster.sh", "new.txt"]


################################################################################
## download()
class FakeResponse:
    def __init__(self, chunks, status_code=200, content_length=True, error_after=None):
        self.chunks = chunks
        self.status_code = status_code
        self.error_after = error_after
        self.headers = {}
        if content_length:
            self.headers['content-length'] = str(sum(len(c) for c in chunks))

    def iter_content(self, chunk_size=None, decode_unicode=False):
        for i, chunk in enumerate(self.chunks):
            if self.error_after is not None and i == self.error_after:
                raise self.error_after_exc

            yield chunk


@pytest.fixture
def fake_get(monkeypatch):
    def _fake_get(response):
        monkeypatch.setattr(util.net.requests, "get", lambda *args, **kwargs: response)
        return response

    return _fake_get


DATA = [b"a" * 100, b"b" * 100]
DATA_MD5 = hashlib.md5(b"".join(DATA)).hexdigest()


def test_download_ok(tmp_path, fake_get, callback):
    fake_get(FakeResponse(DATA))
    target = tmp_path / "file.zip"
    md5_result = [None]

    result = util.download(target, "https://example.com/file.zip", md5_source=DATA_MD5, md5_result=md5_result, callback=callback)

    assert result == target
    assert target.read_bytes() == b"".join(DATA)
    assert md5_result[0] == DATA_MD5
    assert callback.message_boxes == []

    ## Progress is reported per chunk with the total, then cleared.
    data_progress = [call for call in callback.progress_calls if call[0] is not None]
    assert data_progress[-1][1:] == (200, 200, 'data')
    assert callback.progress_calls[-1] == (None, None, None, None)


def test_download_md5_mismatch_removes_file(tmp_path, fake_get, callback):
    fake_get(FakeResponse(DATA))
    target = tmp_path / "file.zip"

    result = util.download(target, "https://example.com/file.zip", md5_source="0" * 32, callback=callback)

    assert result is None
    assert not target.exists()
    assert len(callback.message_boxes) == 1


def test_download_no_check_skips_md5(tmp_path, fake_get, callback):
    fake_get(FakeResponse(DATA))
    target = tmp_path / "file.zip"

    assert util.download(target, "https://example.com/file.zip", md5_source="0" * 32, callback=callback, no_check=True) == target


def test_download_http_error(tmp_path, fake_get, callback):
    fake_get(FakeResponse([], status_code=404))
    target = tmp_path / "file.zip"

    assert util.download(target, "https://example.com/file.zip", callback=callback) is None
    assert not target.exists()
    assert len(callback.message_boxes) == 1


def test_download_request_exception_removes_file(tmp_path, fake_get, callback):
    response = fake_get(FakeResponse(DATA, error_after=1))
    response.error_after_exc = requests.ConnectionError("dropped")
    target = tmp_path / "file.zip"

    assert util.download(target, "https://example.com/file.zip", callback=callback) is None
    assert not target.exists()
    assert len(callback.message_boxes) == 1


def test_download_cancel_removes_file_and_reraises(tmp_path, fake_get):
    class CancellingCallback(harbourmaster.Callback):
        def progress(self, message, amount, total=None, fmt=None):
            if message is not None:
                raise harbourmaster.CancelEvent()

    fake_get(FakeResponse(DATA))
    target = tmp_path / "file.zip"

    with pytest.raises(harbourmaster.CancelEvent):
        util.download(target, "https://example.com/file.zip", callback=CancellingCallback())

    assert not target.exists()


################################################################################
## JSON
def test_json_safe_loads():
    assert util.json_safe_loads('{"a": 1}') == {"a": 1}
    assert util.json_safe_loads('{broken') is None
