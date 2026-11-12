#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
#
# Makes the pictures in THEME.md (docs/theme/) from real renders of the default theme:
#
#     .venv/bin/pip install pillow          # once: only this tool needs it
#     .venv/bin/python tools/theme_docs.py  # renders with the theme server, then draws docs/theme/
#
# --renders DIR reuses an earlier run's renders (they take a few minutes). The screenshots show the
# theme server's fixed clock and disk, and its cached ports list, so a run changes a picture only
# when the theme (or PortMaster) changed what it shows.

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
PM_DIR = ROOT / "PortMaster"
DEFAULT_THEME = PM_DIR / "pylibs" / "default_theme"
OUT = ROOT / "docs" / "theme"
FONT = str(PM_DIR / "pylibs" / "resources" / "DejaVuSans.ttf")
FONT_BOLD = str(DEFAULT_THEME / "Roboto-Medium.ttf")

SCHEMES = ("Dark Mode", "Light Mode", "OLED Mode")
## The screens a theme draws (the selection lists and the warnings are always PortMaster's own).
SCREENS = ("main_menu", "ports_all", "port_info", "port_info_popup", "port_links", "filters", "featured",
           "featured_list", "options", "runtimes", "themes", "theme_schemes", "language", "theme_editor",
           "messages", "message_box")

## Region boxes: one colour each, readable on the dark and the light schemes.
BOX_COLOURS = [(255, 99, 71), (64, 196, 255), (124, 252, 0), (255, 215, 0), (238, 130, 238),
               (0, 255, 200), (255, 160, 60), (180, 160, 255), (255, 105, 180), (150, 230, 120)]


