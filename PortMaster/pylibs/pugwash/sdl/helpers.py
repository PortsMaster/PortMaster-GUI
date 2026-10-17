# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Small helpers shared by the modules above.

import functools
from collections.abc import Mapping
from ctypes import c_ubyte, byref
import sdl2
import sdl2.ext
import sdl2.sdlmixer


def deep_update(d, u, r=False):
    '''
    Add contents of dict u into dict d. This will change the provided
    d parameter dict

    :param d: dict to add new values to
    :param u: dict with values to add into d
    :rvalue dict: the updated dict, same as d
    '''
    o = d
    for k, v in u.items():
        if not isinstance(d, Mapping):
            o = u

        elif isinstance(v, Mapping):
            r = deep_update(d.get(k, {}), v, True)
            o[k] = r

        else:
            o[k] = u[k]

    return o

def deep_merge(d, u, r=False):
    '''
    Add contents of dict u into a copy of dict d. This will not change the
    provided d parameter dict, only return a new copy.

    :param d: dict to add new values to
    :param u: dict with values to add into d
    :rvalue dict: the new dict with u merged into d
    '''
    n = deep_update({}, d)
    return deep_update(n, u)

def deep_print(d, name=None, l=0, file=None):
    '''
    Pretty print a dict recursively, included all child dicts

    :param d: dict to pring
    :param name: name of dict to use in printing
    :param l: used internaly
    :param file: open file to print into instead of to the console
    '''
    if name: print(f'{"  " * l}{name}', file=file)
    for k, v in d.items():
        if isinstance(v, Mapping):
            deep_print(v, k, l + 1, file)

        else:
            print(f'{"  " * (l + 1)}{k}: {v}', file=file)


def range_list(start, low, high, step):
    '''
    Creates a list of strings representing numbers within a given
    range. Meant for use with gui.options_menu as an alternative to
    a slider widget. The values will be a listin numerical order, but
    rotated to have the start value first.

    :param start: the value to start at (first value)
    :param low: lowest value for list
    :param hight: highest value for list
    :param step: the numerical value between each item in the list
    :rvalue list: a list of numerical values, rotate to have start value
            first

    example: range_list(50, 0, 100, 10) ->
            [50, 60, 70, 80, 90, 100, 0, 10, 20, 30, 40]
    '''
    return [str(i) for i in range(start, high + 1, step)] + [
            str(i) for i in reversed(range(start - step, low - 1, -step))]


def get_color_mod(texture):
    '''
    Get color_mod value of a texture as an RGB 3-tuple
    NOT WORKING
    '''
    r, g, b = c_ubyte(0), c_ubyte(0), c_ubyte(0)
    sdl2.SDL_GetTextureColorMod(texture.tx, byref(r), byref(g), byref(b))
    print('inside get', r.value, g.value, b.value)
    return  r.value, g.value, b.value


def set_color_mod(texture, color):
    '''
    Set color_mod value of a texture using an RGB 3-tuple
    NOT WORKING
    '''
    r, g, b = c_ubyte(color[0]), c_ubyte(color[1]), c_ubyte(color[2])
    sdl2.SDL_SetTextureColorMod(texture.tx, r, g, b)


def autoscroll_text(text_rect, area_rect, alignment, scroll_amount, is_vertical=True):
    # Calculate the fitted rect for the text within the area
    x, y = getattr(area_rect, alignment, area_rect.topleft)

    if is_vertical:
        max_scroll = max(0, text_rect.height - area_rect.height)
        scroll_amount = min(scroll_amount, max_scroll)

        if max_scroll > 0 and alignment == 'center':
            # TEKKENHAX
            return autoscroll_text(text_rect, area_rect, 'topcenter', scroll_amount, is_vertical)

        if 'top' in alignment:
            y -= scroll_amount

        elif 'bottom' in alignment:
            y += scroll_amount

    else:
        max_scroll = max(0, text_rect.width - area_rect.width)
        scroll_amount = min(scroll_amount, max_scroll)

        if max_scroll > 0 and alignment == 'center':
            # TEKKENHAX
            return autoscroll_text(text_rect, area_rect, 'midleft', scroll_amount, is_vertical)

        if 'left' in alignment:
            x -= scroll_amount

        elif 'right' in alignment:
            x += scroll_amount

    return x, y, max_scroll, alignment


@functools.lru_cache(512)
def hex_color_decode(hex_code):
    if hex_code.startswith('#'):
        hex_code = hex_code[1:]

    if len(hex_code) in (3, 4):
        hex_code = ''.join(
            c + c
            for c in hex_code)

    if len(hex_code) not in (6, 8):
        print(f'bad hex_code: {hex_code}')
        return [255, 255, 255]

    return [
        int(hex_code[i:i+2], 16)
        for i in range(0, len(hex_code), 2)]
