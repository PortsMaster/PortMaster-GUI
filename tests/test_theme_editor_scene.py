# SPDX-License-Identifier: MIT
#
# Options -> Theme Editor (pugwash/scenes/theme_server.py) with a fake server process:
# what it starts, and what the screen says when it can't start, the device has no network,
# or the server stops by itself. test_theme_server.py runs the real server.

import io
import json
import subprocess
import time

import pytest

import harbourmaster


pytestmark = pytest.mark.sdl


class FakeProc:
    """A theme server process: answers `line` on stdout, then exits with `returncode` when asked."""
    made = []

    def __init__(self, command, line='{"ok": true, "ready": true, "port": 51234}\n', stays_up=True, slow_to_stop=False, **kwargs):
        self.command = command
        self.kwargs = kwargs
        self.stdout = io.StringIO(line)
        self.stdin = io.StringIO()
        self.returncode = None if stays_up else 3
        self.slow_to_stop = slow_to_stop
        self.killed = False
        FakeProc.made.append(self)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        if self.slow_to_stop:
            raise subprocess.TimeoutExpired("theme_server", timeout)
        self.returncode = 0
        return 0

    def kill(self):
        self.killed = True
        self.returncode = -9


@pytest.fixture
def editor(gui, hm_dirs, monkeypatch):
    """start(**fake_proc_options) -> the scene, once the fake server has answered."""
    from pugwash.scenes import theme_server as scene_module

    FakeProc.made = []
    gui.hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=gui, **hm_dirs)
    saved_scenes = list(gui.scenes)
    monkeypatch.setattr(scene_module, "get_ip_address", lambda force_update=False: "192.168.1.50")

    def start(**options):
        def popen(command, **kwargs):
            if options.get('fail'):
                raise OSError(2, "No such file or directory")
            return FakeProc(command, **{key: value for key, value in options.items() if key != 'fail'}, **kwargs)

        monkeypatch.setattr(scene_module.subprocess, "Popen", popen)
        scene = scene_module.ThemeServerScene(gui)
        gui.push_scene('theme-editor', scene)
        end = time.monotonic() + 10
        while gui.text_data.get('theme_server.status') == scene_module._("Starting the theme editor...") and time.monotonic() < end:
            gui.do_loop(no_delay=True)
        gui.do_loop(no_delay=True)
        return scene

    start.module = scene_module
    yield start

    gui.scenes = saved_scenes
    gui.hm = None


def status(gui):
    return gui.text_data.get('theme_server.status', "")


################################################################################
def test_command(editor, gui, hm_dirs):
    scene = editor()
    command = FakeProc.made[0].command

    assert command[1:4] == ["-m", "theme_server.serve", "--managed"]
    port = int(command[command.index("--port") + 1])
    assert editor.module.PORT_RANGE[0] <= port <= editor.module.PORT_RANGE[1]
    assert "--any-port" in command and command[command.index("--try-ports") + 1] == "20"
    assert command[command.index("--themes") + 1] == str(gui.hm.themes_dir)
    assert command[command.index("--ports-config") + 1] == str(gui.hm.cfg_dir)
    assert 1 <= int(command[command.index("--max-workers") + 1]) <= editor.module.MAX_WORKERS
    ## pylibs and exlibs for the server's imports; its log next to pugwash.txt.
    assert "pylibs" in FakeProc.made[0].kwargs['env']['PYTHONPATH']
    assert (gui.hm.cfg_dir.parent / "theme_server.txt").is_file()

    assert scene.url == "http://192.168.1.50:51234/"
    assert gui.text_data['theme_server.url'] == scene.url and scene.url in status(gui)
    assert gui.hm.cfg_data['theme_server_port'] == 51234


def test_cannot_start(editor, gui):
    scene = editor(fail=True)
    assert "Unable to start the theme editor" in status(gui) and "No such file" in status(gui)
    assert scene.proc is None and gui.text_data['theme_server.url'] == ""


def test_server_says_no(editor, gui):
    scene = editor(line=json.dumps({"ok": False, "error": "port 51234 is busy"}) + "\n")
    assert "port 51234 is busy" in status(gui)
    assert scene.proc is None and scene.stopped


