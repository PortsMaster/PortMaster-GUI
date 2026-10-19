# SPDX-License-Identifier: MIT
#
# The theme dev server's scenes: every screen pugwash has, set up with real port data, and
# the renderer that draws one into a PNG with the regions it drew. Imported by worker.py,
# after it has set up the environment pugwash and harbourmaster read on import.

import json
from pathlib import Path

import harbourmaster
from harbourmaster import i18n
from loguru import logger

from pugwash import scenes as pug_scenes
from pugwash.app import PortMasterGUI
from pugwash.scenes.base import BaseScene

from theme_server import catalogue


class MissingSection(Exception):
    """A screen needs a theme section this theme doesn't have."""


## Which theme section a scene was made from, for the debug boxes; a missing one is
## reported as such instead of pugwash's KeyError.
_load_regions = BaseScene.load_regions


def _recording_load_regions(self, section, required_tags):
    if section not in self.gui.theme_data:
        raise MissingSection(f"this theme has no {section} section")

    self.theme_section = section
    return _load_regions(self, section, required_tags)


BaseScene.load_regions = _recording_load_regions


class EmptyScene(BaseScene):
    """Nothing on screen: the scene under the dialogs (not every theme has a "blank" section)."""
    def __init__(self, gui):
        super().__init__(gui)
        self.theme_section = ""


class RecordingDict(dict):
    """A translations dict that notes every string looked up in it: which strings a screen uses."""
    def __init__(self, data, seen):
        super().__init__(data)
        self.seen = seen

    def get(self, key, default=None):
        self.seen.append(key)
        return super().get(key, default)


def record_lookups():
    """Swap harbourmaster.i18n's dicts for recording ones: {'messages': [...], 'themes': [...]},
    in lookup order, for the caller to clear."""
    seen = {'messages': [], 'themes': []}
    i18n._messages = RecordingDict(i18n._messages, seen['messages'])
    i18n._themes = RecordingDict(i18n._themes, seen['themes'])
    i18n._theme_own = RecordingDict(i18n._theme_own, seen['themes'])
    return seen


def _unique(items):
    found = []
    for item in items:
        if item not in found:
            found.append(item)
    return found


class NoThemeDownloads:
    """The themes list without the online theme list: installed themes only."""
    def get_theme_list(self):
        return {}


## pugwash's fifo_control (autoinstall, PortMasterDialog) always uses the default theme.
DEFAULT_THEME_ONLY = {"selection_list", "selection_description", "selection_images", "selection_description_images"}


## Ports picked for the port info screens, the first one that's in the cache wins.
PORT_INFO_PORTS = ("2048.zip", "cave-story.zip", "celeste.zip", "stardewvalley.zip")


################################################################################
## The shots: (name, title, builder). A builder sets up gui.scenes.
def _root(gui, scene):
    gui.scenes = [('root', [scene])]


def _ports_list(gui, mode='install', base_filters=(), name=None):
    scene = pug_scenes.PortsListScene(gui, {'mode': mode, 'base_filters': list(base_filters), 'name': name})
    _root(gui, pug_scenes.MainMenuScene(gui))
    gui.push_scene('ports', scene)
    return scene


def _info_port(gui, required=True):
    for name in PORT_INFO_PORTS:
        if gui.hm.port_info(name) is not None:
            return name

    name = next(iter(gui.hm.list_ports()), None)
    if name is None and required:
        raise MissingSection("no ports downloaded yet, start the server once with the network on")

    return name


def shot_main_menu(gui):
    _root(gui, pug_scenes.MainMenuScene(gui))


def shot_ports_all(gui):
    _ports_list(gui, 'install')


def shot_ports_rtr(gui):
    _ports_list(gui, 'install', ['rtr'], "Ready to Run Ports")


def shot_ports_manage(gui):
    _ports_list(gui, 'uninstall', ['installed'], "Manage Ports")


def shot_port_info(gui):
    list_scene = _ports_list(gui, 'install')
    gui.push_scene('port_info', pug_scenes.PortInfoScene(gui, _info_port(gui), 'install', list_scene))


def shot_port_info_popup(gui):
    from pugwash.scenes.port_info import PortInfoPopup
    shot_port_info(gui)
    info_scene = gui.scenes[-1][1][-1]
    gui.push_scene('port_info', PortInfoPopup(gui, info_scene))


def _links_port(gui):
    """A port with a few links (website and stores): one of PORT_INFO_PORTS if it has, or
    the port with the most."""
    def links(name):
        return len(gui.get_port_links(name, gui.hm.port_info(name)))

    for name in PORT_INFO_PORTS:
        if gui.hm.port_info(name) is not None and links(name) >= 3:
            return name

    return max(gui.hm.list_ports(), key=links, default=None) or _info_port(gui)


def shot_port_links(gui):
    name = _links_port(gui)
    list_scene = _ports_list(gui, 'install')
    info_scene = pug_scenes.PortInfoScene(gui, name, 'install', list_scene)
    gui.push_scene('port_info', info_scene)
    gui.push_scene('port_links', pug_scenes.PortLinksScene(gui, name, info_scene.port_info))

    ## A store, not the website, so a store's address shows.
    scene = gui.scenes[-1][1][-1]
    if len(scene.links) > 1:
        scene.tags['links_list'].list_select(1)
        scene.last_select = 1
        scene.show_link(1)


