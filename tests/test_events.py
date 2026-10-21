# SPDX-License-Identifier: MIT
#
# pugwash.sdl.events.EventManager: SDL keyboard, controller and stick events pushed
# onto SDL's queue, turned into named buttons.

import ctypes

import pytest


pytestmark = pytest.mark.sdl


@pytest.fixture
def events(gui, monkeypatch):
    import sdl2
    events = gui.events
    saved = (dict(events.buttons), dict(events.last_buttons), dict(events.repeat), dict(events.axis_button), events.running)

    sdl2.SDL_FlushEvents(sdl2.SDL_FIRSTEVENT, sdl2.SDL_LASTEVENT)
    for key in events.buttons:
        events.buttons[key] = False
    events.last_buttons.update(events.buttons)
    for key in events.repeat:
        events.repeat[key] = None
    for key in events.axis_button:
        events.axis_button[key] = None

    yield events

    sdl2.SDL_FlushEvents(sdl2.SDL_FIRSTEVENT, sdl2.SDL_LASTEVENT)
    events.buttons.clear()
    events.buttons.update(saved[0])
    events.last_buttons.clear()
    events.last_buttons.update(saved[1])
    events.repeat.update(saved[2])
    events.axis_button.update(saved[3])
    events.running = saved[4]


def push(event):
    import sdl2
    assert sdl2.SDL_PushEvent(ctypes.byref(event)) == 1


def key(sym, down=True):
    import sdl2
    event = sdl2.SDL_Event()
    event.type = sdl2.SDL_KEYDOWN if down else sdl2.SDL_KEYUP
    event.key.keysym.sym = sym
    push(event)


def button(which, down=True):
    import sdl2
    event = sdl2.SDL_Event()
    event.type = sdl2.SDL_CONTROLLERBUTTONDOWN if down else sdl2.SDL_CONTROLLERBUTTONUP
    event.cbutton.button = which
    push(event)


def axis(which, value):
    import sdl2
    event = sdl2.SDL_Event()
    event.type = sdl2.SDL_CONTROLLERAXISMOTION
    event.caxis.axis = which
    event.caxis.value = value
    push(event)


def test_every_button_is_known(events):
    for name in ('A', 'START', 'SELECT', 'SCRN', 'L_LEFT', 'R_DOWN', 'L2', 'R2'):
        assert name in events.buttons, name

    ## Only names.
    assert all(isinstance(name, str) for name in events.buttons)


def test_keyboard(events):
    import sdl2
    key(sdl2.SDLK_z)
    events.handle_events()

    assert events.was_pressed('A')
    assert events.any_pressed()
    assert not events.was_released('A')

    ## Held: no longer "was pressed".
    events.handle_events()
    assert not events.was_pressed('A')
    assert not events.any_pressed()

    key(sdl2.SDLK_z, down=False)
    events.handle_events()
    assert events.was_released('A')
    assert events.any_released()


def test_unknown_key_is_ignored(events):
    import sdl2
    key(sdl2.SDLK_F12)
    events.handle_events()

    assert not events.any_pressed()


def test_escape_and_quit_stop(events):
    import sdl2
    key(sdl2.SDLK_ESCAPE)
    events.handle_events()
    assert events.running is False

    events.running = True
    event = sdl2.SDL_Event()
    event.type = sdl2.SDL_QUIT
    push(event)
    events.handle_events()
    assert events.running is False


def test_controller_buttons(events):
    import sdl2
    button(sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP)
    button(sdl2.SDL_CONTROLLER_BUTTON_START)
    events.handle_events()

    assert events.was_pressed('UP') and events.was_pressed('START')
    assert events.repeat['UP'] is not None

    button(sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP, down=False)
    events.handle_events()
    assert events.was_released('UP')
    assert events.repeat['UP'] is None


def test_unmapped_controller_button(events):
    import sdl2
    button(sdl2.SDL_CONTROLLER_BUTTON_MISC1)
    button(sdl2.SDL_CONTROLLER_BUTTON_MISC1, down=False)
    events.handle_events()

    assert not events.any_pressed()


