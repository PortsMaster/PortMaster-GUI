# SPDX-License-Identifier: MIT
#
# Language selection.

from harbourmaster.i18n import _
from pugwash import lang
from .base import BaseScene


class LanguageScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Language Select")

        self.load_regions("option_menu", ['option_list', ])

        languages = lang.lang_list()
        selected_lang = lang.CURRENT_LANG

        self.tags['option_list'].reset_options()
        for index, (lang_code, lang_name) in enumerate(languages.items()):
            if lang_code == selected_lang:
                self.tags['option_list'].add_option((None, ''), _("{lang_name} (Selected)").format(lang_name=lang_name))
                self.tags['option_list'].list_select(index)
            else:
                self.tags['option_list'].add_option(('select-language', lang_code), lang_name)

        self.tags['option_list'].add_option(None, "")
        self.tags['option_list'].add_option(('back', None), _("Back"))
        self.set_buttons({'A': _('Select'), 'B': _('Back')})

    def do_update(self, events):
        super().do_update(events)

        if events.was_pressed('A'):
            selected = self.tags['option_list'].selected_option()
            if not isinstance(selected, tuple):
                ## The blank row (the d-pad skips it, a theme's list might not).
                return True

            selected_option, selected_parameter = selected

            self.button_activate()

            # print(f"Selected {selected_option} -> {selected_parameter}")

            if selected_option == 'back':
                self.gui.pop_scene()
                return True

            elif selected_option == 'select-language':
                ## Applies straight away, back in this list.
                from .options import OptionScene
                if selected_parameter == lang.DEFAULT_LANG:
                    self.gui.hm.cfg_data.pop('language', None)

                else:
                    self.gui.hm.cfg_data['language'] = selected_parameter

                self.gui.hm.save_config()
                self.gui.reload_language(selected_parameter, then=[('option', OptionScene), ('select-language', LanguageScene)])
                return True

        elif events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True