def shot_filters(gui):
    list_scene = _ports_list(gui, 'install')
    gui.push_scene('ports', pug_scenes.FiltersScene(gui, list_scene))


def _need_featured(gui):
    if not gui.hm.featured_ports(pre_load=True):
        raise MissingSection("no featured ports downloaded yet, start the server once with the network on")


def shot_featured(gui):
    from pugwash.scenes import FeaturedPortsNavigationScene
    _need_featured(gui)
    _root(gui, pug_scenes.MainMenuScene(gui))
    gui.push_scene('featured-ports', FeaturedPortsNavigationScene(gui))


def shot_featured_list(gui):
    from pugwash.scenes.ports import FeaturedPortsScene
    _need_featured(gui)
    _root(gui, pug_scenes.MainMenuScene(gui))
    items = gui.hm.featured_ports()

    def first_list(items):
        for item in items:
            if item.get('ports'):
                return item
            found = first_list(item.get('children') or [])
            if found:
                return found
        return None

    item = first_list(items)
    if item is None:
        raise RuntimeError("no featured ports list in the cache")

    gui.push_scene('port-list', FeaturedPortsScene(gui, item))


def shot_options(gui):
    _root(gui, pug_scenes.MainMenuScene(gui))
    gui.push_scene('option', pug_scenes.OptionScene(gui))


def shot_runtimes(gui):
    shot_options(gui)
    gui.push_scene('runtime-manager', pug_scenes.RuntimesScene(gui))


def shot_themes(gui):
    gui.theme_downloader = NoThemeDownloads()
    shot_options(gui)
    gui.push_scene('select-theme', pug_scenes.ThemesScene(gui))


def shot_theme_schemes(gui):
    shot_options(gui)
    gui.push_scene('select-scheme', pug_scenes.ThemeSchemeScene(gui))


def shot_language(gui):
    shot_options(gui)
    gui.push_scene('select-language', pug_scenes.LanguageScene(gui))


def shot_keyboard(gui):
    shot_options(gui)
    gui.push_scene('osk', pug_scenes.OnScreenKeyboard(gui))


def shot_theme_editor(gui):
    ## Not started: a renderer mustn't run a server. A theme without a "theme_server"
    ## section shows PortMaster's plain fallback, as on a device.
    shot_options(gui)
    scene = pug_scenes.ThemeServerScene(gui, start=False)
    gui.push_scene('theme-editor', scene)
    scene.show("http://192.168.0.2:8090/")


def shot_messages(gui):
    _ports_list(gui, 'install')
    gui.messages_begin(internal=True)
    for text in ("Downloading cave-story.zip", "Checking cave-story.zip", "Installing cave-story.zip",
                 "Extracting Cave Story/gamedata/data.pak", "Downloading runtime: love_11.5.squashfs"):
        gui.message(text)
    gui.progress("Downloading love_11.5.squashfs", 7340032, 12582912, 'data')


def shot_message_box(gui):
    _ports_list(gui, 'install')
    gui.push_scene('message_box', pug_scenes.MessageBoxScene(
        gui, "Do you want to install Cave Story?\n\nIt needs the love_11.5 runtime (12 MB).",
        title_text="Install", want_cancel=True))


SUMMARY = {
    'cave-story.zip': {'title': "Cave Story: installed", 'description': "Installed from autoinstall.\n\nIt is in your Ports list now."},
    'broken.zip': {'title': "broken.zip: not installed", 'description': "Not a zip file.\n\nIt was kept in the autoinstall folder."},
    'love_11.5.squashfs': {'title': "love_11.5: runtime installed", 'description': "Moved to PortMaster/libs."},
    }


def _selection(gui, want_description, want_images):
    from pugwash.scenes import DialogSelectionList
    _root(gui, EmptyScene(gui))
    register = json.loads(json.dumps(SUMMARY))
    if want_images:
        port = _info_port(gui, required=False)
        image = gui.hm.port_images(port).get('screenshot') if port else None
        for value in register.values():
            value['image'] = str(image) if image else "NO_IMAGE"

    gui.push_scene('selection_list', DialogSelectionList(gui, {
        'title': "Autoinstall", 'want_description': want_description, 'want_images': want_images,
        'want_cancel': False, 'ok_text': "Okay"}, register))


def shot_selection_list(gui):
    _selection(gui, False, False)


def shot_selection_description(gui):
    _selection(gui, True, False)


def shot_selection_images(gui):
    _selection(gui, False, True)


def shot_selection_description_images(gui):
    _selection(gui, True, True)


def shot_disclaimer(gui):
    from pugwash.scenes import DisclaimerScene
    _root(gui, DisclaimerScene(gui))


