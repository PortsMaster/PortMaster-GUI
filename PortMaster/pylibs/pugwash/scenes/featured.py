# SPDX-License-Identifier: MIT
#
# Featured ports navigation.

from gettext import gettext as _
from .base import BaseScene
from .ports import FeaturedPortsScene


class FeaturedPortsNavigationScene(BaseScene):
    def __init__(self, gui, items=None, breadcrumb=""):
        super().__init__(gui)

        # If no items provided, we're at the root level
        if items is None:
            items = self.gui.hm.featured_ports(pre_load=True)
            self.scene_title = _("Featured Ports")
        else:
            self.scene_title = breadcrumb if breadcrumb else _("Featured Ports")

        self.load_regions("featured_ports_list", ['option_list', ])
        self.items = items
        self.breadcrumb = breadcrumb

        self.tags['option_list'].reset_options()

        for idx, item in enumerate(self.items):
            self.tags['option_list'].add_option(idx, item['name'])

        self.set_buttons({'A': _('Select'), 'B': _('Back')})
        self.update_selection()

    def update_selection(self):
        if len(self.items) == 0:
            return

        selected = self.tags['option_list'].selected_option()
        item = self.items[selected]
        self.gui.set_data('featured_ports.name', item['name'])
        self.gui.set_data('featured_ports.description', item['description'])
        self.gui.set_data('featured_ports.image', str(item['image']))
        self.last_select = selected

    def do_update(self, events):
        super().do_update(events)
        if len(self.items) == 0:
            self.gui.message_box(_("No featured ports found, internet connection is required."))
            self.gui.pop_scene()
            return True

        selected = self.tags['option_list'].selected_option()

        if self.last_select != selected:
            self.update_selection()

        if events.was_pressed('A'):
            self.button_activate()
            item = self.items[selected]

            if item['type'] == 'category':
                # Navigate deeper into the submenu
                new_breadcrumb = f"{self.breadcrumb} > {item['name']}" if self.breadcrumb else item['name']
                self.gui.push_scene('featured-ports-nav', FeaturedPortsNavigationScene(
                    self.gui, item['children'], new_breadcrumb))
            else:  # item['type'] == 'ports'
                # Show the ports list
                self.gui.push_scene('port-list', FeaturedPortsScene(self.gui, item))

            return True

        elif events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True


# Keep the old class name for backward compatibility
class FeaturedPortsListScene(FeaturedPortsNavigationScene):
    def __init__(self, gui):
        super().__init__(gui)
