# SPDX-License-Identifier: MIT
#
# Edge cases of harbourmaster.util and harbourmaster.info, and uninstalling safely
# whatever an installed port.json says.

import datetime
import hashlib
import json

import pytest

import harbourmaster
from harbourmaster import info as hm_info_module
from harbourmaster import util
from harbourmaster.util import files as util_files
from harbourmaster.util import net as util_net
from harbourmaster.util import text as util_text

from conftest import RecordingCallback, basic_port_files, write_port_zip


################################################################################
## Text
@pytest.mark.parametrize("size, expected", [
    (0, "0 B"),
    (767, "767 B"),
    (768, "0.75 KB"),
    (1024 * 1024, "1.00 MB"),
    (5 * 1024 ** 4, "5.00 TB"),
    (1024 ** 6, "1048576.00 TB"),
    ])
def test_nice_size_edges(size, expected):
    assert util.nice_size(size) == expected


@pytest.mark.parametrize("version, expected", [
    ("", ()),
    ("2.30", (2, 30)),
    ("v1.2", ("v", 1, 2)),
    ("1.0beta2", (1, 0, "beta", 2)),
    ("2026.10.18-0059", (2026, 10, 18, 59)),
    ("(1)[2],3_4", (1, 2, 3, 4)),
    ("abc", ("abc",)),
    ])
def test_version_parse_edges(version, expected):
    assert util.version_parse(version) == expected


def test_version_parse_orders_releases():
    versions = ["2026.10.18-0059", "2026.06.23-1000", "2026.10.18-0100", "2025.12.31-2359"]
    assert sorted(versions, key=util.version_parse) == ["2025.12.31-2359", "2026.06.23-1000", "2026.10.18-0059", "2026.10.18-0100"]


def test_list_to_tuple():
    @util.list_to_tuple
    def echo(*args):
        return list(args)

    assert echo([1, 2], "x") == ((1, 2), "x")


@pytest.mark.parametrize("text, expected", [
    ("Half-Life.zip", "half-life.zip"),
    ("  Cave Story+.ZIP ", "cave.story.zip"),
    ("a  b..c", "a.b.c"),
    ("日本語.zip", ".zip"),
    ("", ""),
    ])
def test_name_cleaner_edges(text, expected):
    assert util.name_cleaner(text) == expected


@pytest.mark.parametrize("runtime, expected", [
    ("frt_3.5.2.squashfs", "Godot/FRT 3.5.2"),
    ("solarus-1.6.5.squashfs", "Solarus 1.6.5"),
    ("mono-6.12.0.122-aarch64.squashfs", "Mono 6.12.0.122"),
    ("rlvm.squashfs", "RLVM"),
    ("pyxel_2.2.8_python_3.11.squashfs", "Pyxel 2.2.8"),
    ("weston_pkg_0.2.squashfs", "Weston 0.2.squashfs"),
    ("mesa_pkg_0.1.squashfs", "Mesa 0.1.squashfs"),
    ("zulu11.48.21-ca-jdk11.0.11-linux_aarch64.squashfs", "JDK 11.0.11"),
    ("zulu11.48.21-ca-jre11.0.11-linux_aarch64.squashfs", "JRE 11.0.11"),
    ("something.squashfs", "something.squashfs"),
    ## Not named the usual way: shown as they are rather than crashing.
    ("frt.squashfs", "frt.squashfs"),
    ("solarus.squashfs", "solarus.squashfs"),
    ("mono.squashfs", "mono.squashfs"),
    ("pyxel.squashfs", "pyxel.squashfs"),
    ("zulu11-jdk.squashfs", "zulu11-jdk.squashfs"),
    (["rlvm.squashfs", "mono.squashfs"], "RLVM and mono.squashfs"),
    ([], ""),
    ])
def test_runtime_nicename_edges(runtime, expected):
    assert util.runtime_nicename(runtime) == expected


def test_datetime_compare():
    now = datetime.datetime.now()
    hour_ago = (now - datetime.timedelta(hours=1)).isoformat()

    assert 3590 < util.datetime_compare(hour_ago) < 3700
    assert util.datetime_compare("2020-01-01T00:00:00", "2020-01-01T00:01:00") == 60
    assert util.datetime_compare(datetime.datetime(2020, 1, 2), datetime.datetime(2020, 1, 1)) == -86400


