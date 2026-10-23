# SPDX-License-Identifier: MIT
#
# PortMasterGUI CommandsMixin.

import shutil
import zipfile
import harbourmaster
from loguru import logger
from harbourmaster.i18n import _


class CommandsMixin:
    """
    PortMasterGUI methods: GUI front ends for HarbourMaster operations, run on a worker thread.
    """

    def request_frontend_refresh(self):
        """
        Leave the marker that tells the launcher script (PortMaster.sh etc.) to refresh or
        restart the frontend once PortMaster exits, so added / removed ports show up.

        Returns True if a marker was written. Platforms with ES_NAME 'show-refresh' have
        no frontend to restart, the user is told to refresh it themselves instead.
        """
        platform = self.hm.platform

        if harbourmaster.HM_TESTING or platform.ES_NAME in (None, 'show-refresh'):
            return False

        if not platform.ports_changed():
            return False

        refresh_file = (self.hm.tools_dir / "PortMaster" / f".{platform.ES_NAME}-refresh")
        logger.debug(f"{refresh_file}")
        refresh_file.touch(0o644, exist_ok=True)
        return True

    ## Gamelist xml updater
    def update_gamelist_xml(self):
        self.run_task(self._update_gamelist_xml)

    def _update_gamelist_xml(self):
        with self.enable_cancellable(False), \
                self.enable_messages(), \
                self.hm.platform.gamelist_backup() as gamelist_xml:

            self.message(_("Fetching latest gameinfo.xml files and cover images."))

            port_updates = []

            for source_name, source in self.hm.sources.items():
                if 'gameinfo.zip' not in source.utils:
                    continue

                gameinfo_zip = (self.hm.cfg_dir / f'gameinfo_{source_name}.zip')
                do_download = False

                if gameinfo_zip.is_file():
                    md5sum = harbourmaster.hash_file(gameinfo_zip)
                    logger.debug(f"{gameinfo_zip}: {md5sum}")
                    if md5sum != source._data['gameinfo.zip']['md5']:
                        do_download = True

                else:
                    do_download = True

                if do_download:
                    self.message(_("Downloading gameinfo.xml for {source_name}").format(
                        source_name=source.name))

                    gameinfo_temp = source.download('gameinfo.zip')

                    shutil.copy(gameinfo_temp, gameinfo_zip)

                with zipfile.ZipFile(gameinfo_zip, 'r') as zf:
                    for file_info in zf.infolist():
                        file_name = self.hm.ports_dir / file_info.filename

                        if not file_name.parent.is_dir():
                            logger.debug(f"- Skipping {file_name.parent.name}/{file_name.name}")
                            continue

                        if file_name.name == 'gameinfo.xml':
                            logger.debug(f"- Updating {file_name.parent.name}/{file_name.name}")
                            port_updates.append(file_name)
                        else:
                            logger.debug(f"- Adding {file_name.parent.name}/{file_name.name}")


                        zf.extract(file_info, path=self.hm.ports_dir)

            for port_update in port_updates:
                self.hm.platform.gamelist_add(port_update)

    ## HarbourMaster Commands.
    def do_install(self, port_name, port_url=None, allow_cancel=True, md5_source=None):
        if port_url is None:
            port_url = port_name

        with self.enable_messages():
            self.message(_("Installing {port_name}").format(port_name=port_name))

            with self.enable_cancellable(allow_cancel):
                self.run_task(self._install_task, port_url, md5_source)

    def _install_task(self, port_url, md5_source=None):
        ## md5_source: the self-update's md5 from version.json, the download is checked against it.
        self.hm.install_port(port_url, md5_source=md5_source)
        self.hm.load_ports()

    def do_uninstall(self, port_name):
        with self.enable_messages():
            self.message(_("Uninstalling {port_name}").format(port_name=port_name))

            with self.enable_cancellable(False):
                self.run_task(self._uninstall_task, port_name)
                self.delete_port_size(port_name)

    def _uninstall_task(self, port_name):
        self.hm.uninstall_port(port_name)
        self.hm.load_ports()

    def do_update_ports(self):
        with self.enable_messages():
            with self.enable_cancellable(False):
                self.message(_('Updating all port sources:'))
                self.run_task(self._update_ports_task)

    def _update_ports_task(self):
        self.hm.load_info(force_load=True)
        for source in self.hm.sources:
            self.hm.sources[source].update()

        self.hm.load_ports()

    def do_runtime_check(self, runtime_name, in_install=False):
        with self.enable_messages():
            self.message(_("Checking {runtime_name}").format(
                runtime_name=harbourmaster.runtime_nicename(runtime_name)))

            with self.enable_cancellable(True):
                self.run_task(self.hm.check_runtime, runtime_name, in_install=in_install)
