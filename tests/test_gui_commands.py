# SPDX-License-Identifier: MIT
#
# The GUI's install / uninstall / update / runtime / gamelist commands (app_commands),
# on the shared headless GUI with a HarbourMaster in tmp dirs.

import hashlib
import io
import json
import zipfile

import pytest

import harbourmaster
from harbourmaster.util import net

from conftest import basic_port_files, write_port_zip, write_raw_zip


pytestmark = pytest.mark.sdl


@pytest.fixture
def app(gui, hm_dirs, monkeypatch):
    """The GUI with a HarbourMaster; message boxes are answered with A."""
    gui.hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=gui, **hm_dirs)
    monkeypatch.setattr(gui.events, "was_pressed", lambda button: button == 'A')

    boxes = []
    real_message_box = gui.message_box

    def message_box(message, *args, **kwargs):
        boxes.append(message)
        return real_message_box(message, *args, **kwargs)

    monkeypatch.setattr(gui, "message_box", message_box)
    gui.test_boxes = boxes

    yield gui

    gui.hm = None


def assert_idle(gui):
    assert gui.task is None
    assert gui.scene_list() == ["root"]


def test_do_install(app, hm_dirs, tmp_path):
    app.do_install("Test Port", str(write_port_zip(tmp_path / "testport.zip", basic_port_files())))

    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()
    assert "testport.zip" in app.hm.installed_ports
    assert app.test_boxes[-1] == "Port 'testport.zip' installed successfully."
    assert_idle(app)


@pytest.fixture
def served_zip(app, monkeypatch, tmp_path):
    """Downloads of http://pm.test/testport.zip get testport.zip, with net.download's md5 check."""
    ## URLs are refused offline; requests.get below is all the network there is.
    monkeypatch.setitem(app.hm.config, 'offline', False)
    zip_data = write_port_zip(tmp_path / "served.zip", basic_port_files()).read_bytes()
    md5_sources = []
    real_download = net.download

    def fake_get(url, stream=False, timeout=None):
        class Response:
            status_code = 200
            headers = {'Content-Length': str(len(zip_data))}

            def iter_content(self, chunk_size=1, decode_unicode=False):
                yield zip_data

        return Response()

    def download(file_name, file_url, md5_source=None, *args, **kwargs):
        md5_sources.append(md5_source)
        return real_download(file_name, file_url, md5_source, *args, **kwargs)

    monkeypatch.setattr(net.requests, "get", fake_get)
    monkeypatch.setattr(net, "download", download)
    served = type("Served", (), {})()
    served.url = "http://pm.test/testport.zip"
    served.md5 = hashlib.md5(zip_data).hexdigest()
    served.md5_sources = md5_sources
    return served


def test_do_install_checks_md5_source(app, hm_dirs, served_zip):
    ## The self-update passes version.json's md5: it was dropped, so PortMaster.zip went unchecked.
    app.do_install("Test Port", served_zip.url, md5_source=served_zip.md5)

    assert served_zip.md5_sources == [served_zip.md5]
    assert "testport.zip" in app.hm.installed_ports
    assert_idle(app)


def test_do_install_wrong_md5_installs_nothing(app, hm_dirs, served_zip):
    app.do_install("Test Port", served_zip.url, md5_source="0" * 32)

    assert served_zip.md5_sources == ["0" * 32]
    assert list(hm_dirs['ports_dir'].iterdir()) == []
    assert "Download validation failed." in app.test_boxes
    assert_idle(app)


def test_do_install_bad_zip(app, hm_dirs, tmp_path):
    app.do_install("Bad", str(write_raw_zip(tmp_path / "testport.zip", b"garbage")))

    assert list(hm_dirs['ports_dir'].iterdir()) == []
    assert app.test_boxes[-1] == "Port testport.zip failed to install."
    assert_idle(app)


