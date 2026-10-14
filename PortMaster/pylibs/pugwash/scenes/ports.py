# SPDX-License-Identifier: MIT
#
# Ports lists.

from loguru import logger
from gettext import gettext as _
from .base import BaseScene
from .filters import FiltersScene
from .port_info import PortInfoScene


class PortListBaseScene():
    ## How many ports either side of the selection have their images loaded ahead in a plain list.
    LIST_PRELOAD = 3

    def set_port_images(self):
        ## Grid themes draw each port's image; the grid looks them up only for the tiles on screen.
        if self.tags['ports_list'].list_columns > 1:
            self.tags['ports_list'].list_image = self.port_image

    def port_image(self, index):
        if index >= len(self.port_list):
            return None

        return str(self.gui.get_port_image(self.port_list[index]))

    def update_ports(self):
        if self.gui.hm is None:
            self.all_ports = {}
            self.port_list = []
            self.last_port = 0
            self.tags['ports_list'].selected = 0
            self.tags['ports_list'].list = [
                _('NO PORTS')]

            self.gui.set_port_info(None, {})

            self.gui.set_data("port_info.title", _("** NO PORTS FOUND **"))

            self.gui.set_data("port_info.description", _("Download ports first."))
            self.ready = True
            return

        if not self.ready:
            self.gui.set_data('ports_list.total_ports', str(len(self.gui.hm.list_ports_names_new(self.options['base_filters']))))

        sort_by = self.options['sort_by']
        reverse = False
        if sort_by.endswith('_rev'):
            sort_by = sort_by[:-4]
            reverse = True

        self.all_ports = self.gui.hm.list_ports_new(
            filters=(self.options['base_filters'] + self.options['filters']),
            sort_by=sort_by,
            reverse=reverse)
        self.port_list = list(self.all_ports.keys())

        self.gui.set_data('ports_list.filters', ', '.join(sorted(self.options['filters'])))
        self.gui.set_data('ports_list.filter_ports', str(len(self.port_list)))

        if len(self.port_list) == 0:
            self.gui.set_data('ports_list.position', "0")
            self.tags['ports_list'].list = [
                _('NO PORTS')]

            # if 'port_image' in self.tags:
            #     self.tags['port_image'].image = self.gui.get_port_image("no-image")

            self.gui.set_port_info(None, {})

            self.gui.set_data("port_info.title", _("** NO PORTS FOUND **"))

            if len(self.options['filters']) == 0:
                self.gui.set_data("port_info.description", _("Download ports first."))
            else:
                self.gui.set_data("port_info.description", _("Try removing some filters."))

        else:
            self.tags['ports_list'].list = [
                self.all_ports[port_name]['attr']['title']
                for port_name in self.port_list]

        if self.tags['ports_list'].selected >= len(self.port_list):
            if len(self.port_list) == 0:
                self.tags['ports_list'].selected = 0

            else:
                self.tags['ports_list'].selected = len(self.port_list) - 1

        self.last_port = self.tags['ports_list'].selected + 1
        self.ready = True

    def show_selected_port(self):
        ## Port info for the selected port. Scenes call this as they are made too, so their first
        ## frame doesn't show the port_info.* (screenshot and all) of the port shown before.
        if len(self.port_list) == 0:
            return

        self.last_port = self.tags['ports_list'].selected
        self.gui.set_data('ports_list.position', str(self.last_port + 1))

        if self.tags['ports_list'].list_columns == 1:
            ## Get the neighbours' screenshots decoding before they are scrolled to.
            for offset in range(1, self.LIST_PRELOAD + 1):
                for index in (self.last_port + offset, self.last_port - offset):
                    self.gui.images.load(self.port_image(index % len(self.port_list)))

        port_name = self.port_list[self.last_port]
        self.gui.set_port_info(port_name, self.all_ports[port_name], self.options['mode'] != 'install')

    def try_to_select(self, port_name, port_title):
        ## Try and select a port
        if port_name in self.port_list:
            # We found it
            self.tags['ports_list'].selected = self.port_list.index(port_name)
            self.last_port = self.tags['ports_list'].selected + 1
            return

        ## Okay find a port with a name greater than ours, and then select the one before it.
        for i in range(len(self.port_list)):
            if self.all_ports[self.port_list[i]]['attr']['title'] > port_title:
                self.tags['ports_list'].selected = max(i-1, 0)
                self.last_port = self.tags['ports_list'].selected + 1
                return

        ## Do nothing.

    def selected_port(self):
        if len(self.port_list) == 0:
            return 0

        self.last_port = self.tags['ports_list'].selected
        return self.port_list[self.last_port]

    def select_next_port(self):
        if len(self.port_list) == 0:
            return

        self.last_port = self.tags['ports_list'].selected = (self.last_port + 1) % len(self.port_list)

        port_name = self.port_list[self.last_port]
        port_info = self.all_ports[port_name]

        self.gui.set_port_info(port_name, port_info, self.options['mode'] != 'install')

        return port_name

    def select_prev_port(self):
        if len(self.port_list) == 0:
            return

        self.last_port = self.tags['ports_list'].selected = (self.last_port - 1) % len(self.port_list)

        port_name = self.port_list[self.last_port]
        port_info = self.all_ports[port_name]

        self.gui.set_port_info(port_name, port_info, self.options['mode'] != 'install')

        return port_name

    def do_update(self, events):
        super().do_update(events)
        if not self.ready:
            self.update_ports()
            if not self.ready:
                return True

        if len(self.port_list) > 0 and self.last_port != self.tags['ports_list'].selected:
            self.show_selected_port()

        if self.options['mode'] in ('install', 'uninstall') and events.was_pressed('X'):
            self.button_activate()

            if len(self.port_list) > 0 or len(self.options['filters']) > 0:
                self.gui.push_scene('ports', FiltersScene(self.gui, self))

            return True

        if events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True

        if events.was_pressed('A') and len(self.port_list) > 0:
            self.button_activate()
            self.last_port = self.tags['ports_list'].selected
            port_name = self.port_list[self.last_port]

            logger.debug(f"{self.options['mode']}: {port_name}")
            if self.options['mode'] == 'featured-ports':
                # self.ready = False
                self.gui.push_scene('port_info', PortInfoScene(self.gui, port_name, 'install', self))

            elif self.options['mode'] == 'install':
                self.ready = False
                self.gui.push_scene('port_info', PortInfoScene(self.gui, port_name, 'install', self))

            elif self.options['mode'] == 'uninstall':
                self.ready = False
                self.gui.push_scene('port_info', PortInfoScene(self.gui, port_name, 'uninstall', self))

            return True


