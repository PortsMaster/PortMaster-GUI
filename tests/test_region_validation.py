# SPDX-License-Identifier: MIT
#
# Theme validation: the Region._verify_* checks every value a theme's JSON gives a region
# goes through. Run on a bare Region (no SDL window): a theme author's typo must be a
# GUIThemeError (the theme then falls back), never a crash of some other kind.

from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.sdl


@pytest.fixture
def region(pugwash):
    """make(data, pallet=None, files=()) -> a Region with only what the checks use."""
    from pugwash.sdl.region import Region
    from pugwash.sdl import geometry

    def make(data, pallet=None, files=()):
        region = Region.__new__(Region)
        region._dict = dict(data)
        region.pallet = pallet or {}
        region.gui = SimpleNamespace(resources=SimpleNamespace(find=lambda name: name if name in files else None))
        region.parent = 'root'
        region.name = 'test'
        region._rects = geometry.NamedRects((0, 0, 640, 480))
        return region

    return make


@pytest.fixture
def ThemeError(pugwash):
    from pugwash.sdl.errors import GUIThemeError
    return GUIThemeError


################################################################################
## Numbers
@pytest.mark.parametrize("value, expected", [(0, 0), (18, 18), (-4, -4)])
def test_int(region, value, expected):
    assert region({'v': value})._verify_int('v') == expected


@pytest.mark.parametrize("value", ["18", 18.5, [18], None, {"a": 1}])
def test_int_bad(region, ThemeError, value):
    with pytest.raises(ThemeError):
        region({'v': value})._verify_int('v')


def test_int_default_optional_and_clamped(region):
    assert region({})._verify_int('v', default=7) == 7
    assert region({})._verify_int('v', default=None, optional=True) is None
    assert region({'v': 500})._verify_int('v', maximum=128) == 128
    assert region({'v': -3})._verify_int('v', minimum=0) == 0
    assert region({'v': 3})._verify_int('v', minimum=1, maximum=6) == 3


@pytest.mark.parametrize("value, expected", [(1.5, 1.5), (2, 2.0), (0, 0.0), (-0.5, -0.5)])
def test_float(region, value, expected):
    ## "font-scale": 2 is as good as 2.0 (it was "is not an float").
    result = region({'v': value})._verify_float('v')
    assert result == expected and isinstance(result, float)


@pytest.mark.parametrize("value", ["1.5", True, False, [1.0], None])
def test_float_bad(region, ThemeError, value):
    with pytest.raises(ThemeError):
        region({'v': value})._verify_float('v')


def test_float_clamped(region):
    assert region({'v': 9})._verify_float('v', maximum=2.5) == 2.5
    assert region({'v': -9})._verify_float('v', minimum=0.1) == 0.1
    assert region({})._verify_float('v', default=None, optional=True) is None


@pytest.mark.parametrize("value, count", [([1, 2], 2), ([0, 0, 0, 0], 4), ((5, 6), 2)])
def test_ints(region, value, count):
    assert list(region({'v': value})._verify_ints('v', count)) == list(value)


@pytest.mark.parametrize("value, count", [([1], 2), ([1, 2, 3], 2), ([1, "2"], 2), ([1, 2.5], 2), ("12", 2), (12, 2)])
def test_ints_bad(region, ThemeError, value, count):
    with pytest.raises(ThemeError):
        region({'v': value})._verify_ints('v', count)


################################################################################
## Booleans, text, options, lists
@pytest.mark.parametrize("value, expected", [(True, True), (False, False), (1, True), (0, False)])
def test_bool(region, value, expected):
    assert region({'v': value})._verify_bool('v') is expected


@pytest.mark.parametrize("value", ["true", 2, None, [], "yes"])
def test_bool_bad(region, ThemeError, value):
    with pytest.raises(ThemeError):
        region({'v': value})._verify_bool('v', default=None)


def test_text(region, ThemeError):
    assert region({'v': "Hello {port_info.title}"})._verify_text('v') == "Hello {port_info.title}"
    assert region({})._verify_text('v', optional=True) is None
    ## A number where text goes: a theme error (it raised a str, so a TypeError).
    for value in (5, ["a"], {"a": 1}):
        with pytest.raises(ThemeError):
            region({'v': value})._verify_text('v')


