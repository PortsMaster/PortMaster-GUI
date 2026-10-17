"""
Copyright (C) 2020, Michael C Palmer <michaelcpalmer1980@gmail.com>

This file is part of pySDL2gui

pySDLgui is a simple, low level gui module that handles input and draws multiple
rectangular Regions using hardware GPU rendering. Written in python, pySDLgui
uses pySDL2, a low level SDL2 wrapper also written in pure python with no other
dependencies.

This module is designed to produce full screen GUIs for lower powered
GNU/Linux based retro handhelds using game controller style input, but it may
prove useful on other hardware.

The main building block of GUIs built with this module is the Region, which
represents a rectangular area that can display text, lists, and images. Each
Region has numerous attributes that should be defined in theme.json or
defaults.json and can be used to change the look and feel of a GUI without
change the program's code.

CLASSES:
    Image: simple class to represent and draw textures and subtexture
        regions onto a pySDL render context
    ImageManager: class to load and cache images as Image objects in
        texture memory
    Rect: class used to represent and modify Rectangular regions
    Region: draws a rectangular region with a backround, outline, image,
        lists, etc. The main building block of pySDL2gui GUIs
    SoundManager: class used to load and play sound effects and music

FUNCTIONS:
    deep_merge: used internally to merge option dicts
    deep_print: available to display nested dict items or save them to disk
    deep_update: used internally to update an options dict from a second one
    get_color_mod: get the color_mod value of a texture (not working)
    get_text_size: get the size a text string would be if drawn with given font
    range_list: generate a list of numerical values to select from in a option
        menu, similar to a slider widget
    set_color_mod: set the color_mod value of a texture (not working)

pySDL2gui is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.
pytmx is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Lesser General Public License for more details.
You should have received a copy of the GNU Lesser General Public
License along with pySDL2gui.

If not, see <http://www.gnu.org/licenses/>.
"""

# pugwash.sdl is pySDL2gui split into modules, everything is re-exported here.

from .errors import (
    GUIException,
    GUIValueError,
    GUIRuntimeError,
    GUIThemeError,
    )
from .geometry import (
    Point,
    Rect,
    NamedRects,
    )
from .resources import (
    ResourceManager,
    )
from .timing import (
    Timer,
    AnimationManager,
    )
from .images import (
    Texture,
    Image,
    PendingImage,
    ImageManager,
    )
from .text import (
    get_text_size,
    FontTTF,
    TextManager,
    )
from .events import (
    EventManager,
    )
from .sound import (
    SoundManager,
    )
from .region import (
    sdlgfx,
    Region,
    )
from .helpers import (
    deep_update,
    deep_merge,
    deep_print,
    range_list,
    get_color_mod,
    set_color_mod,
    autoscroll_text,
    hex_color_decode,
    )


class GUI:
    def __init__(self, renderer, formatter=None):
        self.SWAP_BUTTONS = False

        self.renderer = renderer

        self.resources = ResourceManager(self)
        self.text = TextManager(self)
        self.images = ImageManager(self)
        self.sounds = SoundManager(self)
        self.events = EventManager(self)
        self.animations = AnimationManager(self)
        self.override = {}
        self.pallet = {}
        self.default_rects = NamedRects([0, 0, *self.renderer.logical_size])
        self.formatter = formatter

    def set_data(self, key, value):
        # This needs to be handled by the gui parent class
        pass

    def new_rects(self):
        return self.default_rects.copy()

    def clean(self):
        '''
        Call after a frame to clean up extra textures/resources no longer needed.
        '''
        self.text.clean()
        # sdl2.sdlmixer.Mix_Quit()
        # print('SoundManager closed')


'''
TODO
    Fix image/text confusion in bars
    Text horiz scrolling
    Text animation (rotation, scaling, color changing)
    Tiled image rendering
    Deque the cache list
    Alpha colors for fill and outline
    Alpha for images
'''

'''
## Not used.
def init():
    with open('theme.json') as inp:
        config = json.load(inp)
    if os.path.isfile('defaults.json'):
        with open('defaults.json') as inp:
            defaults = json.load(inp)
        config = deep_update(defaults, config)
    deep_print(config, 'config')

    logical_size = config.get('options', {}).get('logical_size', DEFAULT_SIZE)
    sdl2.ext.init()
    mode = sdl2.ext.displays.DisplayInfo(0).current_mode
    if 'window' in sys.argv:
        screen_size = config['options'].get('screen_size') or logical_size
        flags = None
    else:
        screen_size = config['options'].get('screen_size') or mode.w, mode.h
        flags = sdl2.SDL_WINDOW_FULLSCREEN_DESKTOP # TODO should not use fullscreen_desktop on actual device
    print(f'Current display mode: {mode.w}x{mode.h}@{mode.refresh_rate}Hz')
    print(f'Logical Size: {logical_size}, Screen Size: {screen_size}')

    window = sdl2.ext.Window("Harbour Master",
            size=screen_size, flags=flags)
    screen = sdl2.ext.renderer.Renderer(window,
            flags=sdl2.SDL_RENDERER_ACCELERATED, logical_size=logical_size)
    screen.clear((0, 0, 0))
    sdl2.ext.renderer.set_texture_scale_quality('linear') #nearest, linear, best

    Image.renderer = screen
    images = ImageManager(screen)
    fonts = FontManager(screen)
    inp = InputHandler()
    window.show()

    if 'sounds' in config:
        sounds.init()
        for k, v in config['sounds'].items():
            print('loading sound: ', v)
            sounds.load(v, k)
    if config['options'].get('music'):
        sounds.init()
        sounds.music(config['options']['music'], volume=.3)

    defaults = config.get('defaults', {})
    print('Defaults:', defaults)
    Region.set_defaults(defaults, screen, images, fonts)

    gui.set_globals(config, screen, images, fonts, inp)
    utility.set_globals(config, screen, images, fonts, inp)

    return config, screen, fonts, images, inp
'''
