# SPDX-License-Identifier: MIT
#
# pugwash.sdl's plain helpers: Rect maths, theme area parsing (NamedRects), colours,
# dict merging, autoscroll, timers and animations.

from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.sdl


@pytest.fixture
def geometry(pugwash):
    from pugwash.sdl import geometry
    return geometry


@pytest.fixture
def helpers(pugwash):
    from pugwash.sdl import helpers
    return helpers


################################################################################
## Rect
def test_rect_basics(geometry):
    Rect = geometry.Rect
    rect = Rect(10.7, 20.2, 100, 50)

    assert rect.tuple() == (10, 20, 100, 50)
    assert repr(rect) == "Rect(10, 20, 100, 50)"
    assert len(rect) == 4 and list(rect) == [10, 20, 100, 50]
    assert rect[-1] == 50

    copy = rect.copy()
    copy.move(5, 5)
    assert rect.topleft == (10, 20) and copy.topleft == (15, 25)
    assert rect.moved(-10, -20).topleft == (0, 0)

    rect.update(1, 2, 3, 4)
    assert rect.tuple() == (1, 2, 3, 4)


def test_rect_edges(geometry):
    rect = geometry.Rect(0, 0, 100, 50)
    rect.right = 300
    rect.bottom = 200
    assert (rect.left, rect.top) == (200, 150)

    rect.left, rect.top = 5, 6
    rect.centerx, rect.centery = 50, 25
    assert rect.topleft == (0, 0)
    assert (rect.w, rect.h) == (100, 50)


def test_rect_size_keeps_the_centre(geometry):
    rect = geometry.Rect(0, 0, 100, 100)
    rect.size = (50, 20)
    assert rect.tuple() == (25, 40, 50, 20)


def test_rect_scale(geometry):
    rect = geometry.Rect(0, 0, 100, 100) * 0.5
    assert rect.tuple() == (25, 25, 50, 50)


def test_rect_inflate(geometry):
    rect = geometry.Rect(10, 10, 100, 100)
    rect.inflate(-20)
    assert rect.tuple() == (20, 20, 80, 80)

    assert geometry.Rect(10, 10, 100, 100).inflated(20, 10).tuple() == (0, 5, 120, 110)
    assert geometry.Rect(10, 10, 100, 100).inflated(4).tuple() == (8, 8, 104, 104)


def test_rect_from(geometry):
    import sdl2
    assert geometry.Rect.from_corners(10, 20, 110, 70).tuple() == (10, 20, 100, 50)
    assert geometry.Rect.from_sdl(sdl2.SDL_Rect(1, 2, 3, 4)).tuple() == (1, 2, 3, 4)

    sdl_rect = geometry.Rect(1, 2, 3, 4).sdl()
    assert (sdl_rect.x, sdl_rect.y, sdl_rect.w, sdl_rect.h) == (1, 2, 3, 4)


@pytest.mark.parametrize("image, area, expected", [
    ## Wide image in a square: full width, centred vertically.
    ((0, 0, 200, 100), (0, 0, 100, 100), (0, 25, 100, 50)),
    ## Tall image in a wide area: full height, centred across.
    ((0, 0, 50, 100), (10, 10, 200, 100), (85, 10, 50, 100)),
    ## Same shape: fills it.
    ((0, 0, 10, 10), (5, 5, 40, 40), (5, 5, 40, 40)),
    ])
def test_rect_fit(geometry, image, area, expected):
    Rect = geometry.Rect
    assert Rect(*image).fitted(Rect(*area)).tuple() == expected

    rect = Rect(*image)
    rect.fit(Rect(*area))
    assert rect.tuple() == expected


@pytest.mark.parametrize("rect, area, expected", [
    ((10, 10, 50, 50), (0, 0, 100, 100), (10, 10, 50, 50)),
    ((-10, -10, 50, 50), (0, 0, 100, 100), (0, 0, 40, 40)),
    ((80, 80, 50, 50), (0, 0, 100, 100), (80, 80, 20, 20)),
    ((-10, 20, 200, 10), (0, 0, 100, 100), (0, 20, 100, 10)),
    ((200, 200, 10, 10), (0, 0, 100, 100), (200, 200, 0, 0)),
    ((20, 200, 10, 10), (0, 0, 100, 100), (20, 200, 0, 0)),
    ((-50, 10, 10, 10), (0, 0, 100, 100), (-50, 10, 0, 0)),
    ((10, -50, 10, 10), (0, 0, 100, 100), (10, -50, 0, 0)),
    ])
def test_rect_clip(geometry, rect, area, expected):
    Rect = geometry.Rect
    assert Rect(*rect).clip(Rect(*area)).tuple() == expected


