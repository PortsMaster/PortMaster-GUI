# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Textures and images, including background loading of port screenshots.

import contextlib
import ctypes
import os
import sdl2
import sdl2.ext
import sdl2.sdlmixer
from loguru import logger
from .errors import GUIRuntimeError, GUIValueError
from .geometry import Rect
from .helpers import set_color_mod


QR_PREFIX = "qr:"


def qr_matrix(text):
    '''
    The QR code of text as rows of booleans (True is dark), with its quiet zone. None
    for no text.
    '''
    if not text:
        return None

    import qrcode

    code = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_M)
    code.add_data(text)
    code.make(fit=True)
    return code.get_matrix()


def qr_surface(text):
    'The QR code of text as an SDL surface, one pixel per module (free it after use).'
    matrix = qr_matrix(text)
    if matrix is None:
        return None

    size = len(matrix)
    dark, light = b"\x00\x00\x00\xff", b"\xff\xff\xff\xff"
    pixels = b"".join(dark if module else light for row in matrix for module in row)

    surf = sdl2.SDL_CreateRGBSurfaceWithFormat(0, size, size, 32, sdl2.SDL_PIXELFORMAT_RGBA32)
    if not surf:
        raise GUIRuntimeError(sdl2.SDL_GetError().decode("utf-8", "replace"))

    sdl2.SDL_LockSurface(surf)
    try:
        for y in range(size):
            ctypes.memmove(surf.contents.pixels + y * surf.contents.pitch, pixels[y * size * 4:(y + 1) * size * 4], size * 4)

    finally:
        sdl2.SDL_UnlockSurface(surf)

    return surf


class Texture:
    '''
    The Texture class is a base texture class used within pySDL2gui.

    The texture can be a subtexture by using srcrect.
    '''
    def __init__(self, gui, texture, size=None, parent=None, srcrect=None, color_mod=None):
        self.gui = gui
        self.renderer = gui.renderer
        self.parent = parent
        self.texture = texture
        self.children = []
        self.__in_delete = False

        if isinstance(size, Rect):
            self.size = size
        elif isinstance(size, (list, tuple)) and len(size) == 4:
            self.size = Rect(*size)
        elif isinstance(size, (sdl2.SDL_Rect)):
            self.size = Rect.from_sdl(size)
        elif size is None:
            self.size = Rect(0, 0, *texture.size)
        else:
            raise GUIValueError('srcrect not a supported type')

        if parent is not None:
            parent.children.append(self)

        if color_mod is None:
            color_mod = (255, 255, 255)
        else:
            color_mod = color_mod[:3]

        self.color_mod = color_mod

        # else:
        #     self.gui.textures.append(self)

        if isinstance(srcrect, Rect):
            self.srcrect = srcrect.sdl()
        elif isinstance(srcrect, (list, tuple)) and len(srcrect) == 4:
            self.srcrect = sdl2.SDL_Rect(*srcrect)
        elif isinstance(srcrect, (sdl2.SDL_Rect)):
            self.srcrect = srcrect
        elif srcrect is None:
            self.srcrect = sdl2.SDL_Rect(0, 0, *texture.size)
        else:
            raise GUIValueError('srcrect not a supported type')

    def __del__(self):
        if self.__in_delete:
            return

        self.__in_delete = True

        if self.parent is not None:
            if self in self.parent.children:
                self.parent.children.remove(self)

        # else:
        #     if self in self.gui.textures:
        #         self.gui.textures.remove(self)

        children = self.children
        self.children = []
        for child in self.children:
            del child

        self.texture.destroy()

    @contextlib.contextmanager
    def with_color_mod(self, color):
        old_color = self.color_mod
        try:

            self.color_mod = color[:3]
            yield

        finally:
            self.color_mod = old_color

    def set_color_mod(self, color):
        self.color_mod = color[:3]

    def get_color_mod(self):
        return self.color_mod[:]

    def draw(self):
        sdl2.SDL_SetTextureColorMod(self.texture.tx, *self.color_mod)
        self.renderer.copy(self.texture, self.srcrect, dstrect=self.size.sdl())

    def draw_at(self, x, y):
        '''
        Draw image with topleft corner at x, y and at the original size.

        x: x position to draw at
        y: y position to draw at
        '''

        sdl2.SDL_SetTextureColorMod(self.texture.tx, *self.color_mod)
        self.renderer.copy(self.texture, self.srcrect, dstrect=(x, y))

    def draw_in(self, dest, fit=False, clip=False):
        '''
        Draw image inside given Rect region (may squish or stretch image)

        dest: Rect area to draw the image into
        fit: set true to fit the image into dest without changing its aspect
             ratio
        clip: set true to clip the image into the dest.
        '''

        sdl2.SDL_SetTextureColorMod(self.texture.tx, *self.color_mod)

        if fit:
            dest = self.size.fitted(dest)
            self.renderer.copy(self.texture, self.srcrect, dstrect=dest.sdl())

            return Rect(*dest)

        elif clip:
            destrect = Rect(*dest)

            # Calculate the scaling factors for width and height
            width_scale = self.size.width / self.srcrect.w
            height_scale = self.size.height / self.srcrect.h

            # Calculate the clipped size
            clipped_width = min(self.size.width, destrect.width)
            clipped_height = min(self.size.height, destrect.height)

            # Calculate the source rectangle within the texture
            srcrect_x = self.srcrect.x + (destrect.x - self.size.x) / width_scale
            srcrect_y = self.srcrect.y + (destrect.y - self.size.y) / height_scale
            srcrect_x = self.srcrect.x + max(0, (destrect.x - self.size.x)) / width_scale
            srcrect_y = self.srcrect.y + max(0, (destrect.y - self.size.y)) / height_scale

            srcrect_width = clipped_width / width_scale
            srcrect_height = clipped_height / height_scale

            # Calculate the destination rectangle
            # destrect_x = destrect.x
            # destrect_y = destrect.y
            destrect_x = destrect.x + max(0, (self.size.x - destrect.x))
            destrect_y = destrect.y + max(0, (self.size.y - destrect.y))

            destrect_width = clipped_width
            destrect_height = clipped_height

            self.renderer.copy(self.texture, (srcrect_x, srcrect_y, srcrect_width, srcrect_height),
                               dstrect=(destrect_x, destrect_y, destrect_width, destrect_height))

            return Rect(destrect_x, destrect_y, destrect_width, destrect_height)

        else:
            self.renderer.copy(self.texture, self.srcrect, dstrect=dest.sdl())

            return Rect(*dest)


