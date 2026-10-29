# SPDX-License-Identifier: MIT
#
# What the theme editor knows about theme.json, for its autocomplete and its checks: read
# from pugwash's own code (no import, so no SDL), so it can't drift from what PortMaster
# accepts.
#   - region keys and their types: the `self._verify_<type>('key', ...)` calls in
#     sdl/region.py, with the options of `_verify_option`
#   - sections: the default theme's, and the `load_regions("section", ...)` of the scenes
#   - template tags: every "x.y" key pugwash sets with `set_data` / `text_data[...]`
#   - capabilities: the [...] requirements the default theme and the other themes use
#
# Python 3.7, standard library only.

import ast
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
PYLIBS = HERE.parent
PUGWASH = PYLIBS / "pugwash"
DEFAULT_THEME = PYLIBS / "default_theme" / "theme.json"
RESOURCES = PYLIBS / "resources"

## Keys a region can have that aren't a _verify_* call.
EXTRA_KEYS = {
    'image':        {'type': "image"},
    'pimage':       {'type': "image"},
    'pointer':      {'type': "image"},
    'music':        {'type': "file"},
    'music-volume': {'type': "int", 'min': 0, 'max': 128},
    'tag':          {'type': "text"},
    'comment':      {'type': "text"},
    }

## The top level of theme.json: "#" sections, then the screens.
TOP_KEYS = {
    '#info':         "the theme's name, creator, description and default-scheme",
    '#schemes':      "color schemes: each has a #pallet and can change #resources and any section",
    '#base':         "keys every region starts from",
    '#elements':     "named regions sections can use with \"#element:<name>\"",
    '#resources':    "images, fonts and sounds: names, atlases, image-mod",
    '#pallet':       "named colors",
    '#override':     "text for the special words (_A, _B, _CHECKED ...)",
    '#animations':   "named animations",
    '#translations': "the theme's own translations: {lang: {English: translation}}",
    }

INFO_KEYS = {
    'name':           {'type': "text"},
    'creator':        {'type': "text"},
    'description':    {'type': "text"},
    'version':        {'type': "text"},
    'default-scheme': {'type': "scheme"},
    }

## Keys of a section's "#config".
CONFIG_KEYS = {
    'buttons': {'type': "object"},
    }

SPECIAL_WORDS = ['_A', '_B', '_X', '_Y', '_UP', '_DOWN', '_LEFT', '_RIGHT', '_START', '_SELECT',
                 '_L', '_R', '_CHECKED', '_UNCHECKED', '_MORE']

## Capabilities every device has one of, as well as what the themes use.
BASE_CAPABILITIES = ['640x480', '480x320', '720x720', '1280x720', '1920x1080', '4:3', '16:9', '3:2', '1:1',
                     'wide', 'hires', 'lowres', 'opengl', 'power']


_MISSING = object()


def _const(node):
    """A literal's value, or _MISSING: Python 3.7 parses them as Str/Num/NameConstant, 3.8+ as Constant."""
    if isinstance(node, ast.Constant):
        return node.value
    for kind, field in (("Str", "s"), ("Num", "n"), ("NameConstant", "value")):
        if hasattr(ast, kind) and type(node).__name__ == kind:
            return getattr(node, field)
    return _MISSING


def _literal(node, names):
    """A literal option list, with the names we know (Rect.POINTS, BLEND_MODES) filled in."""
    if isinstance(node, ast.Attribute) and node.attr in names:
        return names[node.attr]
    if isinstance(node, ast.Name) and node.id in names:
        return names[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "list" and node.args:
        return _literal(node.args[0], names)
    try:
        value = ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError):
        return None
    if isinstance(value, (list, tuple)):
        return [item for item in value if isinstance(item, str)]
    return None


def _class_constants(tree):
    """{'POINTS': [...], 'BLEND_MODES': [...]}: string tuples/lists and dict keys assigned in classes."""
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = node.value
            if isinstance(value, ast.Dict):
                keys = [_const(key) for key in value.keys if isinstance(_const(key), str)]
                if keys:
                    found[node.targets[0].id] = keys
            elif isinstance(value, (ast.Tuple, ast.List)):
                items = [_const(item) for item in value.elts if isinstance(_const(item), str)]
                if items and len(items) == len(value.elts):
                    found[node.targets[0].id] = items
    return found


