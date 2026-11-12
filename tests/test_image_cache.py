# SPDX-License-Identifier: MIT
#
# The ImageManager's two kinds of image: the theme's (its files, found by name) stay loaded
# until the theme reloads; data images (screenshots by absolute path, QR codes) are kept in a
# cache of the most recently used, and one a region still holds loads itself again.

import pytest


pytestmark = pytest.mark.sdl


def write_png(path, width=8, height=4):
    import png
    rows = [[255, 0, 0] * width for _ in range(height)]
    with open(str(path), "wb") as fh:
        png.Writer(width, height, greyscale=False).write(fh, rows)

    return str(path)


@pytest.fixture
def images(gui, monkeypatch, tmp_path):
    """The GUI's ImageManager, loading screenshots on the main thread, with a theme folder
    of its own (theme_dir) for images found by name."""
    theme_dir = tmp_path / "theme"
    theme_dir.mkdir()
    monkeypatch.setattr(gui.images, "async_executor", None)
    gui.resources.add_path(theme_dir)
    yield gui.images, theme_dir
    gui.resources.remove_path(theme_dir)


def flood(images, tmp_path, count=None):
    """Load more data images than the cache keeps, then clean it as the main loop does."""
    for number in range(count or images.max_images + 10):
        images.load(write_png(tmp_path / f"shot{number}.png"))

    images._clean()


def test_which_images_are_data():
    from pugwash.sdl.images import ImageManager

    assert ImageManager.is_data_image("/roms/ports/PortMaster/images/shot.png")
    assert ImageManager.is_data_image("qr:https://portmaster.games")
    assert not ImageManager.is_data_image("pill_cap.png")
    assert not ImageManager.is_data_image("frames/spin_003.png")


def test_theme_images_stay_loaded(images, tmp_path):
    ## A pointer the theme doesn't list in #resources (or an animation frame): only load()
    ## knows it, and a region holds it from the start.
    images, theme_dir = images
    write_png(theme_dir / "arrow.png")
    arrow = images.load("arrow.png")

    flood(images, tmp_path)

    assert images.load("arrow.png") is arrow
    assert arrow.texture._tx is not None
    assert "arrow.png" not in images.cache


def test_a_pointer_not_in_resources_survives_scrolling(gui, images, tmp_path):
    ## The crash: scrolling past enough screenshots unloaded the list's pointer, and the next
    ## draw used its destroyed texture ("Cannot use a texture after it has been destroyed").
    from pugwash import sdl

    images, theme_dir = images
    write_png(theme_dir / "arrow.png")
    region = sdl.Region(gui, {"area": [0.1, 0.1, 0.6, 0.9], "font": "DejaVuSans.ttf", "font-size": 20,
                              "pointer": "arrow.png", "list": ["one", "two"]})
    region.selected = 0

    flood(images, tmp_path)
    region.draw(region.area)

    assert region.pointer.texture._tx is not None


def test_a_held_data_image_loads_itself_again(gui, images, tmp_path):
    ## A screenshot (or a QR code) a region still shows when the cache drops it: drawn again,
    ## not a crash.
    from pugwash import sdl

    images, _ = images
    shot = write_png(tmp_path / "held.png", 16, 9)
    region = sdl.Region(gui, {"area": [0.1, 0.1, 0.6, 0.9], "image": shot})
    held = region.image

    flood(images, tmp_path)
    assert shot not in images.images and held.texture._tx is None

    region.draw(region.area)

    assert held.texture._tx is not None
    assert (held.srcrect.w, held.srcrect.h) == (16, 9)
    ## Back in the cache, so it's unloaded again in time, and loads again if it's still shown.
    assert images.cache[0] == shot and images.load(shot).texture is held.texture


def test_held_qr_code_loads_itself_again(gui, images, tmp_path):
    images, _ = images
    qr = images.load("qr:https://portmaster.games")
    assert qr in [images.images.get(name) for name in images.cache]

    flood(images, tmp_path)
    qr.draw_in((0, 0, 50, 50))

    assert qr.texture._tx is not None


def test_theme_reload_unloads_theme_images(images, tmp_path):
    images, theme_dir = images
    write_png(theme_dir / "arrow.png")
    arrow = images.load("arrow.png")

    images.unload_all()

    assert "arrow.png" not in images.images and arrow.texture._tx is None
    ## A region of the old theme, drawn once more before the new screens replace it: nothing.
    arrow.draw_in((0, 0, 10, 10))
