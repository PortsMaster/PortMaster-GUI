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


@pytest.fixture
def bar_progress_theme(gui):
    """The message window's progress as a bar, like jimmyhat999_grid_dark does it."""
    import copy

    saved = copy.deepcopy(gui.theme_data['message_window'])
    progress = gui.theme_data['message_window']['progress_bar']
    progress.pop('text', None)
    progress['bar'] = ["{system.progress_text}", None, "{system.progress_amount}"]

    yield gui.theme_data['message_window']['progress_bar']

    gui.theme_data['message_window'] = saved


def progress_bar_strings(gui):
    region = gui.message_box_scene.tags['progress_bar']
    ## The region lays its bar out as (dest rect, item) pairs.
    return [item for dest, item in region.bar if isinstance(item, str)]


def test_bar_template_filled_on_first_display(gui, bar_progress_theme):
    gui.progress(None, None, None)

    with gui.enable_messages():
        assert progress_bar_strings(gui) == ["", ""]

        gui.progress("Downloading", 1, 4, 'data')
        assert progress_bar_strings(gui) == ["Downloading", "1 B / 4 B"]


def test_bar_template_still_updates_in_later_windows(gui, bar_progress_theme):
    with gui.enable_messages():
        gui.progress("First", 1, 2)

    ## The theme's own data must not be overwritten with the values.
    assert bar_progress_theme['bar'] == ["{system.progress_text}", None, "{system.progress_amount}"]

    with gui.enable_messages():
        gui.progress("Second", 1, 2)
        assert progress_bar_strings(gui)[0] == "Second"


################################################################################
## Port screenshots: no stale image when a ports list opens, and neighbours load ahead.
@pytest.fixture
def screenshot_ports(gui, tmp_path, monkeypatch):
    """A fake hm with 12 ports, each with its own screenshot."""
    from types import SimpleNamespace

    ports = {}
    images = {}
    for i in range(12):
        name = f"port{i:02}.zip"
        images[name] = str(write_png(tmp_path / f"port{i:02}.png"))
        ports[name] = {'name': name, 'attr': {
            'title': f"Port {i}", 'desc': "", 'inst': "", 'genres': [], 'porter': ["someone"],
            'rtr': True, 'runtime': []}}

    hm = SimpleNamespace(
        port_images=lambda name: {'screenshot': images[name]},
        port_download_size=lambda name: 0,
        libs_dir=tmp_path)
    monkeypatch.setattr(gui, "hm", hm)
    monkeypatch.setattr(gui.images, "max_images", gui.images.max_images)
    return SimpleNamespace(ports=ports, images=images)


def featured_scene(gui, ports):
    from pugwash.scenes.ports import FeaturedPortsScene
    return FeaturedPortsScene(gui, {'name': "Test", 'description': "", 'image': "NO_IMAGE", 'ports': ports})


def test_ports_list_opens_with_its_own_screenshot(gui, screenshot_ports):
    ## The previous list's port must not be what the new list draws first.
    gui.set_data("port_info.image", screenshot_ports.images["port11.zip"])
    gui.set_data("port_info.title", "Port 11")

    scene = featured_scene(gui, screenshot_ports.ports)

    assert gui.get_data("port_info.image") == screenshot_ports.images["port00.zip"]
    assert gui.get_data("port_info.title") == "Port 0"

    scene.update_data(set(gui.changed_keys))
    shown = [region.image for region, text in scene.image_regions.values() if "port_info.image" in text]
    assert shown and all(image is gui.images.images[screenshot_ports.images["port00.zip"]] for image in shown)


def test_list_loads_neighbouring_screenshots(gui, screenshot_ports):
    scene = featured_scene(gui, screenshot_ports.ports)
    assert scene.tags['ports_list'].list_columns == 1

    for name in screenshot_ports.images.values():
        gui.images.images.pop(name, None)
        gui.images.cache = [cached for cached in gui.images.cache if cached != name]

    scene.tags['ports_list'].selected = 5
    scene.show_selected_port()
    ## The scene isn't pushed, so hand it the changed keys like do_update would.
    scene.update_data(set(gui.changed_keys))

    loaded = {i for i in range(12) if screenshot_ports.images[f"port{i:02}.zip"] in gui.images.images}
    assert loaded == set(range(2, 9))
    ## The selected port's image is the newest in the cache.
    assert gui.images.cache[0] == screenshot_ports.images["port05.zip"]


def test_grid_keeps_rows_either_side_loaded(gui, tmp_path, monkeypatch):
    from pugwash import sdl

    files = [str(write_png(tmp_path / f"tile{i:02}.png")) for i in range(60)]
    monkeypatch.setattr(gui.images, "max_images", gui.images.max_images)
    region = sdl.Region(gui, {"area": [0.0, 0.0, 1.0, 0.5], "font": "DejaVuSans.ttf", "list-columns": 3, "item-size": 60})
    region.list = [f"Tile {i}" for i in range(60)]
    region.list_image = lambda i: files[i] if i < len(files) else None

    def loaded():
        return {i for i, name in enumerate(files) if name in gui.images.images}

    region.draw(region.area)
    page = region.page_size
    preload = sdl.Region.GRID_PRELOAD_ROWS * 3
    assert 0 < page and page + preload * 2 < 60
    assert loaded() == set(range(page + preload))
    assert gui.images.max_images >= page + preload * 2

    ## Halfway down the list the rows above stay loaded too.
    region.selected = 30
    region.draw(region.area)
    start = region.grid_start_row * 3
    assert loaded() >= set(range(start - preload, start + page + preload))

    gui.images._clean()
    assert set(range(start - preload, start + page + preload)) <= loaded()


def test_image_keep_only_raises():
    from pugwash.sdl.images import ImageManager

    images = ImageManager.__new__(ImageManager)
    images.max_images = 30
    images.keep(40)
    assert images.max_images == 40 + ImageManager.MAX_IMAGES // 2
    images.keep(5)
    assert images.max_images == 40 + ImageManager.MAX_IMAGES // 2
