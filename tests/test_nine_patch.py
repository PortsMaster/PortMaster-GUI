# SPDX-License-Identifier: MIT
#
# 9-patch images (a region's "patch"): the corners drawn as they are, the edges and middle
# stretched, or with "patch-repeat" repeated at their own size and cut off where the box ends.

from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.sdl


def write_png(path, width, height):
    import png
    rows = [[v for x in range(width) for v in ((x * 7) % 256, (y * 5) % 256, 128, 255)] for y in range(height)]
    with open(str(path), "wb") as fh:
        png.Writer(width, height, greyscale=False, alpha=True).write(fh, rows)
    return str(path)


@pytest.fixture
def patch_region(gui, tmp_path, monkeypatch):
    """make(**keys) -> (region, copies): a 9-patch region of a 40x30 picture with [ 10, 5, 10, 5 ]
    edges, whose drawing is recorded as (src, dst) rects instead of drawn."""
    from pugwash import sdl

    monkeypatch.setattr(gui.images, "async_executor", None)
    picture = write_png(tmp_path / "panel.png", 40, 30)

    def make(**keys):
        data = {"area": [0, 0, 1.0, 1.0], "image": picture, "patch": [10, 5, 10, 5]}
        data.update({key.replace("_", "-"): value for key, value in keys.items()})
        region = sdl.Region(gui, data)
        copies = []
        region.renderer = SimpleNamespace(copy=lambda texture, srcrect, dstrect: copies.append((tuple(srcrect), tuple(dstrect))))
        return region, copies

    return make


def draw(region, x, y, w, h):
    from pugwash.sdl.geometry import Rect
    region._draw_patch(Rect(x, y, w, h), region.pimage)


def covered(copies):
    """Every target pixel the copies draw, and how often."""
    seen = {}
    for _, (x, y, w, h) in copies:
        for px in range(x, x + w):
            for py in range(y, y + h):
                seen[(px, py)] = seen.get((px, py), 0) + 1
    return seen


def test_stretched_is_nine_pieces(patch_region):
    region, copies = patch_region()
    draw(region, 0, 0, 100, 60)

    assert len(copies) == 9
    ## The middle: the picture's middle (20x20) stretched to the box's (80x50).
    assert ((10, 5, 20, 20), (10, 5, 80, 50)) in copies
    ## The bottom edge: stretched along, its height kept.
    assert ((10, 25, 20, 5), (10, 55, 80, 5)) in copies
    seen = covered(copies)
    assert len(seen) == 100 * 60 and set(seen.values()) == {1}


def test_repeated_edges_are_cut_off_at_the_end(patch_region):
    region, copies = patch_region(patch_repeat="edges")
    draw(region, 0, 0, 100, 60)

    ## The bottom edge's 20-wide middle, along 80: 20, 20, 20, 20; along 50 it'd end in a 10.
    bottom = [c for c in copies if c[1][1] == 55 and 10 <= c[1][0] < 90]
    assert [(src[2], dst[2]) for src, dst in bottom] == [(20, 20)] * 4
    ## The left edge's 20-tall middle, down 50: 20, 20, 10 (cut off: the source's top 10).
    left = [c for c in copies if c[1][0] == 0 and 5 <= c[1][1] < 55]
    assert [(src[1], src[3], dst[3]) for src, dst in left] == [(5, 20, 20), (5, 20, 20), (5, 10, 10)]
    ## The middle still stretches.
    assert ((10, 5, 20, 20), (10, 5, 80, 50)) in copies
    seen = covered(copies)
    assert len(seen) == 100 * 60 and set(seen.values()) == {1}


def test_repeated_middle(patch_region):
    region, copies = patch_region(patch_repeat="all")
    draw(region, 0, 0, 65, 50)

    middle = [c for c in copies if c[1][0] >= 10 and c[1][1] >= 5 and c[1][0] < 55 and c[1][1] < 45]
    ## 45x40 of 20x20 tiles: 3 across (20, 20, 5) by 2 down.
    assert sorted({dst[2] for _, dst in middle}) == [5, 20] and len(middle) == 6
    seen = covered(copies)
    assert len(seen) == 65 * 50 and set(seen.values()) == {1}


@pytest.mark.parametrize("repeat", [None, "edges", "all"])
def test_a_box_smaller_than_its_corners(patch_region, repeat):
    ## No negative sizes (SDL draws those flipped), no endless loop.
    region, copies = patch_region(patch_repeat=repeat)
    draw(region, 0, 0, 15, 8)
    assert all(src[2] > 0 and src[3] > 0 and dst[2] > 0 and dst[3] > 0 for src, dst in copies)


def test_unknown_repeat_is_stretched(patch_region):
    region, copies = patch_region(patch_repeat="sideways")
    assert region.patch_repeat is None


def test_patch_takes_the_tint(patch_region, monkeypatch):
    from pugwash.sdl import region as region_module
    mods = []
    monkeypatch.setattr(region_module.sdl2, "SDL_SetTextureColorMod", lambda tx, r, g, b: mods.append((r, g, b)))
    region, _ = patch_region(image_mod=[46, 196, 182])
    draw(region, 0, 0, 100, 60)
    assert mods == [(46, 196, 182)]
