# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Point, Rect and NamedRects.

import sdl2
import sdl2.ext
import sdl2.sdlmixer
from .errors import GUIThemeError, GUIValueError


class Point:
    __slots__ = ('x', 'y')

    def __init__(self, x, y):
        self.x = x
        self.y = y


class Rect:
    POINTS = (
        'topleft',
        'midtop',
        'topcenter',
        'topright',
        'midleft',
        'center',
        'midright',
        'bottomleft',
        'midbottom',
        'bottomcenter',
        'bottomright',
        )

    __slots__ = ('x', 'y', 'width', 'height')

    def __init__(self, x, y, width, height):
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)

    def __repr__(self):
        return f'Rect({self.x}, {self.y}, {self.width}, {self.height})'

    def __mul__(self, v):
        'Scale by v keeping center in position'
        cx, cy = self.center
        r = Rect(self.x, self.y, self.width, self.height)
        r.width = int(r.width * v)
        r.height = int(r.height * v)
        r.center = cx, cy
        return r

    def copy(self):
        'Returns a copy of the called Rect object'
        return Rect(self.x, self.y, self.width, self.height)

    def fit(self, other):
        'Move and resize myself to fill other rect maintaining aspect ratio'
        r = self.fitted(other)
        self.x = r.x
        self.y = r.y
        self.width = r.width
        self.height = r.height

    def fitted(self, other):
        '''
        Return new Rect with other centered and resized to fill self.
        Aspect ration is retained
        '''
        xr = self.width / other.width
        yr = self.height / other.height
        mr = max(xr, yr)

        w = int(self.width / mr)
        h = int(self.height / mr)
        x = int(other.x + (other.width - w) / 2)
        y = int(other.y + (other.height - h) / 2)
        return Rect(x, y, w, h)

    @staticmethod
    def from_corners(x, y, x2, y2):
        '''
        Creat a new rect using bottom and right coordinates instead
        of width and height
        '''
        return Rect(x, y, x2 - x, y2 - y)

    @staticmethod
    def from_sdl(r):
        '''
        Create a new rect based on the position and size of an sdl_rect
        object'''
        return Rect(r.x, r.y, r.w, r.h)

    def inflate(self, x, y=None):
        '''
        Add x to width and y to height of rect, or x to both.
        The rect will remain centered around the same point
        '''
        if y is None:
            y = x

        self.x -= x // 2
        self.y -= y // 2
        self.width += x
        self.height += y

    def inflated(self, x, y=None):
        '''
        Return a copy of self with x added to the width and y to the
        height of rect, or x to both. The rect will remain centered
        around the same point
        '''
        if y is None:
            y = x

        nx = self.x - x // 2
        ny = self.y - y // 2
        nw = self.width + x
        nh = self.height + y
        return Rect(nx, ny, nw, nh)

    def move(self, x, y):
        '''
        Move self by x/y pixels
        '''
        self.x += x
        self.y += y

    def moved(self, x, y):
        '''
        Return copy of self moved by x/y pixels
        '''
        return Rect(
            self.x + x, self.y + y,
            self.width, self.height)

    def sdl(self):
        '''
        Return my value as an sdl_rect
        '''
        return sdl2.SDL_Rect(self.x, self.y, self.width, self.height)

    def tuple(self):
        '''
        Return my value as a 4-tuple
        '''
        return self.x, self.y, self.width, self.height

    def update(self, x, y, w, h):
        '''
        Update myself with new position and size
        '''
        self.x = x
        self.y = y
        self.width = w
        self.height = h

    def clip(self, other):
        '''
        Return copy of self cropped to fit inside other Rect
        '''
        # LEFT
        if self.x >= other.x and self.x < (other.x + other.width):
            x = self.x
        elif other.x >= self.x and other.x < (self.x + self.width):
            x = other.x
        else:
            return Rect(self.x, self.y, 0, 0)

        # RIGHT
        if (self.x + self.width) > other.x and (self.x + self.width) <= (other.x + other.width):
            w = self.x + self.width - x
        elif (other.x + other.width) > self.x and (other.x + other.width) <= (self.x + self.width):
            w = other.x + other.width - x
        else:
            return Rect(self.x, self.y, 0, 0)

        # TOP
        if self.y >= other.y and self.y < (other.y + other.height):
            y = self.y
        elif other.y >= self.y and other.y < (self.y + self.height):
            y = other.y
        else:
            return Rect(self.x, self.y, 0, 0)

        # BOTTOM
        if (self.y + self.height) > other.y and (self.y + self.height) <= (other.y + other.height):
            h = self.y + self.height - y
        elif other.y + other.height > self.y and (other.y + other.height) <= (self.y + self.height):
            h = other.y + other.height - y
        else:
            return Rect(self.x, self.y, 0, 0)

        return Rect(x, y, w, h)

    @property
    def w(self):
        return self.width

    @w.setter
    def w(self, v):
        self.width = v
        self.x -= v // 2

    @property
    def h(self):
        return self.height

    @h.setter
    def h(self, v):
        self.height = v
        self.y -= v // 2

    # EDGES
    @property
    def top(self):
        return self.y

    @top.setter
    def top(self, v):
        self.y = v

    @property
    def bottom(self):
        return self.y + self.height

    @bottom.setter
    def bottom(self, v):
        self.y = v - self.height

    @property
    def left(self):
        return self.x

    @left.setter
    def left(self, v):
        self.x = v

    @property
    def right(self):
        return self.x + self.width

    @right.setter
    def right(self, v):
        self.x = v - self.width

    @property
    def centerx(self):
        return self.x + (self.width // 2)

    @centerx.setter
    def centerx(self, v):
        self.x = v - (self.width // 2)

    @property
    def centery(self):
        return self.y + (self.height // 2)

    @centery.setter
    def centery(self, v):
        self.y = v - (self.height // 2)

    # FIRST ROW
    @property
    def topleft(self):
        return self.x, self.y

    @topleft.setter
    def topleft(self, v):
        x, y = v
        self.x = x
        self.y = y

    @property
    def midtop(self):
        return self.x + (self.width // 2), self.y

    @midtop.setter
    def midtop(self, v):
        x, y = v
        self.x = x - (self.width // 2)
        self.y = y

    @property
    def topcenter(self):
        return self.midtop

    @topcenter.setter
    def topcenter(self, v):
        self.midtop = v

    @property
    def topright(self):
        return self.x + self.width, self.y

    @topright.setter
    def topright(self, v):
        x, y = v
        self.x = x - self.width
        self.y = y

    # SECOND ROW
    @property
    def midleft(self):
        return self.x, self.y + (self.height // 2)

    @midleft.setter
    def midleft(self, v):
        x, y = v
        self.x = x
        self.y = y - (self.height // 2)

    @property
    def center(self):
        return self.x + (self.width // 2), self.y + (self.height // 2)

    @center.setter
    def center(self, v):
        x, y = v
        self.x = x - (self.width // 2)
        self.y = y - (self.height // 2)

    @property
    def midright(self):
        return self.x + self.width, self.y + (self.height // 2)

    @midright.setter
    def midright(self, v):
        x, y = v
        self.x = x - self.width
        self.y = y - (self.height // 2)

    # THIRD ROW
    @property
    def bottomleft(self):
        return self.x, self.y + self.height

    @bottomleft.setter
    def bottomleft(self, v):
        x, y = v
        self.x = x
        self.y = y - self.height

    @property
    def midbottom(self):
        return self.x + (self.width // 2), self.y + self.height

    @midbottom.setter
    def midbottom(self, v):
        x, y = v
        self.x = x - (self.width // 2)
        self.y = y - self.height

    @property
    def bottomcenter(self):
        return self.midbottom

    @bottomcenter.setter
    def bottomcenter(self, v):
        self.midbottom = v

    @property
    def bottomright(self):
        return self.x + self.width, self.y + self.height

    @bottomright.setter
    def bottomright(self, v):
        x, y = v
        self.x = x - self.width
        self.y = y - self.height

    @property
    def size(self):
        return self.width, self.height

    @size.setter
    def size(self, v):
        cx, cy = self.center
        self.width, self.height = v
        self.center = cx, cy

    def __len__(self):
        return 4

    def __getitem__(self, i):
        return (self.x, self.y, self.width, self.height)[i]

    def __setitem__(self, i, value):
        if not isinstance(value, int):
            raise GUIValueError(f"{value} is not an int")

        if i < 0:
            i = 4 + i

        if i == 0:
            self.x = value
        elif i == 1:
            self.y = value
        elif i == 2:
            self.width = value
        elif i == 3:
            self.height = value
        else:
            raise GUIValueError(f"{i} is out of bounds.")


class NamedRects:
    def __init__(self, root):
        self._rects = {
            'root': Rect(*root),
            }

    def copy(self):
        new_rects = NamedRects(self._rects['root'])
        new_rects._rects.update(self._rects)
        return new_rects

    def make_rect(self, parent, child, value):
        if parent in self._rects:
            root = self._rects[parent]
        else:
            root = self._rects['root']

        try:
            if len(value) != 4:
                raise GUIThemeError('Region area incorrect length')

        except TypeError:
            print('Region area not iterable')
            raise

        value = list(value)

        # print(f"{child} <- {parent}")
        # print(f"    {value} x {root}")
        for i, p in enumerate(value):
            if not isinstance(p, (int, float)):
                raise GUIThemeError(f'point {i}{p} is not a number')

            if isinstance(p, float) and (0 <= p <= 1):
                value[i] = root.topleft[i % 2] + int(p * root.size[i % 2])

            elif i > 1:
                if p < 0:
                    value[i] = max(0, root.bottomright[i % 2] + int(p))

                else:
                    value[i] = int(p)

            else:
                if p < 0:
                    value[i] = max(0, root.bottomright[i % 2] + int(p))

                else:
                    value[i] = root.topleft[i % 2] + int(p)

        value = Rect.from_corners(*value)

        # print(f"  = {list(value)}")
        if child is not None:
            self._rects[child] = value.copy()

        return value
