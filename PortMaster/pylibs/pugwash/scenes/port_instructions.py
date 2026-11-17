# SPDX-License-Identifier: MIT
#
# A port's installation instructions and description, full screen: Select on the port info
# screen. The text is one region (tagged port_instructions) the player scrolls with up and
# down; B or Select goes back.

from harbourmaster.i18n import _
from .base import BaseScene


def instructions_text(port_info):
    """The instructions first (what someone opening this wants), then the description."""
    attr = (port_info or {}).get('attr', {}) or {}
    parts = []
    instructions = (attr.get('inst') or "").strip()
    description = (attr.get('desc') or "").strip()
    if instructions:
        parts.append(_("Instructions") + "\n" + instructions)
    if description:
        parts.append(_("Description") + "\n" + description)
    return "\n\n".join(parts)


class PortInstructionsScene(BaseScene):
    def __init__(self, gui, port_info):
        super().__init__(gui)
        self.scene_title = _("Instructions")
        ## Before the regions: their text is a template of it.
        self.gui.set_data("port_instructions.text", instructions_text(port_info))
        self.load_regions("port_instructions", ['port_instructions'])
        self.set_buttons({'B': _('Back')})

    def do_update(self, events):
        super().do_update(events)

        if events.was_pressed('B') or self.select_tapped(events):
            self.button_back()
            self.gui.pop_scene()
            return True

        return False
