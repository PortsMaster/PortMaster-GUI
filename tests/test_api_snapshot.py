# SPDX-License-Identifier: MIT
#
# Guards the restructure: every public name that existed before must still be
# reachable afterwards (new names are fine). Only AREAS changes when code moves.
#
# Regenerate (only when removing something on purpose):
#   PM_UPDATE_API_SNAPSHOT=1 pytest tests/test_api_snapshot.py

import inspect
import json
import os

from types import SimpleNamespace

import pytest

import harbourmaster

from conftest import DATA_DIR


SNAPSHOT_FILE = DATA_DIR / "api_snapshot.json"


def _merge(*namespaces):
    merged = {}
    for namespace in namespaces:
        merged.update(vars(namespace))

    return SimpleNamespace(**merged)


## What used to be the pugwash script.
_GUI_MODULES = ("pugwash.main", "pugwash.lang", "pugwash.util", "pugwash.update", "pugwash.app")


def _gui_modules():
    import importlib
    return [importlib.import_module(name) for name in _GUI_MODULES]


## Where each area lives: (needs SDL, locate, modules its own definitions come from).
## Update these, not the snapshot, when code moves.
AREAS = {
    'harbourmaster':          (False, lambda: harbourmaster, ("harbourmaster",)),
    'harbourmaster.util':     (False, lambda: harbourmaster.util, ("harbourmaster.util",)),
    'harbourmaster.source':   (False, lambda: harbourmaster.source, ("harbourmaster.source",)),
    'harbourmaster.platform': (False, lambda: harbourmaster.platform, ("harbourmaster.platform",)),
    'HarbourMaster':          (False, lambda: harbourmaster.HarbourMaster, None),
    'harbourmaster script':   (False, lambda: __import__("harbourmaster.cli").cli, ("harbourmaster.cli",)),
    'pugtask':                (False, lambda: __import__("pugwash.tasks").tasks, ("pugwash.tasks",)),
    'pySDL2gui':              (True,  lambda: __import__("pugwash.sdl").sdl, ("pugwash.sdl",)),
    'pugtheme':               (True,  lambda: __import__("pugwash.theme").theme, ("pugwash.theme",)),
    'pugscene':               (True,  lambda: __import__("pugwash.scenes").scenes, ("pugwash.scenes",)),
    'pugwash script':         (True,  lambda: _merge(*_gui_modules()), _GUI_MODULES),
    'PortMasterGUI':          (True,  lambda: __import__("pugwash.app").app.PortMasterGUI, None),
    }


def _star_import_sources():
    ## Constants that modules only have because of `from .config import *` and friends.
    from harbourmaster import config, hardware, info, util
    return [config, hardware, info, util]


def public_names(obj, own_modules):
    names = set()

    if inspect.isclass(obj):
        for name in dir(obj):
            if name.startswith("__") or name.startswith("_HarbourMaster__"):
                continue

            names.add(name)

        return names

    name_of = getattr(obj, "__name__", "")
    is_script = any(module.startswith("script_") or module == "harbourmaster.cli" for module in own_modules)
    borrowed = set()
    for source in _star_import_sources():
        if not name_of.startswith(source.__name__) and obj is not harbourmaster:
            borrowed.update(vars(source))

    for name, value in vars(obj).items():
        if name.startswith("_") or inspect.ismodule(value):
            continue

        if inspect.isclass(value) or inspect.isfunction(value):
            module = getattr(value, "__module__", "") or ""
            if module.startswith(own_modules):
                names.add(name)

        elif name.isupper() and name not in borrowed and not is_script:
            ## The scripts' own constants are bootstrap details that stay in the scripts.
            names.add(name)

    return names


def current_api(include_sdl=True):
    api = {}
    for area, (needs_sdl, locate, own_modules) in AREAS.items():
        if needs_sdl and not include_sdl:
            continue

        api[area] = sorted(public_names(locate(), own_modules))

    return api


def _sdl_available():
    ## The GUI modules import all of these.
    try:
        import sdl2  # noqa: F401
        import sdl2.sdlimage  # noqa: F401
        import sdl2.sdlmixer  # noqa: F401
        import sdl2.sdlttf  # noqa: F401
        return True

    except ImportError:
        return False


def test_api_snapshot():
    if os.environ.get("PM_UPDATE_API_SNAPSHOT") == "1":
        SNAPSHOT_FILE.write_text(json.dumps(current_api(), indent=2, sort_keys=True) + "\n")

    snapshot = json.loads(SNAPSHOT_FILE.read_text())
    have_sdl = _sdl_available()
    current = current_api(include_sdl=have_sdl)

    missing = {}
    for area, names in snapshot.items():
        if area not in current:
            assert not have_sdl, f"area {area} not checked"
            continue

        lost = sorted(set(names) - set(current[area]))
        if lost:
            missing[area] = lost

    assert missing == {}
