# SPDX-License-Identifier: MIT
#
# Language selection.

import os
import harbourmaster
from gettext import gettext as _
from .base import BaseScene


class LanguageScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Language Select")

        self.load_regions("option_menu", ['option_list', ])

        languages = gui.lang_list
        selected_lang = os.environ['LANG']

        self.tags['option_list'].reset_options()
        for lang_code, lang_name in languages.items():
            if lang_code == selected_lang:
                self.tags['option_list'].add_option((None, ''), _("{lang_name} (Selected)").format(lang_name=lang_name))
            else:
                self.tags['option_list'].add_option(('select-language', lang_code), lang_name)

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

            elif selected_option == 'select-language':
                if self.gui.message_box(_("Do you want to change language?\n\nYou will have to restart for it to take affect."), want_cancel=True):
                    from pugwash import lang
                    if selected_parameter == lang.DEFAULT_LANG:
                        del self.gui.hm.cfg_data['language']

                    else:
                        self.gui.hm.cfg_data['language'] = selected_parameter

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
