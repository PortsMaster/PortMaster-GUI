# SPDX-License-Identifier: MIT
#
# Port information screens.

from loguru import logger
from gettext import gettext as _
from .base import BaseScene


class PortInfoPopup(BaseScene):
    def __init__(self, gui, parent):
        super().__init__(gui)
        self.scene_title = _("Port Info Popup")
        self.parent_info_scene = parent
        self.load_regions("port_info_popup", [])
        self.update_selection()

    def update_selection(self):
        buttons = {}

        if 'buttons' in self.config:
            for button, action in self.config['buttons'].items():
                if action == 'pop_scene':
                    buttons[button] = _('Hide Info')

        else:
            buttons['DOWN'] = _('Hide Info')

            self.config['buttons'] = {
                'DOWN': 'pop_scene',
                'L_DOWN': 'pop_scene',
                'R_DOWN': 'pop_scene',
                }

        if 'installed' in self.parent_info_scene.port_attrs:
            buttons.update({'A': _('Reinstall'), 'Y': _('Uninstall'), 'B': _('Back')})

        else:
            buttons.update({'A': _('Install'), 'B': _('Back')})

        self.port_name = self.gui.get_data("port_info.name")
        self.set_buttons(buttons)

    def do_update(self, events):
        super().do_update(events)

        if self.port_name != self.gui.get_data("port_info.name"):
            self.update_selection()

        for action in self.config_buttons(events):
            if action == "pop_scene":
                self.parent_info_scene.popup_shown = False
                self.button_back()
                self.gui.pop_scene()
                return True

        return False


class PortInfoScene(BaseScene):
    def __init__(self, gui, port_name, action, port_list_scene):
        super().__init__(gui)
        self.scene_title = _("Port Info")

        self.load_regions("port_info", [])

        self.port_name = port_name
        self.port_list_scene = port_list_scene
        self.popup_shown = False
        self.action = action
        self.ready = False
        self.update_port()

    def update_port(self):
        if self.gui.hm is None:
            return

        self.port_info = self.gui.hm.port_info(self.port_name, installed=(self.action != 'install'))
        if self.port_info is None:
            self.port_info = self.gui.hm.port_info(self.port_name, installed=True)

        self.port_attrs = self.gui.hm.port_info_attrs(self.port_info)

        logger.debug(f"{self.action}: {self.port_name} -> {self.port_attrs} -> {self.port_info}")

        # if 'port_image' in self.tags:
        #     self.tags['port_image'].image = self.gui.get_port_image(self.port_name)

        self.gui.set_port_info(self.port_name, self.port_info)

        buttons = {}

        if 'buttons' in self.config:
            for button, action in self.config['buttons'].items():
                if action == 'port_info_popup' and 'port_info_popup' in self.gui.theme_data:
                    buttons[button] = _('Show Info')

        else:

            if 'port_info_popup' in self.gui.theme_data:
                buttons['UP'] = _('Show Info')

                self.config['buttons'] = {
                    'UP': 'port_info_popup',
                    'L_UP': 'port_info_popup',
                    'R_UP': 'port_info_popup',

                    'LEFT': 'prev_port',
                    'L_LEFT': 'prev_port',
                    'R_LEFT': 'prev_port',

                    'RIGHT': 'next_port',
                    'L_RIGHT': 'next_port',
                    'R_RIGHT': 'next_port',
                    }

            else:
                self.config['buttons'] = {
                    'UP': 'prev_port',
                    'L_UP': 'prev_port',
                    'R_UP': 'prev_port',

                    'DOWN': 'next_port',
                    'L_DOWN': 'next_port',
                    'R_DOWN': 'next_port',
                    }

        if 'installed' in self.port_attrs:
            buttons.update({'A': _('Reinstall'), 'Y': _('Uninstall'), 'B': _('Back')})
        else:
            buttons.update({'A': _('Install'), 'B': _('Back')})

        self.set_buttons(buttons)

        self.ready = True

    def do_update(self, events):
        super().do_update(events)

        if events.was_pressed('A'):
            self.button_activate()
            self.gui.pop_scene()

            # if self.action == 'install':
            self.gui.do_install(self.port_name)

            return True

        if events.was_pressed('Y'):
            if 'installed' in self.port_attrs:
                if self.gui.message_box(_("Are you sure you want to uninstall {port_name}?").format(
                        port_name=self.port_info['attr']['title']), want_cancel=True):

                    self.gui.do_uninstall(self.port_name)
                    self.gui.pop_scene()

        if events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True

        for action in self.config_buttons(events):
            if action == "port_info_popup":
                if 'port_info_popup' in self.gui.theme_data:
                    if self.popup_shown:
                        return True

                    scene = PortInfoPopup(self.gui, self)
                    scene.button_activate()
                    self.popup_shown = True
                    self.gui.push_scene('port_info', scene)
                    return True

            if action == "prev_port":
                self.port_name = self.port_list_scene.select_prev_port()
                self.update_port()
                self.button_activate()
                return True

            if action == "next_port":
                self.port_name = self.port_list_scene.select_next_port()
                self.update_port()
                self.button_activate()
                return True

            else:
                logger.debug(f"Unknown #config.button action: {action}")

        return False
