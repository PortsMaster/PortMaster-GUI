# SPDX-License-Identifier: MIT
#
# The options menu.

import shutil
import subprocess
import harbourmaster
from pathlib import Path
from loguru import logger
from gettext import gettext as _
from .base import BaseScene
from .keyboard import OnScreenKeyboard
from .language import LanguageScene
from .runtimes import RuntimesScene
from .themes import ThemeSchemeScene, ThemesScene


class OptionScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Options Menu")

        self.load_regions("option_menu", ['option_list'])

        self.tags['option_list'].reset_options()

        self.tags['option_list'].add_option(None, _("Interface"))

        self.tags['option_list'].add_option(
            'select-language',
            _("Choose Language"),
            description=_("Select the language PortMaster uses."))
        self.tags['option_list'].add_option(
            'select-theme',
            _("Select Theme"),
            description=_("Select a theme for PortMaster."))

        schemes = self.gui.themes.get_theme_schemes_list()
        if len(schemes) > 1:
            self.tags['option_list'].add_option(
                'select-scheme',
                _("Select Color Scheme"),
            description=_("Select a colour scheme for PortMaster"))

        self.tags['option_list'].add_option(None, _("Audio"))

        self.tags['option_list'].add_option(
            'toggle-music',
            _("Music: ") + (self.gui.sounds.music_is_disabled and _("Disabled") or _("Enabled")),
            description=_("Enable or Disable background music in PortMaster."))
        self.tags['option_list'].add_option(
            'toggle-sfx',
            _("Sound FX: ") + (self.gui.sounds.sound_is_disabled and _("Disabled") or _("Enabled")),
            description=_("Enable or Disable soundfx in PortMaster."))

        if self.gui.hm.platform.gamelist_file() is not None:
            self.tags['option_list'].add_option(None, _("Port Metadata"))

            self.tags['option_list'].add_option(
                'toggle-gamelist',
                _("Metadata Update: ") + (self.gui.hm.cfg_data.get('gamelist_update', True) and _("Auto") or _("Manual")),
                description=_("PortMaster updates metadata when ports are installed so that it shows port images and descriptions when browsing ports on your device."))

            self.tags['option_list'].add_option(
                'update-gamelist',
                _("Metadata Refresh"),
                description=_("Manually update port metadata with missing/updated information and artwork."))

        if self.gui.hm.platform_name == 'trimui':
            self.tags['option_list'].add_option(
                'trimui-port-mode-toggle',
                _("Ports Location: ") +  (self.gui.hm.cfg_data.get('trimui-port-mode', 'roms') == 'roms' and _("Roms section") or _("Ports tab")),
                description=_("Location where ports should be installed to."))

        if self.gui.hm.platform_name == 'muos':
            if '/mnt/sdcard' in subprocess.getoutput(['df']):
                MUOS_MMC_TOGGLE = Path('/mnt/mmc/MUOS/PortMaster/config/muos_mmc_master_race.txt')

                self.tags['option_list'].add_option(
                    'muos-port-mode-toggle',
                    _("Ports Location: ") +  (MUOS_MMC_TOGGLE.is_file() and _("SD 1") or _("SD 2")),
                    description=_("Location where ports should be installed to."))

        self.tags['option_list'].add_option(None, _("System"))

        self.tags['option_list'].add_option(
            'runtime-manager',
            _("Runtime Manager"),
            description=_("Manage port runtimes."))

        self.tags['option_list'].add_option(
            'toggle-experimental',
            _("Experimental Ports: ") + (self.gui.hm.cfg_data.get('show_experimental', False) and _("Enabled") or _("Disabled")),
            description=_("Show or hide experimental ports."))

        self.tags['option_list'].add_option(
            'update-ports',
            _("Update Ports"),
            description=_("Fetch latest ports information."))

        self.tags['option_list'].add_option(
            'update-portmaster',
            _("Update PortMaster"),
            description=_("Force check for a new PortMaster version."))

        if self.gui.hm.platform_name not in ('muos', 'trimui'):
            self.tags['option_list'].add_option(
                'restore-portmaster',
                _("Restore PortMaster"),
                description=_("This will restore PortMaster to the latest stable version of PortMaster."))

        self.tags['option_list'].add_option(
            'release-channel',
            _("Release Channel: {channel}").format(
                channel=self.gui.hm.cfg_data.get('release_channel', "stable")),
            description=_("Change release channel of PortMaster, either beta or stable."))

        if self.gui.hm.cfg_data.get('konami', False):
            if self.gui.hm.cfg_data.get('release_channel', 'stable') != 'alpha':
                self.tags['option_list'].add_option(
                    'release-alpha',
                    _("Enable Alpha Releases"),
                    description=_("Change release channel of PortMaster to alpha."))

        if len(self.gui.hm.get_gcd_modes()) > 0:
            gcd_mode = self.gui.hm.get_gcd_mode()
            self.tags['option_list'].add_option(
                'toggle-gcd',
                _("Controller Mode: {controller_mode}").format(controller_mode=gcd_mode),
                description=_("Toggle between various controller layouts."))

        if self.gui.hm.cfg_data.get('konami', False):
            self.tags['option_list'].add_option(None, _("Secret Options"))
            self.tags['option_list'].add_option(
                'toggle-all',
                _("All Ports: ") + (self.gui.hm.cfg_data.get('show_all', False) and _("Enabled") or _("Disabled")),
                description=_("Show all ports, ignoring requirements."))
            self.tags['option_list'].add_option(
                'toggle-cwtbe',
                _("CWTBE Mode: ") + ((self.gui.hm.tools_dir / "PortMaster" / "cwtbe_flag").is_file() and _("Enabled") or _("Disabled")),
                description=_("Enable gptokeyb2 by default."))
            self.tags['option_list'].add_option(
                'toggle-debug',
                _("Debug Mode: ") + ((self.gui.hm.tools_dir / "PortMaster" / "debug_all_the_things_flag").is_file() and _("Enabled") or _("Disabled")),
                description=_("Enable debug logging all the time."))
            self.tags['option_list'].add_option(
                'delete-config',
                _("Delete PortMaster Config"),
                description=_("This can break stuff, don't touch unless you know what you are doing."))
            self.tags['option_list'].add_option(
                'delete-runtimes',
                _("Delete PortMaster Runtimes"),
                description=_("This can break stuff, don't touch unless you know what you are doing."))

        # self.tags['option_list'].add_option(None, "")
        # self.tags['option_list'].add_option('back', _("Back"))
        self.tags['option_list'].list_select(0)
        self.set_buttons({'A': _('Enter'), 'B': _('Back')})
        self.last_selected = None

    def do_update(self, events):
        super().do_update(events)

        if self.last_selected != self.tags['option_list'].selected_option():
            self.set_tooltip(self.tags['option_list'].selected_description())
            self.last_selected = self.tags['option_list'].selected_option()
            self.gui.set_data('menu.selected', self.last_selected)

        if events.was_pressed('A'):
            selected_option = self.tags['option_list'].selected_option()

            self.button_activate()

            # print(f"Selected {selected_option}")

            if selected_option == 'update-ports':
                self.gui.do_update_ports()
                return True

            if selected_option == 'update-portmaster':
                self.gui.hm.cfg_data['update_checked'] = None
                self.gui.hm.save_config()
                self.gui.events.running = False

                if not harbourmaster.HM_TESTING:
                    reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                    if not reboot_file.is_file():
                        reboot_file.touch(0o644)

                return True

            if selected_option == 'toggle-all':
                self.gui.hm.cfg_data['show_all'] = not self.gui.hm.cfg_data.get('show_all', False)
                self.gui.hm.save_config()

                self.gui.hm._port_attrs_updated = True

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("All Ports: ") + (self.gui.hm.cfg_data.get('show_all', False) and _("Enabled") or _("Disabled")))

                return True

            if selected_option == 'toggle-experimental':
                self.gui.hm.cfg_data['show_experimental'] = not self.gui.hm.cfg_data.get('show_experimental', False)
                self.gui.hm.save_config()

                self.gui.hm._port_attrs_updated = True

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("Experimental Ports: ") + (self.gui.hm.cfg_data.get('show_experimental', False) and _("Enabled") or _("Disabled")))

                return True

            if selected_option == 'toggle-cwtbe':
                cwtbe_flag = (self.gui.hm.tools_dir / "PortMaster" / "cwtbe_flag")

                if cwtbe_flag.is_file():
                    cwtbe_flag.unlink()
                else:
                    cwtbe_flag.touch()

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("CWTBE Mode: ") + (cwtbe_flag.is_file() and _("Enabled") or _("Disabled")))

            if selected_option == 'toggle-debug':
                debug_flag = (self.gui.hm.tools_dir / "PortMaster" / "debug_all_the_things_flag")

                if debug_flag.is_file():
                    debug_flag.unlink()
                else:
                    debug_flag.touch()

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("Debug Mode: ") + ((self.gui.hm.tools_dir / "PortMaster" / "debug_all_the_things_flag").is_file() and _("Enabled") or _("Disabled")))

            if selected_option == 'restore-portmaster':
                if not self.gui.message_box(
                        _("Are you sure you want to restore PortMaster?\n\nThis will require you to run a specially crafted port that will be installed."),
                        want_cancel=True):
                    return True

                logger.warning("-- RESTORE PORTMASTER --")
                with self.gui.enable_cancellable(False), self.gui.enable_messages():
                    if self.gui.run_task(self.gui.hm.install_port, "restore.portmaster.zip") != 0:
                        return True

                self.gui.message_box(
                    _("A special port has been installed called \"Restore PortMaster.sh\"\n\nRun this port to restore your PortMaster installation."))

                self.gui.message_box(
                    _("PortMaster will now quit so you can run the restoration port."))

                self.gui.events.running = False
                return True

            if selected_option == 'release-alpha':
                if self.gui.message_box(
                        _("Are you sure you want to change to the alpha release channel?\n\nPortMaster will upgrade or downgrade accordingly.\n\nTHIS CAN AND WILL BREAK STUFF, YOU HAVE BEEN WARNED"),
                        want_cancel=True):

                    self.gui.hm.cfg_data['release_channel'] = 'alpha'
                    self.gui.hm.cfg_data['change_channel'] = True
                    self.gui.hm.cfg_data['update_checked'] = None
                    self.gui.hm.save_config()
                    self.gui.events.running = False

                    if not harbourmaster.HM_TESTING:
                        reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                        if not reboot_file.is_file():
                            reboot_file.touch(0o644)

                return True

            if selected_option == 'release-channel':
                channel_change = {
                    "alpha": "beta",
                    "stable": "beta",
                    "beta": "stable",
                    }

                current_channel = self.gui.hm.cfg_data.get('release_channel', "stable")
                new_channel = channel_change[current_channel]

                if self.gui.message_box(
                        _("Are you sure you want to change the release channel from {current_channel} to {new_channel}?\n\nPortMaster will upgrade or downgrade accordingly.").format(
                            current_channel=current_channel,
                            new_channel=new_channel,
                            ),
                        want_cancel=True):

                    self.gui.hm.cfg_data['release_channel'] = new_channel
                    self.gui.hm.cfg_data['change_channel'] = True
                    self.gui.hm.cfg_data['update_checked'] = None
                    self.gui.hm.save_config()
                    self.gui.events.running = False

                    if not harbourmaster.HM_TESTING:
                        reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                        if not reboot_file.is_file():
                            reboot_file.touch(0o644)

                return True

            if selected_option == 'toggle-music':
                self.gui.hm.cfg_data['music-disabled'] = self.gui.sounds.music_is_disabled = not self.gui.sounds.music_is_disabled
                self.gui.hm.save_config()

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("Music: ") + (self.gui.sounds.music_is_disabled and _("Disabled") or _("Enabled")))
                return True

            if selected_option == 'toggle-sfx':
                self.gui.hm.cfg_data['sfx-disabled'] = self.gui.sounds.sound_is_disabled = not self.gui.sounds.sound_is_disabled
                self.gui.hm.save_config()

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("Sound FX: ") + (self.gui.sounds.sound_is_disabled and _("Disabled") or _("Enabled")))
                return True

            if selected_option == 'toggle-gcd':
                gcd_modes = self.gui.hm.get_gcd_modes()
                if len(gcd_modes) == 0:
                    return True

                gcd_mode = self.gui.hm.get_gcd_mode()
                if gcd_mode not in gcd_modes:
                    gcd_mode = gcd_modes[0]
                else:
                    gcd_mode = gcd_modes[(gcd_modes.index(gcd_mode) + 1) % len(gcd_modes)]

                self.gui.hm.set_gcd_mode(gcd_mode)

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("Controller Mode: {controller_mode}").format(controller_mode=gcd_mode))

                return True

            if selected_option == 'toggle-gamelist':
                self.gui.hm.cfg_data['gamelist_update'] = not self.gui.hm.cfg_data.get('gamelist_update', True)
                self.gui.hm.save_config()

                item = self.tags['option_list'].list_selected()
                self.tags['option_list'].list[item] = (
                    _("Metadata Update: ") + (self.gui.hm.cfg_data.get('gamelist_update', True) and _("Auto") or _("Manual")))

                return True

            if selected_option == 'update-gamelist':
                if self.gui.message_box(
                        _("Are you sure you want to update your gamelist.xml?\n\nThis will override any scraped artwork or port information and will require a 50+ MB download."),
                        want_cancel=True):

                    self.gui.update_gamelist_xml()

                return True

            if selected_option == 'trimui-port-mode-toggle':
                language_map = {
                    'roms':  _('Roms section'),
                    'ports': _('Ports tab'),
                    }

                change_map = {
                    'roms':  'ports',
                    'ports': 'roms',
                    }

                from_mode = self.gui.hm.cfg_data.get('trimui-port-mode', 'roms')
                to_mode = change_map[from_mode]
                if self.gui.message_box(
                        _("Are you sure you want to move ports from the {from_mode} to the {to_mode}").format(
                            from_mode=language_map[from_mode],
                            to_mode=language_map[to_mode]),
                        want_cancel=True):

                    self.gui.hm.cfg_data['trimui-port-mode'] = to_mode
                    self.gui.hm.save_config()

                    item = self.tags['option_list'].list_selected()
                    self.tags['option_list'].list[item] = (
                        _("Ports Location: ") +  language_map[to_mode])

                    self.gui.hm.platform.do_move_ports()

            if selected_option == 'muos-port-mode-toggle':
                if '/mnt/sdcard' in subprocess.getoutput(['df']):
                    MUOS_MMC_TOGGLE = Path('/mnt/mmc/MUOS/PortMaster/config/muos_mmc_master_race.txt')

                    language_map = {
                        True:  _('SDCARD 1'),
                        False: _('SDCARD 2'),
                        }

                    if self.gui.message_box(
                            _("Are you sure you want to manage and install ports on {to_loc}?\n\nAlready installed ports will not be moved.\nPortMaster will restart for this to take effect.").format(
                                to_loc=language_map[(not MUOS_MMC_TOGGLE.is_file())]),
                            want_cancel=True):

                        self.gui.events.running = False

                        if MUOS_MMC_TOGGLE.is_file():
                            MUOS_MMC_TOGGLE.unlink()

                        else:
                            MUOS_MMC_TOGGLE.touch(0o644)

                        if not harbourmaster.HM_TESTING:
                            reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                            if not reboot_file.is_file():
                                reboot_file.touch(0o644)

                        return True

            if selected_option == 'runtime-manager':
                self.gui.push_scene('runtime-manager', RuntimesScene(self.gui))
                return True

            if selected_option == 'source-manager':
                self.gui.push_scene('source-manager', SourceScene(self.gui))
                return True

            if selected_option == 'keyboard':
                self.gui.push_scene('osk', OnScreenKeyboard(self.gui))
                return True

            if selected_option == 'select-theme':
                self.gui.push_scene('select-theme', ThemesScene(self.gui))
                return True

            if selected_option == 'select-scheme':
                self.gui.push_scene('select-scheme', ThemeSchemeScene(self.gui))
                return True

            if selected_option == 'select-language':
                self.gui.push_scene('select-language', LanguageScene(self.gui))
                return True

            ## Secret options
            if selected_option == 'delete-config':
                self.gui.events.running = False

                shutil.rmtree(harbourmaster.HM_TOOLS_DIR / "PortMaster" / "config")

                if not harbourmaster.HM_TESTING:
                    reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                    if not reboot_file.is_file():
                        reboot_file.touch(0o644)

                return True

            if selected_option == 'delete-runtimes':
                runtimes = list((harbourmaster.HM_TOOLS_DIR / "PortMaster" / "libs").glob("*.squashfs"))
                if len(runtimes) == 0:
                    self.gui.message_box("No runtimes found.")
                    return True

                with self.gui.enable_cancellable(False):
                    with self.gui.enable_messages():
                        self.gui.message(_("Deleting Runtimes:"))
                        self.gui.do_loop()

                        for runtime_file in runtimes:
                            logger.info(f"removing {runtime_file}")
                            self.gui.message(f"- {runtime_file}")
                            runtime_file.unlink()
                            self.gui.do_loop()

                self.gui.message_box(f"Removed {len(runtimes)} runtimes.")
                return True

            if selected_option == 'back':
                self.gui.pop_scene()
                return True

        elif events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True


class SourceScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Source Manager")

        self.load_regions("option_list", ['option_list', ])
