# SPDX-License-Identifier: MIT
#
# pugwash's fifo_control commands (app_fifo.py) other than install / autoinstall, and
# the do_fifo_control loop itself, in-process on the shared headless GUI.

import json
import stat
import threading
import time

import pytest


pytestmark = pytest.mark.sdl


class FifoWriter:
    """What PortMasterDialog.txt does: write a command, wait for the done file to answer."""
    TIMEOUT = 10

    def __init__(self, pipe, done):
        self.pipe = pipe
        self.done = done

    def wait_ready(self):
        end = time.monotonic() + self.TIMEOUT
        while time.monotonic() < end:
            try:
                if stat.S_ISFIFO(self.pipe.stat().st_mode) and self.done.read_text() == "DONE":
                    return
            except OSError:
                pass

            time.sleep(0.01)

        raise AssertionError("fifo_control never started")

    def send_raw(self, text):
        with open(str(self.pipe), "w") as fh:
            fh.write(text)

    def send(self, *args):
        self.done.write_text("WAIT")
        self.send_raw("".join(f"{arg}\1" for arg in args) + "\n")

        end = time.monotonic() + self.TIMEOUT
        while time.monotonic() < end:
            answer = self.done.read_text()
            if answer not in ("", "WAIT"):
                return answer

            time.sleep(0.01)

        raise AssertionError(f"no answer to {args}")


@pytest.fixture
def fifo(gui, tmp_path, monkeypatch):
    from pugwash import tasks

    done = tasks.DoneFile(tmp_path / "pm_done")
    done.write_text("WAIT")
    config = {'done-file': done, 'register': {}}

    calls = []
    monkeypatch.setattr(gui, "message", lambda text: calls.append(('message', text)))
    monkeypatch.setattr(gui, "progress", lambda *args: calls.append(('progress',) + args))
    gui.fifo_calls = calls

    def run(command, *args):
        getattr(gui, f"fifo_{command}")(config, list(args))
        return done.read_text()

    gui.run_fifo = run
    gui.fifo_config = config
    yield gui

    while gui.message_box_depth > 0:
        gui.messages_end(internal=True)


################################################################################
## Registers
def test_register_set_and_dump(fifo):
    assert fifo.run_fifo("reg_set_info", "ports", "a.zip", "title:A Port", "desc:line one\\nline two", "no colon") == "DONE"
    assert fifo.run_fifo("reg_set_info", "ports", "a.zip", "status:ok") == "DONE"

    assert json.loads(fifo.run_fifo("reg_dump", "ports")) == {
        "a.zip": {"title": "A Port", "desc": "line one\nline two", "status": "ok"}}


@pytest.mark.parametrize("command, args", [
    ("reg_set_info", ("ports", "a.zip")),
    ("reg_clear_info", ("ports",)),
    ("reg_clear", ()),
    ("reg_dump", ()),
    ("reg_dump", ("missing",)),
    ])
def test_register_bad_arguments(fifo, command, args):
    assert fifo.run_fifo(command, *args) == "FAIL"


def test_register_clear_info(fifo):
    ## It unpacked three values from two: every call raised ValueError.
    fifo.run_fifo("reg_set_info", "ports", "a.zip", "title:A")
    fifo.run_fifo("reg_set_info", "ports", "b.zip", "title:B")

    assert fifo.run_fifo("reg_clear_info", "ports", "a.zip") == "DONE"
    assert json.loads(fifo.run_fifo("reg_dump", "ports")) == {"b.zip": {"title": "B"}}

    ## Not there: still done.
    assert fifo.run_fifo("reg_clear_info", "ports", "missing.zip") == "DONE"
    assert fifo.run_fifo("reg_clear_info", "other", "x") == "DONE"


def test_register_clear(fifo):
    fifo.run_fifo("reg_set_info", "ports", "a.zip", "title:A")

    assert fifo.run_fifo("reg_clear", "ports") == "DONE"
    assert fifo.run_fifo("reg_dump", "ports") == "FAIL"
    assert fifo.run_fifo("reg_clear", "ports") == "DONE"


################################################################################
## Messages and progress
def test_messages(fifo):
    assert fifo.run_fifo("messages_end") == "FAIL"
    assert fifo.run_fifo("messages_begin") == "DONE"
    ## Not twice.
    assert fifo.run_fifo("messages_begin") == "FAIL"

    assert fifo.run_fifo("message", "Hello\\nWorld") == "DONE"
    assert fifo.run_fifo("message") == "FAIL"
    assert ('message', "Hello\nWorld") in fifo.fifo_calls

    assert fifo.run_fifo("messages_end") == "DONE"


@pytest.mark.parametrize("args, expected", [
    (("Copying",), ("Copying", 0, 100, None)),
    (("Copying", "5"), ("Copying", 5, 100, None)),
    (("Copying", "5", "20"), ("Copying", 5, 20, None)),
    (("Copying", "30", "20"), ("Copying", 20, 30, None)),
    (("Copying", "0", "0"), ("Copying", 0, 100, None)),
    (("Copying", "x", "y"), ("Copying", 0, 100, None)),
    ## The format: it went into total, so it was never used (and "abc" as the total crashed).
    (("Copying", "5", "20", "data"), ("Copying", 5, 20, 'data')),
    (("Copying", "5", "abc", "%"), ("Copying", 5, 100, '%')),
    (("Copying", "5", "20", "bogus"), ("Copying", 5, 20, None)),
    ])