class Image:
    renderer = None
    '''
    The Image class represents an image with its position, angle,
    and flipped(x/y) status. An image references a Texture and
    has a srcrect(Rect) to define which part of the Texture to
    draw
    '''

    def __init__(self, texture, srcrect=None, renderer=None, color_mod=None):
        '''
        Create a new Image from a texture and a source Rect.

        :param texture: a sdl2.ext.Texture object to draw the image from
        :param srcrect: a gui.Rect object defining which part of the
            texture to draw
        :param renderer: a sdl2.ext.Renderer context to draw into
        '''

        renderer = renderer or Image.renderer
        if renderer is None:
            raise GUIRuntimeError('No renderer context provided')

        if Image.renderer is None:
            Image.renderer = renderer  # set default

        self.texture = texture
        if isinstance(srcrect, Rect):
            self.srcrect = srcrect.sdl()
        elif isinstance(srcrect, (list, tuple)) and len(srcrect) == 4:
            self.srcrect = sdl2.SDL_Rect(*srcrect)
        elif isinstance(srcrect, (sdl2.SDL_Rect)):
            self.srcrect = srcrect
        elif srcrect is None:
            self.srcrect = sdl2.SDL_Rect(0, 0, *texture.size)
        else:
            raise GUIValueError('srcrect not a supported type')

        if color_mod is None:
            color_mod = (255, 255, 255)
        else:
            color_mod = color_mod[:3]

        self.color_mod = color_mod

        self.x = self.y = 0
        self.flip_x = self.flip_y = 0
        self.angle = 0
        self.center = None

        # default dest rect is fitted to full screen
        self.dstrect = Rect.from_sdl(self.srcrect).fitted(
            Rect(0, 0, *self.renderer.logical_size)).sdl()

    def set_color_mod(self, color):
        self.color_mod = color[:3]

    def get_color_mod(self):
        return self.color_mod[:]

    def draw_at(self, x, y, angle=0, flip_x=None, flip_y=None, center=None):
        '''
        Draw image with topleft corner at x, y and at the original size.

        x: x position to draw at
        y: y position to draw at
        angle: optional angle to rotate image
        flip_x: optional flag to flip image horizontally
        flip_y: optional flag to flip image vertically
        center: optional point to rotate the image around if angle provided
        '''
        center = center or self.center
        angle = angle or self.angle

        if flip_x is None and flip_y is None:
            flip = 1 * bool(self.flip_x) | 2 * bool(self.flip_y)
        else:
            flip = 1 * bool(flip_x) | 2 * bool(flip_y)

        sdl2.SDL_SetTextureColorMod(self.texture.tx, *self.color_mod)
        self.renderer.copy(
            self.texture,
            self.srcrect,
            dstrect=(x, y),
            angle=angle,
            flip=flip,
            center=center,
            )

    def draw_fit(self, source, dest, orientation='vertical', align='center'):
        if orientation is None:
            orientation = 'vertical'

        if align is None:
            align = 'center'

        new_coords = Rect(0, 0, 0, 0)
        if 'horizontal' in orientation:
            new_coords.width = dest.width
            new_coords.height = int(dest.height * (source.height / source.width))

        else:
            new_coords.width = int(dest.width * (source.width / source.height))
            new_coords.height = dest.height

        w = getattr(dest, align)
        setattr(new_coords, align, w)

        # print(f"{list(new_coords)} {w}")

        self.draw_in(new_coords, fit=True)

    def draw_in(self, dest, angle=0, flip_x=None, flip_y=None,
                center=None, fit=False, color=None):
        '''
        Draw image inside given Rect region (may squish or stretch image)

        dest: Rect area to draw the image into
        angle: optional angle to rotate image
        flip_x: optional flag to flip image horizontally
        flip_y: optional flag to flip image vertically
        center: optional point to rotate the image around if angle provided
        fit: set true to fit the image into dest without changing its aspect
             ratio
        '''
        center = center or self.center
        angle = angle or self.angle

        if fit:
            dest = Rect.from_sdl(self.srcrect).fitted(dest).sdl()

        if flip_x is None and flip_y is None:
            flip = 1 * bool(self.flip_x) | 2 * bool(self.flip_y)
        else:
            flip = 1 * bool(flip_x) | 2 * bool(flip_y)

        set_color_mod(self.texture, (255, 255, 255))
        sdl2.SDL_SetTextureColorMod(self.texture.tx, *self.color_mod)
        self.renderer.copy(self.texture, self.srcrect,
            dstrect=dest, angle=angle, flip=flip, center=center)

    def draw(self):
        ''''Draw image to its current destrect(Rect region), which defaults to
        full screen maintaining aspect ratio'''
        flip = 1 * bool(self.flip_x) | 2 * bool(self.flip_y)
        sdl2.SDL_SetTextureColorMod(self.texture.tx, *self.color_mod)
        self.renderer.copy(self.texture, self.srcrect,
            dstrect=self.dstrect, angle=self.angle,
            flip=flip, center=self.center)


