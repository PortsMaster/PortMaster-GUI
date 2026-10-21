# SPDX-License-Identifier: MIT
#
# pugwash.main.main(): flags, logging, offline detection, the update check, and the
# frontend refresh afterwards. SDL allows one GUI per process, so the GUI and
# HarbourMaster here are stand-ins.

import contextlib
from types import SimpleNamespace

import pytest

import harbourmaster


class FakeGUI:
    made = []

    def __init__(self, first_scene=None, force_theme=None):
        self.first_scene = first_scene
        self.force_theme = force_theme
        self.hm = None
        self.calls = []
        FakeGUI.made.append(self)

    @contextlib.contextmanager
    def enable_cancellable(self, value):
        yield

    def run_task(self, func, *args, **kwargs):
        return func(*args, **kwargs)

    def apply_button_mapping(self):
        self.calls.append('apply_button_mapping')

    def do_fifo_control(self, config, argv):
        self.calls.append(('fifo', argv))

    def run(self):
        self.calls.append('run')

    def message_box(self, text, *args, **kwargs):
        self.calls.append(('box', text))

    def request_frontend_refresh(self):
        self.calls.append('refresh')

    def quit(self):
        self.calls.append('quit')


@pytest.fixture
def main(pugwash, monkeypatch, tmp_path):
    import pugwash.main as main

    FakeGUI.made = []
    tools = tmp_path / "tools"
    (tools / "PortMaster").mkdir(parents=True)

    hms = []

    def make_hm(config, temp_dir=None, callback=None):
        platform = SimpleNamespace(ES_NAME=main.ES_NAME, ports_changed=lambda: main.PORTS_CHANGED, ROMS_REFRESH_TEXT="")
        hm = SimpleNamespace(config=dict(config), platform=platform)
        hms.append(hm)
        return hm

    removed, added = [], []
    monkeypatch.setattr(main, "PortMasterGUI", FakeGUI)
    monkeypatch.setattr(main, "HarbourMaster", make_hm)
    monkeypatch.setattr(main, "get_ip_address", lambda: "192.168.0.2")
    monkeypatch.setattr(main, "portmaster_check_update", lambda pm, config, temp_dir: False)
    monkeypatch.setattr(main.logger, "remove", lambda handler=None: removed.append(handler))
    monkeypatch.setattr(main.logger, "add", lambda *args, **kwargs: added.append(args[0]) or len(added) + 100)
    monkeypatch.setattr(main.console, "do_color", lambda mode=None: main.COLOURS.append(mode))
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", tools)
    monkeypatch.setattr(main, "LOG_FILE_HANDLE", 7)

    main.ES_NAME = None
    main.PORTS_CHANGED = False
    main.COLOURS = []
    main.hms = hms
    main.removed = removed
    main.added = added
    main.tools = tools
    return main


def run(main, *args):
    return main.main(["pugwash", *args])


def test_runs_the_gui(main):
    assert run(main) == 0

    pm = FakeGUI.made[-1]
    assert pm.calls == ['run', 'quit']
    assert main.hms[-1].config['offline'] is False


def test_flags(main):
    assert run(main, "--quiet", "--no-check", "--no-log", "--no-colour", "--weird") == 0

    config = main.hms[-1].config
    assert config['quiet'] and config['no-check'] and config['no-log']
    assert 'weird' not in config
    assert main.COLOURS == [False]
    ## --no-log drops the log file.
    assert 7 in main.removed


def test_force_colour(main):
    run(main, "--force-colour")
    assert main.COLOURS == [True]


def test_double_dash(main):
    run(main, "--", "--quiet")
    assert main.hms[-1].config['quiet'] is False


def test_debug_flag_file(main):
    (main.tools / "PortMaster" / "debug_all_the_things_flag").write_text("")
    run(main)

    assert main.hms[-1].config['debug'] is True
    assert 0 in main.removed


def test_no_log_without_a_log_file(main, monkeypatch):
    ## logger.remove(None) removes every handler.
    monkeypatch.setattr(main, "LOG_FILE_HANDLE", None)
    assert run(main, "--no-log") == 0
    assert None not in main.removed


def test_quiet_logs_errors_only(main):
    import sys
    run(main, "--quiet")
    assert 0 in main.removed and sys.stderr in main.added


def test_offline_without_a_network(main, monkeypatch):
    monkeypatch.setattr(main, "get_ip_address", lambda: None)
    run(main)
    assert main.hms[-1].config['offline'] is True


def test_fifo_control(main):
    assert run(main, "fifo_control", "/tmp/pipe", "/tmp/done") == 0

    pm = FakeGUI.made[-1]
    assert pm.force_theme == "default_theme"
    assert pm.calls == ['apply_button_mapping', ('fifo', ['/tmp/pipe', '/tmp/done']), 'quit']
    assert pm.hm is main.hms[-1]


def test_fifo_control_without_harbourmaster(main):
    run(main, "--no-harbour", "fifo_control", "pipe", "done")

    assert FakeGUI.made[-1].hm is None
    assert main.hms == []


def test_reboot_file_skips_the_gui(main):
    (main.tools / "PortMaster" / ".pugwash-reboot").write_text("")
    run(main)
    assert FakeGUI.made[-1].calls == ['quit']


@pytest.fixture
def on_device(main, monkeypatch):
    monkeypatch.setattr(harbourmaster, "HM_TESTING", False)
    return main


def test_update_installed_quits(on_device, monkeypatch):
    monkeypatch.setattr(on_device, "portmaster_check_update", lambda pm, config, temp_dir: True)

    assert run(on_device) == 0
    assert FakeGUI.made[-1].calls == ['quit']
    assert on_device.hms == []


def test_no_check_skips_the_update_check(on_device, monkeypatch):
    def fail(*args):
        raise AssertionError("checked")

    monkeypatch.setattr(on_device, "portmaster_check_update", fail)
    run(on_device, "--no-check")


@pytest.mark.parametrize("es_name, changed, expected", [
    (None, True, []),
    ("emulationstation", False, []),
    ("emulationstation", True, ['refresh']),
    ("show-refresh", True, ['box']),
    ])
def test_frontend_refresh(on_device, es_name, changed, expected):
    on_device.ES_NAME = es_name
    on_device.PORTS_CHANGED = changed

    run(on_device)

    calls = [call if isinstance(call, str) else call[0] for call in FakeGUI.made[-1].calls]
    assert calls == ['run'] + expected + ['quit']