def test_do_uninstall(app, hm_dirs, tmp_path):
    app.do_install("Test Port", str(write_port_zip(tmp_path / "testport.zip", basic_port_files())))
    app.port_size_files["testport.zip"] = {}

    app.do_uninstall("testport.zip")

    assert list(hm_dirs['ports_dir'].iterdir()) == []
    assert app.hm.installed_ports == {}
    assert "testport.zip" not in app.port_size_files
    assert app.test_boxes[-1] == "Successfully uninstalled Test Port"
    assert_idle(app)


def test_do_runtime_check_unknown(app):
    app.do_runtime_check("nothing.squashfs")

    ## (boxes raised on the worker pass through message_box twice: worker, then main thread)
    assert set(app.test_boxes) == {"Port nothing.squashfs contains an unknown runtime, game may not run correctly."}
    assert_idle(app)


def test_do_update_ports(app, ports_json_data, monkeypatch):
    fetched = []

    def fetch_json(url):
        fetched.append(url)
        return json.loads(json.dumps(ports_json_data))

    monkeypatch.setattr(net, "fetch_json", fetch_json)

    app.do_update_ports()

    assert len(fetched) == 2
    assert sorted(app.hm.sources['pm'].ports) == sorted(ports_json_data['ports'])
    assert_idle(app)


def test_update_gamelist_xml(app, hm_dirs, ports_json_data, tmp_path, monkeypatch):
    ## An installed port, and a gameinfo.zip in the source with its gameinfo.xml.
    app.do_install("Test Port", str(write_port_zip(tmp_path / "testport.zip", basic_port_files())))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        zf.writestr("testport/gameinfo.xml", "<gameList />")
        zf.writestr("notinstalled/gameinfo.xml", "<gameList />")

    gameinfo = buffer.getvalue()
    data = json.loads(json.dumps(ports_json_data))
    data['utils']['gameinfo.zip'].update({'md5': hashlib.md5(gameinfo).hexdigest(), 'size': len(gameinfo)})

    monkeypatch.setattr(net, "fetch_json", lambda url: json.loads(json.dumps(data)))
    app.hm.sources['pm'].update()

    def download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        file_name.write_bytes(gameinfo)
        return file_name

    monkeypatch.setattr(net, "download", download)

    added = []
    monkeypatch.setattr(app.hm.platform, "gamelist_add", lambda path: added.append(path))

    app.update_gamelist_xml()

    ## Only ports that are installed get their gameinfo.xml.
    assert added == [hm_dirs['ports_dir'] / "testport" / "gameinfo.xml"]
    assert not (hm_dirs['ports_dir'] / "notinstalled").exists()
    assert (app.hm.cfg_dir / "gameinfo_pm.zip").read_bytes() == gameinfo
    assert_idle(app)


def test_runtime_manager_shows_the_selected_runtime(app, monkeypatch):
    ## The details are filled in when the screen opens, not only after the selection moves
    ## (it showed "{runtime_info.name}" until then).
    from pugwash.scenes import RuntimesScene

    runtimes = [
        ("love_11.5.squashfs", {'name': "Love 11.5", 'remote': {'aarch64': {'size': 12582912}}}),
        ("godot_4.3.squashfs", {'name': "Godot 4.3", 'remote': {'aarch64': {'size': 1048576}}}),
        ]
    monkeypatch.setattr(app.hm, "list_runtimes", lambda: runtimes)
    for key in ('runtime_info.name', 'runtime_info.download_size'):
        app.set_data(key, None)

    scene = RuntimesScene(app)
    assert scene.last_select == "godot_4.3.squashfs"
    assert app.get_data('runtime_info.name') == "Godot 4.3"
    assert app.get_data('runtime_info.download_size') == harbourmaster.nice_size(1048576)


def test_runtime_manager_without_runtimes(app, monkeypatch):
    ## Only "Download All" (after a separator): nothing to fill in yet, and no crash.
    from pugwash.scenes import RuntimesScene

    monkeypatch.setattr(app.hm, "list_runtimes", lambda: [])
    RuntimesScene(app)