class PendingImage(Image):
    '''
    Stands in for an image that is still being decoded on another thread.

    It draws nothing and reports a 1x1 srcrect until resolve() gives it a texture,
    so layout code that reads srcrect keeps working.
    '''

    def __init__(self, renderer=None):
        renderer = renderer or Image.renderer
        if renderer is None:
            raise GUIRuntimeError('No renderer context provided')

        self.renderer = renderer
        self.texture = None
        self.srcrect = sdl2.SDL_Rect(0, 0, 1, 1)
        self.dstrect = sdl2.SDL_Rect(0, 0, 1, 1)
        self.color_mod = (255, 255, 255)
        self.x = self.y = 0
        self.flip_x = self.flip_y = 0
        self.angle = 0
        self.center = None

    @property
    def loaded(self):
        return self.texture is not None

    def resolve(self, texture):
        self.texture = texture
        self.srcrect = sdl2.SDL_Rect(0, 0, *texture.size)
        self.dstrect = Rect.from_sdl(self.srcrect).fitted(
            Rect(0, 0, *self.renderer.logical_size)).sdl()

    def draw_at(self, *args, **kwargs):
        if self.texture is not None:
            super().draw_at(*args, **kwargs)

    def draw_in(self, *args, **kwargs):
        if self.texture is not None:
            super().draw_in(*args, **kwargs)

    def draw(self):
        if self.texture is not None:
            super().draw()