def test_rect_setitem(geometry):
    rect = geometry.Rect(0, 0, 1, 1)
    for i, value in enumerate((5, 6, 7, 8)):
        rect[i] = value

    assert rect.tuple() == (5, 6, 7, 8)

    rect[-4] = 9
    assert rect.x == 9

    with pytest.raises(geometry.GUIValueError):
        rect[0] = 1.5

    with pytest.raises(geometry.GUIValueError):
        rect[4] = 1


def test_point(geometry):
    point = geometry.Point(3, 4)
    assert (point.x, point.y) == (3, 4)


################################################################################
## Theme areas
@pytest.fixture
def rects(geometry):
    rects = geometry.NamedRects((0, 0, 640, 480))
    rects.make_rect('root', 'panel', [0.5, 0.0, 1.0, 0.5])
    return rects


@pytest.mark.parametrize("value, expected", [
    ## Fractions of the parent.
    ([0.0, 0.0, 1.0, 1.0], (320, 0, 320, 240)),
    ([0.5, 0.5, 1.0, 1.0], (480, 120, 160, 120)),
    ## Pixels from the parent's corner, the far corner absolute.
    ([10, 10, 400, 100], (330, 10, 70, 90)),
    ## Negative: from the parent's far edge.
    ([-100, -40, -10, -10], (540, 200, 90, 30)),
    ])
def test_named_rect(rects, value, expected):
    assert rects.make_rect('panel', 'child', value).tuple() == expected
    assert rects._rects['child'].tuple() == expected


def test_named_rect_unknown_parent_is_root(rects):
    assert rects.make_rect('nothing', None, [0.0, 0.0, 0.5, 0.5]).tuple() == (0, 0, 320, 240)
    assert 'None' not in rects._rects and None not in rects._rects


def test_named_rect_copy(rects):
    copy = rects.copy()
    copy.make_rect('root', 'extra', [0, 0, 10, 10])

    assert 'panel' in copy._rects
    assert 'extra' not in rects._rects


@pytest.mark.parametrize("value, error", [
    ([0, 0, 10], "GUIThemeError"),
    ([0, 0, 10, 10, 10], "GUIThemeError"),
    ([0, "a", 10, 10], "GUIThemeError"),
    (5, "TypeError"),
    ])
def test_named_rect_bad(rects, geometry, value, error):
    with pytest.raises(Exception) as exc:
        rects.make_rect('root', 'x', value)

    assert type(exc.value).__name__ == error


################################################################################
## Colours and dicts
@pytest.mark.parametrize("code, expected", [
    ("#fff", (255, 255, 255)),
    ("#F00", (255, 0, 0)),
    ("#0f08", (0, 255, 0, 136)),
    ("#123456", (0x12, 0x34, 0x56)),
    ("12345678", (0x12, 0x34, 0x56, 0x78)),
    ## Bad length or not hex: white, never a crash.
    ("#12345", (255, 255, 255)),
    ("#ggg", (255, 255, 255)),
    ("#zz00zz", (255, 255, 255)),
    ])
def test_hex_color_decode(helpers, code, expected):
    assert helpers.hex_color_decode(code) == expected


def test_hex_color_decode_cache_cant_be_changed(helpers):
    with pytest.raises(TypeError):
        helpers.hex_color_decode("#abc")[0] = 0


def test_deep_update_and_merge(helpers):
    base = {"a": 1, "b": {"c": 2, "d": {"e": 3}}}
    merged = helpers.deep_merge(base, {"b": {"d": {"f": 4}}, "g": 5})

    assert merged == {"a": 1, "b": {"c": 2, "d": {"e": 3, "f": 4}}, "g": 5}
    ## deep_merge leaves the original alone.
    assert base == {"a": 1, "b": {"c": 2, "d": {"e": 3}}}

    helpers.deep_update(base, {"a": {"x": 1}})
    assert base["a"] == {"x": 1}


def test_deep_print(helpers, capsys):
    helpers.deep_print({"a": 1, "b": {"c": 2}}, name="root")
    assert capsys.readouterr().out == "root\n  a: 1\n  b\n    c: 2\n"


def test_range_list(helpers):
    assert helpers.range_list(50, 0, 100, 10) == ["50", "60", "70", "80", "90", "100", "0", "10", "20", "30", "40"]
    assert helpers.range_list(0, 0, 20, 10) == ["0", "10", "20"]