def test_progress(fifo, args, expected):
    assert fifo.run_fifo("progress", *args) == "DONE"
    assert fifo.fifo_calls[-1] == ('progress',) + expected


def test_progress_bad(fifo):
    assert fifo.run_fifo("progress") == "FAIL"
    assert fifo.run_fifo("progress_clear") == "DONE"
    assert fifo.fifo_calls[-1] == ('progress', None, None, None)


################################################################################
## Message boxes and selection lists (their option parsing)
@pytest.fixture
def boxes(fifo, monkeypatch):
    shown = []
    fifo.box_answer = True

    def message_box(text, **kwargs):
        shown.append((text, kwargs))
        return fifo.box_answer

    monkeypatch.setattr(fifo, "message_box", message_box)
    return shown


@pytest.mark.parametrize("args", [(), ("--want-cancel",), ("--weird",)])
def test_message_box_nothing_to_show(fifo, boxes, args):
    assert fifo.run_fifo("message_box", *args) == "TRUE"
    assert boxes == []


def test_message_box(fifo, boxes):
    assert fifo.run_fifo("message_box", "--want-cancel", "--ok-text", "Yes", "--cancel-text", "No", "--odd", "Line\\nTwo") == "TRUE"
    assert boxes == [("Line\nTwo", {'want_cancel': True, 'ok_text': "Yes", 'cancel_text': "No"})]

    fifo.box_answer = False
    assert fifo.run_fifo("message_box", "Again") == "FALSE"


def test_message_box_double_dash(fifo, boxes):
    assert fifo.run_fifo("message_box", "--", "--not an option") == "TRUE"
    assert boxes[-1][0] == "--not an option"


def test_message_box_option_without_its_value(fifo, boxes):
    ## A trailing --ok-text has nothing to take: it's dropped.
    assert fifo.run_fifo("message_box", "Text", "--ok-text") == "TRUE"
    assert boxes[-1] == ("Text", {'want_cancel': False})


@pytest.fixture
def selections(fifo, monkeypatch):
    shown = []
    fifo.selection_answer = "b"

    def show_selection_list(config, register):
        shown.append((config, register))
        return fifo.selection_answer

    monkeypatch.setattr(fifo, "show_selection_list", show_selection_list)
    return shown


def test_selection_list_options(fifo, selections):
    fifo.run_fifo("reg_set_info", "choices", "b", "title:B")

    assert fifo.run_fifo(
        "selection_list", "--cancel-text=Nope", "--ok-text=Yep", "--register=choices",
        "--want-cancel", "--want-description", "--want-images", "--strange", "Title") == "b"

    config, register = selections[-1]
    assert config['cancel_text'] == "Nope" and config['ok_text'] == "Yep"
    assert config['want_cancel'] and config['want_description'] and config['want_images']
    assert register == {"b": {"title": "B"}}


def test_selection_list_defaults(fifo, selections):
    fifo.run_fifo("selection_list", "--register=missing", "--", "--want-cancel")

    config, register = selections[-1]
    assert config['want_cancel'] is False
    assert register == {}


def test_selection_list_cancelled(fifo, selections):
    fifo.selection_answer = fifo.SELECTION_CANCELLED
    assert fifo.run_fifo("selection_list", "--want-cancel") == "CANCEL"


################################################################################
## The loop
def test_fifo_control_needs_two_paths(gui):
    ## It checked the length of the second path, not of the arguments.
    assert gui.do_fifo_control({}, ["only-one"]) == 0
    assert gui.do_fifo_control({}, []) == 0


def test_fifo_control_loop(gui, tmp_path, monkeypatch):
    pipe = tmp_path / "pg_input"
    done = tmp_path / "pg_done"
    ## Left over from a crashed run.
    pipe.write_text("old")
    done.write_text("old")

    def explode(self, fifo_config, args):
        raise RuntimeError("boom")

    monkeypatch.setitem(type(gui).fifo_commands, 'explode', explode)

    writer = FifoWriter(pipe, done)
    answers = {}

    def script():
        writer.wait_ready()
        answers['set'] = writer.send("register_set_info", "r", "k", "a:1")
        answers['dump'] = writer.send("REGISTER_DUMP", "r")
        answers['unknown'] = writer.send("frobnicate")
        answers['explode'] = writer.send("explode")
        answers['after'] = writer.send("register_dump", "r")
        writer.send_raw("exit\n")

    thread = threading.Thread(target=script, daemon=True)
    thread.start()

    assert gui.do_fifo_control({}, [str(pipe), str(done)]) == 0
    thread.join(10)

    assert answers['set'] == "DONE"
    assert json.loads(answers['dump']) == {"k": {"a": "1"}}
    assert answers['unknown'] == "DONE"
    ## A command that raises still answers, and the loop carries on.
    assert answers['explode'] == "FAIL"
    assert json.loads(answers['after']) == {"k": {"a": "1"}}

    assert done.read_text() == "DONE"
    assert not pipe.exists()
