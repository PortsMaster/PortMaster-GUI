# SPDX-License-Identifier: MIT
#
# The on screen keyboard.

from gettext import gettext as _
from .base import BaseScene


class OnScreenKeyboard(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)

        self.load_regions("on_screen_keyboard", ['keyboard'])

        self.mode = 'lower'
        self.build_keyboard()
        self.tags['keyboard'].list_select(2)
        self.tags['keyboard'].bar_select(4, 2)

    def build_keyboard(self, keep=False):
        if keep:
            last_list_select = self.tags['keyboard'].list_selected()
            last_bar_select = self.tags['keyboard'].bar_selected()

        self.tags['keyboard'].reset_options()
        if self.mode == 'lower':
            self.tags['keyboard'].add_option('row-1', [' ` ', ' 1 ', ' 2 ', ' 3 ', ' 4 ', ' 5 ', ' 6 ', ' 7 ', ' 8 ', ' 9 ', ' 0 ', ' - ', ' = '], 0)
            self.tags['keyboard'].add_option('row-2', [' q ', ' w ', ' e ', ' r ', ' t ', ' y ', ' u ','  i ', ' o ', ' p ', ' [ ', ' ] ', ' \\ '], 0)
            self.tags['keyboard'].add_option('row-3', [' a ', ' s ', ' d ', ' f ', ' g ', ' h ', ' j ', ' k ', ' l ', ' ; ', ' \' '], 0)
            self.tags['keyboard'].add_option('row-4', [' z ', ' x ', ' c ', ' v ', ' b ', ' n ', ' m ', ' , ', ' . ', ' / '], 0)
            self.tags['keyboard'].add_option('row-5', [' UPPER ', '    [_____]    ', ' << '], 0)

            self.set_buttons({'A': _('Select'), 'B': _('Delete'), 'X': _('Upper Case'), 'Y': _('Space'), 'START': _('Enter'), 'SELECT': _('Cancel')})
        else:
            self.tags['keyboard'].add_option('row-1', [' ~ ', ' ! ', ' @ ', ' # ', ' $ ', ' % ', ' ^ ', ' & ', ' * ', ' ( ', ' ) ', ' _ ', ' + '], 0)
            self.tags['keyboard'].add_option('row-2', [' Q ', ' W ', ' E ', ' R ', ' T ', ' Y ', ' U ','  I ', ' O ', ' P ', ' { ', ' } ', ' | '], 0)
            self.tags['keyboard'].add_option('row-3', [' A ', ' S ', ' D ', ' F ', ' G ', ' H ', ' J ', ' K ', ' L ', ' : ', ' " '], 0)
            self.tags['keyboard'].add_option('row-4', [' Z ', ' X ', ' C ', ' V ', ' B ', ' N ', ' M ', ' < ', ' > ', ' ? '], 0)
            self.tags['keyboard'].add_option('row-5', [' LOWER ', '    [_____]    ', ' << '], 0)

            self.set_buttons({'A': _('Select'), 'B': _('Delete'), 'X': _('Lower Case'), 'Y': _('Space'), 'START': _('Enter'), 'SELECT': _('Cancel')})

        if keep:
            self.tags['keyboard'].list_select(last_list_select)
            self.tags['keyboard'].bar_select(last_bar_select)

        self.last_select = self.tags['keyboard'].list_selected()

    def do_update(self, events):
        super().do_update(events)

        if self.last_select != self.tags['keyboard'].list_selected():
            item = self.tags['keyboard'].bar_selected(self.last_select)
            self.tags['keyboard'].bar_select(item)
            self.last_select = self.tags['keyboard'].list_selected()

        if events.was_pressed('START') or events.was_pressed('A'):
            selected_option = self.tags['keyboard'].selected_option()
            selected_key = self.tags['keyboard'].bar_selected()

            # print(_("Selected {selected_option}"))

            if selected_option == 'back':
                self.gui.pop_scene()
                return True

            return True

        elif events.was_pressed('B'):
            self.gui.pop_scene()
            return True

        elif events.was_pressed('X'):
            if self.mode == 'upper':
                self.mode = 'lower'
            else:
                self.mode = 'upper'

            self.build_keyboard(keep=True)
