# SPDX-License-Identifier: MIT
#
# fifo_control install / check_runtime, called directly on a headless GUI. This is
# what PortMaster.sh's autoinstall uses through PortMasterDialog.txt, which waits
# (for up to 30 minutes) until the done file stops saying WAIT.

import pytest
import requests

import harbourmaster

from conftest import basic_port_files, port_files_with, write_port_zip, write_raw_zip


pytestmark = pytest.mark.sdl


@pytest.fixture
def fifo(gui, hm_dirs, tmp_path, monkeypatch):
    """The GUI with a HarbourMaster in tmp dirs, and a fifo_config like do_fifo_control's."""
    gui.hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=gui, **hm_dirs)

    done_file = tmp_path / "pm_done"
    done_file.write_text("WAIT")

    ## Record what the messages window shows.
    shown = []
    real_message = gui.message

    def message(text):
        shown.append(text)
        real_message(text)

    monkeypatch.setattr(gui, "message", message)

    yield SimpleFifo(gui, {'done-file': done_file, 'register': {}}, shown)

    gui.hm = None


class SimpleFifo:
    def __init__(self, gui, config, shown):
        self.gui = gui
        self.config = config
        self.shown = shown

    def install(self, *args):
        self.gui.fifo_install(self.config, list(args))
        return self.config['done-file'].read_text()

    def check_runtime(self, *args):
        self.gui.fifo_check_runtime(self.config, list(args))
        return self.config['done-file'].read_text()


def test_install(fifo, hm_dirs, tmp_path):
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())

    assert fifo.install(str(zip_file)) == "OKAY"
    assert (hm_dirs['ports_dir'] / "Test Port.sh").is_file()
    assert fifo.gui.scene_list() == ["root"]


@pytest.mark.parametrize("make_zip", [
    lambda t: write_raw_zip(t / "testport.zip", b"garbage"),
    lambda t: write_port_zip(t / "testport.zip", port_files_with(port_json="{nope")),
    lambda t: write_port_zip(t / "testport.zip", {"Test Port.sh": "#!/bin/bash\n"}),
    ], ids=["not_a_zip", "bad_port_json", "no_directory"])
def test_install_bad_zip_fails(make_zip, fifo, hm_dirs, tmp_path):
    assert fifo.install(str(make_zip(tmp_path))) == "FAIL"
    assert list(hm_dirs['ports_dir'].iterdir()) == []


def test_install_failure_reason_is_shown(fifo, tmp_path):
    fifo.install(str(write_raw_zip(tmp_path / "testport.zip", b"garbage")))

    assert any(m.startswith("Installation failed:") for m in fifo.shown), fifo.shown
    assert any("failed to install" in m for m in fifo.shown), fifo.shown


def test_install_missing_file(fifo, tmp_path):
    assert fifo.install(str(tmp_path / "missing.zip")) == "FAIL"


def test_install_without_arguments(fifo):
    assert fifo.install() == "FAIL"


def test_install_without_harbourmaster(fifo):
    fifo.gui.hm = None
    assert fifo.install("/some/port.zip") == "FAIL"


@pytest.mark.parametrize("error", [
    RuntimeError("something broke"),
    harbourmaster.CancelEvent(),
    requests.exceptions.ConnectionError("no network"),
    ], ids=["exception", "cancelled", "connection_error"])
def test_install_error_always_answers(error, fifo, monkeypatch):
    def install_port(port_name, md5_source=None):
        raise error

    monkeypatch.setattr(fifo.gui.hm, "install_port", install_port)

    assert fifo.install("/some/port.zip") == "FAIL"
    ## And the GUI is left in a usable state.
    assert fifo.gui.scene_list() == ["root"]
    assert fifo.gui.task is None


@pytest.fixture
def press_a(fifo, monkeypatch):
    """fifo_check_runtime keeps message boxes on (a person is at the device), answer them."""
    monkeypatch.setattr(fifo.gui.events, "was_pressed", lambda button: button == 'A')


def test_check_runtime_unknown(fifo, press_a):
    assert fifo.check_runtime("nothing.squashfs") == "FAIL"


def test_check_runtime_without_arguments(fifo):
    assert fifo.check_runtime() == "FAIL"


