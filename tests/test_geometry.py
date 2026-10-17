# SPDX-License-Identifier: MIT
#
# pugwash.sdl.geometry.Rect: every anchor point in Rect.POINTS can be read and set
# (themes name them in "align", "image-align" and "pointer-align").

import pytest


pytestmark = pytest.mark.sdl

EXPECTED = {
    'topleft':      (10, 20),
    'midtop':       (60, 20),
    'topcenter':    (60, 20),
    'topright':     (110, 20),
    'midleft':      (10, 45),
    'center':       (60, 45),
    'midright':     (110, 45),
    'bottomleft':   (10, 70),
    'midbottom':    (60, 70),
    'bottomcenter': (60, 70),
    'bottomright':  (110, 70),
    }


@pytest.fixture
def Rect(pugwash):
    from pugwash.sdl.geometry import Rect
    return Rect


def test_points_are_all_covered(Rect):
    assert set(Rect.POINTS) == set(EXPECTED)


@pytest.mark.parametrize("point", sorted(EXPECTED))
def test_point_get(Rect, point):
    assert getattr(Rect(10, 20, 100, 50), point) == EXPECTED[point]


@pytest.mark.parametrize("point", sorted(EXPECTED))
def test_point_set_moves_rect(Rect, point):
    rect = Rect(0, 0, 100, 50)
    setattr(rect, point, EXPECTED[point])

    assert (rect.x, rect.y, rect.width, rect.height) == (10, 20, 100, 50)
