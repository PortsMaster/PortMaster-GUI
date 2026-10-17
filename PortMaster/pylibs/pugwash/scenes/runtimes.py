# SPDX-License-Identifier: MIT
#
# The runtime manager.

import harbourmaster
from gettext import gettext as _
from .base import BaseScene


class RuntimesScene(BaseScene):
    def __init__(self, gui):
        super().__init__(gui)
        self.scene_title = _("Runtime Manager")

        self.load_regions("runtime_list", ['runtime_list', ])
        self.update_runtimes()

    def update_runtimes(self):
        runtimes = []
        self.runtimes_data = {}
        self.runtimes = {}

        all_download_size = 0
        all_installed = True
        primary_arch = self.gui.hm.device['primary_arch']
        for runtime, runtime_data in self.gui.hm.list_runtimes():
            if primary_arch not in runtime_data['remote']:
                continue

            runtimes.append(runtime)
            self.runtimes_data[runtime] = runtime_data
            if not (self.gui.hm.libs_dir / runtime).is_file():
                all_installed = False

            all_download_size += runtime_data["remote"][primary_arch]["size"]

        runtimes.sort(key=lambda name: self.runtimes_data[name]['name'])

        runtimes.append('all')

        self.tags['runtime_list'].reset_options()
        all_installed = True

        for runtime in runtimes:
            if runtime == "all":
                self.runtimes[runtime] = {
                    'name': _("Download All"),
                    'installed': all_installed,
                    'file': None,
                    'ports': [],
                    'download_size': all_download_size,
                    'disk_size': 0,
                    }

                self.tags['runtime_list'].add_option(None, "")

            else:
                self.runtimes[runtime] = {
                    'name': self.runtimes_data[runtime]['name'],
                    'installed': None,
                    'file': (self.gui.hm.libs_dir / runtime),
                    'ports': [],
                    'download_size': self.runtimes_data[runtime]['remote'][primary_arch]['size'],
                    'disk_size': 0,
                    }

                self.runtimes[runtime]['installed'] = self.runtimes[runtime]['file'].is_file()

                if self.runtimes[runtime]['file'].is_file():
                    self.runtimes[runtime]['disk_size'] = self.runtimes[runtime]['file'].stat().st_size

                else:
                    all_installed = False

            self.tags['runtime_list'].add_option(runtime, self.runtimes[runtime]['name'])

        for port_name, port_info in self.gui.hm.list_ports_new(filters=['installed']).items():
            for runtime in port_info['attr']['runtime']:
                if runtime in self.runtimes:
                    self.runtimes[runtime]['ports'].append(port_info['attr']['title'])

        self.last_select = self.tags['runtime_list'].selected_option()
        self.last_verified = None
        if not runtimes:
            self.update_selection()
            
    def update_selection(self):
        runtime_info = self.runtimes[self.last_select]

        self.gui.set_data('runtime_info.name', runtime_info['name'])
        self.gui.set_data('runtime_info.status', runtime_info['installed'] and _('Installed') or _('Not Installed'))
        self.gui.set_data('runtime_info.in_use', len(runtime_info['ports']) > 0 and _('Used') or _('Not Used'))
        self.gui.set_data('runtime_info.ports', harbourmaster.oc_join(runtime_info['ports']))
        self.gui.set_data('runtime_info.download_size', harbourmaster.nice_size(runtime_info['download_size']))

        if runtime_info['installed']:
            self.gui.set_data('runtime_info.disk_size', harbourmaster.nice_size(runtime_info['disk_size']))

        else:
            self.gui.set_data('runtime_info.disk_size', "")

        # self.gui.set_data('runtime_info.verified', "To be done.")

        # self.gui.set_runtime_info(self.last_select, theme_info)

        if runtime_info['installed']:
            buttons = {'A': _('Check'), 'Y': _('Uninstall'), 'B': _('Back')}

        else:
            buttons = {'A': _('Install'), 'B': _('Back')}

        self.set_buttons(buttons)

    def do_update(self, events):
        super().do_update(events)
        selected = self.tags['runtime_list'].selected_option()

        if selected != self.last_select:
            self.last_select = selected
            self.update_selection()

        if events.was_pressed('A'):
            self.button_activate()
            if selected == 'all':
                if self.gui.message_box(_("Are you sure you want to download and verify all runtimes?"), want_cancel=True):
                    with self.gui.enable_cancellable(False):
                        with self.gui.enable_messages():
                            for runtime in self.runtimes:
                                if runtime == 'all':
                                    continue

                                self.gui.do_runtime_check(runtime, in_install=True)

                                if self.runtimes[runtime]['file'].is_file():
                                    self.runtimes[runtime]['disk_size'] = self.runtimes[runtime]['file'].stat().st_size
                                    self.runtimes[runtime]['verified'] = "Verified"
                                else:
                                    self.runtimes[runtime]['disk_size'] = ""
                                    self.runtimes[runtime]['verified'] = ""

                                self.update_runtimes()

            else:
                self.gui.do_runtime_check(selected)
                self.runtimes[selected]['installed'] = self.runtimes[selected]['file'].is_file()

                if self.runtimes[selected]['file'].is_file():
                    self.runtimes[selected]['disk_size'] = self.runtimes[selected]['file'].stat().st_size
                    self.runtimes[selected]['verified'] = "Verified"
                else:
                    self.runtimes[selected]['disk_size'] = ""
                    self.runtimes[selected]['verified'] = ""

                self.update_runtimes()

            self.last_select = None

        if events.was_pressed('Y'):
            if selected != 'all' and self.runtimes[selected]['file'].is_file():
                self.button_activate()

                self.runtimes[selected]['file'].unlink()
                self.runtimes[selected]['installed'] = False
                self.runtimes[selected]['disk_size'] = ""
                self.runtimes[selected]['verified'] = ""

                self.gui.message_box(_("Deleted runtime {runtime}").format(
                    runtime=self.runtimes[selected]['name']))

                self.last_select = None
                self.update_runtimes()

            return True

        elif events.was_pressed('B'):
            self.button_back()
            self.gui.pop_scene()
            return True