def test_keyboard_repeat(events, monkeypatch):
    import sdl2
    now = [1000]
    monkeypatch.setattr(sdl2, "SDL_GetTicks64", lambda: now[0])

    key(sdl2.SDLK_DOWN)
    events.handle_events()
    assert events.was_pressed('DOWN')

    ## Held, before the delay: nothing.
    now[0] += events.REPEAT_DELAY - 1
    events.handle_events()
    assert not events.was_pressed('DOWN')

    ## After it: pressed again, then every REPEAT_RATE.
    now[0] += 1
    events.handle_events()
    assert events.was_pressed('DOWN')

    now[0] += events.REPEAT_RATE
    events.handle_events()
    assert events.was_pressed('DOWN')

    key(sdl2.SDLK_DOWN, down=False)
    events.handle_events()
    now[0] += 10_000
    events.handle_events()
    assert not events.was_pressed('DOWN')


def test_stick(events):
    import sdl2
    LX = sdl2.SDL_CONTROLLER_AXIS_LEFTX

    ## Inside the dead zone: nothing.
    axis(LX, events.analog_min - 1)
    events.handle_events()
    assert not events.any_pressed()

    axis(LX, 30000)
    events.handle_events()
    assert events.was_pressed('L_RIGHT')
    assert events.axis['LX'] == 30000

    ## Straight across: right is let go, left pressed.
    axis(LX, -30000)
    events.handle_events()
    assert events.buttons['L_RIGHT'] is False
    assert events.was_pressed('L_LEFT')

    axis(LX, 0)
    events.handle_events()
    assert events.was_released('L_LEFT')
    assert events.axis_button['LX'] is None


def test_trigger(events):
    import sdl2
    axis(sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 32000)
    events.handle_events()
    assert events.was_pressed('R2')

    ## A trigger has no "negative" button.
    axis(sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT, 0)
    events.handle_events()
    assert events.was_released('R2')


def test_unknown_axis(events):
    import sdl2
    axis(sdl2.SDL_CONTROLLER_AXIS_MAX, 30000)
    events.handle_events()
    assert not events.any_pressed()


@pytest.mark.parametrize("value, expected", [(0, 1), (4095, 1), (-4095, 1), (4096, 2), (-4096, 0), (32767, 2), (-32768, 0)])
def test_axis_map(events, value, expected):
    assert events._axis_map(value, 4096) == expected


def test_controller_hotplug(events, monkeypatch):
    import sdl2
    opened, closed = [], []
    monkeypatch.setattr(sdl2, "SDL_GameControllerOpen", lambda which: opened.append(which))
    monkeypatch.setattr(sdl2, "SDL_GameControllerFromInstanceID", lambda which: f"pad{which}")
    monkeypatch.setattr(sdl2, "SDL_GameControllerClose", lambda pad: closed.append(pad))

    for kind, which in ((sdl2.SDL_CONTROLLERDEVICEADDED, 3), (sdl2.SDL_CONTROLLERDEVICEREMOVED, 7)):
        event = sdl2.SDL_Event()
        event.type = kind
        event.cdevice.which = which
        push(event)

    events.handle_events()
    assert opened == [3] and closed == ["pad7"]


def test_xbox_fix_once(gui):
    import sdl2
    events = gui.events
    saved = (dict(events.BUTTON_MAP), events.XBOX_FIXED)
    try:
        events.XBOX_FIXED = False
        events.fix_xbox_mode()
        events.fix_xbox_mode()

        assert events.BUTTON_MAP[sdl2.SDL_CONTROLLER_BUTTON_A] == 'B'
        assert events.BUTTON_MAP[sdl2.SDL_CONTROLLER_BUTTON_X] == 'Y'

    finally:
        events.BUTTON_MAP.clear()
        events.BUTTON_MAP.update(saved[0])
        events.XBOX_FIXED = saved[1]
