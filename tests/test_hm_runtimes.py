# SPDX-License-Identifier: MIT
#
# Runtimes (hm_runtimes.py) and featured ports lists (hm_featured.py).

import hashlib
import json

import pytest

from harbourmaster import hm_runtimes
from harbourmaster.util import CancelEvent


RUNTIME = "gmtoolkit.squashfs"
DATA = b"runtime data"
MD5 = hashlib.md5(DATA).hexdigest()


@pytest.fixture
def rt_hm(online_hm, monkeypatch):
    """online_hm with gmtoolkit's aarch64 build being DATA, served by `downloads`."""
    online_hm.runtimes_info[RUNTIME]['remote']['aarch64']['md5'] = MD5
    online_hm.runtime_downloads = []
    online_hm.runtime_result = DATA

    def download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        online_hm.runtime_downloads.append(file_url)
        result = online_hm.runtime_result
        if isinstance(result, BaseException):
            file_name.write_bytes(b"partial")
            raise result

        if result is None:
            return None

        file_name.write_bytes(result)
        return file_name

    monkeypatch.setattr(hm_runtimes, "download", download)
    return online_hm


def local(hm, runtime=RUNTIME):
    return hm.runtimes_info[runtime].get('local', {})


################################################################################
## list_runtimes
def test_list_runtimes_not_installed(rt_hm):
    result = dict(rt_hm.list_runtimes())

    assert result[RUNTIME]['local'] == {'status': 'Not Installed', 'md5': None, 'arch': None}
    assert json.loads(rt_hm.runtimes_file.read_text())[RUNTIME]['local']['status'] == 'Not Installed'


def test_list_runtimes_verified_by_the_remote_md5(rt_hm):
    (rt_hm.libs_dir / RUNTIME).write_bytes(DATA)
    rt_hm.list_runtimes()

    assert local(rt_hm) == {'status': 'Verified', 'md5': MD5, 'arch': 'aarch64'}


def test_list_runtimes_verified_by_an_md5_file(rt_hm):
    (rt_hm.libs_dir / RUNTIME).write_bytes(b"other")
    (rt_hm.libs_dir / (RUNTIME + ".md5")).write_text(hashlib.md5(b"other").hexdigest() + "  " + RUNTIME + "\n")
    rt_hm.list_runtimes()

    assert local(rt_hm)['status'] == 'Verified'


def test_list_runtimes_md5_file_mismatch_is_unverified(rt_hm):
    (rt_hm.libs_dir / RUNTIME).write_bytes(DATA)
    (rt_hm.libs_dir / (RUNTIME + ".md5")).write_text("0" * 32)
    rt_hm.list_runtimes()

    assert local(rt_hm)['status'] == 'Unverified'


def test_list_runtimes_broken(rt_hm):
    (rt_hm.libs_dir / RUNTIME).write_bytes(b"corrupted")
    rt_hm.list_runtimes()

    assert local(rt_hm)['status'] == 'Broken'


def test_list_runtimes_deleted_since(rt_hm):
    (rt_hm.libs_dir / RUNTIME).write_bytes(DATA)
    rt_hm.list_runtimes()
    (rt_hm.libs_dir / RUNTIME).unlink()

    rt_hm.list_runtimes()
    assert local(rt_hm)['status'] == 'Not Installed'


def test_list_runtimes_upgrades_the_old_remote_layout(rt_hm):
    rt_hm.runtimes_info["old.squashfs"] = {"name": "Old", "remote": {"name": "Old", "md5": "x", "url": "u", "size": 1}}
    rt_hm.list_runtimes()

    assert rt_hm.runtimes_info["old.squashfs"]['remote'] == {"aarch64": {"name": "Old", "md5": "x", "url": "u", "size": 1}}


def test_list_runtimes_nothing_changed_doesnt_save(rt_hm, monkeypatch):
    rt_hm.list_runtimes()
    saved = []
    monkeypatch.setattr(rt_hm, "save_config", lambda: saved.append(1))

    rt_hm.list_runtimes()
    assert saved == []


################################################################################
## check_runtime
@pytest.mark.parametrize("runtime", [None, 5, ["x"]])
def test_check_runtime_not_a_name(rt_hm, runtime):
    assert rt_hm.check_runtime(runtime) == 255


@pytest.mark.parametrize("in_install, boxes", [(False, 1), (True, 0)])
def test_check_runtime_path_is_rejected(rt_hm, callback, in_install, boxes):
    assert rt_hm.check_runtime("../evil.squashfs", in_install=in_install) == 255
    assert len(callback.message_boxes) == boxes


