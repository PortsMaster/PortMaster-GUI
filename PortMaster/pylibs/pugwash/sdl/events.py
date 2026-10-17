# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Input: keyboard, controllers and button mapping.

import sdl2
import sdl2.ext
import sdl2.sdlmixer
from loguru import logger


class EventManager:
    ## TODO: add deadzone code

    BUTTON_MAP = {
        sdl2.SDL_CONTROLLER_BUTTON_A: 'A',
        sdl2.SDL_CONTROLLER_BUTTON_B: 'B',
        sdl2.SDL_CONTROLLER_BUTTON_X: 'X',
        sdl2.SDL_CONTROLLER_BUTTON_Y: 'Y',

        sdl2.SDL_CONTROLLER_BUTTON_LEFTSHOULDER: 'L1',
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSHOULDER: 'R1',
        # sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT:    'L2',
        # sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT:   'R2',
        sdl2.SDL_CONTROLLER_BUTTON_LEFTSTICK:    'L3',
        sdl2.SDL_CONTROLLER_BUTTON_RIGHTSTICK:   'R3',

        sdl2.SDL_CONTROLLER_BUTTON_DPAD_UP:      'UP',
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN:    'DOWN',
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_LEFT:    'LEFT',
        sdl2.SDL_CONTROLLER_BUTTON_DPAD_RIGHT:   'RIGHT',

        sdl2.SDL_CONTROLLER_BUTTON_START:        'START',
        sdl2.SDL_CONTROLLER_BUTTON_GUIDE:        'GUIDE',
        sdl2.SDL_CONTROLLER_BUTTON_BACK:         'BACK',
        }

    KEY_MAP = {
        sdl2.SDLK_UP:       'UP',
        sdl2.SDLK_DOWN:     'DOWN',
        sdl2.SDLK_LEFT:     'LEFT',
        sdl2.SDLK_RIGHT:    'RIGHT',

        sdl2.SDLK_KP_ENTER: 'START',
        sdl2.SDLK_RETURN:   'START',
        sdl2.SDLK_ESCAPE:   'SELECT',

        sdl2.SDLK_SPACE:    'A',
        sdl2.SDLK_z:        'A',
        sdl2.SDLK_x:        'B',
        sdl2.SDLK_a:        'X',
        sdl2.SDLK_s:        'Y',
        sdl2.SDLK_q:        'L1',
        sdl2.SDLK_e:        'R1',
        sdl2.SDLK_p:        'SCRN',
        }

    AXIS_MAP = {
        sdl2.SDL_CONTROLLER_AXIS_LEFTX: 'LX',
        sdl2.SDL_CONTROLLER_AXIS_LEFTY: 'LY',
        sdl2.SDL_CONTROLLER_AXIS_RIGHTX: 'RX',
        sdl2.SDL_CONTROLLER_AXIS_RIGHTY: 'RY',
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERLEFT: 'L2',
        sdl2.SDL_CONTROLLER_AXIS_TRIGGERRIGHT: 'R2',
        }

    AXIS_TO_BUTTON = {
        'LX': ('L_LEFT', None, 'L_RIGHT'),
        'LY': ('L_UP',   None, 'L_DOWN'),
        'RX': ('R_LEFT', None, 'R_RIGHT'),
        'RY': ('R_UP',   None, 'R_DOWN'),
        'L2': (None,     None, 'L2'),
        'R2': (None,     None, 'R2'),
        }

    REPEAT_MAP = [
        'UP',
        'DOWN',
        'LEFT',
        'RIGHT',

        'L_UP',
        'L_DOWN',
        'L_LEFT',
        'L_RIGHT',

        'R_UP',
        'R_DOWN',
        'R_LEFT',
        'R_RIGHT',
        ]

    # Wait 1.5 seconds
    REPEAT_DELAY = 800
    # Trigger every 1 second
    REPEAT_RATE = 60

    ANALOG_MIN = 4096
    TRIGGER_MIN = 1024

    def __init__(self, gui):
        self.gui = gui
        sdl2.ext.init(controller=True)

        self.XBOX_FIXED = False

        self.running = True
        self.buttons = {
            key: False
            for key in self.BUTTON_MAP.values()}

        self.buttons.update({
            key: False
            for key in self.AXIS_TO_BUTTON.keys()})

        self.buttons.update({
            key: False
            for key in self.KEY_MAP.keys()})

        self.axis = {
            key: 0.0
            for key in self.AXIS_MAP.values()}

        self.axis_button = {
            key: None
            for key in self.AXIS_MAP.values()}

        self.repeat = {
            key: None
            for key in self.REPEAT_MAP}

        self.last_buttons = {}
        self.last_buttons.update(self.buttons)

        self.controller = None
        self.trigger_min = self.TRIGGER_MIN
        self.analog_min = self.ANALOG_MIN
        self.ticks = sdl2.SDL_GetTicks()

        ## Change this to handle other controllers.
        for i in range(sdl2.SDL_NumJoysticks()):
            if sdl2.SDL_IsGameController(i) == sdl2.SDL_TRUE:
                self.controller = sdl2.SDL_GameControllerOpen(i)

    def fix_retrodeck_mode(self):
        self.KEY_MAP[sdl2.SDLK_q] = 'START'

    def fix_xbox_mode(self):
        if self.XBOX_FIXED:
            return

        print("XBOX FIXER")
        self.XBOX_FIXED = True
        self.BUTTON_MAP.update({
            sdl2.SDL_CONTROLLER_BUTTON_A: 'B',
            sdl2.SDL_CONTROLLER_BUTTON_B: 'A',
            sdl2.SDL_CONTROLLER_BUTTON_X: 'Y',
            sdl2.SDL_CONTROLLER_BUTTON_Y: 'X',
            })

    def _axis_map(self, axis, limit):
        if abs(axis) < limit:
            return 1

        if axis < 0:
            return 0

        return 2

    def handle_events(self):
        # To handle WAS pressed do: 
        #    self.buttons['UP'] and not self.last_buttons['UP']
        self.last_buttons.update(self.buttons)

        ticks_now = sdl2.SDL_GetTicks64()

        for event in sdl2.ext.get_events():
            if event.type == sdl2.SDL_QUIT:
                self.running = False

            elif event.type == sdl2.SDL_KEYDOWN:
                if event.key.keysym.sym == sdl2.SDLK_ESCAPE:
                    self.running = False
                    break

                key = self.KEY_MAP.get(event.key.keysym.sym, None)
                if key is not None:
                    logger.debug(f'PRESSED {key}')
                    self.buttons[key] = True

                    if key in self.repeat:
                        self.repeat[key] = ticks_now + self.REPEAT_DELAY

            elif event.type == sdl2.SDL_KEYUP:
                key = self.KEY_MAP.get(event.key.keysym.sym, None)
                if key is not None:
                    logger.debug(f'RELEASED {key}')
                    self.buttons[key] = False

                    if key in self.repeat:
                        self.repeat[key] = None

            elif event.type == sdl2.SDL_CONTROLLERBUTTONDOWN:
                key = self.BUTTON_MAP.get(event.cbutton.button, None)
                if key is not None:
                    logger.debug(f'PRESSED {key}')
                    self.buttons[key] = True

                    if key in self.repeat:
                        self.repeat[key] = ticks_now + self.REPEAT_DELAY

            elif event.type == sdl2.SDL_CONTROLLERBUTTONUP:
                key = self.BUTTON_MAP.get(event.cbutton.button, None)
                if key is not None:
                    logger.debug(f'RELEASED {key}')
                    self.buttons[key] = False

                    if key in self.repeat:
                        self.repeat[key] = None

            elif event.type == sdl2.SDL_CONTROLLERAXISMOTION:
                if event.caxis.axis in self.AXIS_MAP:
                    key = self.AXIS_MAP[event.caxis.axis]
                    # print(f'MOVED {key} {event.caxis.value}')
                    self.axis[key] = event.caxis.value

                    last_axis_key = self.axis_button[key]
                    axis_key = self.AXIS_TO_BUTTON[key][self._axis_map(event.caxis.value, self.analog_min)]

                    if axis_key is not None:
                        if last_axis_key is None:
                            logger.debug(f"PRESSED {axis_key}")
                            self.buttons[axis_key] = True

                            if axis_key in self.repeat:
                                self.repeat[axis_key] = ticks_now + self.REPEAT_DELAY

                        elif last_axis_key != axis_key:
                            logger.debug(f"RELEASED {last_axis_key}")
                            self.buttons[last_axis_key] = False
                            if last_axis_key in self.repeat:
                                self.repeat[last_axis_key] = None

                            logger.debug(f"PRESSED {axis_key}")
                            self.buttons[axis_key] = True

                            if axis_key in self.repeat:
                                self.repeat[axis_key] = ticks_now + self.REPEAT_DELAY

                    else:
                        if last_axis_key is not None:
                            logger.debug(f"RELEASED {last_axis_key}")
                            self.buttons[last_axis_key] = False
                            if last_axis_key in self.repeat:
                                self.repeat[last_axis_key] = None

                    self.axis_button[key] = axis_key

            elif event.type == sdl2.SDL_CONTROLLERDEVICEADDED:
                # print(f"Opening {event.cdevice.which}")
                controller = sdl2.SDL_GameControllerOpen(event.cdevice.which)

            elif event.type == sdl2.SDL_CONTROLLERDEVICEREMOVED:
                # print(f"Closing {event.cdevice.which}")
                controller = sdl2.SDL_GameControllerFromInstanceID(event.cdevice.which)
                sdl2.SDL_GameControllerClose(controller)

        for key in self.repeat.keys():
            next_repeat = self.repeat[key]
            if next_repeat is not None and next_repeat <= ticks_now:
                # Trigger was_pressed state
                self.last_buttons[key] = False
                print(f'REPEAT {key} {ticks_now - next_repeat}')
                self.repeat[key] = ticks_now + self.REPEAT_RATE

    def any_pressed(self):
        for button in self.buttons:
            if self.was_pressed(button):
                return True

        return False

    def any_released(self):
        for button in self.buttons:
            if self.was_released(button):
                return True

        return False

    def was_pressed(self, button):
        return self.buttons.get(button, False) and not self.last_buttons.get(button, False)

    def was_released(self, button):
        return not self.buttons.get(button, False) and self.last_buttons.get(button, False)