@pytest.mark.parametrize("text, align, amount, vertical, expected", [
    ## Fits: nothing to scroll.
    ((0, 0, 50, 50), 'topleft', 30, True, (0, 0, 0, 'topleft')),
    ## Taller than the area: scrolls up, at most by the overflow.
    ((0, 0, 50, 300), 'topleft', 30, True, (0, -30, 200, 'topleft')),
    ((0, 0, 50, 300), 'topleft', 999, True, (0, -200, 200, 'topleft')),
    ((0, 0, 50, 300), 'bottomleft', 10, True, (0, 110, 200, 'bottomleft')),
    ## Centred text that overflows scrolls from the top.
    ((0, 0, 50, 300), 'center', 10, True, (50, -10, 200, 'topcenter')),
    ((0, 0, 300, 50), 'topleft', 30, False, (-30, 0, 200, 'topleft')),
    ((0, 0, 300, 50), 'topright', 30, False, (130, 0, 200, 'topright')),
    ((0, 0, 300, 50), 'center', 5, False, (-5, 50, 200, 'midleft')),
    ])
def test_autoscroll_text(geometry, helpers, text, align, amount, vertical, expected):
    Rect = geometry.Rect
    assert helpers.autoscroll_text(Rect(*text), Rect(0, 0, 100, 100), align, amount, vertical) == expected


################################################################################
## Timers and animations
@pytest.fixture
def ticks(monkeypatch):
    import sdl2
    now = [1000]
    monkeypatch.setattr(sdl2, "SDL_GetTicks64", lambda: now[0])
    return now


def test_timer(pugwash, ticks):
    from pugwash.sdl.timing import Timer
    timer = Timer()

    assert timer.since("a") == 0
    ticks[0] += 250
    assert timer.since("a") == 250

    ## First check: not elapsed unless run_first.
    assert timer.elapsed("b", 100) is False
    assert timer.elapsed("c", 100, run_first=True) is True
    ticks[0] += 99
    assert timer.elapsed("b", 100) is False
    ticks[0] += 1
    assert timer.elapsed("b", 100) is True
    ## And reset.
    assert timer.elapsed("b", 100) is False

    timer.clear()
    assert timer.since("a") == 0


class FakeGui:
    def __init__(self):
        self.data = {}

    def set_data(self, key, value):
        self.data[key] = value


def test_animation_options_are_checked(pugwash):
    from pugwash.sdl.timing import AnimationManager
    manager = AnimationManager(FakeGui())

    manager.add_animation("bad", {'max-frames': -1, 'skip-frames': 9, 'start': 9, 'update': 5, 'loop': "yes", 'reset-on-scene': 1})
    bad = manager._animations["bad"]
    assert (bad['max-frames'], bad['skip-frames'], bad['start'], bad['update'], bad['loop'], bad['reset-on-scene']) == (1, 1, 0, 100, True, True)

    manager.add_animation("good", {'max-frames': 10, 'skip-frames': 2, 'start': 3, 'update': 200, 'loop': False, 'reset-on-scene': False})
    good = manager._animations["good"]
    assert (good['max-frames'], good['skip-frames'], good['start'], good['update'], good['loop'], good['reset-on-scene']) == (10, 2, 3, 200, False, False)
    assert manager._gui.data["animation.good"] == "000"


def test_animation_loops(pugwash, ticks):
    from pugwash.sdl.timing import AnimationManager
    gui = FakeGui()
    manager = AnimationManager(gui)
    manager.add_animation("spin", {'max-frames': 3, 'update': 100})

    frames = []
    for step in range(5):
        manager.update_animations()
        frames.append(gui.data["animation.spin"])
        ticks[0] += 100

    assert frames == ["000", "001", "002", "000", "001"]


def test_animation_stops(pugwash, ticks):
    from pugwash.sdl.timing import AnimationManager
    gui = FakeGui()
    manager = AnimationManager(gui)
    manager.add_animation("once", {'max-frames': 2, 'update': 100, 'loop': False})

    for step in range(5):
        manager.update_animations()
        ticks[0] += 100

    assert gui.data["animation.once"] == "001"
    assert manager._animations["once"]['done']

    ## Not before its time.
    manager.add_animation("slow", {'max-frames': 5, 'update': 1000})
    manager.update_animations()
    ticks[0] += 999
    manager.update_animations()
    assert gui.data["animation.slow"] == "000"


def test_animation_scene_change(pugwash, ticks):
    from pugwash.sdl.timing import AnimationManager
    gui = FakeGui()
    manager = AnimationManager(gui)
    manager.add_animation("resets", {'max-frames': 5, 'update': 100})
    manager.add_animation("keeps", {'max-frames': 5, 'update': 100, 'reset-on-scene': False})

    for step in range(3):
        manager.update_animations()
        ticks[0] += 100

    manager.change_scene()
    assert gui.data["animation.resets"] == "000"
    assert gui.data["animation.keeps"] == "002"

    manager.clear()
    assert manager._animations == {}