@pytest.mark.parametrize("in_install, boxes", [(False, 1), (True, 0)])
def test_check_runtime_unknown(rt_hm, callback, in_install, boxes):
    assert rt_hm.check_runtime("nothing", in_install=in_install) == 255
    assert len(callback.message_boxes) == boxes


def test_check_runtime_downloads(rt_hm, callback):
    ## The .squashfs is optional.
    assert rt_hm.check_runtime("gmtoolkit") == 0

    assert (rt_hm.libs_dir / RUNTIME).read_bytes() == DATA
    assert local(rt_hm) == {'arch': 'aarch64', 'md5': MD5, 'status': 'Verified'}
    assert callback.message_boxes[-1].startswith("Successfully downloaded")
    assert json.loads(rt_hm.runtimes_file.read_text())[RUNTIME]['local']['status'] == 'Verified'


def test_check_runtime_creates_the_libs_dir(rt_hm):
    import shutil
    shutil.rmtree(str(rt_hm.libs_dir))

    assert rt_hm.check_runtime(RUNTIME, in_install=True) == 0
    assert (rt_hm.libs_dir / RUNTIME).is_file()


def test_check_runtime_verified(rt_hm, callback):
    (rt_hm.libs_dir / RUNTIME).write_bytes(DATA)

    assert rt_hm.check_runtime(RUNTIME) == 0
    assert rt_hm.runtime_downloads == []
    assert callback.message_boxes[-1].startswith("Verified ")
    ## Verifying reports progress, then clears it.
    assert callback.progress_calls[-1] == (None, None, None, None)


def test_check_runtime_verified_in_install(rt_hm, callback):
    (rt_hm.libs_dir / RUNTIME).write_bytes(DATA)

    assert rt_hm.check_runtime(RUNTIME, in_install=True) == 0
    assert callback.message_boxes == []
    assert any(m.startswith("Verified ") for m in callback.messages)


def test_check_runtime_update_available(rt_hm, callback):
    ## Verified against an older release's md5: the new one is downloaded.
    (rt_hm.libs_dir / RUNTIME).write_bytes(b"old build")
    rt_hm.list_runtimes()
    rt_hm.runtimes_info[RUNTIME]['local'] = {'status': 'Verified', 'md5': hashlib.md5(b"old build").hexdigest(), 'arch': 'aarch64'}

    assert rt_hm.check_runtime(RUNTIME) == 0
    assert any(m.startswith("Updating ") for m in callback.messages)
    assert (rt_hm.libs_dir / RUNTIME).read_bytes() == DATA


def test_check_runtime_broken_is_reinstalled(rt_hm, callback):
    (rt_hm.libs_dir / RUNTIME).write_bytes(b"corrupted")

    assert rt_hm.check_runtime(RUNTIME) == 0
    assert any("is broken, reinstalling" in m for m in callback.messages)
    assert (rt_hm.libs_dir / RUNTIME).read_bytes() == DATA


def test_check_runtime_unverified_is_reinstalled(rt_hm, callback):
    ## No md5 known locally, and not the remote's: treated as broken.
    (rt_hm.libs_dir / RUNTIME).write_bytes(b"unknown build")
    (rt_hm.libs_dir / (RUNTIME + ".md5")).write_text("0" * 32)

    assert rt_hm.check_runtime(RUNTIME) == 0
    assert (rt_hm.libs_dir / RUNTIME).read_bytes() == DATA


def test_check_runtime_offline(rt_hm, callback):
    rt_hm.config['offline'] = True

    assert rt_hm.check_runtime(RUNTIME) == 255
    assert "offline" in callback.message_boxes[-1]

    ## Installed is good enough when nothing can be checked.
    (rt_hm.libs_dir / RUNTIME).write_bytes(b"anything")
    assert rt_hm.check_runtime(RUNTIME) == 0
    assert rt_hm.runtime_downloads == []


def test_check_runtime_wrong_arch(rt_hm, callback):
    rt_hm.device['primary_arch'] = "riscv64"

    assert rt_hm.check_runtime(RUNTIME) == 255
    assert "riscv64" in callback.message_boxes[-1]


@pytest.mark.parametrize("in_install, boxes", [(False, 1), (True, 0)])
def test_check_runtime_download_fails(rt_hm, callback, in_install, boxes):
    rt_hm.runtime_result = None

    assert rt_hm.check_runtime(RUNTIME, in_install=in_install) == 255
    assert not (rt_hm.libs_dir / RUNTIME).exists()
    assert len(callback.message_boxes) == boxes


def test_check_runtime_download_error_cleans_up(rt_hm, callback, log_errors):
    rt_hm.runtime_result = OSError("disk full")

    assert rt_hm.check_runtime(RUNTIME) == 255
    assert not (rt_hm.libs_dir / RUNTIME).exists()
    assert any("disk full" in message for message in log_errors)