class FeaturedPortsScene(PortListBaseScene, BaseScene):
    def __init__(self, gui, options):
        super().__init__(gui)
        self.scene_title = options['name']

        self.load_regions("featured_ports", [
            'ports_list',
            ])

        self.options = {
            'mode': 'featured-ports',
            'filters': [],
            'base_filters': [],
            'skip_genres': [],
            }

        self.options.update(**options)

        self.all_ports = options['ports']
        self.port_list = list(options['ports'].keys())

        self.gui.set_data('featured_ports.name', options['name'])
        self.gui.set_data('featured_ports.description', options['description'])
        self.gui.set_data('featured_ports.image', str(options['image']))
        self.gui.set_data('ports_list.total_ports', str(len(self.port_list)))
        self.gui.set_data('ports_list.filter_ports', str(len(self.port_list)))
        self.gui.set_data('ports_list.filters', "")

        self.ready = True
        self.tags['ports_list'].list = [
            self.all_ports[port_name]['attr']['title']
            for port_name in self.port_list]
        self.set_port_images()
        self.show_selected_port()

        self.set_buttons({'A': _('Show Info'), 'B': _('Back')})

class PortsListScene(PortListBaseScene, BaseScene):
    def __init__(self, gui, options):
        super().__init__(gui)
        self.scene_title = options.get('name') or _("Ports List")

        self.options = options
        self.options.setdefault('base_filters', [])
        self.options.setdefault('filters', [])
        self.options.setdefault('sort_by', 'alphabetical')
        self.options.setdefault('skip_genres', [])

        if self.options['mode'] == 'install':
            self.options['skip_genres'].append('broken')

        self.load_regions("ports_list", [
            'ports_list',
            ])
        self.set_port_images()

        self.ready = False
        self.update_ports()
        self.show_selected_port()

        if self.options['mode'] == 'install':
            self.set_buttons({'A': _('Show Info'), 'B': _('Back'), 'X': _('Filters')})
        else:
            self.set_buttons({'A': _('Show Info'), 'B': _('Back')})
