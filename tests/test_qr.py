# SPDX-License-Identifier: MIT
#
# QR codes as theme images: "image": "qr:{some.text}" (pugwash/sdl/images.py).

import ctypes

import pytest


def test_qr_matrix():
    from pugwash.sdl.images import qr_matrix

    matrix = qr_matrix("http://192.168.0.2:8090/")
    ## A square of modules, with the 4 module quiet zone all round.
    assert len(matrix) == len(matrix[0]) >= 21 + 8
    assert not any(matrix[0]) and not any(row[0] for row in matrix)
    ## The top left finder pattern starts after the quiet zone.
    assert all(matrix[4][4:11])

    assert qr_matrix("") is None


def read_texture(gui, image, size):
    """Draws image size x size into a target texture and reads it back, RGBA rows."""
    import sdl2

    renderer = gui.renderer.sdlrenderer
    target = sdl2.SDL_CreateTexture(renderer, sdl2.SDL_PIXELFORMAT_RGBA32, sdl2.SDL_TEXTUREACCESS_TARGET, size, size)
    sdl2.SDL_SetRenderTarget(renderer, target)
    try:
        image.draw_in((0, 0, size, size))
        pixels = (ctypes.c_uint8 * (size * size * 4))()
        sdl2.SDL_RenderReadPixels(renderer, None, sdl2.SDL_PIXELFORMAT_RGBA32, pixels, size * 4)

    finally:
        sdl2.SDL_SetRenderTarget(renderer, None)
        sdl2.SDL_DestroyTexture(target)

    return bytes(pixels)


@pytest.mark.sdl
def test_qr_image(gui):
    from pugwash.sdl.images import qr_matrix

    text = "qr:http://192.168.0.2:8090/"
    image = gui.images.load(text)
    matrix = qr_matrix(text[3:])
    modules = len(matrix)
    assert (image.srcrect.w, image.srcrect.h) == (modules, modules)
    assert gui.images.load(text) is image

    ## Scaled up without smoothing: every pixel is pure black or white, matching its module.
    scale = 5
    pixels = read_texture(gui, image, modules * scale)
    stride = modules * scale * 4
    for y in range(modules * scale):
        for x in range(modules * scale):
            red, alpha = pixels[y * stride + x * 4], pixels[y * stride + x * 4 + 3]
            assert alpha == 255 and red == (0 if matrix[y // scale][x // scale] else 255), (x, y)


@pytest.mark.sdl
def test_qr_image_without_text(gui):
    assert gui.images.load("qr:") is None