def font(size, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def render(renders, python):
    """Exports the default theme (and a copy whose default layout is Grid) with the theme server."""
    themes = Path(tempfile.mkdtemp(prefix="theme-docs-"))
    try:
        grid = themes / "default_grid"
        shutil.copytree(str(DEFAULT_THEME), str(grid))
        data = json.loads((grid / "theme.json").read_text(encoding="utf-8"))
        data["#info"]["default-layout"] = "Grid"
        (grid / "theme.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        serve = [python, str(ROOT / "tools" / "theme_server" / "serve.py"), "--themes", str(themes), "--export", str(renders)]
        subprocess.run(serve + ["--theme", "default_theme", "--theme", "default_grid", "--resolutions", "640x480",
                                "--schemes", "all", "--langs", "en_US,ja_JP,de_DE"], check=True)
        subprocess.run(serve + ["--theme", "default_theme", "--resolutions", "480x320,1280x720,720x720",
                                "--langs", "en_US"], check=True)
    finally:
        shutil.rmtree(str(themes), ignore_errors=True)


class Renders:
    def __init__(self, folder):
        self.folder = Path(folder)

    def path(self, screen, theme="default_theme", size="640x480", scheme="Dark Mode", lang="en_US"):
        return self.folder / theme / size / scheme / lang / f"{screen}.png"

    def image(self, screen, **where):
        return Image.open(str(self.path(screen, **where))).convert("RGB")

    def regions(self, screen, **where):
        return json.loads(self.path(screen, **where).with_suffix(".json").read_text(encoding="utf-8"))["regions"]


def caption(image, text, size=18, pad=10, fill=(30, 30, 30), colour=(235, 235, 235)):
    """The image with a caption bar under it."""
    bar = size + pad * 2
    out = Image.new("RGB", (image.width, image.height + bar), fill)
    out.paste(image, (0, 0))
    draw = ImageDraw.Draw(out)
    draw.text((image.width // 2, image.height + bar // 2), text, font=font(size, bold=True), fill=colour, anchor="mm")
    return out


def grid(images, columns, gap=12, background=(18, 18, 18)):
    """Images in rows of columns, scaled to the first one's height per row."""
    rows = [images[i:i + columns] for i in range(0, len(images), columns)]
    cell_w = max(im.width for im in images)
    cell_h = max(im.height for im in images)
    out = Image.new("RGB", (columns * cell_w + (columns + 1) * gap, len(rows) * cell_h + (len(rows) + 1) * gap), background)
    for r, row in enumerate(rows):
        for c, im in enumerate(row):
            out.paste(im, (gap + c * (cell_w + gap) + (cell_w - im.width) // 2, gap + r * (cell_h + gap)))
    return out


def scaled(image, height):
    return image.resize((round(image.width * height / image.height), height), Image.LANCZOS)


def save(image, name):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(str(path), optimize=True)
    print(f"{path.relative_to(ROOT)}  {image.width}x{image.height}  {path.stat().st_size // 1024} KB")


def boxes(image, regions, only=None, scale=2, legend_width=330):
    """The screen at scale times its size with each region's area outlined and numbered, and a
    legend of the numbers beside it (names on the boxes would hide what they point at)."""
    image = image.resize((image.width * scale, image.height * scale), Image.LANCZOS).convert("RGBA")
    shown = [r for r in regions if (only is None or r["name"] in only) and r["rect"][2] > 0 and r["rect"][3] > 0]
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    badge_font = font(13, bold=True)
    for number, region in enumerate(shown, 1):
        x, y, w, h = [v * scale for v in region["rect"]]
        colour = BOX_COLOURS[(number - 1) % len(BOX_COLOURS)]
        draw.rectangle([x, y, x + w - 1, y + h - 1], outline=colour + (255,), width=2)
        draw.ellipse([x + 2, y + 2, x + 24, y + 24], fill=colour + (255,))
        draw.text((x + 13, y + 13), str(number), font=badge_font, fill=(0, 0, 0, 255), anchor="mm")
    screen = Image.alpha_composite(image, overlay).convert("RGB")

    rows = len(shown)
    line = min(30, max(18, (screen.height - 20) // max(rows, 1)))
    out = Image.new("RGB", (screen.width + legend_width, screen.height), (18, 18, 18))
    out.paste(screen, (0, 0))
    draw = ImageDraw.Draw(out)
    name_font = font(min(17, line - 6))
    for number, region in enumerate(shown, 1):
        colour = BOX_COLOURS[(number - 1) % len(BOX_COLOURS)]
        y = 10 + (number - 1) * line
        draw.ellipse([screen.width + 14, y, screen.width + 14 + line - 8, y + line - 8], fill=colour)
        draw.text((screen.width + 14 + (line - 8) // 2, y + (line - 8) // 2), str(number), font=font(max(10, line // 2 - 1), True), fill=(0, 0, 0), anchor="mm")
        draw.text((screen.width + 22 + line, y + (line - 8) // 2), region["name"], font=name_font, fill=(230, 230, 230), anchor="lm")
    return out


## ---------------------------------------------------------------- the pictures
def hero(r):
    images = []
    for scheme in SCHEMES:
        for theme, label in (("default_theme", "List"), ("default_grid", "Grid")):
            images.append(caption(r.image("ports_all", theme=theme, scheme=scheme), f"{scheme} · {label}"))
    save(grid(images, 3), "hero.png")


def screens(r):
    for screen in SCREENS:
        if r.path(screen).exists():     ## (a section the default theme leaves out: port_info_popup)
            save(r.image(screen), f"screens/{screen}.png")


def region_maps(r):
    for screen in ("main_menu", "ports_all", "port_info", "options", "messages"):
        save(boxes(r.image(screen), r.regions(screen)), f"regions/{screen}.png")


def schemes(r):
    save(grid([caption(r.image("main_menu", scheme=s), s) for s in SCHEMES], 3), "schemes.png")


def layouts(r):
    save(grid([caption(r.image("ports_all"), "List  (layout_list)"),
               caption(r.image("ports_all", theme="default_grid"), "Grid  (layout_grid)")], 2), "layouts.png")


def languages(r):
    save(grid([caption(r.image("ports_all", lang=lang), lang) for lang in ("en_US", "de_DE", "ja_JP")], 3), "languages.png")


def screen_sizes(r):
    images = [caption(scaled(r.image("main_menu", size=size), 360), size) for size in ("480x320", "640x480", "720x720", "1280x720")]
    save(grid(images, 4), "screen-sizes.png")


def pointer(r):
    ## The selected row of the options list, at 1280x720: the pill's caps are the pointer.
    image = r.image("options", size="1280x720")
    region = next(reg for reg in r.regions("options", size="1280x720") if reg["name"] == "option_list")
    pointers = [d for d in region["drawn"] if d[0] == "pointer"]
    x0 = min(d[1] for d in pointers) - 12
    x1 = max(d[1] + d[3] for d in pointers) + 12
    y0 = min(d[2] for d in pointers) - 40
    y1 = max(d[2] + d[4] for d in pointers) + 40
    crop = image.crop((x0, y0, x1, y1))
    crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)
    draw = ImageDraw.Draw(crop)
    for d in pointers:
        px, py, pw, ph = [(v - o) * 2 for v, o in zip(d[1:5], (x0, y0, 0, 0))]
        draw.rectangle([px, py, px + d[3] * 2 - 1, py + d[4] * 2 - 1], outline=(64, 196, 255), width=3)
    save(crop, "pointer-fit.png")


def nine_patch():
    ## The card image, its fixed corners marked, and the same image stretched as a 9-patch.
    card = Image.open(str(DEFAULT_THEME / "card_dark.png")).convert("RGBA")
    patch = 14
    zoom = 6
    big = card.resize((card.width * zoom, card.height * zoom), Image.NEAREST)
    canvas = Image.new("RGB", (big.width + 60 + 520, max(big.height + 70, 50 + 140 + 200 + 20)), (18, 18, 18))
    canvas.paste(big, (20, 50), big)
    draw = ImageDraw.Draw(canvas)
    for edge in (patch, card.width - patch):
        draw.line([(20 + edge * zoom, 50), (20 + edge * zoom, 50 + big.height)], fill=(255, 99, 71), width=2)
    for edge in (patch, card.height - patch):
        draw.line([(20, 50 + edge * zoom), (20 + big.width, 50 + edge * zoom)], fill=(255, 99, 71), width=2)
    draw.text((20, 14), f"card_dark.png ×{zoom},  \"patch\": [ {patch}, {patch}, {patch}, {patch} ]", font=font(16, True), fill=(235, 235, 235))

    def stretched(width, height):
        out = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        cw, ch = card.size
        xs = [(0, patch, 0, patch), (patch, cw - patch, patch, width - patch), (cw - patch, cw, width - patch, width)]
        ys = [(0, patch, 0, patch), (patch, ch - patch, patch, height - patch), (ch - patch, ch, height - patch, height)]
        for sx0, sx1, dx0, dx1 in xs:
            for sy0, sy1, dy0, dy1 in ys:
                piece = card.crop((sx0, sy0, sx1, sy1)).resize((max(1, dx1 - dx0), max(1, dy1 - dy0)), Image.NEAREST)
                out.paste(piece, (dx0, dy0))
        return out

    x = big.width + 60
    wide = stretched(480, 120)
    tall = stretched(200, 200)
    canvas.paste(wide, (x, 50), wide)
    canvas.paste(tall, (x, 50 + 140), tall)
    draw.text((x, 14), "drawn as any size: the corners stay sharp", font=font(16, True), fill=(235, 235, 235))
    save(canvas, "nine-patch.png")


def areas():
    """Three regions inside a pane, with the area that places each."""
    W, H = 900, 520
    canvas = Image.new("RGB", (W, H), (24, 26, 30))
    draw = ImageDraw.Draw(canvas)
    screen = (20, 20, W - 20, H - 20)
    draw.rectangle(screen, outline=(120, 120, 120), width=2)
    draw.text((30, 28), "root: the whole screen", font=font(15, True), fill=(160, 160, 160))
    pw = screen[2] - screen[0]
    ph = screen[3] - screen[1]

    def rect(parent, area):
        px, py, px2, py2 = parent
        out = []
        for i, v in enumerate(area):
            lo, size, hi = (px, px2 - px, px2) if i % 2 == 0 else (py, py2 - py, py2)
            if isinstance(v, float) and 0 <= v <= 1:
                out.append(lo + int(v * size))
            elif v < 0:
                out.append(hi + v)
            else:
                out.append(lo + v)
        return out

    pane_area = [0.45, 0.12, 0.97, 0.95]
    pane = rect(screen, pane_area)
    draw.rectangle(pane, outline=(64, 196, 255), width=3)
    draw.text((pane[0] + 8, pane[1] - 22), f'"right_pane":  "area": {json.dumps(pane_area)}', font=font(14, True), fill=(64, 196, 255))
    examples = [
        ("title", [0.0, 0.0, 1.0, 0.2], (255, 215, 0), "fractions of right_pane"),
        ("image", [10, 0.2, -10, 0.7], (124, 252, 0), "10 px in from each side, 20%-70% down"),
        ("text", [10, 0.7, -10, -10], (255, 99, 71), "to 10 px above the bottom"),
        ]
    for name, area, colour, note in examples:
        box = rect(pane, area)
        draw.rectangle(box, outline=colour, width=3)
        draw.text((box[0] + 8, box[1] + 6), f'"{name}"  {json.dumps(area)}', font=font(13, True), fill=colour)
        draw.text((box[0] + 8, box[1] + 26), note, font=font(12), fill=(200, 200, 200))
    left = rect(screen, [0.03, 0.12, 0.42, 0.95])
    draw.rectangle(left, outline=(238, 130, 238), width=3)
    draw.text((left[0] + 8, left[1] + 6), '"left_pane"', font=font(14, True), fill=(238, 130, 238))
    draw.text((left[0] + 8, left[1] + 28), '"area": [ 0.03, 0.12, 0.42, 0.95 ]', font=font(12), fill=(200, 200, 200))
    draw.text((left[0] + 8, left[1] + 70), "children name it as", font=font(12), fill=(200, 200, 200))
    draw.text((left[0] + 8, left[1] + 88), '"parent": "left_pane"', font=font(12, True), fill=(238, 130, 238))
    save(canvas, "areas.png")


def editor_shots(python, port=8097):
    """The theme server's page: the gallery, one screen with its region boxes, the editor."""
    chrome = sorted(Path.home().glob(".cache/ms-playwright/chromium_headless_shell-*/*/chrome-headless-shell"))
    if not chrome:
        print("no headless Chromium (playwright's): skipping the theme server pictures")
        return
    server = subprocess.Popen([python, str(ROOT / "tools" / "theme_server" / "serve.py"), "--port", str(port)],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import time
        import urllib.request
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1)
                break
            except OSError:
                time.sleep(0.2)
        for name, query in (("server-gallery", "#view=preview&mode=screens&res=640x480"),
                            ("server-sizes", "#view=preview&mode=resolutions&modeShot=ports_all"),
                            ("server-edit", "#view=edit&res=640x480"),
                            ("server-translate", "#view=translate&lang=de_DE&res=640x480")):
            target = OUT / f"{name}.png"
            subprocess.run([str(chrome[-1]), "--headless", "--no-sandbox", "--hide-scrollbars", "--window-size=1440,900",
                            "--virtual-time-budget=25000", f"--screenshot={target}", f"http://127.0.0.1:{port}/{query}"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            if target.exists():
                print(f"{target.relative_to(ROOT)}")
    finally:
        server.terminate()
        server.wait()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Makes THEME.md's pictures (docs/theme/).")
    parser.add_argument("--renders", type=Path, help="an earlier run's renders, instead of rendering again")
    parser.add_argument("--python", default=str(ROOT / ".venv" / "bin" / "python"), help="the Python that runs the theme server")
    parser.add_argument("--no-server-shots", action="store_true", help="skip the pictures of the theme server's page")
    options = parser.parse_args(argv)

    renders = options.renders
    temporary = None
    if renders is None:
        temporary = Path(tempfile.mkdtemp(prefix="theme-docs-renders-"))
        renders = temporary
        render(renders, options.python)

    try:
        r = Renders(renders)
        for make in (hero, screens, region_maps, schemes, layouts, languages, screen_sizes, pointer):
            make(r)
        nine_patch()
        areas()
        if not options.no_server_shots:
            editor_shots(options.python)
    finally:
        if temporary is not None:
            shutil.rmtree(str(temporary), ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
