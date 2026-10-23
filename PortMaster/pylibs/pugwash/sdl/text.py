# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Fonts and rendered text.

import collections
from ctypes import c_int, byref
import sdl2
import sdl2.ext
import sdl2.sdlmixer
from .errors import GUIValueError
from .images import Texture


def get_text_size(font, text=''):
    '''
    Calculate the size of given text using the given font, or if
    no text is provided, then return the font's height instead

    font: an existing sdl2.ext.FontTTF object
    text: optional text string to generate size of
    :rvalue (int, int) or int: (width(int), height(int)) if text provided,
            or height(int) otherwise
    '''
    text_w, text_h = c_int(0), c_int(0)
    f = font.get_ttf_font()
    sdl2.sdlttf.TTF_SizeText(f, text.encode(), byref(text_w), byref(text_h))
    if not text:
        return text_h.value
    return text_w.value, text_h.value


class FontTTF(sdl2.ext.FontTTF):
    """
    Adds quick_render to sdl2.ext.FontTTF
    """
    def line_height(self, size):
        style_key = f"{size}"
        if style_key not in self._styles:
            self.add_style(style_key, size, (255, 255, 255))

        return self._get_line_size("", style_key)[1]

    def quick_render(self, text, size, width=None, align='left', line_h=None):
        """Renders a string of text to a new surface.

        Uses render_text to render text to a new surface.

        It adds a style that matches what we need if it doesnt exist,
        """
        style_key = f"{size}"
        if style_key not in self._styles:
            self.add_style(style_key, size, (255, 255, 255))

        if text == "":
            text = " "

        return self.render_text(text, style_key, width=width, align=align, line_h=line_h)


class TextManager:
    MAX_TEXTURES = 50

    def __init__(self, gui):
        self.gui = gui
        self.renderer = gui.renderer
        self._textures = {}
        self._texture_list = collections.deque([])
        self.fonts = {}

    def add_font(self, font_name, font_file):
        if font_name not in self.fonts:
            self.fonts[font_name] = FontTTF(str(font_file), 22, (255, 255, 255, 255))

    def clean(self):
        """
        Call at the end of a frame to clean up any of the oldest textures.
        """

        while len(self._texture_list) > self.MAX_TEXTURES:
            key = self._texture_list.pop()
            del self._textures[key]

    def line_height(self, font_name, size):
        if font_name not in self.fonts:
            font_file = self.gui.resources.find(font_name)
            if font_file is None:
                raise GUIValueError(f"Unknown font {font_name}.")

            self.add_font(font_name, font_file)

        font = self.fonts[font_name]

        return font.line_height(size)

    def render_text(self, text, font_name, size, *, width=None, align="left", line_h=None):
        if font_name not in self.fonts:
            font_file = self.gui.resources.find(font_name)
            if font_file is None:
                raise GUIValueError(f"Unknown font {font_name}.")

            self.add_font(font_name, font_file)

        font = self.fonts[font_name]

        if text == "":
            text = " "

        key = f"{font.family_name}:{size!r}:{width}:{align}:{line_h}:{text}"
        if key not in self._textures:
            surface = font.quick_render(text, size, width=width, align=align, line_h=line_h)
            texture = self._textures[key] = Texture(
                self.gui,
                sdl2.ext.Texture(self.renderer, surface))
            sdl2.SDL_FreeSurface(surface)
            self._texture_list.appendleft(key)
            return texture

        self._texture_list.remove(key)
        self._texture_list.appendleft(key)
        return self._textures[key]
