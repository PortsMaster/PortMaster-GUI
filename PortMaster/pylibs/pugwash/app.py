# SPDX-License-Identifier: MIT
#
# PortMasterGUI, the GUI itself.

import ctypes
import datetime
import json
import os
import shutil
import subprocess
import threading
from pathlib import Path
import harbourmaster
import png
import sdl2
import sdl2.ext
from pugwash import sdl
from pugwash import tasks
from loguru import logger
from pugwash.theme import ThemeEngine
from pugwash.scenes import MainMenuScene, StringFormatter, TempMenuScene
from harbourmaster.i18n import _
from pugwash import PYLIB_PATH, PORTMASTER_VERSION, PORTMASTER_DEBUG
from pugwash.lang import lang_list
from pugwash.util import battery_level, get_ip_address, is_process_running
from pugwash.app_callbacks import CallbackMixin
from pugwash.app_commands import CommandsMixin
from pugwash.app_fifo import FifoControlMixin
from pugwash.app_ports import PortInfoMixin
from pugwash import lang


def parse_resolution(text):
    """(width, height) from "1024x768", None for anything else."""
    width, _x, height = text.strip().lower().partition('x')
    if not (width.isdigit() and height.isdigit() and int(width) > 0 and int(height) > 0):
        return None

    return (int(width), int(height))


