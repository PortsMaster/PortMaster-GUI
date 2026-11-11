# SPDX-License-Identifier: MIT
#
# A list's pointer: where it's drawn and how big, with and without "pointer-fit": "row"
# (the pointer a row tall, in side padding as wide as the pointer, at any font size).

from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.sdl


class FakePointer:
    """Stands in for the pointer image and records where the list draws it."""

    def __init__(self, width, height):
        self.srcrect = SimpleNamespace(w=width, h=height)
        self.drawn = []

    def draw_in(self, dest, fit=False, flip_x=None, flip_y=None, **kwargs):
        rect = (dest.x, dest.y, dest.width, dest.height) if fit else tuple(dest)
        self.drawn.append((rect, fit, bool(flip_x)))


@pytest.fixture
def pointer_list(gui):
    """make(rows, **theme keys) -> (region, pointer): a list region with a 64x128 fake pointer."""
    from pugwash import sdl

    def make(rows, **data):
        region_data = {
            "area": [0.1, 0.1, 0.6, 0.9], "font": "DejaVuSans.ttf", "font-size": 20,
            "select-fill": [244, 149, 25], "pointer-attach": "list",
            "pointer-align": ["midleft", "midright"], "pointer-mirror": True,
            }
        region_data.update({key.replace('_', '-'): value for key, value in data.items()})
        region = sdl.Region(gui, region_data)
        region.reset_options()
        for number, row in enumerate(rows):
            region.add_option(number, row)
        region.selected = 1
        region.pointer = FakePointer(64, 128)
        return region, region.pointer

    return make


def row_height(region):
    return int(region.texts.line_height(region.font, region.fontsize) * region.lineheight)


@pytest.mark.parametrize("font_size, line_height", [(14, 1.0), (20, 1.55), (27, 1.5), (40, 1.45)])
def test_pointer_fit_row_is_a_row_tall_in_the_padding(pointer_list, font_size, line_height):
    region, pointer = pointer_list(["one", "two", "three"], pointer_fit="row", font_size=font_size, line_height=line_height, border_x=3)
    area = region.area
    region.draw(area)

    row = row_height(region)
    width = int(row / 2 + 0.5)
    y = area.y + row
    ## The padding is the pointer's width, whatever border-x says: the ends touch the row's fill
    ## and the region's edges, and are drawn into their exact rects.
    assert pointer.drawn == [
        ((area.x, y, width, row), False, False),
        ((area.right - width, y, width, row), False, True),
        ]


def test_pointer_fit_row_marks_selected_bar_rows(pointer_list):
    rows = [["    ", "Genre", None, "12 "], ["    ", "Puzzle", None, "3 "]]
    region, pointer = pointer_list(rows, pointer_fit="row")
    area = region.area
    region.draw(area)

    row = row_height(region)
    width = int(row / 2 + 0.5)
    assert [rect for rect, fit, flip in pointer.drawn] == [
        (area.x, area.y + row, width, row),
        (area.right - width, area.y + row, width, row),
        ]


def test_pointer_without_fit_is_unchanged(pointer_list):
    rows = [["    ", "Genre", None, "12 "], "two", "three"]
    region, pointer = pointer_list(rows, pointer_size=[10, 20], border_x=12)
    area = region.area
    region.draw(area)

    ## pointer-size and border-x as given, fitted into the rect, and no pointer on bar rows.
    row = row_height(region)
    y = area.y + row + row // 2 - 10
    assert pointer.drawn == [
        ((area.x + 12 - 10, y, 10, 20), True, False),
        ((area.right - 12, y, 10, 20), True, True),
        ]

    region.selected = 0
    pointer.drawn.clear()
    region.draw(area)
    assert pointer.drawn == []
