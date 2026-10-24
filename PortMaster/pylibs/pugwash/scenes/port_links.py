# SPDX-License-Identifier: MIT
#
# A port's links: its page on the PortMaster website and its stores, each shown as a QR code
# and an address, so it can be opened on a phone. Opened with X from the port info screen.

from harbourmaster.i18n import _
from .base import BaseScene, plain_font


def fallback_section():
    """For themes without a "port_links" section: plain, in PortMaster's own font."""
    text = {"font": plain_font(), "font-color": "#e8e8ec", "font-size": 16}
    return {
        "background": {"area": [0.0, 0.0, 1.0, 1.0], "fill": "#1c1c22"},
        "links_title": {**text, "area": [0.04, 0.02, 0.96, 0.12], "font-size": 24, "align": "center",
                        "text-clip": True, "text": "{port_info.title}"},
        "links_list": {**text, "area": [0.04, 0.15, 0.44, 0.95], "select-fill": "#3c3c48",
                       "select-color": "#ffffff", "text-clip": True},
        "link_qr": {"area": [0.5, 0.15, 0.96, 0.7], "image": "qr:{port_links.url}", "image-mode": "fit"},
        "link_info": {**text, "area": [0.5, 0.72, 0.96, 0.98], "font-size": 14, "text-wrap": True,
                      "align": "center", "text": "{port_links.name}\n{port_links.url}"},
        }


class PortLinksScene(BaseScene):
    def __init__(self, gui, port_name, port_info):
        super().__init__(gui)
        self.scene_title = _("Links")

        self.links = self.gui.get_port_links(port_name, port_info)

        if "port_links" not in self.gui.theme_data:
            self.gui.theme_data["port_links"] = fallback_section()

        self.gui.set_data("port_links.count", str(len(self.links)))
        self.last_select = None
        self.show_link(0)

        self.load_regions("port_links", ['links_list'])

        self.tags['links_list'].reset_options()
        for index, (label, kind, url) in enumerate(self.links):
            self.tags['links_list'].add_option(index, label)

        if len(self.links) == 0:
            self.tags['links_list'].add_option(None, _("No links for this port."))

        self.tags['links_list'].list_select(0)
        self.last_select = self.tags['links_list'].selected_option()

        self.set_buttons({'B': _('Back')})

    def show_link(self, index):
        if index is None or not (0 <= index < len(self.links)):
            label, kind, url = "", "", ""
        else:
            label, kind, url = self.links[index]

        self.gui.set_data("port_links.name", label)
        self.gui.set_data("port_links.kind", kind)
        self.gui.set_data("port_links.url", url)

    def do_update(self, events):
        super().do_update(events)

        if self.tags['links_list'].selected_option() != self.last_select:
            self.last_select = self.tags['links_list'].selected_option()
            self.show_link(self.last_select)

        if events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True

        return False