@pytest.mark.parametrize("value, expected", [
    ("center", "center"),
    ("sideways", "left"),
    (["top", "left"], ["top", "left"]),
    (["top", "sideways"], "left"),
    (["top"], "left"),
    ])
def test_option(region, value, expected):
    ## Anything unknown is the default, not an error.
    options = ("left", "center", "right", "top")
    assert region({'v': value})._verify_option('v', options, default="left", length=2 if isinstance(value, list) else None) == expected


def test_list(region, ThemeError):
    assert region({'v': ["a", "b"]})._verify_list('v') == ["a", "b"]
    assert region({'v': ["a", None]})._verify_list('v', allow_null=True) == ["a", None]
    for value in ("a", 5, ["a", 5], ["a", None]):
        with pytest.raises(ThemeError):
            region({'v': value})._verify_list('v')


################################################################################
## Colours
@pytest.mark.parametrize("value, expected", [
    ([1, 2, 3], (1, 2, 3, 255)),
    ([1, 2, 3, 4], (1, 2, 3, 4)),
    ((255, 255, 255), (255, 255, 255, 255)),
    ("#ff0000", (255, 0, 0, 255)),
    ("#0f08", (0, 255, 0, 136)),
    ("accent", (10, 20, 30, 255)),
    ("dim", (1, 2, 3, 4)),
    ])
def test_color(region, value, expected):
    pallet = {"accent": [10, 20, 30], "dim": "#01020304"}
    assert tuple(region({'v': value}, pallet=pallet)._verify_color('v')) == expected


@pytest.mark.parametrize("value", [
    "red",            ## not in the pallet, not a #code
    [1, 2],           ## too short
    [1, 2, 3, 4, 5],  ## too long
    [256, 0, 0],      ## out of range
    [-1, 0, 0],
    [1.5, 0, 0],      ## not ints
    ["1", 0, 0],
    ])
def test_color_bad(region, ThemeError, value):
    with pytest.raises(ThemeError):
        region({'v': value})._verify_color('v')


def test_color_optional(region):
    assert region({})._verify_color('v', optional=True) is None
    assert tuple(region({})._verify_color('v', default=(1, 2, 3))) == (1, 2, 3, 255)


def test_outline(region, ThemeError):
    assert region({'v': [[0, 0, 0], 2]})._verify_outline('v', None, True) == ((0, 0, 0, 255), 2)
    assert region({})._verify_outline('v', None, True) is None
    for value in ([[0, 0, 0]], "black", [[0, 0, 0], "2"], [["x"], 2]):
        with pytest.raises(ThemeError):
            region({'v': value})._verify_outline('v', None, True)


################################################################################
## Files and areas
def test_file(region, ThemeError):
    assert region({'v': "font.ttf"}, files=("font.ttf",))._verify_file('v') == "font.ttf"
    assert region({})._verify_file('v', optional=True) is None
    with pytest.raises(ThemeError):
        region({'v': "missing.ttf"})._verify_file('v')
    with pytest.raises(ThemeError):
        region({'v': 5}, files=(5,))._verify_file('v')


@pytest.mark.parametrize("area, expected", [
    ([0.0, 0.0, 1.0, 1.0], (0, 0, 640, 480)),
    ([0.5, 0.5, 1.0, 1.0], (320, 240, 320, 240)),
    ([10, 20, -10, -20], (10, 20, 620, 440)),
    ])
def test_rect(region, area, expected):
    assert region({'area': area})._verify_rect('area').tuple() == expected


@pytest.mark.parametrize("area", [[0, 0, 1], [0, 0, 1, 1, 1], [0, "a", 1, 1]])
def test_rect_bad(region, ThemeError, area):
    with pytest.raises(ThemeError):
        region({'area': area})._verify_rect('area')


def test_rect_not_a_list(region):
    with pytest.raises(TypeError):
        region({'area': 5})._verify_rect('area')


################################################################################
## Bars (the button bar)
def test_bar(region, ThemeError):
    assert region({})._verify_bar('bar') is None
    for value in ("A: Okay", 5):
        with pytest.raises(ThemeError):
            region({'bar': value})._verify_bar('bar')
    with pytest.raises(ThemeError):
        region({'bar': ["a", "None", "b", "None"]})._verify_bar('bar')
