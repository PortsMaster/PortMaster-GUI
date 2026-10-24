# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Region, the themeable widget every scene element is drawn with.

import sdl2
import sdl2.ext
import sdl2.sdlmixer
from .errors import GUIThemeError
from .geometry import Rect
from .helpers import autoscroll_text, deep_merge, hex_color_decode
from .images import Image


try:
    import sdl2.sdlgfx as sdlgfx
except ImportError:
    sdlgfx = False

class Region:
    '''
    The Region class is the primary building block of pySDL2gui interfaces.
    It represents a rectangular region, defines its attributes, handles
    user interaction, and draws itself onto the screen. Each region may
    have a fill color, outline, and image, as well as scrolling text, an
    interactive list, or a horizontal toolbar. These attributes are loaded
    from a json file and then passed to the class as a standard dict.

    FILL AND OUTLINE
    area: 4-tuple representing a rectangular area for the region, defined in (left, top, right, bottom) format, not in (x, y, width, height) format like a normal Rect object. It can be in pixels (10, 10, 200, 400), or in screen percent (0.1, 0.1, 0.5, 0.9).
    fill: 3-tuple rgb fill color
    outline: 3-tuple rgb outline color
    thickness: int outline thickness,
    roundness: int radius to draw the region as a rounded rectangle
    border: int border around all sides of text, or use borderx and bordery instead
    borderx: int left/right border around text
    bordery: int top/bottom border around text

    IMAGE RENDERING
    image: filename for an image to draw in the region
    imagesize: an 2-tuple of ints (width, height) to draw image at a specific size
    imagemode: draw mode for the image can be 'fit', 'stretch', or 'repeat'
    imagealign: string options to align the image include: topleft, topright, midtop,
    midleft, center, midright, bottomleft, midbottom, and bottomright
    patch: a 4-tuple of ints (left, top, right, bottom) that defines the size of
    non-stretched portions of the image when drawing as a 9-patch, or None to
    render it normally
    pattern: (TODO) if True the image attribute is loaded as a base64 string value
    pimage: filename or image to use for patch rendering if different than image

    TEXT RENDERING
    align: string options to align the text include: topleft, topright, midtop,
    midleft, center, midright, bottomleft, midbottom, and bottomright
    autoscroll: number of rendered frames (update calls) between each line of auto
    scrolling for the text, or 0 to disable auto-scrolling (default)
    font: filename for the font to draw with
    fontsize: int size of font to draw with
    fontcolor: 3-tuple rgb color used to draw text
    fontoutline: 2-tuple (RGB 3-tuple color, int outline thickness)
    linespace: int extra space between each line of wrapped text
    scrollable: bool that allows up/down events to scroll wrapped text when set to True
    text: text string to draw, which may include newlines
    wrap: set True to allow multiline text wrapping

    LIST RENDERING
    list: a list of items to be displayed and selected from
    itemsize: the height that each list item is drawn with
    select: a 3-tuple rgb color for the selected item, or a Region for rendering it
    selectable: a list including the index for each item of the list that may be selected by the user
    selected: the currently selected list item, which will be drawn using the color or Region referenced by the select attribute
    listcolumns: int number of columns, when above 1 the list is drawn as a grid of tiles
    listimage: a function taking a list index and returning an image filename (or None), called only for the tiles drawn in grid mode
    itempadding: int space between a grid tile's edge and its image/label
    In grid mode itemsize is the tile height (default: 3:4 image plus one line of text),
    itemspacer is the gap between tiles, and altfill is the background of unselected tiles.

    BARS (toolbars)
    bar: a list that may include strings, Image objects, and image filenames. They will be drawn as a horizontal bar. A single null value will split the bar into 2 sides, the first one left aligned and the second one right aligned
    barspace: additional space between each bar item beyond its natural size
    barwidth: the minimum width for each bar item
    selectablex: TODO a list indluding the index for each item in the bar that may be selected by the user
    selectedx: the currently selected list item, or -1 if nothing is selected.
    The selected item will be drawn in the color of or with the Region referenced by the select attribute.
    '''
    SCROLL_START_PAUSE, SCROLL_FORWADS, SCROLL_BACKWARDS, SCROLL_END_PAUSE = (
        'SCROLL_START_PAUSE', 'SCROLL_FORWADS', 'SCROLL_BACKWARDS', 'SCROLL_END_PAUSE')

    SCROLL_FSM = {
        None: {
            SCROLL_START_PAUSE: SCROLL_START_PAUSE,
            },
        'slide': {
            SCROLL_START_PAUSE: SCROLL_FORWADS,
            SCROLL_FORWADS: SCROLL_END_PAUSE,
            SCROLL_END_PAUSE: SCROLL_FORWADS,
            },
        'marquee': {
            SCROLL_START_PAUSE: SCROLL_FORWADS,
            SCROLL_FORWADS: SCROLL_END_PAUSE,
            SCROLL_END_PAUSE: SCROLL_BACKWARDS,
            SCROLL_BACKWARDS: SCROLL_START_PAUSE,
            },
        }

    BLEND_MODES = {
        None:    sdl2.SDL_BLENDMODE_NONE,
        "none":  sdl2.SDL_BLENDMODE_NONE,  # No blending
        "blend": sdl2.SDL_BLENDMODE_BLEND, # Alpha channel blending
        "add":   sdl2.SDL_BLENDMODE_ADD,   # Additive blending
        "mod":   sdl2.SDL_BLENDMODE_MOD,   # Color modulation
        "mul":   sdl2.SDL_BLENDMODE_MUL,   # Color multiplication (SDL >= 2.0.12)
        }

    DATA = {}

    ## Rows above and below the visible ones whose images a grid keeps loaded.
    GRID_PRELOAD_ROWS = 2

    def __init__(self, gui, data, name=None, number=0, rects=None):
        'Create a new Region for future drawing.'
        self._dict = deep_merge(self.DATA, data)

        self.gui = gui
        self.renderer = gui.renderer
        self.images = gui.images
        self.texts = gui.text
        self.pallet = gui.pallet

        if rects is None:
            self._rects = gui.default_rects
        else:
            self._rects = rects

        self.z_position = number
        self.z_index = self._verify_int('z-index', default=None, optional=True)
        self.visible = self._verify_bool('visible', default=True, optional=True)

        self.blendmode = self._verify_option('blend-mode', list(self.BLEND_MODES), optional=True)

        self.name = name
        self.parent = self._verify_text('parent', default='root', optional=True)
        self.area = self._verify_rect('area')
        self.fill = self._verify_color('fill', optional=True)
        self.alt_fill = self._verify_color('alt-fill', optional=True)
        self.progress_fill = self._verify_color('progress-fill', optional=True)
        self.outline = self._verify_color('outline', optional=True)
        self.thickness = self._verify_int('thickness', 0)
        self.roundness = self._verify_int('roundness', 0)
        self.border = self._verify_int('border', 0)
        self.bordery = self._verify_int('border-y', self.border) or 0
        self.borderx = self._verify_int('border-x', self.border)

        self.image = self.images.load(self._dict.get('image'))
        self.image_mod = self._verify_color('image-mod', optional=True)
        self.imagesize = self._verify_ints('image-size', 2, None, optional=True)
        self.imagemode = self._verify_option('image-mode',
                ('fit', 'fit-horizontal', 'fit-vertical', 'stretch', 'repeat', None), 'fit')
        self.imagealign = self._verify_option('image-align', Rect.POINTS, None)
        self.patch = self._verify_ints('patch', 4, optional=True)
        self.pimage = self.images.load(self._dict.get('pimage'))
        if self.patch and not self.pimage:
            self.pimage = self.image
            self.image = None

        self.pattern = False

        self.pointer = self.images.load(self._dict.get('pointer'))
        self.pointer_align = self._verify_option('pointer-align', Rect.POINTS, default=['midright', 'midleft'], length=2)
        self.pointer_size = self._verify_ints('pointer-size', 2, optional=True)
        self.pointer_attach = self._verify_option('pointer-attach', ['text', 'list'], default='text')
        self.pointer_offset = self._verify_ints('pointer-offset', 2, default=[0, 0])
        self.pointer_flip_x = self._verify_bool('pointer-flip-x', False)
        self.pointer_flip_y = self._verify_bool('pointer-flip-y', False)

        self.pointer_mirror = self._verify_bool('pointer-mirror', False)
        self.pointer_mirror_x = self._verify_bool('pointer-mirror-x', self.pointer_mirror)
        self.pointer_mirror_y = self._verify_bool('pointer-mirror-y', False)

        # TODO figure out how to use default/system fonts
        self.font = self._verify_file('font', optional=True)
        self.fontsize = self._verify_int('font-size', 30)
        self.fontsize *= self._verify_float('font-scale', 1.0, optional=True)
        self.font_color = self._verify_color('font-color', (255, 255, 255))
        self.fontoutline = self._verify_outline('font-outline', None, optional=True)
        self._text = self._verify_text('text', optional=True)
        self.textclip = self._verify_bool('text-clip', True, optional=True)
        self.textwrap = self._verify_bool('text-wrap', False, optional=True)
        self.linespace = self._verify_int('line-space', 0, optional=True)
        self.lineheight = self._verify_float('line-height', 1.0, optional=True)
        self.align = self._verify_option('align', Rect.POINTS, 'topleft')

        self.imagelist = 0 ## TODO
        self.ilistalign = 0 ## TODO

        self.itemsize = self._verify_int('item-size', None, optional=True)
        self.item_spacer = self._verify_int('item-spacer', 0, optional=True)
        self.item_padding = self._verify_int('item-padding', 4, optional=True, minimum=0)

        self.list_columns = self._verify_int('list-columns', 1, minimum=1, maximum=6)
        self.list_image = None
        self.grid_start_row = 0

        self.select_color = self._verify_color('select-color', optional=True)
        self.select_fill = self._verify_color('select-fill', optional=True)
        self.noselect_color = self._verify_color('no-select-color', optional=True)
        self.noselect_fill = self._verify_color('no-select-fill', optional=True)
        self.inactive_select_color = self._verify_color('inactive-select-color', optional=True)
        self.inactive_select_fill = self._verify_color('inactive-select-fill', optional=True)

        self.click_sound = self._verify_text('click-sound', optional=True)
        self.click_sound_volume = self._verify_int('click-sound-volume', 128, optional=True, minimum=0, maximum=128)
        self.button_sound = self._verify_text('button-sound', optional=True)
        self.button_sound_volume = self._verify_int('button-sound-volume', 128, optional=True, minimum=0, maximum=128)
        self.button_sound_alt = self._verify_text('button-sound-alt', optional=True)
        self.button_sound_alt_volume = self._verify_int('button-sound-alt-volume', 128, optional=True, minimum=0, maximum=128)

        self.scrollable = self._verify_bool('scrollable', False, True)

        self.autoscroll = self._verify_option('autoscroll', (None, 'slide', 'marquee'), None)
        self.scroll_speed = self._verify_int('scroll-speed', 30, optional=True)
        self.scroll_amount = self._verify_int('scroll-amount', 1, optional=True, minimum=0, maximum=10)
        self.scroll_direction = self._verify_option(
            'scroll-direction',
            ('vertical', 'horizontal'),
            self.textwrap and 'vertical' or 'horizontal')

        self.scroll_delay_start = self._verify_int('scroll-delay-start', 1000, True)
        self.scroll_delay_end = self._verify_int('scroll-delay-end', 1000, True)
        self.scroll_state = self.SCROLL_START_PAUSE

        self.barspace = self._verify_int('bar-space', 4)
        self.barwidth = self._verify_int('bar-width', 0, optional=True)
        self.bar_select_mode = 'item'
        self._bar = self._verify_bar('bar', optional=True, align=self.align)
        self.list = self._verify_list('list', optional=True)
        if self.list is not None:
            self._list_selected = [0] * len(self.list)

        self.list_header = self._verify_text('list-header', optional=True)
        self.list_header_add_blank = self._verify_bool('list-header-add-blank', False, optional=True)

        self.list_section_add_blank = self._verify_bool('list-section-add-blank', False, optional=True)

        if self._text and self.list:
            raise GUIThemeError('Cannot define text and a list')

        self.scroll_pos = 0
        self.scroll_max = 0
        self.scroll_last_update = sdl2.SDL_GetTicks64()
        self.progress_amount = 0
        self.page_size = 1

        self.selected = 0
        self.selectedx = 0

        self.info = self._verify_list('info', optional=True)
        self.options = self._verify_list('options', optional=True, allow_null=True)

        if self._text is not None:
            # Trigger text setting code
            self.text = self._text


    def draw(self, area=None, text=None, image=None):
        '''
        Draw all features of this Region

        area: override Region's area, used internally
        text: override Region's text and list, used internally
        image: override Region's image, used internally
        '''

        area = area or self.area.copy()
        image = image or self.image

        if self.blendmode not in self.BLEND_MODES:
            self.blendmode = None

        self.gui.renderer.blendmode = self.BLEND_MODES[self.blendmode]

        # FILL AND OUTLINE
        if self.patch:
            self._draw_patch(area, self.pimage)
            area = Rect.from_corners(
                area.x + self.patch[0], area.y + self.patch[1],
                area.right - self.patch[2], area.bottom - self.patch[3])

        elif self.fill and self.outline:
            if self.roundness and sdlgfx:
                sdlgfx.roundedBoxRGBA(self.renderer.sdlrenderer,
                    area.x, area.y, area.right, area.bottom,
                    self.roundness, *self.outline)

            area.inflate(-self.thickness)

            if self.roundness and sdlgfx:
                sdlgfx.roundedBoxRGBA(self.renderer.sdlrenderer,
                    area.x, area.y, area.right, area.bottom,
                    self.roundness, *self.fill)

            else:
                self.renderer.fill(area.sdl(), self.outline)
                area.inflate(-self.thickness)
                self.renderer.fill(area.sdl(), self.fill)

            if self.progress_amount > 0 and self.progress_fill:
                amount = int(min(self.progress_amount, 100))

                progress_area = area.copy()
                progress_area.width = int(area.width / 100 * amount)

                if self.roundness and sdlgfx:
                    sdlgfx.roundedBoxRGBA(self.renderer.sdlrenderer,
                        progress_area.x, progress_area.y, progress_area.right, progress_area.bottom,
                        self.roundness, *self.progress_fill)

                else:
                    progress_area.inflate(-self.thickness)
                    self.renderer.fill(progress_area.sdl(), self.progress_fill)

        elif self.fill:
            if self.roundness and sdlgfx:
                sdlgfx.roundedBoxRGBA(self.renderer.sdlrenderer,
                    area.x, area.y, area.right, area.bottom,
                    self.roundness, *self.fill)
            else:
                # print(self.fill)
                self.renderer.fill(area.sdl(), self.fill)

            if self.progress_amount > 0 and self.progress_fill:
                amount = int(min(self.progress_amount, 100))

                progress_area = area.copy()
                progress_area.width = int(area.width / 100 * amount)

                if self.roundness and sdlgfx:
                    sdlgfx.roundedBoxRGBA(self.renderer.sdlrenderer,
                        progress_area.x, progress_area.y, progress_area.right, progress_area.bottom,
                        self.roundness, *self.progress_fill)

                else:
                    progress_area.inflate(-self.thickness)
                    self.renderer.fill(progress_area.sdl(), self.progress_fill)

        elif self.outline:
            r = area.sdl()
            for _ in range(self.thickness - 1):
                if self.roundness and sdlgfx:
                    sdlgfx.roundedRectangleRGBA(self.renderer.sdlrenderer,
                        r.x, r.y, r.x + r.w, r.y + r.h,
                        self.roundness, *self.outline)
                else:
                    self.renderer.draw_rect(r, self.outline)

                r.x += 1
                r.y += 1
                r.w -= 2
                r.h -= 2

            area.size = area.w - self.thickness, area.h - self.thickness

        # RENDER IMAGE
        if self.image and not self.patch:
            image = self.image #s.load(self.image)
            dest = Rect.from_sdl(image.srcrect)

            color_mod = None
            if self.image_mod is not None:
                color_mod = image.get_color_mod()
                image.set_color_mod(self.image_mod[:3])

            if self.imagesize:
                dest.size = self.imagesize

            if self.imagemode == 'fit':
                dest.fit(area)
                if self.imagealign:
                    w = getattr(area, self.imagealign)
                    setattr(dest, self.imagealign, w)

                image.draw_in(dest.tuple())

            elif self.imagemode.startswith('fit-'):
                image.draw_fit(
                    dest,
                    area,
                    ('horizontal' in self.imagemode and 'horizontal' or 'vertical'),
                    (self.imagealign or 'center')
                    )

            elif self.imagemode == 'stretch':
                image.draw_in(area.tuple())

            elif self.imagemode == 'repeat':
                pass # TODO

            else:
                dest.topleft = area.topleft
                image.draw_in(dest.clip(area).tuple())

            if color_mod is not None:
                image.set_color_mod(color_mod)

        text_area = area.inflated(-self.borderx * 2, -self.bordery * 2)

        # if self.font and self.fontsize:
        #     self.fonts.load(self.font, self.fontsize)
        # else:
        #     return

        # RENDER BAR (toolbarish)
        align_to_textalign = {
            'center': 'center',
            'topleft': 'left',
            'midleft': 'left',
            'bottomleft': 'left',
            'topcenter': 'center',
            'bottomcenter': 'center',
            'topright': 'right',
            'midright': 'right',
            'bottomright': 'right',
            'midtop': 'center',
            'midbottom': 'center',
            }

        align_opposite = {
            'midtop': 'midbottom',
            'midbottom': 'midtop',
            'bottomcenter': 'topcenter',
            'topcenter': 'bottomcenter',
            'bottomcenter': 'topcenter',
            'center': 'center',
            'topleft': 'bottomright',
            'midleft': 'midright',
            'bottomleft': 'topright',
            'bottomcenter': 'topcenter',
            'topright': 'bottomleft',
            'midright': 'midleft',
            'bottomright': 'topleft',
            }

        if self._bar:
            self._draw_bar(text_area, self._bar)

        # RENDER TEXT
        elif text:
            # x, y = getattr(text_area, self.align, text_area.topleft)
            # self.fonts.draw(text, x, y, self.font_color, 255, self.align,
            #         text_area, outline=self.fontoutline).height + self.linespace
            ...

        elif self._text:
            if text_area.width > 0 and text_area.height > 0:
                itemsize = self.texts.line_height(self.font, self.fontsize) * self.lineheight
                self.page_size = max(text_area.height // (itemsize), 1)

                if self.textwrap:
                    texture = self.texts.render_text(
                        self._text,
                        self.font,
                        self.fontsize,
                        width=text_area.width,
                        align=align_to_textalign[self.align],
                        line_h=int(itemsize))

                else:
                    texture = self.texts.render_text(
                        self._text,
                        self.font,
                        self.fontsize,
                        align=align_to_textalign[self.align],
                        line_h=int(itemsize),
                        )

                # x, y = getattr(text_area, self.align, text_area.topleft)
                x, y, self.scroll_max, alignment = autoscroll_text(
                    texture.size,
                    text_area,
                    self.align,
                    self.scroll_pos,
                    self.scroll_direction == 'vertical')

                setattr(texture.size, alignment, (x, y))

                with texture.with_color_mod(self.font_color):
                    if self.textclip:
                        texture.draw_in(text_area, clip=True)
                    else:
                        texture.draw_in(text_area, fit=True)

            else:
                self.page_size = 1

            # pos = self.scroll_pos % len(self._text)

            # x, y = getattr(text_area, self.align, text_area.topleft)
            # #y += self.linespace // 2
            # for l in self._text[pos:]:
            #     if y + self.fonts.height > text_area.bottom:
            #         break

            #     y += self.fonts.draw(l, x, y, self.font_color, 255, self.align,
            #             text_area, outline=self.fontoutline).height + self.linespace

        # RENDER GRID
        elif self.list and self.list_columns > 1:
            self._draw_grid(text_area)

        # RENDER LIST
        elif self.list:
            if self.itemsize is not None:
                itemsize = self.itemsize
            else:
                itemsize = self.texts.line_height(self.font, self.fontsize)

            itemsize = int(itemsize * self.lineheight)

            self.page_size = max(area.height // (itemsize + self.item_spacer), 1)
            self.selected = self.selected % len(self.list)

            # self.fonts.load(self.font, self.fontsize)
            if len(self.list) > self.page_size:
                start = max(0, min(self.selected - self.page_size // 3,
                        len(self.list) -self.page_size))
            else:
                start = 0

            irect = text_area.copy()
            irect.height = itemsize
            i = start
            for zz, t in enumerate(self.list[start: start + self.page_size], i):
                if self.select_fill is not None and self.selected == i:
                    self.renderer.fill(irect, self.select_fill)

                elif self.noselect_fill is not None and not self.list_selectable(i):
                    self.renderer.fill(irect, self.noselect_fill)

                elif self.alt_fill is not None and (zz & 1):
                    self.renderer.fill(irect, self.alt_fill)

                if isinstance(t, (list, tuple)):
                    bar = self._verify_bar(None, t, irect, align=align_to_textalign[self.align])

                    x = self.bar_selected(i)
                    # if i == self.selected:
                    # else:
                    #     x = None

                    self._draw_bar(irect, bar, x, active=(self.selected==i))

                elif self.selected == i:
                    ## Not sure what this is used for.
                    #
                    # if isinstance(self.select_color, Region):
                    #     r = irect.inflated(self.borderx * 2, self.bordery * 2)
                    #     self.select_color.draw(irect, t)
                    #     self.fonts.load(self.font, self.fontsize)
                    # else:
                    if self.select_color is None:
                        self.select_color = self.font_color

                    texture = self.texts.render_text(
                        t,
                        self.font, self.fontsize, align=align_to_textalign[self.align])

                    x, y, self.scroll_max, alignment = autoscroll_text(
                        texture.size,
                        irect,
                        self.align,
                        self.scroll_pos,
                        self.scroll_direction == 'vertical')

                    setattr(texture.size, alignment, (x, y))

                    with texture.with_color_mod(self.select_color):
                        if self.textclip:
                            drawn_rect = texture.draw_in(irect, clip=True)
                        else:
                            drawn_rect = texture.draw_in(irect, fit=True)

                    if self.pointer is not None:
                        if self.pointer_size is not None:
                            pointer_rect = Rect(*(0, 0, self.pointer_size[0], self.pointer_size[1]))

                        else:
                            pointer_rect = Rect(*(0, 0, self.pointer.srcrect.w, self.pointer.srcrect.h))

                        if self.pointer_attach == 'list':
                            drawn_rect = irect

                        (x, y) = getattr(drawn_rect, self.pointer_align[0])
                        setattr(pointer_rect, self.pointer_align[1], (x, y))

                        pointer_rect.x += self.pointer_offset[0]
                        pointer_rect.y += self.pointer_offset[1]

                        self.pointer.draw_in(
                            pointer_rect, fit=True, flip_x=self.pointer_flip_x, flip_y=self.pointer_flip_y)

                        if self.pointer_mirror:
                            if self.pointer_size is not None:
                                pointer_rect = Rect(*(0, 0, self.pointer_size[0], self.pointer_size[1]))

                            else:
                                pointer_rect = Rect(*(0, 0, self.pointer.srcrect.w, self.pointer.srcrect.h))

                            if self.pointer_attach == 'list':
                                drawn_rect = irect

                            (x, y) = getattr(drawn_rect, align_opposite[self.pointer_align[0]])
                            setattr(pointer_rect, align_opposite[self.pointer_align[1]], (x, y))

                            pointer_rect.x -= self.pointer_offset[0]
                            pointer_rect.y -= self.pointer_offset[1]

                            pointer_flip_x = self.pointer_flip_x
                            if self.pointer_mirror_x:
                                pointer_flip_x = not pointer_flip_x

                            pointer_flip_y = self.pointer_flip_y
                            if self.pointer_mirror_y:
                                pointer_flip_y = not pointer_flip_y

                            self.pointer.draw_in(
                                pointer_rect, fit=True, flip_x=pointer_flip_x, flip_y=pointer_flip_y)                            

                else:
                    if self.noselect_color and not self.list_selectable(i):
                        fontcolor = self.noselect_color
                    else:
                        fontcolor = self.font_color

                    texture = self.texts.render_text(
                        t,
                        self.font, self.fontsize, align=align_to_textalign[self.align])

                    x, y = getattr(irect, self.align, irect.topleft)
                    setattr(texture.size, self.align, (x, y))

                    with texture.with_color_mod(fontcolor):
                        if self.textclip:
                            texture.draw_in(irect, clip=True)
                        else:
                            texture.draw_in(irect, fit=True)

                irect.y += itemsize + self.item_spacer
                i += 1

    def _draw_grid(self, area):
        '''
        Draw the list as a grid of tiles, each tile showing its image from
        list_image above its label. Used internally
        '''
        columns = self.list_columns
        spacer = self.item_spacer
        label_h = int(self.texts.line_height(self.font, self.fontsize) * self.lineheight)

        tile_w = max((area.width - spacer * (columns - 1)) // columns, 1)
        if self.itemsize is not None:
            tile_h = self.itemsize
        else:
            tile_h = tile_w * 3 // 4 + label_h

        rows = max((area.height + spacer) // (tile_h + spacer), 1)
        total_rows = (len(self.list) + columns - 1) // columns

        self.page_size = rows * columns
        self.selected = self.selected % len(self.list)

        # Only scroll once the selection leaves the visible rows.
        selected_row = self.selected // columns
        if selected_row < self.grid_start_row:
            self.grid_start_row = selected_row
        elif selected_row >= self.grid_start_row + rows:
            self.grid_start_row = selected_row - rows + 1

        self.grid_start_row = max(0, min(self.grid_start_row, total_rows - rows))
        start = self.grid_start_row * columns
        visible_rows = rows

        for i, t in enumerate(self.list[start: start + self.page_size], start):
            row, column = divmod(i - start, columns)
            tile = Rect(
                area.x + column * (tile_w + spacer),
                area.y + row * (tile_h + spacer),
                tile_w, tile_h)

            is_selected = (i == self.selected)
            if is_selected and self.select_fill is not None:
                fill = self.select_fill
            elif self.noselect_fill is not None and not self.list_selectable(i):
                fill = self.noselect_fill
            else:
                fill = self.alt_fill

            if fill is not None:
                # Didn't use sdlgfx as not every device ships with it.
                radius = min(self.roundness, tile.width // 2, tile.height // 2)
                rows = [(tile.x, tile.y + radius, tile.width, tile.height - radius * 2)]
                for row, cut in enumerate(self._corner_cuts(radius)):
                    rows += [
                        (tile.x + cut, tile.y + row, tile.width - cut * 2, 1),
                        (tile.x + cut, tile.bottom - row - 1, tile.width - cut * 2, 1)]

                self.renderer.fill(rows, fill)

            inner = tile.inflated(-self.item_padding * 2)
            image_area = Rect(inner.x, inner.y, inner.width, inner.height - label_h)
            label_area = Rect(inner.x, inner.bottom - label_h, inner.width, label_h)

            image = None
            if self.list_image is not None:
                image = self.images.load(self.list_image(i))

            if image is not None and image_area.width > 0 and image_area.height > 0:
                dest = Rect.from_sdl(image.srcrect)
                dest.fit(image_area)
                image.draw_in(dest.tuple())

                if self.roundness and fill is not None:
                    # Round the image by painting over its corners in the tile colour.
                    radius = min(self.roundness, dest.width // 2, dest.height // 2)
                    corners = []
                    for row, cut in enumerate(self._corner_cuts(radius)):
                        top, bottom = dest.y + row, dest.bottom - row - 1
                        left, right = dest.x, dest.right - cut
                        corners += [
                            (left, top, cut, 1), (right, top, cut, 1),
                            (left, bottom, cut, 1), (right, bottom, cut, 1)]

                    if corners:
                        self.renderer.fill(corners, fill)

            if is_selected:
                color = self.select_color if self.select_color is not None else self.font_color
            elif self.noselect_color and not self.list_selectable(i):
                color = self.noselect_color
            else:
                color = self.font_color

            texture = self.texts.render_text(
                str(t),
                self.font, self.fontsize, align='center')

            if is_selected:
                # Only the selected tile's label autoscrolls, like the plain list.
                x, y, self.scroll_max, alignment = autoscroll_text(
                    texture.size,
                    label_area,
                    'center',
                    self.scroll_pos,
                    False)
            else:
                alignment = 'center'
                x, y = label_area.center

            setattr(texture.size, alignment, (x, y))

            with texture.with_color_mod(color):
                texture.draw_in(label_area, clip=True)

        if self.list_image is not None:
            self._preload_grid(start, visible_rows, columns)

    def _preload_grid(self, start, rows, columns):
        '''
        Load the images of the GRID_PRELOAD_ROWS rows either side of the visible ones, after
        the visible tiles so those decode first, and keep room for all of them in the cache.
        Used internally
        '''
        preload = self.GRID_PRELOAD_ROWS * columns
        self.images.keep(rows * columns + preload * 2)

        end = start + rows * columns
        for i in list(range(end, min(end + preload, len(self.list)))) + list(range(max(start - preload, 0), start)):
            self.images.load(self.list_image(i))

    def _corner_cuts(self, radius):
        '''
        How far each row of a rounded corner is cut in, top row first. Used internally
        '''
        return [
            radius - int((radius ** 2 - (radius - row - 0.5) ** 2) ** 0.5)
            for row in range(radius)]

    def _update_grid(self):
        '''
        Handle input for a grid list: LEFT/RIGHT move one tile, UP/DOWN
        move one row, L1/R1 move one page. Used internally

        RETURNS: True if the selection changed
        '''
        events = self.gui.events
        columns = self.list_columns
        last = len(self.list) - 1

        if events.was_pressed('LEFT') or events.was_pressed('L_LEFT') or events.was_pressed('R_LEFT'):
            target = self.selected - 1

        elif events.was_pressed('RIGHT') or events.was_pressed('L_RIGHT') or events.was_pressed('R_RIGHT'):
            target = self.selected + 1

        elif events.was_pressed('UP') or events.was_pressed('L_UP') or events.was_pressed('R_UP'):
            target = self.selected - columns

        elif events.was_pressed('DOWN') or events.was_pressed('L_DOWN') or events.was_pressed('R_DOWN'):
            target = self.selected + columns
            # Moving down onto a shorter last row lands on its final tile.
            if target > last and self.selected // columns < last // columns:
                target = last

        elif events.was_pressed('L1'):
            target = max(self.selected - self.page_size, 0)

        elif events.was_pressed('R1'):
            target = min(self.selected + self.page_size, last)

        else:
            return False

        if target < 0 or target > last or target == self.selected:
            return False

        self.list_select(target, direction=(1 if target > self.selected else -1))
        self.gui.sounds.play(self.click_sound, volume=self.click_sound_volume)
        return True

    def reset_options(self):
        self.list = []
        self.options = []
        self.descriptions = []
        self._list_selected = []

        if self.list_header not in ("", None):
            if self.selected == 0:
                self.selected += 1

            self.add_option(None, self.list_header)

            if self.list_header_add_blank:
                self.add_option(None, "")
                if self.selected == 1:
                    self.selected += 1

        self.gui.updated = True

    def add_option(self, option, text, index=0, description=None, in_section=False):
        if self.list is None:
            self.list = []
            self.options = []
            self.descriptions = []
            self._list_selected = []

        if self.options is None:
            self.options = []

        if self.options is None:
            self.descriptions = []

        if self._list_selected is None:
            self._list_selected = []

        while len(self.options) < len(self.list):
            self.options.append(None)

        while len(self.descriptions) < len(self.list):
            self.descriptions.append("")

        while len(self._list_selected) < len(self.list):
            self._list_selected.append(0)

        if not in_section and option is None and text is not None and len(self.options) > 0 and self.list_section_add_blank:
            # We add a blank before a "section" in the list.
            self.add_option(None, "", in_section=True)

        self.gui.updated = True
        self.descriptions.append(description)
        self.options.append(option)
        self.list.append(text)
        self._list_selected.append(index)

    def selected_option(self):
        if self.options is None:
            return None
        if self.list is None:
            return None

        if len(self.options) == 0:
            return None

        if self.selected >= len(self.options):
            return None

        return self.options[self.selected]

    def selected_description(self):
        if self.descriptions is None:
            return ""
        if self.list is None:
            return ""

        if len(self.descriptions) == 0:
            return ""

        if self.selected >= len(self.descriptions):
            return ""

        return self.descriptions[self.selected]

    def list_selected(self):
        return self.selected

    def list_selectable(self, index):
        if self.list is None:
            return False

        if self.options is None:
            return True

        if index >= len(self.options):
            return True

        return self.options[index] is not None

    def list_select(self, index, direction=1, allow_wrap=False):
        if self.list is None:
            return

        length = len(self.list)
        options = self.options

        if options and len(options) < length:
            options = None

        if options and not any(options):
            options = None

        while True:
            if index < 0:
                if allow_wrap:
                    new_index = index % length
                else:
                    new_index = 0
                    direction = 1

            elif index >= length:
                if allow_wrap:
                    new_index = index % length
                else:
                    new_index = length - 1
                    direction = -1

            else:
                new_index = index

            if options is None:
                self.selected = new_index
                self.gui.update = True
                return new_index

            if options[new_index] is not None:
                self.selected = new_index
                self.gui.update = True
                return new_index

            index += direction

        return None

    def bar_selected(self, selected=None):
        if selected is None:
            selected = self.selected

        if self._bar is None:
            if self.list is None:
                return -1

            if not isinstance(self.list[selected], list):
                return -1

            return self._list_selected[selected]

        else:
            return self.selectedx

    def bar_select(self, index, selected=None, allow_wrap=False):
        if selected is None:
            selected = self.selected

        if self._bar is None:
            if self.list is None:
                return -1

            if not isinstance(self.list[selected], list):
                return -1

            bar = self.list[selected]

        else:
            bar = self._bar

        length = len(bar)

        if index < 0:
            if allow_wrap:
                new_index = index % length
            else:
                new_index = 0

        elif index >= length:
            if allow_wrap:
                new_index = index % length
            else:
                new_index = length - 1

        else:
            new_index = index

        if self._bar is None:
            self._list_selected[selected] = new_index
            self.gui.updated = True

        else:
            self.selectedx = self.new_index
            self.gui.update = True

        return new_index

    def update(self):
        '''
        Update current region based on given input and autoscrolling parameters

        inp: reference to an gui.InputHandler to receive input
        RETURNS: True if screen should redraw, otherwise False
        '''
        updated = False
        current_time = sdl2.SDL_GetTicks64()

        if self.autoscroll and self.scroll_max > 0:
            scroll_change = False
            scroll_pos = self.scroll_pos
            scroll_dt = (current_time - self.scroll_last_update)
            # print(f"{self.autoscroll} -> {self.scroll_state} -> {scroll_dt} -> {self.scroll_pos} / {self.scroll_max}")

            if self.scroll_state == self.SCROLL_FORWADS:
                if self.scroll_pos >= self.scroll_max:
                    self.scroll_state = self.SCROLL_FSM[self.autoscroll][self.scroll_state]
                    self.scroll_last_update = current_time
                    scroll_dt = 0
                    # updated = True

            elif self.scroll_state == self.SCROLL_BACKWARDS:
                if self.scroll_pos <= 0:
                    self.scroll_state = self.SCROLL_FSM[self.autoscroll][self.scroll_state]
                    self.scroll_last_update = current_time
                    scroll_dt = 0
                    # updated = True

            if self.scroll_state == self.SCROLL_FORWADS:
                if scroll_dt >= self.scroll_speed:
                    self.scroll_pos += self.scroll_amount
                    self.scroll_last_update = current_time
                    # updated = True

            elif self.scroll_state == self.SCROLL_BACKWARDS:
                if scroll_dt >= self.scroll_speed:
                    self.scroll_pos -= self.scroll_amount
                    self.scroll_last_update = current_time
                    # updated = True

            elif self.scroll_state == self.SCROLL_START_PAUSE:
                if scroll_dt >= self.scroll_delay_start:
                    self.scroll_state = self.SCROLL_FSM[self.autoscroll][self.scroll_state]
                    self.scroll_last_update = current_time
                    scroll_change = True
                    # updated = True

            elif self.scroll_state == self.SCROLL_END_PAUSE:
                if scroll_dt >= self.scroll_delay_end:
                    self.scroll_state = self.SCROLL_FSM[self.autoscroll][self.scroll_state]
                    self.scroll_last_update = current_time
                    scroll_change = True
                    # updated = True

            if scroll_change:
                if self.scroll_state == self.SCROLL_FORWADS:
                    self.scroll_pos = 0
                if self.scroll_state == self.SCROLL_BACKWARDS:
                    self.scroll_pos = self.scroll_max

            if scroll_pos != self.scroll_pos:
                # print(f"{scroll_pos} -> {self.scroll_pos}")
                updated = True

        if self.text and self.scrollable:
            if self.gui.events.was_pressed('UP'):
                updated = True
                self.scroll_pos -= 1

            elif self.gui.events.was_pressed('DOWN'):
                self.scroll_pos += 1
                updated = True
            self.scroll_pos = min(max(0, self.scroll_pos), len(self.text) - 1)

        elif self.list is not None:
            length= len(self.list)
            selected = self.selected
            options = self.options
            changed = False
            if options is not None and len(options) != length:
                options = None

            if self.list_columns > 1:
                changed = length > 0 and self._update_grid()

            elif self.gui.events.was_pressed('L1'):
                self.list_select(self.selected - self.page_size, direction=-1, allow_wrap=False)

                self.gui.sounds.play(self.click_sound, volume=self.click_sound_volume)
                changed = True

            elif self.gui.events.was_pressed('R1'):
                self.list_select(self.selected + self.page_size, direction=1, allow_wrap=False)

                self.gui.sounds.play(self.click_sound, volume=self.click_sound_volume)
                changed = True

            elif self.gui.events.was_pressed('UP') or self.gui.events.was_pressed('L_UP') or self.gui.events.was_pressed('R_UP'):
                self.list_select(self.selected - 1, direction=-1, allow_wrap=True)

                self.gui.sounds.play(self.click_sound, volume=self.click_sound_volume)
                changed = True

            elif self.gui.events.was_pressed('DOWN') or self.gui.events.was_pressed('L_DOWN') or self.gui.events.was_pressed('R_DOWN'):
                self.list_select(self.selected + 1, direction=1, allow_wrap=True)

                self.gui.sounds.play(self.click_sound, volume=self.click_sound_volume)
                changed = True

            elif self.gui.events.was_pressed('LEFT'):
                self.bar_select(self.bar_selected() - 1, allow_wrap=False)
                changed = True

            elif self.gui.events.was_pressed('RIGHT'):
                self.bar_select(self.bar_selected() + 1, allow_wrap=False)
                changed = True

            if changed:
                if self.autoscroll:
                    self.scroll_state = self.SCROLL_START_PAUSE
                    self.scroll_last_update = current_time

                updated = True

        if updated:
            self.gui.updated = True

        return updated

    @property
    def text(self):
        return self._text
    @text.setter
    def text(self, val):
        'Process text for proper wrapping when user changes it.'
        if self.textwrap:
            self._text = val
            self.scroll_state = self.SCROLL_START_PAUSE
            self.scroll_pos = 0
            self.scroll_last_update = sdl2.SDL_GetTicks64()
            self.gui.update = True
        else:
            self._text = val
        #print(f'text set to:\n{self._text}')

    @property
    def bar(self):
        return self._bar
    @bar.setter
    def bar(self, val):
        self._bar = self._verify_bar(None, val, align=self.align)
        self.gui.update = True

    def _verify_bar(self, name, default=None, area=None, optional=True, align=None):
        '''
        Process bar list for future display and selection. Used internally.

        name: key for Region dict to read bar list from
        default: default value is None
        area: override Region's area, used internally
        '''
        vals = self._dict.get(name, default)
        if vals is None and optional: return None

        if not isinstance(vals, (list, tuple)):
            raise GUIThemeError("bar is not a list")

        if vals.count('None') > 1:
            raise GUIThemeError('bar has more than one null value separator')

        if not area:
            area = self.area
            if self.patch:
                area = Rect.from_corners(
                    area.x + self.patch[0], area.y + self.patch[1],
                    area.right - self.patch[2], area.bottom - self.patch[3])
            else:
                area = area.inflated(-self.borderx * 2, -self.bordery * 2)

        x = area.x
        y = area.centery
        max_width = 0

        items = left = []
        right = []

        for i, v in enumerate(vals):
            im = v if isinstance(v, Image) else self.images.load(v)
            if not im and v in self.gui.override:
                v = self.gui.override[v]

            if im:
                dest = Rect.from_sdl(im.srcrect).fitted(area)
                dest.x = x
                dest.width = max(dest.w, self.barwidth)
                x = dest.right + self.barspace
                items.append((dest, im))

            elif isinstance(v, str):
                texture = self.texts.render_text(
                    v,
                    self.font, self.fontsize, align='left')

                dest = Rect(x, y, max(texture.size.width, self.barwidth), texture.size.width)
                dest.centery = area.centery
                x = dest.right + self.barspace
                items.append((dest, v))

            elif v is None:
                items = right

            else:
                raise GUIThemeError(f'bar item {i}({v}) not valid type')

            max_width = x - area.x

        if align is not None and len(right) == 0 and ('center' in align or 'right' in align):
            if 'center' in align:
                offset = (area.width - max_width) // 2

            elif 'right' in align:
                offset = (area.width - max_width)

            for dest, item in left:
                dest.x += offset

        elif len(right):
            x = area.right
            for dest, item in right:
                dest.right = x
                x -= dest.width + self.barspace

        return left + right

    def _draw_bar(self, area, bar, selected=None, active=False):
        '''
        Draw bar in given area. Used internally
        '''
        #mode, self.renderer.blendmode = self.renderer.blendmode, sdl2.SDL_BLENDMODE_BLEND
        #self.fonts.load(self.font, self.fontsize)

        for i, (dest, item) in enumerate(bar):
            if isinstance(item, Image):
                item.draw_in(Rect.from_sdl(item.srcrect).fitted(dest).tuple())

            elif self.bar_select_mode == 'item' and i == selected:
                if not active and self.inactive_select_color is not None:
                    select = self.inactive_select_color

                elif self.select_color is not None:
                    select = self.select_color

                else:
                    select = self.font_color

                texture = self.texts.render_text(
                    item,
                    self.font, self.fontsize, align='left')

                setattr(texture.size, 'center', dest.center)

                with texture.with_color_mod(select):
                    texture.draw_in(dest, fit=True)

            else:
                if self.bar_select_mode == 'full':
                    if active and self.select_color is not None:
                        select = self.select_color
                    elif not active and self.inactive_select_color is not None:
                        select = self.inactive_select_color
                    else:
                        select = self.font_color
                else:
                    select = self.font_color

                texture = self.texts.render_text(
                    item,
                    self.font, self.fontsize, align='left')

                setattr(texture.size, 'center', dest.center)

                with texture.with_color_mod(select):
                    texture.draw_in(dest, fit=True)
        #self.renderer.blendmode = mode

    def _verify_outline(self, name, default, optional):
        # print(name, default)
        val = self._dict.get(name, default)
        if val is None and optional: return None

        # print(val)
        if isinstance(val, (list, tuple)) and len(val) == 2:
            color = self._verify_color(None, val[0])
            thickness = self._verify_int(None, val[1])
            if color and thickness:
                return color, thickness

        else:
            raise GUIThemeError(f'fontoutline is not a 2-tuple')

        if not isinstance(val, int):
            raise GUIThemeError(f'{name} is not an int')
        #print(f'{name}: {val}')
        return None

    def _draw_patch(self, area, image):
        '''
        Draw 9-patch image in given area
        '''
        target = area.copy()
        bounds = Rect.from_sdl(image.srcrect)
        texture = image.texture

        self.renderer.copy(texture,  # TOP
                srcrect=(bounds.left, bounds.top, self.patch[0], self.patch[1]),
                dstrect=(target.left, target.top, self.patch[0], self.patch[1]))
        self.renderer.copy(texture,  # LEFT
            srcrect=(bounds.left, bounds.top + self.patch[1], self.patch[0],
                    bounds.height - self.patch[1] - self.patch[3]),
            dstrect=(target.left, target.top + self.patch[1], self.patch[0],
                    target.height - self.patch[1] - self.patch[3]))
        self.renderer.copy(texture,  # BOTTOM-LEFT
            srcrect=(bounds.left, bounds.bottom - self.patch[3],
                    self.patch[0], self.patch[3]),
            dstrect=(target.left, target.bottom - self.patch[3],
                    self.patch[0], self.patch[3]))

        self.renderer.copy(texture, # TOP -RIGHT
            srcrect=(bounds.right - self.patch[2], bounds.top,
                    self.patch[2], self.patch[1]),
            dstrect=(target.right - self.patch[2], target.top,
                    self.patch[2], self.patch[1]))
        self.renderer.copy(texture, # RIGHT
            srcrect=(bounds.right - self.patch[2], bounds.top + self.patch[1],
                    self.patch[2], bounds.height - self.patch[3] - self.patch[1]),
            dstrect=(target.right - self.patch[2], target.top + self.patch[1],
                    self.patch[2], target.height - self.patch[3] - self.patch[1]))
        self.renderer.copy(texture, # BOTTOM-RIGHT
            srcrect=(bounds.right - self.patch[2], bounds.bottom - self.patch[3],
                    self.patch[2], self.patch[3]),
            dstrect=(target.right - self.patch[2], target.bottom - self.patch[3],
                    self.patch[2], self.patch[3]))

        self.renderer.copy(texture, # TOP
            srcrect=(bounds.left + self.patch[0], bounds.top,
                    bounds.width - self.patch[0] - self.patch[2], self.patch[1]),
            dstrect=(target.left + self.patch[0], target.top,
                    target.width - self.patch[0] - self.patch[2], self.patch[1]))
        self.renderer.copy(texture, # CENTER
            srcrect=(bounds.left + self.patch[0], bounds.top + self.patch[1],
                    bounds.width - self.patch[2] - self.patch[0],
                    bounds.height - self.patch[1] - self.patch[3]),
            dstrect=(target.left + self.patch[0], target.top + self.patch[1],
                    target.width - self.patch[2] - self.patch[0],
                    target.height - self.patch[1] - self.patch[3]))
        self.renderer.copy(texture, # BOTTOM
            srcrect=(bounds.left + self.patch[0], bounds.bottom - self.patch[3],
                    bounds.width - self.patch[0] - self.patch[2], self.patch[3]),
            dstrect=(target.left + self.patch[0], target.bottom - self.patch[3],
                    target.width - self.patch[0] - self.patch[2], self.patch[3]))


    def _verify_rect(self, name, default=None, optional=False):
        'Verify that value of self._dict[name] is a usable Rect'

        val = self._dict.get(name, default)
        if val is None and optional: return None

        try:
            if len(val) != 4:
                raise GUIThemeError('Region area incorrect length')

        except TypeError:
            print('Region area not iterable')
            raise

        return self._rects.make_rect(self.parent, self.name, val)

    def _verify_color(self, name, default=None, optional=False):
        'verify that value of self._dict[name] is valid RGB 3-tuple color'
        ## Added support for a colour pallet.

        val = self._dict.get(name, default)
        if val is None and optional: return None

        if isinstance(val, str) and val in self.pallet:
            val = self.pallet.get(val)

        if isinstance(val, str) and val.startswith("#"):
            val = hex_color_decode(val)

        if isinstance(val, str):
            raise GUIThemeError(f'color {val} invalid type')

        try:
            if len(val) == 3:
                val = tuple(val) + (255, )

            elif len(val) != 4:
                raise GUIThemeError('color incorrect length')

        except TypeError:
            # print('color not iterable')
            ## TODO: fix this
            raise

        for i, p in enumerate(val):
            if not isinstance(p, (int)):
                raise GUIThemeError(f'{i}, {p} - invalid color type')

            if p<0 or p>255:
                raise GUIThemeError(f'{i}, {p} - invalid color value')
        #print(f'{name}: {val}')
        return val

    def _verify_int(self, name, default=0, optional=False, minimum=None, maximum=None):
        'verify that value of self._dict[name] is valid int value'

        val = self._dict.get(name, default)
        if val is None and optional:
            return None

        if not isinstance(val, int):
            raise GUIThemeError(f'{name} is not an int')
        #print(f'{name}: {val}')

        if minimum is not None and val < minimum:
            val = minimum

        if maximum is not None and val > maximum:
            val = maximum

        return val

    def _verify_float(self, name, default=0, optional=False, minimum=None, maximum=None):
        'verify that value of self._dict[name] is valid float value'

        val = self._dict.get(name, default)
        if val is None and optional:
            return None

        ## A whole number is a float too: "font-scale": 2 is as good as 2.0.
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise GUIThemeError(f'{name} is not a number')

        val = float(val)

        if minimum is not None and val < minimum:
            val = minimum

        if maximum is not None and val > maximum:
            val = maximum

        return val

    def _verify_file(self, name, default=None, optional=False):
        ''''
        verify that value of self._dict[name] is valid relative path,
        absolute path, or RESOURCES asset
        '''
        val = self._dict.get(name, default)
        if val is None and optional:
            return None

        if not isinstance(val, str):
            raise GUIThemeError(f'{name} is not a string')

        if not self.gui.resources.find(val):
            raise GUIThemeError(f'{name} is not a file')

        #print(f'{name}: {val}')
        return val

    def _verify_bool(self, name, default=None, optional=False):
        'verify that value of self._dict[name] is valid bool value'

        val = self._dict.get(name, default)
        if val is None and optional:
            return None

        if val in (True, False, 0, 1):
            val = True if val else False
            #print(f'{name}: {val}')
            return val
        else:
            raise GUIThemeError(f'{name} is not BOOL')

    def _verify_option(self, name, options, default=None, optional=False, length=None):
        'verify that value of self._dict[name] is in given options list'

        val = self._dict.get(name, default)
        if val is None and optional: return None

        if isinstance(val, (list, tuple)):
            if length is not None and len(val) != length:
                val = default

            for k in val:
                if k not in options:
                    val = default
                    break

        else:
            if val not in options:
                val = default

        return val

    def _verify_text(self, name, default=None, optional=False):
        'verify that value of self._dict[name] is valid str of text'

        val = self._dict.get(name, default)
        if val is None and optional: return None

        if isinstance(val, str):
            return val

        raise GUIThemeError(f'{name} is not text')

    def _verify_list(self, name, default=None, optional=False, allow_null=False):
        'verify that value of self._dict[name] is valid list'

        val = self._dict.get(name, default)
        if val is None and optional: return None

        if not isinstance(val, (list, tuple)):
            raise GUIThemeError(f'{name} is not a list')

        for i, v in enumerate(val):
            if isinstance(v, (list, tuple)):
                self._verify_bar(None, v, Rect(0, 0, 100, 100))

            elif allow_null and v is None:
                continue

            elif not isinstance(v, str):
                raise GUIThemeError(f'{name}[{i}] == {v}, not a string')

        return val

    def _verify_ints(self, name, count, default=None, optional=False):
        'verify that value of self._dict[name] is valid list of ints'

        val = self._dict.get(name, default)
        if val is None and optional: return None

        if not isinstance(val, (list, tuple)):
            raise GUIThemeError(f'{name} is not a list')

        elif len(val) != count:
            raise GUIThemeError(f'{name} must have {count} int values')

        for i, v in enumerate(val):
            if not isinstance(v, int):
                raise GUIThemeError(f'{name}[{i}] == {v}, not an int')

        return val