@pytest.mark.parametrize("value", ["garbage", "", "2026-13-45", 5, None, ["2020-01-01"]])
def test_datetime_compare_unreadable_is_long_ago(value):
    ## A broken last_checked crashed loading the sources.
    assert util.datetime_compare(value) == float('inf')
    assert util.datetime_compare(value) > 10 ** 9


def test_datetime_compare_with_a_timezone():
    ## Aware minus naive raised TypeError.
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    assert abs(util.datetime_compare(now)) < 60


def test_bad_last_checked_updates_the_source(make_hm, hm_dirs, monkeypatch):
    from harbourmaster import hm_info
    fetched = []
    monkeypatch.setattr(util_net, "fetch_json", lambda url: fetched.append(url))
    monkeypatch.setattr(hm_info, "fetch_text", lambda url: '{"tree": []}')

    source_file = hm_dirs['tools_dir'] / "PortMaster" / "config" / "020_portmaster.source.json"
    make_hm()
    data = json.loads(source_file.read_text())
    data['last_checked'] = "yesterday"
    data['version'] = 2
    source_file.write_text(json.dumps(data))

    make_hm(**{'offline': False, 'no-check': False})
    assert data['url'] in fetched


def test_timeit(monkeypatch):
    monkeypatch.setattr(util_text, "HM_PERFTEST", True)

    @util_text.timeit
    def add(a, b=1):
        return a + b

    assert add(1, b=2) == 3
    assert add.__name__ == "add"


def test_timeit_off_returns_the_function():
    def f():
        pass

    assert util_text.timeit(f) is f


################################################################################
## Files
def test_signature_path_types(tmp_path):
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/bash\necho\n")

    util.add_pm_signature(str(script), ["x.zip", "x.sh"])
    assert util.load_pm_signature(str(script)) == ["x.zip", "x.sh"]

    for func in (util.load_pm_signature, util.remove_pm_signature, util.hash_file, util.hash_file_sha, util.calculate_git_blob_sha_file):
        with pytest.raises(ValueError):
            func(5)

    with pytest.raises(ValueError):
        util.add_pm_signature(5, ["a", "b"])

    with pytest.raises(ValueError):
        util.calculate_git_blob_sha_data(5)


def test_signature_replaced_not_duplicated(tmp_path):
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/bash\n# PORTMASTER: old.zip, x.sh\necho\n")

    util.add_pm_signature(script, ["new.zip", "x.sh"])

    assert script.read_text().count("PORTMASTER:") == 1
    assert util.load_pm_signature(script) == ["new.zip", "x.sh"]


def test_signature_unchanged_isnt_rewritten(tmp_path):
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/bash\n# PORTMASTER: x.zip, x.sh\necho\n")
    before = script.stat().st_mtime_ns

    util.add_pm_signature(script, ["x.zip", "x.sh"])
    assert script.stat().st_mtime_ns == before


def test_signature_needs_a_comma(tmp_path):
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/bash\n# PORTMASTER: nothing here\n")
    assert util.load_pm_signature(script) is None


def test_signature_missing_and_non_scripts(tmp_path):
    assert util.load_pm_signature(tmp_path / "missing.sh") is None
    util.add_pm_signature(tmp_path / "missing.sh", ["a", "b"])
    util.remove_pm_signature(tmp_path / "missing.sh")
    assert not (tmp_path / "missing.sh").exists()

    text = tmp_path / "x.txt"
    text.write_text("# PORTMASTER: a, b\n")
    util.remove_pm_signature(text)
    assert text.read_text() == "# PORTMASTER: a, b\n"


def test_remove_signature(tmp_path):
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/bash\n# PORTMASTER: x.zip, x.sh\necho\n")

    util.remove_pm_signature(str(script))
    assert script.read_text() == "#!/bin/bash\necho\n"

    ## Nothing to remove.
    util.remove_pm_signature(script)
    assert script.read_text() == "#!/bin/bash\necho\n"