def test_check_runtime_cancelled(rt_hm, callback, monkeypatch):
    monkeypatch.setattr(type(callback), "was_cancelled", property(lambda self: True), raising=False)

    assert rt_hm.check_runtime(RUNTIME) == 255
    assert not (rt_hm.libs_dir / RUNTIME).exists()


def test_check_runtime_cancel_event_cleans_up(rt_hm):
    rt_hm.runtime_result = CancelEvent()

    assert rt_hm.check_runtime(RUNTIME, in_install=True) == 255
    assert not (rt_hm.libs_dir / RUNTIME).exists()


################################################################################
## Featured ports
def write_featured(hm, data):
    (hm.cfg_dir / "featured_ports.json").write_text(data if isinstance(data, str) else json.dumps(data))


def test_featured_ports_none(online_hm):
    (online_hm.cfg_dir / "featured_ports.json").unlink()
    assert online_hm.featured_ports() == []


@pytest.mark.parametrize("data", ["", "garbage", "{}", "null", "5"])
def test_featured_ports_bad_file(online_hm, data):
    write_featured(online_hm, data)
    assert online_hm.featured_ports() == []


def test_featured_ports_makes_its_folder(online_hm):
    import shutil
    shutil.rmtree(str(online_hm.cfg_dir / "featured_ports"))
    online_hm.featured_ports()

    assert (online_hm.cfg_dir / "featured_ports").is_dir()


def test_featured_ports_list(online_hm):
    (online_hm.cfg_dir / "featured_ports" / "best.png").write_bytes(b"png")
    write_featured(online_hm, [
        {"name": "Best", "description": "The best.", "image": "images/best.png", "ports": ["sprout.zip", "2048plus.zip", "missing.zip"]},
        ])

    featured = online_hm.featured_ports()

    assert len(featured) == 1
    assert featured[0]['name'] == "Best"
    assert featured[0]['type'] == "ports"
    assert featured[0]['image'] == str(online_hm.cfg_dir / "featured_ports" / "best.png")
    assert list(featured[0]['ports']) == ["sprout.zip", "2048plus.zip"]


def test_featured_ports_skips_bad_items(online_hm, log_errors):
    write_featured(online_hm, [
        "not a dict",
        {"description": "no name", "ports": ["sprout.zip"]},
        {"name": "", "ports": ["sprout.zip"]},
        {"name": "Old", "deprecated": True, "ports": ["sprout.zip"]},
        {"name": "No ports"},
        {"name": "Bad ports", "ports": "sprout.zip"},
        {"name": "Empty", "ports": []},
        {"name": "Unknown", "ports": ["missing.zip"]},
        {"name": "Incompatible", "ports": ["starfighter.zip"], "image": "missing.png"},
        {"name": "Good", "ports": ["sprout.zip"], "image": ""},
        ])
    online_hm.device['capabilities'].append("lowres")

    featured = online_hm.featured_ports(pre_load=True)

    assert [item['name'] for item in featured] == ["Good"]
    assert featured[0]['image'] == ""
    assert featured[0]['description'] == ""
    for error in ("Missing name", "Missing ports info", "bad ports item", "unknown port missing.zip"):
        assert any(error in message for message in log_errors), error


def test_featured_ports_errors_only_on_preload(online_hm, log_errors):
    write_featured(online_hm, [{"name": "No ports"}])
    online_hm.featured_ports()
    assert log_errors == []


def test_featured_ports_categories(online_hm, log_errors):
    write_featured(online_hm, [
        {"name": "Genres", "type": "category", "description": "By genre", "children": [
            {"name": "Puzzles", "ports": ["2048plus.zip"]},
            {"name": "Nested", "type": "category", "children": [
                {"name": "Platformers", "ports": ["sprout.zip"]},
                ]},
            {"name": "Empty nest", "type": "category", "children": []},
            ]},
        {"name": "Empty", "type": "category", "children": [{"name": "Nothing", "ports": ["missing.zip"]}]},
        {"name": "Broken", "type": "category", "children": "nope"},
        ])

    featured = online_hm.featured_ports(pre_load=True)

    assert [item['name'] for item in featured] == ["Genres"]
    genres = featured[0]
    assert genres['type'] == "category" and genres['description'] == "By genre"
    assert [child['name'] for child in genres['children']] == ["Puzzles", "Nested"]
    assert list(genres['children'][1]['children'][0]['ports']) == ["sprout.zip"]

    assert any("featured_ports[0].children[2]" not in message and "children must be a list" in message for message in log_errors)
    assert any("featured_ports[1].children[0]['ports'][0]: unknown port" in message for message in log_errors)
