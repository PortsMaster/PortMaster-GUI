# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Timers and animations.

import sdl2
import sdl2.ext
import sdl2.sdlmixer


class Timer:
    def __init__(self):
        self._register = {}

    def since(self, name):
        time = sdl2.SDL_GetTicks64()

        return  (time - self._register.setdefault(name, time))

    def elapsed(self, name, millis, *, run_first=False):
        """
        check if name was last checked more than millis seconds ago, if so reset the timer and return true, otherwise false and do nothing
        """

        time = sdl2.SDL_GetTicks64()
        first_run = name not in self._register
        did_elapse = (time - self._register.setdefault(name, time)) >= millis

        if run_first and first_run:
            return first_run

        if did_elapse:
            self._register[name] = time

        return did_elapse

    def clear(self):
        """
        Reset all timers
        """
        self._register.clear()


class AnimationManager:
    def __init__(self, gui):
        self._gui = gui
        self._animations = {}

    def add_animation(self, animation_name, options):
        animation = {
            # Options
            'start': 0,              # start frame
            'max-frames': 1,         # how many frames we have
            'skip-frames': 1,        # how many frames we skip forward
            'update': 100,           # how many ms between frames
            'loop': True,            # do we run forever?
            'reset-on-scene': True,  # reset on scene change
            # Running variables
            'frame': 0,
            'last-update': None,
            'done': False,
            }

        if 'max-frames' in options and isinstance(options['max-frames'], int):
            if options['max-frames'] > 0:
                animation['max-frames'] = options['max-frames']

        if 'skip-frames' in options and isinstance(options['skip-frames'], int):
            if options['skip-frames'] > 0 and options['skip-frames'] < animation['max-frames']:
                animation['skip-frames'] = options['skip-frames']

        if 'start' in options and isinstance(options['start'], int):
            if options['start'] >= 0 and options['start'] < animation['max-frames']:
                animation['start'] = options['start']

        if 'update' in options and isinstance(options['update'], int):
            if options['update'] >= 100:
                animation['update'] = options['update']

        if 'loop' in options and isinstance(options['loop'], bool):
            animation['loop'] = options['loop']

        if 'reset-on-scene' in options and isinstance(options['reset-on-scene'], bool):
            animation['reset-on-scene'] = options['reset-on-scene']

        self._animations[animation_name] = animation
        self._gui.set_data(f"animation.{animation_name}", f"{animation['frame']:03d}")

    def update_animations(self):
        time = sdl2.SDL_GetTicks64()
        for animation_name, animation in self._animations.items():
            if animation['last-update'] is None:
                animation['frame'] = animation['start']
                animation['last-update'] = time
                animation['done'] = False
                self._gui.set_data(f"animation.{animation_name}", f"{animation['frame']:03d}")
                continue

            if animation['done']:
                continue

            # logger.debug(f"{animation_name}: {(animation['last-update'] - time)} >= {animation['update']}")
            if (time - animation['last-update']) >= animation['update']:
                animation['frame'] += animation['skip-frames']

                if animation['frame'] >= animation['max-frames']:
                    if animation['loop']:
                        animation['frame'] = animation['start']
                    else:
                        animation['frame'] = animation['max-frames'] - 1
                        animation['done'] = True

                animation['last-update'] = time
                self._gui.set_data(f"animation.{animation_name}", f"{animation['frame']:03d}")
                continue

    def change_scene(self):
        time = sdl2.SDL_GetTicks64()
        for animation_name, animation in self._animations.items():
            if animation['reset-on-scene']:
                animation['last-update'] = None
                animation['frame'] = animation['start']
                animation['done'] = False
                self._gui.set_data(f"animation.{animation_name}", f"{animation['frame']:03d}")