def test_check_runtime_error_always_answers(fifo, press_a, monkeypatch):
    def check_runtime(runtime, port_name=None, in_install=False):
        raise RuntimeError("something broke")

    monkeypatch.setattr(fifo.gui.hm, "check_runtime", check_runtime)

    assert fifo.check_runtime("ags_3.6.squashfs") == "FAIL"


################################################################################
## Autoinstall adds ports in this fifo_control process, the launcher script then
## restarts the frontend (EmulationStation etc.) if it finds the refresh marker.
@pytest.fixture
def frontend(fifo, monkeypatch):
    monkeypatch.setattr(harbourmaster, "HM_TESTING", False)
    monkeypatch.setattr(fifo.gui.hm.platform, "ES_NAME", "emulationstation")
    return fifo.gui.hm.tools_dir / "PortMaster" / ".emulationstation-refresh"


def test_install_asks_for_a_frontend_refresh(fifo, frontend, tmp_path):
    assert fifo.install(str(write_port_zip(tmp_path / "testport.zip", basic_port_files()))) == "OKAY"
    assert frontend.is_file()


def test_failed_install_does_not_refresh(fifo, frontend, tmp_path):
    assert fifo.install(str(write_raw_zip(tmp_path / "testport.zip", b"garbage"))) == "FAIL"
    assert not frontend.exists()


@pytest.mark.parametrize("es_name", [None, "show-refresh"])
def test_no_refresh_marker_without_a_frontend_to_restart(es_name, fifo, frontend, tmp_path, monkeypatch):
    monkeypatch.setattr(fifo.gui.hm.platform, "ES_NAME", es_name)

    assert fifo.install(str(write_port_zip(tmp_path / "testport.zip", basic_port_files()))) == "OKAY"
    assert list(frontend.parent.glob(".*-refresh")) == []


################################################################################
## message_box / selection_list options
@pytest.fixture
def boxes(fifo, monkeypatch):
    shown = []

    def message_box(message, **kwargs):
        shown.append((message, kwargs))
        return True

    monkeypatch.setattr(fifo.gui, "message_box", message_box)
    return shown


@pytest.mark.parametrize("args, expected", [
    (["Hello"], ("Hello", {'want_cancel': False})),
    (["--want-cancel", "Hello"], ("Hello", {'want_cancel': True})),
    (["--ok-text", "Yes", "--cancel-text", "No", "--want-cancel", "Hello"],
        ("Hello", {'want_cancel': True, 'ok_text': "Yes", 'cancel_text': "No"})),
    (["--ok-text", "Yes", "Hello\\nWorld"], ("Hello\nWorld", {'want_cancel': False, 'ok_text': "Yes"})),
    (["--", "--not-an-option"], ("--not-an-option", {'want_cancel': False})),
    ])
def test_message_box_options(fifo, boxes, args, expected):
    fifo.gui.fifo_message_box(fifo.config, list(args))

    assert boxes == [expected]
    assert fifo.config['done-file'].read_text() == "TRUE"


def test_selection_list_options(fifo, monkeypatch):
    shown = []
    monkeypatch.setattr(fifo.gui, "show_selection_list", lambda config, register: shown.append(config) or "a")
    fifo.config['register']['things'] = {'a': {'title': "A"}}

    fifo.gui.fifo_selection_list(fifo.config, ["--ok-text=Pick", "--cancel-text=Back", "--want-cancel", "--register=things", "--want-description"])

    assert shown[0]['want_cancel']
    assert shown[0]['ok_text'] == "Pick"
    assert shown[0]['cancel_text'] == "Back"
    assert shown[0]['want_description']
    assert fifo.config['done-file'].read_text() == "a"


@pytest.mark.sdl
def test_selection_list_button_bar(fifo, gui):
    from pugwash.scenes import DialogSelectionList

    scene = DialogSelectionList(gui, {'want_cancel': True, 'ok_text': "Pick", 'cancel_text': "Back"}, {'a': {'title': "A"}})
    texts = [item for _, item in scene.tags['button_bar'].bar if isinstance(item, str)]
    assert texts == ["Pick", "Back"]


def test_register_set_info_newlines(fifo):
    fifo.gui.fifo_reg_set_info(fifo.config, ["summary", "pytest", "title:pytest: 1 failed", "description:Failed:\\ntest_one"])

    assert fifo.config['register']['summary']['pytest'] == {'title': "pytest: 1 failed", 'description': "Failed:\ntest_one"}
    assert fifo.config['done-file'].read_text() == "DONE"