class ImageManager():
    '''
    The ImageManager class loads images into Textures and caches them for later use
    '''

    MAX_IMAGES = 30 # maximum number of images to cache

    def __init__(self, gui, max_images=None):
        '''
        Create a new Image manager that can load images into textures

        gui.renderer: sdl2.ext.Renderer context that the image will draw
            into. A renderer must be provided to create new Texture
            objects.
        max: maximum number of images to cach before old ones are
            unloaded. Defaults to ImageManager.MAX_IMAGES(20)
        '''
        if max_images is None:
            self.max_images = self.MAX_IMAGES
        else:
            self.max_images = max_images

        self.gui = gui
        self.renderer = gui.renderer
        self.images = {}
        self.textures = {}
        self.cache = []
        self.async_dispatcher = None
        self.async_executor = None

    def enable_async(self, dispatcher, max_workers=2):
        '''
        Decode images given by absolute path (eg: port screenshots) on worker threads.

        dispatcher: something with post(fn, *args) that runs fn on the main thread,
            textures are only ever created there.
        '''
        from concurrent.futures import ThreadPoolExecutor

        self.async_dispatcher = dispatcher
        self.async_executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="image-load")

    def disable_async(self):
        if self.async_executor is not None:
            self.async_executor.shutdown(wait=False)
            self.async_executor = None

    def keep(self, count):
        '''
        Make room in the cache for count images that are in use at once (eg: a grid's tiles
        plus the rows it loads ahead), so they aren't unloaded while still on screen.
        Only ever raises max_images.
        '''
        self.max_images = max(self.max_images, count + self.MAX_IMAGES // 2)

    def _decode(self, filename, res_filename, image):
        # Worker thread: only CPU side work here.
        try:
            surf = sdl2.ext.image.load_img(str(res_filename))

        except Exception as err:
            logger.error(f"Unable to load image {res_filename}: {err}")
            return

        self.async_dispatcher.post(self._decoded, filename, image, surf)

    def _decoded(self, filename, image, surf):
        # Main thread: turn the decoded surface into a texture.
        try:
            if self.images.get(filename) is not image:
                # Unloaded before it finished.
                return

            texture = sdl2.ext.renderer.Texture(self.renderer, surf)
            self.textures[filename] = texture
            image.resolve(texture)
            self.gui.updated = True

        finally:
            sdl2.SDL_FreeSurface(surf)

    def load(self, filename):
        '''
        Load an image file into a Texture or receive a previously cached
        Texture with that name.

        :param filename: filename(str) to load
        :rvalue gui.Image: reference to the image just loaded or from cache
        '''
        if filename in self.cache:
            i = self.cache.index(filename)
            self.cache.insert(0, self.cache.pop(i))
            return self.images[filename]

        elif filename in self.images:
            return self.images[filename]

        elif isinstance(filename, str) and filename.startswith(QR_PREFIX):
            image = self._load_qr(filename)
            if image is not None:
                self.images[filename] = image
                self.cache.insert(0, filename)

            return image

        else:
            res_filename = self.gui.resources.find(filename)

            if res_filename is None:
                return None

            if self.async_executor is not None and os.path.isabs(str(filename)):
                image = PendingImage(renderer=self.renderer)
                self.images[filename] = image
                self.cache.insert(0, filename)
                self.async_executor.submit(self._decode, filename, res_filename, image)
                return image

            surf = sdl2.ext.image.load_img(res_filename)

            texture = sdl2.ext.renderer.Texture(self.renderer, surf)

            sdl2.SDL_FreeSurface(surf)

            self.textures[filename] = texture
            self.images[filename] = Image(texture, renderer=self.renderer)
            self.cache.insert(0, filename)

            return self.images[filename]

    def _load_qr(self, filename):
        '''
        "qr:<text>": a QR code of the text, black on white with a quiet zone, one pixel
        per module and drawn without smoothing, so it stays sharp at any size.
        '''
        try:
            surf = qr_surface(filename[len(QR_PREFIX):])

        except Exception as err:
            logger.error(f"Unable to make a QR code of {filename!r}: {err}")
            return None

        if surf is None:
            return None

        ## No smoothing: per texture from SDL 2.0.12, before that the scale quality hint
        ## is read when a texture is made.
        quality = sdl2.SDL_GetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY)
        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"0")
        try:
            texture = sdl2.ext.renderer.Texture(self.renderer, surf)
            texture.set_scale_mode("nearest")

        finally:
            sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, quality or b"")
            sdl2.SDL_FreeSurface(surf)

        self.textures[filename] = texture
        return Image(texture, renderer=self.renderer)

    def load_data_lazy(self, file_name, data):
        res_filename = self.gui.resources.find(file_name)

        if res_filename is None:
            return None

        stored_name = data.get("name", file_name)
        if stored_name in self.images:
            return None

        return self.load_data(file_name, data)

    def load_data(self, file_name, data):
        res_filename = self.gui.resources.find(file_name)

        if res_filename is None:
            return None

        if file_name.lower().endswith('.svg') and "size" in data:
            image_size = data["size"]

            if len(image_size) != 2:
                return None

            if not isinstance(image_size[0], int) or not isinstance(image_size[1], int):
                return None

            surf = sdl2.ext.image.load_svg(res_filename, width=image_size[0], height=image_size[1])
        else:
            surf = sdl2.ext.image.load_img(res_filename)

        texture = sdl2.ext.renderer.Texture(self.renderer, surf)
        sdl2.SDL_FreeSurface(surf)

        stored_name = data.get("name", file_name)
        image_mod = data.get("image-mod", None)

        if "atlas" in data:
            images = {}

            for name, item in data["atlas"].items():
                r = item[:4]
                flip_x, flip_y, angle, *_ = list(item[4:] + [0, 0, 0])

                im = Image(texture, r, renderer=self.renderer, color_mod=image_mod)
                im.flip_x = flip_x
                im.flip_y = flip_y
                im.angle = angle

                self.images[name] = im
                images[name] = im

            return images

        else:
            image = Image(texture, renderer=self.renderer, color_mod=image_mod)

            self.images[stored_name] = image

            return image

    def load_atlas(self, filename, atlas):
        '''
        **** DEPRECATED ****

        Load image filename, create Images from an atlas dict, and create
        a named shortcut for each image in the atlas.

        This does not use the cache.

        :param filename: (str) filename of image to load into a texture
        :param atlas: a dict representing each image in the file
        :rvalue {}: dict of gui.Images in {name: Image} format

        example atlas:
        atlas = {
            'str_name': (x, y, width, height),
            'another_img: (32, 0, 32, 32)
        }
        '''
        images = {}

        res_filename = self.gui.resources.find(filename)

        if res_filename is None:
            return None

        surf = sdl2.ext.image.load_img(res_filename)

        texture = sdl2.ext.renderer.Texture(self.renderer, surf)

        sdl2.SDL_FreeSurface(surf)

        for name, item in atlas.items():
            r = item[:4]
            flip_x, flip_y, angle, *_ = list(item[4:] + [0, 0, 0])

            im = Image(texture, r, renderer=self.renderer)
            im.flip_x = flip_x
            im.flip_y = flip_y
            im.angle = angle

            # Cant happen if using a dict ?
            # if name in images:
            #     raise Exception('Image names must be unique')

            self.images[name] = im
            images[name] = im

        return images

    def load_static(self, filename, data=None):
        '''
        **** DEPRECATED ****

        Load image with filename.

        This does not get removed from the cache.

        :param filename: (str) filename of image to load into a texture
        :rvalue gui.Image: image loaded from filename

        '''
        res_filename = self.gui.resources.find(filename)

        if res_filename is None:
            return None

        if filename.lower().endswith('.svg') and data is not None:
            if len(data) != 2:
                return None

            if not isinstance(data[0], int) or not isinstance(data[1], int):
                return None

            surf = sdl2.ext.image.load_svg(res_filename, width=data[0], height=data[1])

        else:
            surf = sdl2.ext.image.load_img(res_filename)

        texture = sdl2.ext.renderer.Texture(self.renderer, surf)

        sdl2.SDL_FreeSurface(surf)

        image = Image(texture, renderer=self.renderer)

        self.images[filename] = image

        return image

    def _clean(self):
        'Remove old images when max_images is reached'
        for filename in self.cache[self.max_images:]:
            logger.debug(f"Unloaded: {filename}")
            # Still decoding images have no texture yet.
            texture = self.textures.pop(filename, None)
            image = self.images.pop(filename)
            # image.destroy()
            if texture is not None:
                texture.destroy()
        self.cache = self.cache[:self.max_images]