def _startup_warning(gui, keywords):
    """The unsupported-system warning with these of get_startup_warnings()'s warnings."""
    from pugwash.scenes import StartupWarningScene
    from pugwash.scenes import startup
    import unittest.mock

    ## Its warnings come from looking at the device; pretend to be one that gets these.
    def exists(path):
        return {"/mnt/SDCARD/spruce": "spruce", "/etc/trimui_device.txt": "trimui"}.get(str(path).rstrip("/")) in keywords

    with unittest.mock.patch.object(startup.Path, "exists", lambda self: exists(self)):
        info = dict(harbourmaster.device_info(), ram=512 if "lowram" in keywords else 2048)
        warnings = startup.get_startup_warnings(info)

    _root(gui, StartupWarningScene(gui, warnings))


def shot_warning_trimui(gui):
    _startup_warning(gui, {"trimui"})


def shot_warning_long(gui):
    _startup_warning(gui, {"spruce", "lowram"})


## The catalogue's screens with their builders.
SHOTS = tuple((name, title, globals()["shot_" + name]) for name, title in catalogue.SHOTS)

SHOT_BUILDERS = {name: builder for name, _, builder in SHOTS}


################################################################################
## The renderer
def _json_safe(value):
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def scene_regions(gui):
    """The regions on screen, bottom to top, as the debug boxes show them."""
    found = []
    for depth, scene in enumerate(gui.scenes[-1][1]):
        tags = {id(region): tag for tag, region in scene.tags.items()}
        for region in scene.regions:
            area = region.area
            found.append({
                'scene': type(scene).__name__,
                'section': getattr(scene, 'theme_section', ""),
                'depth': depth,
                'name': region.name,
                'tag': tags.get(id(region)),
                'visible': bool(region.visible),
                'z': [region.z_index, region.z_position],
                'rect': [area.x, area.y, area.width, area.height],
                'data': {key: _json_safe(value) for key, value in region._dict.items()},
                })

    return found


class Renderer:
    def __init__(self, work, theme_name, scheme=None, tools_dir=None):
        """tools_dir: the HarbourMaster's (its ports and config), when it isn't
        harbourmaster.HM_TOOLS_DIR (a renderer forked from worker.py's zygote)."""
        self.work = Path(work)
        self.errors = []
        ## pugwash's errors (the theme's), not harbourmaster's (the port data's).
        logger.add(lambda message: self.errors.append(message.record["message"]), level="ERROR",
                   filter=lambda record: not record["name"].startswith("harbourmaster"))

        self.theme_name = theme_name
        self.gui = PortMasterGUI(first_scene=EmptyScene, force_theme=theme_name, force_scheme=scheme)
        self.scheme = self.gui.themes.get_current_theme_scheme()
        dirs = {}
        if tools_dir is not None:
            dirs = {'tools_dir': Path(tools_dir), 'ports_dir': self.work / "ports", 'scripts_dir': self.work / "ports"}
        self.gui.hm = harbourmaster.HarbourMaster(
            {'offline': True, 'no-check': True},
            temp_dir=self.work / "temp", callback=self.gui, **dirs)
        ## Screenshots load as they're drawn, so every image is there in the first frame.
        self.gui.images.disable_async()
        ## Which strings each screen looks up, for the translation editor.
        self.lookups = record_lookups()
        ## No sounds or music in a screenshot.
        self.gui.sounds.sound_is_disabled = True
        self.gui.sounds.music_is_disabled = True

    def load(self, theme_name, scheme, lang):
        """Another theme, colour scheme or language (or the same, saved again): reloaded in
        place, much quicker than a new renderer."""
        gui = self.gui
        gui.themes.force_theme = theme_name
        gui.themes.force_scheme = scheme
        ## Reloads the translations (saved ones too) and then the theme.
        gui.reload_language(lang)
        self.lookups = record_lookups()
        self.theme_name = theme_name
        self.scheme = gui.themes.get_current_theme_scheme()

    def settle(self, frames=3):
        """A few frames, so scenes fill in their lists and text."""
        gui = self.gui
        for _ in range(frames):
            gui.updated = True
            gui.draw_counter = 0
            gui.do_loop(no_delay=True)

    def render(self, shot, out_file):
        builder = SHOT_BUILDERS.get(shot)
        if builder is None:
            raise KeyError(f"no shot called {shot!r}")

        self.errors.clear()
        for seen in self.lookups.values():
            seen.clear()
        gui = self.gui
        ## A screen that "quit" (eg: a scene with nothing to show) mustn't cancel the next one.
        gui.events.running = True
        if shot in DEFAULT_THEME_ONLY and self.theme_name != "default_theme":
            raise MissingSection("autoinstall and PortMasterDialog screens always use the default theme")

        gui.callback_messages = []
        gui.message_box_scene = None
        gui.callback_amount = 0
        builder(gui)
        self.settle()
        gui.create_screenshot(str(out_file))
        regions = scene_regions(gui)
        if gui.message_box_scene is not None:
            gui.messages_end(internal=True)

        return regions, list(self.errors)

    def strings(self):
        """The strings the last render looked up, once each: {'messages': [...], 'themes': [...]}."""
        return {domain: _unique(seen) for domain, seen in self.lookups.items()}

    def quit(self):
        self.gui.quit()