class PortMasterGUI(CallbackMixin, CommandsMixin, FifoControlMixin, PortInfoMixin, sdl.GUI, harbourmaster.Callback):
    """
    The GUI. Methods are grouped into the mixins in app_*.py.
    """
    TICK_INTERVAL = 1000 // 5
    TEXT_DATA_FREQ = 5000
    MIN_THEME_VERSION = 1
    IS_GUI = True
    TASK_INPUT_LAYERS = ('messages', 'message_box')
    FRAME_TIME = 1000 // 30

    def __init__(self, *, first_scene=None, force_theme=None, force_scheme=None):
        ## PM_HEADLESS=Y: no window, no video and no controllers, it draws onto a surface
        ## with the software renderer. The theme server's render workers (theme_server/
        ## worker.py) use it, on a device too: muOS's SDL has only its "mali" driver, and
        ## the PortMaster that started the server owns the screen.
        self.headless = os.environ.get('PM_HEADLESS', '') == 'Y'

        # Initialize SDL
        sdl2.ext.init(
            video=not self.headless,
            controller=not self.headless)

        def nice_version(v):
            return f"{v.major}.{v.minor}.{v.patch}"

        version = sdl2.SDL_version()
        sdl2.SDL_GetVersion(version)

        logger.info(f"PM: {PORTMASTER_VERSION}")
        logger.info(f"HM: {harbourmaster.HARBOURMASTER_VERSION}")
        logger.info(f"SDL DLL: {sdl2.dll.get_dll_file()},  {nice_version(version)}")
        logger.info(f"TTF DLL: {sdl2.sdlttf.get_dll_file()}, {nice_version(sdl2.sdlttf.TTF_Linked_Version()[0])}")
        logger.info(f"IMG DLL: {sdl2.sdlimage.get_dll_file()}, {nice_version(sdl2.sdlimage.IMG_Linked_Version()[0])}")
        logger.info(f"MIX DLL: {sdl2.sdlmixer.get_dll_file()}, {nice_version(sdl2.sdlmixer.Mix_Linked_Version()[0])}")
        logger.info(f"HM_TESTING: {harbourmaster.HM_TESTING}")

        # Load controller.
        count = sdl2.SDL_NumJoysticks()
        for index in range(count):
            is_game_controller = sdl2.SDL_IsGameController(index)
            print(f"{index}: {is_game_controller}")
            if is_game_controller == sdl2.SDL_TRUE:
                pad = sdl2.SDL_GameControllerOpen(index)
                if pad is not None:
                    logger.info(f"Opened GameController {index}: {sdl2.SDL_GameControllerName(pad)}")
                    logger.info(f" {sdl2.SDL_GameControllerMapping(pad)}")

        # Define window dimensions
        self.display_width = 640
        self.display_height = 480
        self.hm = None
        self.timers = sdl.Timer()

        # Get the current display mode
        display_mode = sdl2.video.SDL_DisplayMode()
        capabilities = harbourmaster.device_info()

        if self.headless:
            self.display_width, self.display_height = capabilities['resolution']

        elif sdl2.video.SDL_GetCurrentDisplayMode(0, display_mode) != 0:
            logger.error("Failed to get display mode:", sdl2.SDL_GetError())
            self.display_width, self.display_height = capabilities['resolution']

        else:
            self.display_width = display_mode.w
            self.display_height = display_mode.h
            # Print the display width and height
            logger.info(f"Display size: {self.display_width}x{self.display_height}")

        pretend_resolution = None
        if harbourmaster.HM_TESTING or self.headless:
            ## To pretend to be a different device set the device_info environment
            ## variables, eg: DEVICE_NAME=RG353V CFW_NAME=ArkOS DEVICE_ARCH=aarch64,
            ## and PM_PRETEND_RESOLUTION=1024x768 for its screen (the theme server).
            pretend_resolution = parse_resolution(os.environ.get('PM_PRETEND_RESOLUTION', ''))

            capabilities = harbourmaster.expand_info(dict(capabilities), override_resolution=pretend_resolution)

        if capabilities['device'] == 'default' and pretend_resolution is None:
            device = harbourmaster.find_device_by_resolution((self.display_width, self.display_height))
            logger.info(f"FOUND: {device}")
            if device != 'default':
                capabilities = harbourmaster.device_info(device)

        if capabilities['device'] == 'default' and pretend_resolution is None:
            capabilities = harbourmaster.expand_info(dict(capabilities), override_resolution=(self.display_width, self.display_height))

        ## The theme matches against harbourmaster.device_info(): give it the screen worked
        ## out above and the language (its "font[ja_JP]" & co).
        device_info = harbourmaster.device_info()
        if capabilities is not device_info:
            device_info.update(capabilities)
            capabilities = device_info

        capabilities['capabilities'].append(lang.CURRENT_LANG)

        logger.info(capabilities)
        print(capabilities)

        # Create the window
        if harbourmaster.HM_TESTING or self.headless:
            window_flags = None
        else:
            window_flags = sdl2.SDL_WINDOW_FULLSCREEN

            touch_file = harbourmaster.HM_TOOLS_DIR / "PortMaster" / "utils" / "pmsplash" / "stopsplash"

            if touch_file.parent.is_dir():
                touch_file.touch()

            for i in range(10):
                if not is_process_running(f"love.{capabilities['primary_arch']}"):
                    break

                sdl2.SDL_Delay(500)

            if is_process_running(f"love.{capabilities['primary_arch']}"):
                subprocess.check_output(["pkill", "-f", f"love.{capabilities['primary_arch']}"])

                if touch_file.is_file():
                    touch_file.unlink()


        if self.headless:
            self.window = None
            self.surface = sdl2.SDL_CreateRGBSurfaceWithFormat(
                0, *capabilities['resolution'], 32, sdl2.SDL_PIXELFORMAT_ARGB8888)
            renderer = sdl2.ext.Renderer(self.surface.contents)

        else:
            self.window = sdl2.ext.Window("PortMaster", size=capabilities['resolution'], flags=window_flags)
            self.window.show()

            # Create a renderer for drawing on the window
            renderer = sdl2.ext.Renderer(self.window, flags=sdl2.SDL_RENDERER_ACCELERATED)

        sdl2.SDL_SetHint(sdl2.SDL_HINT_RENDER_SCALE_QUALITY, b"2")

        # Quickly present something, helps on ArkOS.
        renderer.clear()
        renderer.present()

        self.text_data = {}
        self.changed_keys = set()
        formatter = StringFormatter(self.text_data)

        super().__init__(renderer, formatter)

        ## Threading, see run_task()
        self.dispatcher = tasks.MainThreadDispatcher()
        self.task = None

        self.dir_scanner = tasks.DirectoryScanner(self.dispatcher)
        self.dir_scanner.callback = self.dir_scanner_callback

        ## Port screenshots are decoded in the background.
        self.images.enable_async(self.dispatcher)
        self.deferred_keys = set()
        self.pending_progress = None
        self.pending_progress_lock = threading.Lock()

        cfg_data = self.get_config()
        default_sound = False

        if cfg_data.get('analog-min', 0) > 0:
            self.events.analog_min = cfg_data['analog-min']

        if 'arkos' in capabilities['name'].lower() and 'rk3366' in capabilities['cpu']:
            default_sound = not Path('/etc/asound.conf').exists()

        self.sounds.sound_is_disabled = cfg_data.setdefault('sfx-disabled', default_sound)
        self.sounds.music_is_disabled = cfg_data.setdefault('music-disabled', default_sound)

        self.cancellable = True

        self.themes = ThemeEngine(self, force_theme=force_theme, force_scheme=force_scheme)

        self.theme_data = self.themes.gui_init()
        self.theme_dir = self.themes.get_theme_dir(self.themes.get_current_theme())
        self.resources.add_path(PYLIB_PATH / 'resources')
        self.theme_downloader = None

        self.spinner = 0

        if first_scene is not None:
            self.scenes = [
                ('root', [first_scene(self)]),
                ]
        else:
            self.scenes = [
                ('root', [TempMenuScene(self)]),
                ]

        self.callback_messages = []
        self.callback_progress = None
        self.callback_amount = 0
        self.message_box_disable = False
        self.message_box_depth = 0
        self.message_box_scene = None
        self.was_cancelled = False

        self.updated = True
        self.in_screenshot = False

        device_info = harbourmaster.device_info()
        self.set_data('system.portmaster_version', PORTMASTER_VERSION)
        self.set_data('system.harbourmaster_version', harbourmaster.HARBOURMASTER_VERSION)
        self.set_data('system.cfw_name', device_info['name'])
        self.set_data('system.cfw_version', device_info['version'])
        self.set_data('system.device_name', device_info['device'])
        self.set_data('system.ip_address', get_ip_address() or _("Unknown IP"))
        self.set_data('system.progress_text', "")
        self.set_data('system.progress_amount', "")
        self.set_data('system.progress_perc_5', "0")
        self.set_data('system.progress_perc_10', "0")
        self.set_data('system.progress_perc_25', "0")

        self.set_data('ports_list.filters', "")
        self.set_data('ports_list.total_ports', "")
        self.set_data('ports_list.filter_ports', "")

        self.set_port_info(None, {})

        self.lang_list = lang_list()
        self.update_counter = 0
        self.draw_counter = 0

        ## PM_PERF=1 logs frame timing, see tasks.FrameStats
        self.perf = tasks.FrameStats(os.environ.get('PM_PERF', '') == '1')
        self.in_callback_loop = False


        self.port_size_active_port = None
        self.port_size_files = {}
        self.port_size_file_lookup = {}

    # def init_theme(self):
    #     ## This has to run before harbourmaster is initialised, so we gotta work it out ourself.
    #     theme_name = self.get_current_theme()

    #     self.resources.add_path(PYLIB_PATH / 'resources')
    #     self.resources.add_path(self.get_theme_dir(theme_name))

    def get_config(self):
        cfg_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster"
        cfg_file = cfg_dir / "config" / "config.json"
        cfg_data = {}

        if self.hm is None:
            if cfg_file.is_file():
                cfg_data = harbourmaster.json_load_dict(cfg_file)
        else:
            cfg_data = self.hm.cfg_data

        return cfg_data

    def save_config(self, cfg_data):
        cfg_dir = harbourmaster.HM_TOOLS_DIR / "PortMaster"
        cfg_file = cfg_dir / "config" / "config.json"

        if self.hm is None:
            with open(cfg_file, 'w') as fh:
                json.dump(cfg_data, fh, indent=4)

        else:
            self.hm.save_config()

    ## Loop stuff.
    def apply_button_mapping(self):
        """
        The platform's button layout: which physical button is A (xbox fix), and
        whether the button bar shows A/B swapped. Needs self.hm.
        """
        if self.hm is None:
            return

        platform = self.hm.platform

        if platform.WANT_XBOX_FIX:
            self.events.fix_xbox_mode()

        if self.hm.platform_name in ('retrodeck', ):
            self.events.fix_retrodeck_mode()

        self.SWAP_BUTTONS = platform.WANT_SWAP_BUTTONS

        logger.info(f"Buttons: {platform.__class__.__name__}, xbox fix: {platform.WANT_XBOX_FIX}, swap labels: {platform.WANT_SWAP_BUTTONS}")

    def run(self):
        self.apply_button_mapping()

        try:
            while True:
                self.do_loop()

        except harbourmaster.CancelEvent:
            pass

    def do_loop(self, *, no_delay=False):
        frame_start = sdl2.SDL_GetTicks()

        if self.perf.enabled:
            self.perf.frame(
                '/'.join(layer[0] for layer in self.scenes) +
                (' (callback)' if self.in_callback_loop else ''))

        events = self.events
        events.handle_events()

        if events.buttons['START'] and self.events.buttons['BACK']:
            events.running = False

        if events.was_pressed('SCRN') or (events.buttons['BACK'] and events.was_pressed('Y')):
            self.create_screenshot()

        if not events.running:
            self.do_cancel()

        self.do_update()
        self.do_draw()

        ## Sleep for whatever is left of this frame.
        if not no_delay:
            frame_left = self.FRAME_TIME - (sdl2.SDL_GetTicks() - frame_start)
            if frame_left > 0:
                sdl2.SDL_Delay(frame_left)

        if self.timers.elapsed('updates_per_second', 1000, run_first=True):
            if PORTMASTER_DEBUG:
                print(f"UPS: {self.draw_counter} / {self.update_counter}")

            ## Unload extra images.
            self.images._clean()

            self.update_counter = 0
            self.draw_counter = 0
            self.updated = True

    def do_update(self):
        # Run anything worker threads have handed to the main thread.
        self.dispatcher.drain()

        # Update tags
        if self.timers.elapsed('text_data_update', self.TEXT_DATA_FREQ, run_first=True):
            self.set_data("system.time_24hr", datetime.datetime.now().strftime("%H:%M"))
            self.set_data("system.time_12hr", datetime.datetime.now().strftime("%I:%M %p"))

            if harbourmaster.HM_PORTS_DIR.is_dir():
                disk_usage = shutil.disk_usage(str(harbourmaster.HM_PORTS_DIR))

                self.set_data("system.free_space", harbourmaster.nice_size(disk_usage.free))
                self.set_data("system.used_space", harbourmaster.nice_size(disk_usage.used))
                self.set_data("system.total_space", harbourmaster.nice_size(disk_usage.total))
            else:
                self.set_data("system.free_space", "000 B")
                self.set_data("system.used_space", "000 B")
                self.set_data("system.total_space", "000 B")

            level = battery_level()
            if level is not None:
                self.set_data("system.battery_level", f"{level}%")
            else:
                self.set_data("system.battery_level", _("N/A"))

        # Animations.
        self.animations.update_animations()

        # Events get handled in reversed order.
        # While a task is running only the messages / message box layers get input,
        # anything else could touch self.hm while the worker is using it.
        if self.task is None or self.scenes[-1][0] in self.TASK_INPUT_LAYERS:
            for scene in reversed(self.scenes[-1][1]):
                if scene.do_update(self.events):
                    break

        ## Check for any keys changed in our template system.
        if self.task is not None:
            ## Only the top layer is updated during a task, the rest catch up afterwards.
            if len(self.changed_keys):
                for scene in self.scenes[-1][1]:
                    scene.update_data(self.changed_keys)

                self.deferred_keys.update(self.changed_keys)
                self.changed_keys.clear()

        else:
            if len(self.deferred_keys):
                self.changed_keys.update(self.deferred_keys)
                self.deferred_keys.clear()

            if len(self.changed_keys):
                for layer in self.scenes:
                    for scene in layer[1]:
                        scene.update_data(self.changed_keys)

                self.changed_keys.clear()

        self.update_counter += 1

    def do_draw(self):
        if not self.in_screenshot:
            if not self.updated:
                return

            ## While a task runs, only draw its own window (messages / message box). Redrawing the
            ## scene underneath just flashes it up, eg: the empty first scene over the splash
            ## screen while PortMaster checks for updates and loads its sources.
            if self.task is not None and self.scenes[-1][0] not in self.TASK_INPUT_LAYERS:
                return

            if not self.timers.elapsed('maximum_draw', 20, run_first=True):
                return

            if self.draw_counter > 30:
                return

        # Drawing happens in forwards order
        self.renderer.clear()

        for scene in self.scenes[-1][1]:
            scene.do_draw()

        if not self.in_screenshot:
            self.renderer.present()
            self.updated = False
            self.draw_counter += 1

        self.clean()

    def create_screenshot(self, file_name='screenshot.png'):
        """
        Creates a screenshot and saves it to file_name (screenshot.png)
        """
        # Create a texture to render onto
        self.in_screenshot = True
        render_info = sdl2.SDL_RendererInfo()
        sdl2.SDL_GetRendererInfo(self.renderer.sdlrenderer, render_info)
        renderer_format = render_info.texture_formats[0]

        texture = sdl2.SDL_CreateTexture(
            self.renderer.sdlrenderer,
            renderer_format,
            sdl2.SDL_TEXTUREACCESS_TARGET,
            self.renderer.logical_size[0],
            self.renderer.logical_size[1])

        # Set the texture as the rendering target
        sdl2.SDL_SetRenderTarget(self.renderer.sdlrenderer, texture)

        # Draw the GUI
        self.do_draw()

        # Capture screenshot, from the texture: read before the target goes back to the window.
        width, height = ctypes.c_int(0), ctypes.c_int(0)
        sdl2.SDL_QueryTexture(texture, None, None, ctypes.byref(width), ctypes.byref(height))
        pixels = (ctypes.c_uint8 * (width.value * height.value * 4))()
        sdl2.SDL_RenderReadPixels(
            self.renderer.sdlrenderer,
            None,
            sdl2.SDL_PIXELFORMAT_ABGR8888,
            pixels,
            width.value * 4)

        # Reset the rendering target to the default (the window)
        sdl2.SDL_SetRenderTarget(self.renderer.sdlrenderer, None)

        # Save the screenshot using pypng
        with open(file_name, 'wb') as f:
            writer = png.Writer(width=width.value, height=height.value, greyscale=False, alpha=True)
            writer.write_array(f, pixels)

        # Clean up
        sdl2.SDL_DestroyTexture(texture)
        self.in_screenshot = False

    def set_data(self, key, value):
        if self.text_data.get(key, None) == value:
            return

        self.text_data[key] = value
        self.changed_keys.add(key)
        # logger.debug(f"{key}: {value}")

    def get_data(self, key):
        return self.text_data.get(key, None)

    def format_data(self, input_string, used_keys=None):
        return self.formatter.format_string(input_string, used_keys)

    def reload_theme(self, then=()):
        """
        Loads the theme again, the one in the config (or force_theme) with its colour
        scheme, so a new theme, scheme or language applies without a restart. Everything
        the old theme loaded is dropped first. The screens were made from the old theme:
        this makes a new main menu, then pushes then's (layer name, scene class) on it.
        """
        logger.info("Reloading the theme")
        self.sounds.unload_all()
        self.images.unload_all()
        self.text.unload_all()
        self.animations.clear()
        self.pallet.clear()
        self.override.clear()
        self.default_rects = sdl.NamedRects([0, 0, *self.renderer.logical_size])

        ## The theme's folder first, then PortMaster's own resources, as at start.
        self.resources.remove_path(self.theme_dir)
        self.resources.remove_path(PYLIB_PATH / 'resources')
        self.theme_data = self.themes.gui_init()
        self.theme_dir = self.themes.get_theme_dir(self.themes.get_current_theme())
        self.resources.add_path(PYLIB_PATH / 'resources')

        for scene in self.all_scenes():
            scene.scene_deactivate()

        self.message_box_scene = None
        self.scenes = [('root', [MainMenuScene(self)])]
        self.scenes[-1][1][-1].scene_activate()
        for name, scene_class in then:
            self.push_scene(name, scene_class(self))

        self.updated = True

    def reload_language(self, language, then=()):
        """
        Use another language now (None for the system's): its translations, the theme's
        font for it ("font[ja_JP]" & co, matched as a capability), and new screens, as
        reload_theme().
        """
        old_lang = lang.CURRENT_LANG
        new_lang = lang.set_language(language)

        capabilities = harbourmaster.device_info()['capabilities']
        if old_lang in capabilities:
            capabilities.remove(old_lang)
        capabilities.append(new_lang)

        self.set_data('system.ip_address', get_ip_address() or _("Unknown IP"))
        self.lang_list = lang_list()
        self.reload_theme(then)

    def quit(self):
        # Clean up. Anything SDL owns has to be destroyed before SDL_Quit, otherwise the
        # garbage collector frees it afterwards, which segfaults on some drivers (muOS/Mali).
        self.dir_scanner.shutdown()
        self.images.disable_async()

        for texture in list(self.images.textures.values()):
            texture.destroy()

        ## Any texture still referenced becomes a no-op once its renderer is gone.
        self.renderer.destroy()
        if self.window is not None:
            self.window.close()

        else:
            sdl2.SDL_FreeSurface(self.surface)

        sdl2.ext.quit()

    ## Scene code.
    def scene_list(self):
        return [
            scene[0]
            for scene in self.scenes]

    def all_scenes(self):
        for layer, scenes in self.scenes:
            yield from scenes

    def push_scene(self, name, scene):
        """
        Add a scene, if the name is the same as the current layer it is added to it.
        """
        if name is None:
            name = self.scenes[-1][0]

        for old_scene in self.all_scenes():
            if old_scene.active:
                # print(f"DEACTIVATE {scene}")
                old_scene.scene_deactivate()

        if name == self.scenes[-1][0]:
            logger.debug(f"PUSH SCENE ADD {name}")
            self.scenes[-1][1].append(scene)
            logger.debug(f"SCENE LIST: {self.scene_list()}")

        else:
            logger.debug(f"PUSH SCENE LAYER {name}")
            self.scenes.append((name, [scene]))

            logger.debug(f"SCENE LIST: {self.scene_list()}")

        # print(f"ACTIVATE {scene}")
        scene.scene_activate()
        self.updated = True

    def pop_scene(self, name=None):
        """
        Remove a single scene, or remove until we get back to scene named "name".
        """
        if name is None:
            # If name is none, just pop the most top scene.
            if len(self.scenes[-1][1]) > 1:
                logger.debug(f"POP SCENE REM {self.scenes[-1][0]}")

                self.scenes[-1][1].pop(-1)

                logger.debug(f"SCENE LIST: {self.scene_list()}")

                self.updated = True

            elif len(self.scenes) > 1:
                logger.debug(f"POP SCENE LAYER {self.scenes[-1][0]}")
                self.scenes.pop(-1)

                logger.debug(f"SCENE LIST: {self.scene_list()}")

                self.updated = True

        elif name == self.scenes[-1][0]:
            # If name is the active, scene, just remove a single scene layer from it.
            logger.debug(f"POP SCENE {name} REM {self.scenes[-1][0]}")
            if len(self.scenes[-1][1]) > 1:
                self.scenes[-1][1].pop(-1)
                self.updated = True

            logger.debug(f"SCENE LIST: {self.scene_list()}")

        else:

            while len(self.scenes) > 1:
                if self.scenes[-1][0] == name:
                    break

                logger.debug(f"POP SCENE {name} LAYER {self.scenes[-1][0]}")

                self.scenes.pop(-1)
                self.updated = True

            logger.debug(f"SCENE LIST: {self.scene_list()}")

        if not self.scenes[-1][1][-1].active:
            # print(f"ACTIVATE {self.scenes[-1][1][-1]}")
            self.scenes[-1][1][-1].scene_activate()
            self.updated = True
