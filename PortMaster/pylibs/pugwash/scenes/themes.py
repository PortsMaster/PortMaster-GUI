# SPDX-License-Identifier: MIT
#
# Theme and colour scheme selection.

import harbourmaster
from gettext import gettext as _
from .base import BaseScene


class ThemesScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Select Theme")

        self.load_regions("themes_list", ['themes_list', ])

        if self.gui.theme_downloader is None:
            from pugwash import theme
            with self.gui.enable_cancellable(False):
                with self.gui.enable_messages():
                    self.gui.theme_downloader = self.gui.run_task(theme.ThemeDownloader, self.gui, self.gui.themes)

        self.themes = self.gui.themes.get_themes_list(
            self.gui.theme_downloader.get_theme_list())

        selected_theme = self.gui.hm.cfg_data['theme']

        self.tags['themes_list'].reset_options()
        for theme_name, theme_data in self.themes.items():
            if theme_name == selected_theme:
                self.tags['themes_list'].add_option(theme_name, _("{theme_name} (Selected)").format(theme_name=theme_data['name']))

            else:
                self.tags['themes_list'].add_option(theme_name, theme_data['name'])

        self.last_select = self.tags['themes_list'].selected_option()
        self.update_selection()

    def update_selection(self):
        theme_info = self.themes[self.last_select]
        self.gui.set_theme_info(self.last_select, theme_info)

        keys = {}
        if theme_info['status'] in ("Installed", "Update Available"):
            keys['A'] = _('Select')

        keys['B'] = _('Back')

        if theme_info['url'] is not None:
            keys['X'] = _('Download')

        self.set_buttons(keys)

    def do_update(self, events):
        super().do_update(events)

        if self.tags['themes_list'].selected_option() != self.last_select:
            self.last_select = self.tags['themes_list'].selected_option()
            self.update_selection()

        if events.was_pressed('A'):
            theme_info = self.themes[self.last_select]

            if theme_info['status'] not in ("Installed", "Update Available"):
                return True

            self.button_activate()

            if self.gui.message_box(_("Do you want to change theme?\n\nYou will have to restart for it to take effect."), want_cancel=True):
                self.gui.hm.cfg_data['theme'] = self.last_select
                self.gui.hm.cfg_data['theme-scheme'] = None
                self.gui.hm.save_config()
                self.gui.events.running = False

                if not harbourmaster.HM_TESTING:
                    reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                    if not reboot_file.is_file():
                        reboot_file.touch(0o644)

                return True

        if events.was_pressed('X'):
            theme_info = self.themes[self.last_select]

            if theme_info['url'] is None:
                return True

            self.button_activate()

            with self.gui.enable_cancellable(True):
                with self.gui.enable_messages():
                    self.gui.do_install(theme_info['name'], theme_info['url'] + ".md5")

                    self.themes = self.gui.themes.get_themes_list(
                        self.gui.theme_downloader.get_theme_list())

                    self.update_selection()

            return True

        elif events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True


class ThemeSchemeScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Select Colour Scheme")

        self.load_regions("option_menu", ['option_list', ])

        theme_name = self.gui.themes.get_current_theme()
        schemes = self.gui.themes.get_theme_schemes_list()

        default_scheme = self.gui.themes.get_theme(theme_name).theme_data.get("#info", {}).get("default-scheme", None)
        selected_scheme = self.gui.hm.cfg_data.get('theme-scheme', default_scheme)

        self.tags['option_list'].reset_options()
        for scheme_name in schemes:
            if selected_scheme is None or scheme_name == selected_scheme:
                selected_scheme = scheme_name
                self.tags['option_list'].add_option((None, ''), _("{item_name} (Selected)").format(item_name=scheme_name))
            else:
                self.tags['option_list'].add_option(('select-scheme', scheme_name), scheme_name)

        self.tags['option_list'].add_option(None, "")
        self.tags['option_list'].add_option(('back', None), _("Back"))
        self.set_buttons({'A': _('Select'), 'B': _('Back')})

    def do_update(self, events):
        super().do_update(events)

        if events.was_pressed('A'):
            selected_option, selected_parameter = self.tags['option_list'].selected_option()

            self.button_activate()

            # print(f"Selected {selected_option} -> {selected_parameter}")

            if selected_option == 'back':
                self.gui.pop_scene()
                return True

            elif selected_option == 'select-scheme':
                if self.gui.message_box(_("Do you want to change the themes color scheme?\n\nYou will have to restart for it to take affect."), want_cancel=True):
                    self.gui.hm.cfg_data['theme-scheme'] = selected_parameter
                    self.gui.hm.save_config()
                    self.gui.events.running = False

                    if not harbourmaster.HM_TESTING:
                        reboot_file = (harbourmaster.HM_TOOLS_DIR / "PortMaster" / ".pugwash-reboot")
                        if not reboot_file.is_file():
                            reboot_file.touch(0o644)

                    return True

        elif events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True
