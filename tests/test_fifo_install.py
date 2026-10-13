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


@pytest.fixture(scope="module")
def gui(pugwash):
    gui = pugwash.PortMasterGUI(first_scene=pugwash.BlankScene, force_theme="default_theme")
    yield gui
    gui.quit()


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


@pytest.mark.xfail(strict=True, reason="BUG: in fifo mode message boxes are off, so why an install failed is never shown")
def test_install_failure_reason_is_shown(fifo, tmp_path):
    fifo.install(str(write_raw_zip(tmp_path / "testport.zip", b"garbage")))

    assert any(m.startswith("Installation failed:") for m in fifo.shown), fifo.shown
    assert any("installed failed" in m for m in fifo.shown), fifo.shown


def test_install_missing_file(fifo, tmp_path):
    assert fifo.install(str(tmp_path / "missing.zip")) == "FAIL"


def test_install_without_arguments(fifo):
    assert fifo.install() == "FAIL"


def test_install_without_harbourmaster(fifo):
    fifo.gui.hm = None
    assert fifo.install("/some/port.zip") == "FAIL"


@pytest.mark.xfail(strict=True, reason="BUG: an exception during a fifo install leaves the done file on WAIT")
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


@pytest.mark.xfail(strict=True, reason="BUG: an exception during a fifo runtime check leaves the done file on WAIT")
def test_check_runtime_error_always_answers(fifo, press_a, monkeypatch):
    def check_runtime(runtime, port_name=None, in_install=False):
        raise RuntimeError("something broke")

    monkeypatch.setattr(fifo.gui.hm, "check_runtime", check_runtime)

    assert fifo.check_runtime("ags_3.6.squashfs") == "FAIL"