def region_keys():
    """{key: {'type': ..., 'options': [...], 'count': n, 'min': n, 'max': n}} of a region."""
    sdl = PUGWASH / "sdl"
    names = {}
    for path in sorted(sdl.glob("*.py")):
        names.update(_class_constants(ast.parse(path.read_text(encoding="utf-8"))))

    keys = {}
    tree = ast.parse((sdl / "region.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr.startswith("_verify_")):
            continue
        if not node.args or not isinstance(_const(node.args[0]), str):
            continue

        key, kind = _const(node.args[0]), node.func.attr[len("_verify_"):]
        entry = {'type': kind}
        keywords = {keyword.arg: keyword.value for keyword in node.keywords}
        if kind == "option":
            options = _literal(node.args[1], names) if len(node.args) > 1 else None
            if options:
                entry['options'] = options
            if 'length' in keywords and isinstance(_const(keywords['length']), int):
                entry['count'] = _const(keywords['length'])
        elif kind == "ints" and len(node.args) > 1 and isinstance(_const(node.args[1]), int):
            entry['count'] = _const(node.args[1])
        for bound, name in (('minimum', 'min'), ('maximum', 'max')):
            if bound in keywords and isinstance(_const(keywords[bound]), (int, float)):
                entry[name] = _const(keywords[bound])
        keys.setdefault(key, entry)

    for key, entry in EXTRA_KEYS.items():
        keys.setdefault(key, dict(entry))

    return dict(sorted(keys.items()))


def _read_theme(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def sections():
    """{section: [region names]}: the default theme's sections and every scene's."""
    found = {}
    for name, data in _read_theme(DEFAULT_THEME).items():
        if not name.startswith("#") and isinstance(data, dict):
            found[name] = [region for region in data if not region.startswith("#")]

    for path in sorted((PUGWASH / "scenes").glob("*.py")):
        for section, tags in re.findall(r'load_regions\(\s*["\']([a-z_]+)["\']\s*,\s*\[([^\]]*)\]', path.read_text(encoding="utf-8")):
            regions = found.setdefault(section, [])
            for tag in re.findall(r'["\']([a-z_]+)["\']', tags):
                if tag not in regions:
                    regions.append(tag)

    return dict(sorted(found.items()))


def template_tags():
    """Every {tag} pugwash sets: "system.time_24hr", "port_info.title" ..."""
    found = set()
    pattern = re.compile(r'(?:set_data\(\s*|text_data\[\s*)f?["\']([a-z_]+\.[a-z0-9_]+)["\']')
    for path in sorted(PUGWASH.rglob("*.py")):
        found.update(pattern.findall(path.read_text(encoding="utf-8")))
    return sorted(found)


def capabilities(theme_files=()):
    """The [requirements] themes use, split on | and ,."""
    found = set(BASE_CAPABILITIES)
    for path in [DEFAULT_THEME, *theme_files]:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        for group in re.findall(r'\[([^\]"]+)\]"\s*:', text):
            for item in re.split(r'[|,]', group):
                item = item.strip().lstrip("!")
                if item:
                    found.add(item)
    return sorted(found)


def theme_files(theme_dir):
    """Files in the theme a key can name, by kind: {'image': [...], 'font': [...], 'sound': [...]}."""
    kinds = {'image': ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.webp', '.svg'),
             'font': ('.ttf', '.otf'), 'sound': ('.ogg', '.wav', '.mp3')}
    found = {kind: [] for kind in kinds}
    if theme_dir is not None:
        theme_dir = Path(theme_dir)
        for path in sorted(theme_dir.rglob("*")):
            if path.is_file():
                for kind, suffixes in kinds.items():
                    if path.suffix.lower() in suffixes:
                        found[kind].append(path.relative_to(theme_dir).as_posix())
    ## PortMaster's own fonts work in every theme.
    for path in sorted(RESOURCES.glob("*")):
        if path.suffix.lower() in kinds['font'] or path.name == "NotoSans.tar.xz":
            names = [path.name] if path.suffix.lower() in kinds['font'] else \
                ["NotoSansJP-Regular.ttf", "NotoSansKR-Regular.ttf", "NotoSansSC-Regular.ttf", "NotoSansTC-Regular.ttf", "NotoSansHK-Regular.ttf"]
            found['font'] += [name for name in names if name not in found['font']]
    return found


def theme_names(theme_data):
    """Names the theme defines: pallet colors (every scheme's), resources and atlas parts, elements, schemes."""
    colors, resources, elements = set(), set(), set()
    schemes = [name for name in theme_data.get("#schemes", {}) if isinstance(theme_data.get("#schemes"), dict) and not name.startswith("#")]

    def pallet(section):
        if isinstance(section, dict) and isinstance(section.get("#pallet"), dict):
            colors.update(section["#pallet"])
        if isinstance(section, dict) and isinstance(section.get("#resources"), dict):
            for file_name, info in section["#resources"].items():
                resources.add(file_name)
                if isinstance(info, dict):
                    if isinstance(info.get("name"), str):
                        resources.add(info["name"])
                    if isinstance(info.get("atlas"), dict):
                        resources.update(info["atlas"])

    pallet(theme_data)
    if isinstance(theme_data.get("#schemes"), dict):
        for scheme in theme_data["#schemes"].values():
            pallet(scheme)
    if isinstance(theme_data.get("#elements"), dict):
        elements.update(theme_data["#elements"])

    return {'colors': sorted(colors), 'resources': sorted(resources), 'elements': sorted(elements), 'schemes': schemes}


def schema(theme_dir=None, other_themes=()):
    """Everything the editor's autocomplete and checks need, for one theme."""
    data = _read_theme(Path(theme_dir) / "theme.json") if theme_dir is not None else {}
    return {
        'top': TOP_KEYS,
        'info': INFO_KEYS,
        'config': CONFIG_KEYS,
        'keys': region_keys(),
        'sections': sections(),
        'tags': template_tags(),
        'capabilities': capabilities(([Path(theme_dir) / "theme.json"] if theme_dir is not None else []) + list(other_themes)),
        'special_words': SPECIAL_WORDS,
        'files': theme_files(theme_dir),
        'names': theme_names(data),
        }
