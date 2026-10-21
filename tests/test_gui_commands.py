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


def test_do_install_bad_zip(app, hm_dirs, tmp_path):
    app.do_install("Bad", str(write_raw_zip(tmp_path / "testport.zip", b"garbage")))

    assert list(hm_dirs['ports_dir'].iterdir()) == []
    assert app.test_boxes[-1] == "Port testport.zip installed failed."
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