def test_signature_unreadable_script(tmp_path, log_errors, monkeypatch):
    script = tmp_path / "x.sh"
    script.write_text("#!/bin/bash\n")

    def fail(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(util_files, "open", fail, raising=False)
    assert util.load_pm_signature(script) is None
    assert any("denied" in message for message in log_errors)


def test_signature_non_utf8_script(tmp_path, log_errors):
    script = tmp_path / "x.sh"
    script.write_bytes(b"#!/bin/bash\necho \xff\xfe\n")

    util.add_pm_signature(script, ["x.zip", "x.sh"])
    ## Left alone rather than crashing.
    assert script.read_bytes() == b"#!/bin/bash\necho \xff\xfe\n"


def test_hashes(tmp_path):
    path = tmp_path / "x"
    path.write_bytes(b"abc")

    assert util.hash_file(str(path)) == hashlib.md5(b"abc").hexdigest()
    assert util.hash_file_sha(path) == hashlib.sha1(b"abc").hexdigest()
    assert util.hash_file_sha(str(path)) == hashlib.sha1(b"abc").hexdigest()
    assert util.hash_file_sha(tmp_path / "missing") is None
    assert util.hash_file(tmp_path) is None
    assert util.calculate_git_blob_sha_data("abc") == util.calculate_git_blob_sha_data(b"abc")
    assert util.calculate_git_blob_sha_file(str(path)) == util.calculate_git_blob_sha_data(b"abc")


def test_make_temp_directory():
    with util.make_temp_directory() as temp_dir:
        (temp_dir / "x").write_text("x")
        assert temp_dir.is_dir()

    assert not temp_dir.exists()


def test_make_temp_directory_cleans_up_after_errors():
    with pytest.raises(RuntimeError):
        with util.make_temp_directory() as temp_dir:
            raise RuntimeError()

    assert not temp_dir.exists()


def test_get_path_fs_testing():
    ## Never shells out from a checkout.
    assert util.get_path_fs("/") is None


@pytest.mark.parametrize("output, expected", [
    (b"Filesystem Type 1024-blocks Used Available Capacity Mounted on\n/dev/mmcblk0p1 exfat 100 50 50 50% /mnt/sdcard\n", "exfat"),
    (b"Filesystem Type\n", None),
    (b"Filesystem Type\n\n", None),
    (b"Filesystem Type\nonlyone\n", None),
    ])
def test_get_path_fs(tmp_path, monkeypatch, output, expected):
    monkeypatch.setattr(util_files, "HM_TESTING", False)
    monkeypatch.setattr(util_files.subprocess, "check_output", lambda *args, **kwargs: output)

    assert util.get_path_fs(tmp_path) == expected
    assert util.get_path_fs(str(tmp_path)) == expected


def test_get_path_fs_missing_and_errors(tmp_path, monkeypatch):
    monkeypatch.setattr(util_files, "HM_TESTING", False)
    assert util.get_path_fs(tmp_path / "missing") is None
    assert util.get_path_fs(str(tmp_path / "missing")) is None
    assert util.get_path_fs(5) is None

    def fail(*args, **kwargs):
        raise util_files.subprocess.CalledProcessError(1, "df")

    monkeypatch.setattr(util_files.subprocess, "check_output", fail)
    assert util.get_path_fs(tmp_path) is None


################################################################################
## Network
class Response:
    def __init__(self, status_code=200, content=b"", text=None, json_data=None, headers=None, chunks=None):
        self.status_code = status_code
        self.content = content
        self.text = text
        self._json = json_data
        self.headers = headers or {}
        self.encoding = None
        self.chunks = chunks if chunks is not None else [content]

    def json(self):
        return self._json

    def iter_content(self, chunk_size=None, decode_unicode=False):
        yield from self.chunks


def serve(monkeypatch, response):
    monkeypatch.setattr(util_net.requests, "get", lambda *args, **kwargs: response)


def test_fetch_status_error(monkeypatch, log_errors):
    serve(monkeypatch, Response(status_code=404))

    assert util.fetch_json("https://example.com/x") is None
    assert util.fetch_data("https://example.com/x") is None
    assert util.fetch_text("https://example.com/x") is None
    assert any("404" in message for message in log_errors)


def test_fetch_ok(monkeypatch):
    response = Response(content=b"data", text="tëxt", json_data={"a": 1})
    serve(monkeypatch, response)

    assert util.fetch_data("u") == b"data"
    assert util.fetch_json("u") == {"a": 1}
    assert util.fetch_text("u") == "tëxt"
    assert response.encoding == "utf-8"


def test_download_without_content_length(tmp_path, monkeypatch, callback):
    serve(monkeypatch, Response(content=b"abc"))

    result = util.download(tmp_path / "x", "u", hashlib.md5(b"abc").hexdigest(), callback=callback)

    assert result == tmp_path / "x"
    assert any("???? MB" in message for message in callback.messages)
    assert callback.progress_calls[-2][2] is None


def test_download_without_callback(tmp_path, monkeypatch, capsys):
    serve(monkeypatch, Response(content=b"abc", headers={'content-length': "3"}))

    md5_result = [None]
    assert util.download(tmp_path / "x", "u", md5_result=md5_result) == tmp_path / "x"
    assert md5_result == [hashlib.md5(b"abc").hexdigest()]

    out = capsys.readouterr().out
    assert "Downloading" in out and "3 B / 3 B" in out


def test_download_without_callback_unknown_length(tmp_path, monkeypatch, capsys):
    serve(monkeypatch, Response(content=b"abc"))

    util.download(tmp_path / "x", "u", hashlib.md5(b"abc").hexdigest())
    out = capsys.readouterr().out
    assert "?" * 40 in out and "Passed md5 check." in out


def test_download_http_error_without_callback(tmp_path, monkeypatch):
    serve(monkeypatch, Response(status_code=500))
    assert util.download(tmp_path / "x", "u") is None


def test_download_no_md5(tmp_path, monkeypatch, callback, log_errors):
    serve(monkeypatch, Response(content=b"abc", headers={'content-length': "3"}))

    assert util.download(tmp_path / "x", "u", callback=callback) == tmp_path / "x"
    assert "Unable to validate download." in callback.messages


def test_download_md5_mismatch_without_callback(tmp_path, monkeypatch):
    serve(monkeypatch, Response(content=b"abc", headers={'content-length': "3"}))

    assert util.download(tmp_path / "x", "u", "0" * 32) is None
    assert not (tmp_path / "x").exists()


################################################################################
## port_info_load
@pytest.mark.parametrize("item", ["..", "a/..", "../x", "a/../b", "/etc", "", ".", "./", "\\x", "x\\..\\y", 5, None, ["a"]])
def test_load_drops_unsafe_items(item, log_errors):
    info = harbourmaster.port_info_load({"name": "x.zip", "items": ["Good.sh", item, "good/"], "items_opt": [item, "opt/"]})

    assert info['items'] == ["Good.sh", "good/"]
    assert info['items_opt'] == ["opt/"]


def test_load_items_opt_only_unsafe_is_none():
    info = harbourmaster.port_info_load({"name": "x.zip", "items": ["a.sh"], "items_opt": [".."]})
    assert info['items_opt'] is None


@pytest.mark.parametrize("items_opt", ["opt/", 5, {"a": 1}])
def test_load_items_opt_not_a_list(items_opt):
    info = harbourmaster.port_info_load({"name": "x.zip", "items": ["a.sh"], "items_opt": items_opt})
    assert info['items_opt'] is None


@pytest.mark.parametrize("item, safe", [
    ("Port.sh", True),
    ("port/", True),
    ("a..b/", True),
    ("..hidden", True),
    ("..", False),
    ("x/../y", False),
    ])
def test_is_safe_port_item(item, safe):
    assert hm_info_module.is_safe_port_item(item) is safe


@pytest.mark.parametrize("raw", [5, None, 1.5, ["a"]])
def test_load_not_port_info(raw, log_errors):
    assert harbourmaster.port_info_load(raw) is None
    assert harbourmaster.port_info_load(raw, do_default=True)['attr']['title'] == ""


def test_load_bad_strings(tmp_path):
    assert harbourmaster.port_info_load("{not json}") is None
    assert harbourmaster.port_info_load("{not json}", do_default=True)['name'] is None
    assert harbourmaster.port_info_load('{"version": "x"}') is None
    assert harbourmaster.port_info_load('{"attr": []}') is None
    assert harbourmaster.port_info_load("no such file") is None

    path = tmp_path / "port.json"
    path.write_text("[1]")
    assert harbourmaster.port_info_load(str(path)) is None
    assert harbourmaster.port_info_load(path) is None
    assert harbourmaster.port_info_load(str(path), do_default=True)['items'] is None


def test_load_bad_version_with_default():
    assert harbourmaster.port_info_load({"version": 99}, do_default=True)['version'] == 4
    assert harbourmaster.port_info_load({"version": [1]}, do_default=True)['attr']['genres'] == []


def test_load_attr_type_cleanup():
    info = harbourmaster.port_info_load({"name": "x.zip", "attr": {
        "genres": "Puzzle", "porter": None, "runtime": "mono.squashfs", "reqs": ["a", 5], "arch": 5,
        "title": 5, "desc": None, "image": "shot.png", "rtr": "yes", "exp": 0,
        }})
    attr = info['attr']

    assert attr['genres'] == ["puzzle"]
    assert attr['porter'] == []
    assert attr['runtime'] == ["mono.squashfs"]
    assert attr['reqs'] == ["a"]
    assert attr['arch'] == []
    assert attr['title'] == "5"
    assert attr['desc'] == ""
    assert attr['image'] == {"screenshot": "shot.png"}
    assert attr['rtr'] is True and attr['exp'] is False

    assert harbourmaster.port_info_load({"attr": {"image": 5}})['attr']['image'] == {}


def test_load_v1_without_md5():
    info = harbourmaster.port_info_load({"version": 1, "source": "https://x/y/port.zip", "attr": {"runtime": None}})
    assert info['name'] == "port.zip"
    assert 'status' not in info
    assert info['attr']['runtime'] == []


def test_load_v3_runtime_string():
    info = harbourmaster.port_info_load({"version": 3, "attr": {"runtime": "x.squashfs"}})
    assert info['attr']['runtime'] == ["x.squashfs"]


def test_merge_bad_other(log_errors):
    info = harbourmaster.port_info_load({})
    assert harbourmaster.port_info_merge(info, 5) is None


def test_merge_from_a_file(tmp_path):
    path = tmp_path / "port.json"
    path.write_text(json.dumps({"name": "x.zip", "attr": {"title": "From file", "rtr": True}, "status": {"md5": "a"}}))
    info = harbourmaster.port_info_load({})

    harbourmaster.port_info_merge(info, path)

    assert info['name'] == "x.zip"
    assert info['attr']['title'] == "From file"
    assert info['attr']['rtr'] is True
    assert info['status'] == {"md5": "a"}


def test_merge_keeps_what_is_set():
    info = harbourmaster.port_info_load({"name": "a.zip", "items": ["a.sh"], "attr": {"title": "A", "genres": ["rpg"]}, "files": {"x": "y"}})
    other = harbourmaster.port_info_load({"name": "b.zip", "items": ["b.sh"], "attr": {"title": "B", "genres": ["puzzle"], "desc": "From b"}, "files": {"z": "z"}})

    harbourmaster.port_info_merge(info, other)

    assert info['name'] == "a.zip"
    assert info['items'] == ["a.sh"]
    assert info['attr']['title'] == "A"
    assert info['attr']['genres'] == ["rpg"]
    assert info['attr']['desc'] == "From b"
    assert info['files'] == {"x": "y"}


################################################################################
## Uninstalling whatever port.json says
@pytest.fixture
def sandbox(tmp_path):
    """The ports folder inside a folder holding something precious."""
    root = tmp_path / "sdcard"
    dirs = {
        'tools_dir': root / "tools",
        'ports_dir': root / "ports",
        'scripts_dir': root / "ports",
        'temp_dir': tmp_path / "temp",
        }
    for value in dirs.values():
        value.mkdir(parents=True, exist_ok=True)

    (root / "precious.txt").write_text("keep me")
    hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=RecordingCallback(), **dirs)

    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())
    assert hm.install_port(str(zip_file)) == 0
    hm.root = root
    hm.port_json = dirs['ports_dir'] / "testport" / "port.json"
    return hm