@pytest.mark.parametrize("line, shown", [("", "it stopped"), ("Traceback: boom\n", "Traceback: boom")])
def test_server_dies_before_it_answers(editor, gui, line, shown):
    editor(line=line)
    assert "Unable to start the theme editor" in status(gui) and shown in status(gui)


def test_no_network(editor, gui, monkeypatch):
    monkeypatch.setattr(editor.module, "get_ip_address", lambda force_update=False: None)
    scene = editor()
    assert "isn't on a network" in status(gui)
    assert scene.url is None and gui.text_data['theme_server.url'] == ""


def test_server_stops_by_itself(editor, gui):
    scene = editor()
    FakeProc.made[0].returncode = 1
    gui.do_loop(no_delay=True)

    assert "theme_server.txt" in status(gui)
    assert scene.proc is None and scene.url is None and gui.text_data['theme_server.url'] == ""


def test_b_stops_it(editor, gui, monkeypatch):
    scene = editor()
    proc = FakeProc.made[0]
    monkeypatch.setattr(gui.events, "was_pressed", lambda button: button == 'B')
    gui.do_loop(no_delay=True)

    end = time.monotonic() + 5
    while proc.returncode is None and time.monotonic() < end:
        time.sleep(0.01)
    assert proc.stdin.closed and proc.returncode == 0 and not proc.killed
    assert scene.stopped and gui.scenes[-1][1][-1] is not scene


def test_a_server_that_wont_stop_is_killed(editor, gui):
    scene = editor(slow_to_stop=True)
    proc = FakeProc.made[0]
    scene.stop()

    end = time.monotonic() + 5
    while not proc.killed and time.monotonic() < end:
        time.sleep(0.01)
    assert proc.killed


def test_stopping_twice(editor, gui):
    scene = editor()
    scene.stop()
    scene.stop()
    ## A late answer after it was stopped changes nothing.
    scene.started({'ok': True, 'port': 1})
    assert scene.url == "http://192.168.1.50:51234/"


def test_kept_port_is_used_again(editor, gui):
    gui.hm.cfg_data['theme_server_port'] = 55555
    editor(line='{"ok": true, "port": 55555}\n')
    command = FakeProc.made[0].command
    assert command[command.index("--port") + 1] == "55555"


################################################################################
## Its screen
def test_screen_only(editor, gui):
    ## start=False: the theme server's own preview of this screen.
    scene = editor.module.ThemeServerScene(gui, start=False)
    assert scene.proc is None and FakeProc.made == []


def test_plain_screen_for_themes_without_one(editor, gui, monkeypatch):
    monkeypatch.delitem(gui.theme_data, "theme_server", raising=False)
    editor()
    section = gui.theme_data["theme_server"]
    assert section["server_qr"]["image"] == "qr:{theme_server.url}"
    assert section["server_info"]["text"] == "{theme_server.status}"


@pytest.mark.parametrize("lang, font", [("en_US", "DejaVuSans.ttf"), ("ja_JP", "NotoSansJP-Regular.ttf"), ("ko_KR", "NotoSansKR-Regular.ttf")])
def test_plain_screen_font_for_the_language(editor, monkeypatch, lang, font):
    from pugwash import lang as pug_lang
    monkeypatch.setattr(pug_lang, "CURRENT_LANG", lang)
    section = editor.module.fallback_section()
    assert {region.get("font") for region in section.values() if "font" in region} == {font}


@pytest.mark.parametrize("available_mb, expected", [(100, 1), (300, 1), (350, 2), (550, 4), (8000, 4)])
def test_worker_count(editor, tmp_path, available_mb, expected):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(f"MemTotal: 999999 kB\nMemFree: 1 kB\nMemAvailable: {available_mb * 1024} kB\n")
    assert editor.module.worker_count(str(meminfo)) == expected


@pytest.mark.parametrize("contents", ["", "MemAvailable: lots kB\n", "MemTotal: 5 kB\n"])
def test_worker_count_unreadable(editor, tmp_path, contents):
    meminfo = tmp_path / "meminfo"
    meminfo.write_text(contents)
    assert editor.module.worker_count(str(meminfo)) == 2
