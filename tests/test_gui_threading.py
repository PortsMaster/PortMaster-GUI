# SPDX-License-Identifier: MIT
#
# PortMasterGUI.run_task and the thread aware callbacks, using a real (headless)
# PortMasterGUI in this process.

import os
import threading
import time

import pytest

import harbourmaster
from pugwash import tasks as pugtask

from conftest import PYLIB_PATH


pytestmark = pytest.mark.sdl


@pytest.fixture
def count_frames(gui, monkeypatch):
    """Counts main loop iterations, optionally running a hook each frame."""
    frames = []
    original = gui.do_update

    def do_update():
        frames.append(time.monotonic())
        hook = getattr(gui, '_test_frame_hook', None)
        if hook is not None:
            hook(len(frames))

        original()

    monkeypatch.setattr(gui, "do_update", do_update)
    yield frames
    gui._test_frame_hook = None


def press(gui, monkeypatch, button):
    """Make `button` look pressed to message boxes."""
    monkeypatch.setattr(gui.events, "was_pressed", lambda name: name == button)


def test_run_task_returns_result_from_worker(gui):
    def work(a, b=0):
        return (a + b, pugtask.on_main_thread())

    assert gui.run_task(work, 1, b=2) == (3, False)
    assert gui.task is None


def test_run_task_reraises(gui):
    def work():
        raise KeyError("boom")

    with pytest.raises(KeyError):
        gui.run_task(work)

    assert gui.task is None


def test_run_task_keeps_rendering(gui, count_frames):
    ## The worker only reports progress twice, the old code would have drawn twice.
    def work():
        gui.progress("Working", 1, 2)
        time.sleep(0.5)
        gui.progress("Working", 2, 2)

    gui.run_task(work)

    assert len(count_frames) >= 8, count_frames


def test_progress_from_worker_is_applied_on_main(gui):
    def work():
        for i in range(100):
            gui.progress("Downloading", i + 1, 100)

    gui.run_task(work)

    assert gui.callback_amount == 100
    assert gui.pending_progress is None


def test_messages_from_worker(gui):
    with gui.enable_messages():
        def work():
            gui.message("hello from the worker")

        gui.run_task(work)

        assert "hello from the worker" in gui.callback_messages
        assert gui.scene_list()[-1] == "messages"

    assert gui.scene_list() == ["root"]


def test_enable_messages_from_worker(gui):
    seen = []

    def work():
        with gui.enable_messages():
            gui.message("inside")
            seen.append(gui.dispatcher.call(gui.scene_list))

    gui.run_task(work)

    assert seen == [["root", "messages"]]
    assert gui.scene_list() == ["root"]


def test_cancel_raises_in_worker(gui, count_frames):
    reached_end = []

    def work():
        for i in range(500):
            gui.progress("Working", i, 500)
            time.sleep(0.01)

        reached_end.append(True)

    gui._test_frame_hook = lambda frame: frame == 3 and gui.do_cancel()

    with gui.enable_cancellable(True):
        gui.run_task(work)

    assert gui.was_cancelled is True
    assert reached_end == []
    assert gui.task is None


def test_cancel_ignored_when_not_cancellable(gui, count_frames):
    def work():
        for i in range(20):
            gui.progress("Working", i, 20)
            time.sleep(0.01)

        return "finished"

    gui._test_frame_hook = lambda frame: frame == 3 and gui.do_cancel()

    with gui.enable_cancellable(False):
        assert gui.run_task(work) == "finished"

    assert gui.was_cancelled is False


def test_worker_cannot_make_itself_cancellable_through_message_box(gui, monkeypatch):
    ## message_box normally makes things cancellable while it is open, during a task it
    ## must leave that alone or the worker's own setting gets clobbered.
    press(gui, monkeypatch, 'A')
    states = []

    def work():
        with gui.enable_cancellable(False):
            gui.message_box("Hello")
            states.append(gui.cancellable)

    with gui.enable_cancellable(True):
        gui.run_task(work)

    assert states == [False]


@pytest.mark.parametrize("button, expected", [('A', True), ('B', False)])
def test_message_box_from_worker(gui, monkeypatch, button, expected):
    press(gui, monkeypatch, button)
    layers = []

    def work():
        result = gui.message_box("Are you sure?", want_cancel=True)
        layers.append(gui.dispatcher.call(gui.scene_list))
        return result

    assert gui.run_task(work) is expected
    assert layers == [["root"]]


def test_message_box_disabled_from_worker(gui):
    def work():
        with gui.disable_messagebox():
            return gui.message_box("Not shown", want_cancel=True)

    assert gui.run_task(work) is False