def edit_port_json(hm, change):
    data = json.loads(hm.port_json.read_text())
    change(data)
    hm.port_json.write_text(json.dumps(data))
    hm.load_ports()


## Never a real system path here: the test suite also runs on devices, as root. Absolute
## paths point into the sandbox ("{root}").
@pytest.mark.parametrize("item", ["..", "../", "testport/../..", "{root}"])
def test_uninstall_ignores_items_outside_the_ports_folder(sandbox, item):
    ## `..` in an installed port.json's items deleted the folder holding the ports folder.
    item = item.format(root=sandbox.root)
    edit_port_json(sandbox, lambda data: data['items'].append(item))

    assert sandbox.uninstall_port("testport.zip") == 0
    assert (sandbox.root / "precious.txt").read_text() == "keep me"
    assert not (sandbox.ports_dir / "testport").exists()


@pytest.mark.parametrize("value", ["../precious.txt", "..", "{root}/precious.txt", "{root}", "testport/../../precious.txt"])
def test_uninstall_ignores_files_outside_the_ports_folder(sandbox, value, log_errors):
    value = value.format(root=sandbox.root)
    edit_port_json(sandbox, lambda data: data['files'].__setitem__("extra", value))

    assert sandbox.uninstall_port("testport.zip") == 0
    assert (sandbox.root / "precious.txt").read_text() == "keep me"
    assert not (sandbox.ports_dir / "Test Port.sh").exists()
