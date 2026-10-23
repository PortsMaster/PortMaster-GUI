# SPDX-License-Identifier: MIT
#
# The main menu.

from gettext import gettext as _
from .base import BaseScene
from .featured import FeaturedPortsNavigationScene
from .options import OptionScene
from .ports import PortsListScene


class MainMenuScene(BaseScene):
    KONAMI_CODE = ('UP', 'UP', 'DOWN', 'DOWN', 'LEFT', 'RIGHT', 'LEFT', 'RIGHT', 'B', 'A', 'START', 'DONE')

    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Main Menu")

        self.option_options = {
            'install': [],
            'install-rtr': ['rtr'],
            'uninstall': ['installed'],
            }

        self.load_regions("main_menu", ['option_list'])

        self.tags['option_list'].reset_options()
        self.tags['option_list'].add_option(
            'featured-ports',
            _('Featured Ports'),
            description=_("Hand curated lists of ports"))
        self.tags['option_list'].add_option(
            'install',
            _("All Ports"),
            description=_("List all ports available on PortMaster."))
        self.tags['option_list'].add_option(
            'install-rtr',
            _("Ready to Run Ports"),
            description=_("List all ports that are ready to play!"))
        self.tags['option_list'].add_option(
            'uninstall',
            _("Manage Ports"),
            description=_("Update / Uninstall Ports"))

        self.tags['option_list'].add_option(None, "")
        self.tags['option_list'].add_option(
            'options',
            _("Options"),
            description=_("PortMaster Options"))
        self.tags['option_list'].add_option(
            'exit',
            _("Exit"),
            description=_("Quit PortMaster"))

        self.set_buttons({'A': _('Enter'), 'B': _('Quit')})
        self.detecting_konami = 0

        self.set_tooltip(self.tags['option_list'].selected_description())
        self.last_selected = self.tags['option_list'].selected_option()
        self.gui.set_data('menu.selected', self.last_selected)

    def scene_activated(self):
        self.gui.set_data('menu.selected', self.last_selected)

    def do_update(self, events):
        super().do_update(events)

        if events.was_pressed(self.KONAMI_CODE[self.detecting_konami]):
            self.detecting_konami += 1

            if self.KONAMI_CODE[self.detecting_konami] == 'DONE':
                self.gui.hm.cfg_data['konami'] = not self.gui.hm.cfg_data.get('konami', False)
                self.gui.hm.save_config()
                self.detecting_konami = 0
                self.gui.message_box(_('Secret Mode {secret_mode}').format(
                    secret_mode=(self.gui.hm.cfg_data['konami'] and _('Enabled') or _('Disabled'))))

                return True

            if self.KONAMI_CODE[self.detecting_konami-1] in ('B', 'A', 'START'):
                return True

        elif events.any_pressed():
            self.detecting_konami = 0

        if self.last_selected != self.tags['option_list'].selected_option():
            self.set_tooltip(self.tags['option_list'].selected_description())
            self.last_selected = self.tags['option_list'].selected_option()
            self.gui.set_data('menu.selected', self.last_selected)

        if events.was_pressed('A'):
            selected_option = self.tags['option_list'].selected_option()
            selected_parameter = self.option_options.get(selected_option, None)
            selected_name = {
                'install': _("All Ports"),
                'install-rtr': _("Ready to Run"),
                'uninstall': _("Manage Ports"),
                }.get(selected_option)

            if selected_option == 'install-rtr':
                selected_option = 'install'

            self.button_activate()

            if selected_option in ('install', 'install-rtr', 'uninstall'):
                self.gui.push_scene('ports', PortsListScene(self.gui, {'mode': selected_option, 'base_filters': selected_parameter, 'name': selected_name}))
                return True

            elif selected_option == 'featured-ports':
                self.gui.push_scene('featured-ports', FeaturedPortsNavigationScene(self.gui))
                return True

            elif selected_option == 'options':
                self.gui.push_scene('option', OptionScene(self.gui))
                return True

            elif selected_option == 'exit':
                self.gui.do_cancel()
                return True

        elif events.was_pressed('B'):
            self.button_back()
            if self.gui.message_box(
                    _("Are you sure you want to exit PortMaster?"),
                    want_cancel=True):

                self.gui.do_cancel()
                return True
