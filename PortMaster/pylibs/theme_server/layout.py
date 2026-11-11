"""The layout check: what a theme's screens draw where, and what goes wrong at a screen size.

A render records what every region drew (shots.DrawnRecorder): each piece of text with the
scale it was drawn at, and each image. Here that becomes a list of problems:

  - clash: content of two regions of the same screen on top of each other (a popup over
    the screen below it is fine: that's another depth)
  - off screen: content past the edge of the screen
  - outside its box: content past the edge of its own region's area
  - scaled text (a warning): text drawn smaller or bigger than its font size, because the
    box it's drawn to fit doesn't hold it at that size. Sometimes that's the plan: a button
    bar too long for a narrow screen shrinks to fit, keyboard keys fit their labels.
  - pointer clash (a warning): a list's pointer over another region's content. Pointer
    images keep their own size and are mostly see-through, so look at the screen.

The others are errors: something on the screen can't be read.

    python3 -I -m theme_server.layout <export folder>    (from serve.py --export)
"""
import json
import sys
from pathlib import Path

## A list's pointer image is mostly see-through padding, at its own size whatever the screen:
## next to text on a small screen it's often only the padding that overlaps.
WARNINGS = {"scaled text", "pointer clash"}

## Overlaps this small are anti-aliasing and rounding, not a clash.
SLACK = 3
TEXT_SCALE = (0.9, 1.1)


def _overlap(a, b):
    x1, y1 = max(a[0], b[0]), max(a[1], b[1])
    x2, y2 = min(a[0] + a[2], b[0] + b[2]), min(a[1] + a[3], b[1] + b[3])
    return (x2 - x1, y2 - y1) if x2 - x1 > SLACK and y2 - y1 > SLACK else None


def problems(regions, size):
    """[{'kind', 'regions', 'rect', 'text'}] for one rendered screen. regions: as a render
    reports them (shots.scene_regions); size: (width, height)."""
    found = []
    width, height = size
    shown = [region for region in regions if region.get('visible', True) and region.get('drawn')]

    for region in shown:
        for kind, x, y, w, h, scale in region['drawn']:
            if x < -SLACK or y < -SLACK or x + w > width + SLACK or y + h > height + SLACK:
                found.append({'kind': "off screen", 'regions': [region['name']], 'rect': [x, y, w, h],
                              'text': f"{region['name']}: its {kind} is past the edge of the screen"})

            rx, ry, rw, rh = region.get('rect', (x, y, w, h))
            if kind != 'pointer' and (x < rx - SLACK or y < ry - SLACK or x + w > rx + rw + SLACK or y + h > ry + rh + SLACK):
                found.append({'kind': "outside its box", 'regions': [region['name']], 'rect': [x, y, w, h],
                              'text': f"{region['name']}: its {kind} is drawn outside its area"})

            if kind == 'text' and not TEXT_SCALE[0] <= scale <= TEXT_SCALE[1]:
                found.append({'kind': "scaled text", 'regions': [region['name']], 'rect': [x, y, w, h],
                              'text': f"{region['name']}: text drawn at {scale:.0%} of its font size (its box doesn't fit it)"})

    for i, first in enumerate(shown):
        for second in shown[i + 1:]:
            if first.get('depth') != second.get('depth'):
                continue

            clash = None
            for a in first['drawn']:
                for b in second['drawn']:
                    overlap = _overlap(a[1:5], b[1:5])
                    if overlap is not None and (clash is None or overlap[0] * overlap[1] > clash[1][0] * clash[1][1]):
                        clash = ((a, b), overlap)

            if clash is not None:
                (a, b), (w, h) = clash
                found.append({'kind': "pointer clash" if 'pointer' in (a[0], b[0]) else "clash", 'regions': [first['name'], second['name']],
                              'rect': [max(a[1], b[1]), max(a[2], b[2]), w, h],
                              'text': f"{first['name']}'s {a[0]} and {second['name']}'s {b[0]} overlap by {w}x{h}"})

    return found


def check_export(folder):
    """{(theme, resolution, scheme, lang, shot): problems} for every render in an export folder."""
    results = {}
    for info_file in sorted(Path(folder).glob("*/*/*/*/*.json")):
        theme, resolution, scheme, lang = info_file.parts[-5:-1]
        info = json.loads(info_file.read_text(encoding="utf-8"))
        width, height = (int(n) for n in resolution.split("x"))
        results[(theme, resolution, scheme, lang, info_file.stem)] = problems(info.get('regions', []), (width, height))

    return results


def errors(found):
    return [problem for problem in found if problem['kind'] not in WARNINGS]


def main(argv):
    if len(argv) != 1:
        print(__doc__.strip().splitlines()[-1].strip())
        return 2

    results = check_export(argv[0])
    bad = {key: found for key, found in results.items() if found}
    for (theme, resolution, scheme, lang, shot), found in bad.items():
        print(f"{theme} {resolution} {scheme} {lang} {shot}:")
        for problem in found:
            print(f"  {problem['kind']}: {problem['text']}")

    failed = [key for key, found in results.items() if errors(found)]
    print(f"{len(results)} screens: {len(failed)} with errors, {len(bad) - len(failed)} with warnings only")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
