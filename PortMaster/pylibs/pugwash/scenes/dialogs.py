# SPDX-License-Identifier: MIT
#
# Message window, message box and selection list dialogs.

from harbourmaster.i18n import _
from .base import BaseScene


class MessageWindowScene(BaseScene):
    """
    This is a scrolling window showing messages for downloading/installing/uninstalling/updating.

    It can have an optional progress bar at the bottom.
    """
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Messages")

        self.load_regions("message_window", [
            'message_text'
            ])

        self.cancellable = not self.gui.cancellable
        self.update_buttons()

    def update_buttons(self):
        if self.cancellable == self.gui.cancellable:
            return

        self.cancellable = self.gui.cancellable

        if self.cancellable:
            self.set_buttons({'B': _('Cancel')})
        else:
            self.set_buttons({})

    def do_update(self, events):
        super().do_update(events)
        # sdl2.SDL_Delay(1000)

        self.update_buttons()

        if 'progress_bar' in self.tags:
            if self.gui.callback_amount is not None:
                self.tags['progress_bar'].progress_amount = self.gui.callback_amount
            else:
                self.tags['progress_bar'].progress_amount = 0

        if events.was_pressed('B'):
            if self.gui.cancellable:
                if self.gui.message_box(
                        _('Are you sure you want to cancel?'),
                        want_cancel=True):
                    self.gui.do_cancel()


class MessageBoxScene(BaseScene):
    def __init__(self, gui, message, *, title_text=None, want_cancel=False, ok_text=None, cancel_text=None):
        super().__init__(gui)
        if title_text is not None:
            self.scene_title = _(title_text)

        if ok_text is None:
            ok_text = _("Okay")

        if cancel_text is None:
            cancel_text = _("Cancel")

        self.load_regions("message_box", ['message_text', ])

        self.tags['message_text'].text = message

        buttons = {}
        if want_cancel:
            self.set_buttons({'A': ok_text, 'B': cancel_text})

        else:
            self.set_buttons({'A': ok_text})


class DialogSelectionList(BaseScene):
    def __init__(self, gui, options, register):
        super().__init__(gui)

        self.scene_title = options.get('title', "")

        self.options = options
        self.register = register

        self.gui.set_data("selection_list.title", "")
        self.gui.set_data("selection_list.description", "")
        self.gui.set_data("selection_list.image", "NO_IMAGE")

        scene = ("selection_list"
                + (options.get('want_description', False) and "_description" or "")
                + (options.get('want_images', False) and "_images" or "")
                )

        self.load_regions(scene, [
            'selection_list',
            ])

        self.tags['selection_list'].reset_options()

        for reg_key, reg_values in register.items():
            self.tags['selection_list'].add_option(reg_key, reg_values.get("title", reg_key))

        self.last_selection = None
        self.update_selection()

        ok_text = self.options.get('ok_text') or _("Okay")
        cancel_text = self.options.get('cancel_text') or _("Cancel")

        if self.options.get('want_cancel', False):
            self.set_buttons({'A': ok_text, 'B': cancel_text})
        else:
            self.set_buttons({'A': ok_text})

    def update_selection(self):
        selection = self.tags['selection_list'].selected_option()

        if selection == None:
            self.gui.set_data("selection_list.title", "")
            self.gui.set_data("selection_list.description", "")
            self.gui.set_data("selection_list.image", "NO_IMAGE")

        else:
            self.gui.set_data("selection_list.title", self.register[selection].get("title", ""))
            self.gui.set_data("selection_list.description", self.register[selection].get("description", ""))
            self.gui.set_data("selection_list.image", self.register[selection].get("image", "NO_IMAGE"))

        self.last_selection = selection

    def selected_option(self):
        return self.tags['selection_list'].selected_option()

    def do_update(self, events):
        super().do_update(events)

        if self.last_selection != self.tags['selection_list'].selected_option():
            self.update_selection()

        return True
