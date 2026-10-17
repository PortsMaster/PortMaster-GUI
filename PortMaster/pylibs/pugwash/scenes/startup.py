# SPDX-License-Identifier: MIT
#
# First screens: TempMenuScene, the disclaimer and startup warnings.

import harbourmaster
from pathlib import Path
from gettext import gettext as _
from .base import BaseScene
from .main_menu import MainMenuScene


def get_startup_warnings(device_info):
    """
    Check for unsupported configurations that should warn the user.

    Returns a list of (keyword, reason, suggestion) tuples describing each problem.
    """
    warnings = []

    firmware_suggestion = _('For the best experience, switch to a supported firmware such as muOS or KNULLI.')

    # Unsupported firmware checks, most-specific first
    if Path('/mnt/SDCARD/spruce/').exists():
        warnings.append(('spruce', _('SpruceOS is not supported by PortMaster.'), firmware_suggestion))

    try:
        if 'CrossMix-OS' in Path('/mnt/SDCARD/autorun.inf').read_text():
            warnings.append(('crossmix', _('CrossMix-OS is not supported by PortMaster.'), firmware_suggestion))
    except (OSError, UnicodeDecodeError):
        pass

    try:
        if 'NextUI' in Path('/mnt/SDCARD/.system/version.txt').read_text():
            warnings.append(('nextui', _('NextUI is not supported by PortMaster.'), firmware_suggestion))
    except (OSError, UnicodeDecodeError):
        pass

    # TODO: add a check for PakUI when we have a unique marker

    # Generic catch-all for TrimUI-based OSes we can't identify specifically
    if not warnings and Path('/etc/trimui_device.txt').exists():
        warnings.append(('trimui', _('Your OS is not supported by PortMaster.'), firmware_suggestion))

    # Low RAM check
    if device_info.get('ram', 1024) < 1024:
        warnings.append(('lowram', _('Your device has less than 1GB of RAM.'), None))

    return warnings


def get_next_warning_time():
    """
    Returns an ISO date string for when to show the warning again.
    """
    import random
    import datetime

    next_warning = datetime.datetime.now() + datetime.timedelta(days=random.choice([5, 7, 11, 13]))
    return next_warning.date().isoformat()


class TempMenuScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Main Menu")

        self.load_regions("main_menu", ['option_list'])
        self.set_buttons({})

    def do_update(self, events):
        import datetime

        self.scene_deactivate()
        self.gui.updated = True

        cfg_data = self.gui.get_config()

        if not cfg_data.get('disclaimer', False):
            self.gui.scenes = [
                ('root', [DisclaimerScene(self.gui)]),
                ]

        else:
            warnings = get_startup_warnings(harbourmaster.device_info())
            warning_time = cfg_data.get('warning_time', '')

            if warnings and warning_time < datetime.datetime.now().date().isoformat():
                self.gui.scenes = [
                    ('root', [StartupWarningScene(self.gui, warnings)]),
                    ]
            else:
                self.gui.scenes = [
                    ('root', [MainMenuScene(self.gui)]),
                    ]

        return True


class DisclaimerScene(BaseScene):

    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Disclaimer")

        ## Wait x seconds.
        self.disclaimer_wait = 15

        self.load_regions("disclaimer", ['disclaimer_text'])

        self.tags['disclaimer_text'].text = (
            "Disclaimer\n"
            "\n"
            "PortMaster does not endorse or support any form of piracy. All ready-to-run ports included in our software are provided with full respect to the wishes and licenses of the respective copyright holders. We take intellectual property rights very seriously and ensure that our offerings comply with all relevant legal requirements and permissions.\n"
            "\n"
            "It is important to note that game files for ports that are not ready-to-run must be obtained legally. Users are required to purchase or otherwise acquire these games through legitimate means to include support for them in PortMaster. By using our software, you agree to abide by these terms and respect the rights of content creators and developers."
            )

        self.last_elapsed = None

    def do_draw(self):
        elapsed = self.gui.timers.since('disclaimer_wait') // 1000

        elapsed = min(elapsed, self.disclaimer_wait)

        if elapsed != self.last_elapsed:
            if elapsed < self.disclaimer_wait:
                self.tags['button_bar'].bar = [f'Wait {self.disclaimer_wait - elapsed} seconds']
            else:
                self.set_buttons({'A': _('Accept'), 'B': _('Quit')})

            self.last_elapsed = elapsed

        super().do_draw()

    def do_update(self, events):
        super().do_update(events)

        elapsed = self.gui.timers.since('disclaimer_wait') // 1000

        elapsed = min(elapsed, self.disclaimer_wait)

        if elapsed == self.disclaimer_wait:
            if events.was_pressed('A'):
                cfg_data = self.gui.get_config()
                cfg_data['disclaimer'] = True
                self.gui.save_config(cfg_data)

                self.scene_deactivate()
                self.gui.updated = True

                warnings = get_startup_warnings(harbourmaster.device_info())
                if warnings:
                    self.gui.scenes = [
                        ('root', [StartupWarningScene(self.gui, warnings)]),
                        ]
                else:
                    self.gui.scenes = [
                        ('root', [MainMenuScene(self.gui)]),
                        ]

                return True

            if events.was_pressed('B'):
                self.button_back()
                if self.gui.message_box(
                        _("Are you sure you want to exit PortMaster?"),
                        want_cancel=True):

                    self.gui.do_cancel()
                    return True


class StartupWarningScene(BaseScene):

    def __init__(self, gui, warnings):
        super().__init__(gui)
        self.scene_title = _("Warning")

        ## Wait x seconds.
        self.warning_wait = 10

        self.load_regions("disclaimer", ['disclaimer_text'])

        # Build message from warnings: each reason, then suggestions, then common footer
        parts = []
        suggestions = []
        for keyword, reason, suggestion in warnings:
            parts.append(reason)
            if suggestion is not None and suggestion not in suggestions:
                suggestions.append(suggestion)

        parts.append(_('Many ports will not work.'))

        if suggestions:
            parts.append('')
            parts.extend(suggestions)

        self.tags['disclaimer_text'].text = '\n'.join(parts)
        self.tags['disclaimer_text'].fontsize = int(self.tags['disclaimer_text'].fontsize * 1.5)

        self.last_elapsed = None

    def do_draw(self):
        elapsed = self.gui.timers.since('warning_wait') // 1000

        elapsed = min(elapsed, self.warning_wait)

        if elapsed != self.last_elapsed:
            if elapsed < self.warning_wait:
                self.tags['button_bar'].bar = [f'Wait {self.warning_wait - elapsed} seconds']
            else:
                self.set_buttons({'A': _('I Understand'), 'B': _('Quit')})

            self.last_elapsed = elapsed

        super().do_draw()

    def do_update(self, events):
        super().do_update(events)

        elapsed = self.gui.timers.since('warning_wait') // 1000

        elapsed = min(elapsed, self.warning_wait)

        if elapsed == self.warning_wait:
            if events.was_pressed('A'):
                cfg_data = self.gui.get_config()
                cfg_data['warning_time'] = get_next_warning_time()
                self.gui.save_config(cfg_data)

                self.scene_deactivate()
                self.gui.updated = True
                self.gui.scenes = [
                    ('root', [MainMenuScene(self.gui)]),
                    ]

                return True

            if events.was_pressed('B'):
                self.button_back()
                if self.gui.message_box(
                        _("Are you sure you want to exit PortMaster?"),
                        want_cancel=True):

                    self.gui.do_cancel()
                    return True