def test_nested_run_task_from_worker_runs_inline(gui):
    def inner():
        return threading.current_thread().name

    def outer():
        return (threading.current_thread().name, gui.run_task(inner))

    outer_name, inner_name = gui.run_task(outer)
    assert outer_name == inner_name


def test_lower_layers_only_get_data_after_task(gui):
    seen = []

    class Recorder:
        active = False

        def update_data(self, keys):
            seen.append(set(keys))

        def do_update(self, events):
            return False

        def do_draw(self):
            pass

        def scene_deactivate(self):
            pass

        def scene_activate(self):
            pass

    root_scenes = gui.scenes[0][1]
    root_scenes.append(Recorder())

    try:
        with gui.enable_messages():
            def work():
                gui.dispatcher.call(gui.set_data, "test.key", "1")
                time.sleep(0.2)
                return list(seen)

            during = gui.run_task(work)

        gui.do_loop(no_delay=True)

    finally:
        root_scenes.pop()

    assert not any("test.key" in keys for keys in during)
    assert any("test.key" in keys for keys in seen)


def test_dir_scanner_runs_in_background(gui, tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "file.bin").write_bytes(b"x" * 1234)

    assert gui.dir_scanner.check_directory(tmp_path / "data", False) is None

    end = time.monotonic() + 5
    while gui.dir_scanner.check_directory(tmp_path / "data", False) is None:
        gui.do_loop(no_delay=True)
        assert time.monotonic() < end

    assert gui.dir_scanner.check_directory(tmp_path / "data", False) == 1234


def write_png(path, width=8, height=4):
    import png
    rows = [[255, 0, 0] * width for _ in range(height)]
    with open(str(path), "wb") as fh:
        png.Writer(width, height, greyscale=False).write(fh, rows)

    return path


def test_screenshots_load_in_background(gui, tmp_path):
    from pugwash import sdl

    image_file = str(write_png(tmp_path / "screenshot.png"))
    image = gui.images.load(image_file)

    assert isinstance(image, sdl.PendingImage)
    assert gui.images.load(image_file) is image
    ## Drawing before it has loaded is harmless.
    image.draw_in((0, 0, 10, 10))

    end = time.monotonic() + 5
    while not image.loaded:
        gui.do_loop(no_delay=True)
        assert time.monotonic() < end

    assert (image.srcrect.w, image.srcrect.h) == (8, 4)
    assert gui.images.textures[image_file] is image.texture


def test_theme_images_still_load_immediately(gui):
    from pugwash import sdl

    ## Theme assets are found by name through the resource paths.
    for name in os.listdir(str(PYLIB_PATH / "default_theme")):
        if name.endswith(".png"):
            break
    else:
        pytest.skip("default theme has no png images")

    image = gui.images.load(name)
    assert image is not None
    assert not isinstance(image, sdl.PendingImage)


def test_unloading_while_decoding_is_safe(gui, tmp_path, monkeypatch):
    image_file = str(write_png(tmp_path / "evicted.png"))
    image = gui.images.load(image_file)

    ## Evict everything straight away, the finished decode must be dropped.
    monkeypatch.setattr(gui.images, "max_images", 0)
    gui.images._clean()

    time.sleep(0.2)
    gui.do_loop(no_delay=True)

    assert image_file not in gui.images.images
    assert image_file not in gui.images.textures
    assert not image.loaded


@pytest.fixture
def presented(gui, monkeypatch):
    """Counts frames actually put on screen."""
    count = []
    real_present = gui.renderer.present

    def present():
        count.append(gui.scene_list())
        real_present()

    monkeypatch.setattr(gui.renderer, "present", present)
    return count


def test_task_without_its_own_window_does_not_redraw(gui, presented):
    ## Startup (version check, loading sources) runs as tasks over the empty first scene,
    ## drawing that scene just flashes a blank screen over the splash.
    gui.updated = True

    gui.run_task(time.sleep, 0.3)

    assert presented == []


def test_task_redraws_its_messages_window(gui, presented):
    with gui.enable_messages():
        def work():
            for i in range(5):
                gui.progress("Working", i, 5)
                time.sleep(0.05)

        gui.run_task(work)

    assert presented and all(layers[-1] == "messages" for layers in presented)


def test_task_that_opens_messages_is_drawn(gui, presented):
    ## HarbourMaster's startup opens the messages window from the worker.
    def work():
        with gui.enable_messages():
            gui.message("Loading...")
            time.sleep(0.2)

    gui.run_task(work)

    assert presented and all(layers[-1] == "messages" for layers in presented)
