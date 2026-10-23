# SPDX-License-Identifier: MIT

import fnmatch
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from harbourmaster.i18n import _
from loguru import logger
from .console import cprint
from .config import HM_ACCEPTABLE_NON_BASH_TOP_LEVEL_FILES
from .util import HarbourException, add_dict_list_unique, add_list_unique, add_pm_signature, get_dict_list, get_path_fs, hash_file, name_cleaner, runtime_nicename
from .info import is_safe_port_item, port_info_load, port_info_merge
from .source import raw_download
from .captain import check_port


class InstallMixin:
    """
    HarbourMaster methods: Installing and uninstalling ports, themes and PortMaster itself.
    """

    def _fix_permissions(self, path_check=None):
        if path_check is None:
            path_check = self.ports_dir

        path_fs = get_path_fs(path_check)
        logger.debug(f"Fix Perms: {path_check} = {path_fs}")

        if path_fs not in ('ext4', 'ext3', 'overlay'):
            return

        try:
            logger.info(f"Fixing permissions for {path_check}.")
            subprocess.check_output(['chmod', '-R', '777', str(path_check)])

        except subprocess.CalledProcessError as err:
            logger.error(f"Failed to fix permissions: {err}")
            return

    def _install_theme(self, download_file, do_delete=False):
        """
        Installs a theme file.
        """
        logger.info(f"Installing theme: {download_file.name}")

        if not self.themes_dir.is_dir():
            self.themes_dir.mkdir(0o755)

        theme_dir = self.themes_dir / download_file.name.rsplit('.', 2)[0]
        if not theme_dir.is_dir():
            theme_dir.mkdir(0o755)

        with zipfile.ZipFile(download_file, 'r') as zf:
            self.callback.message(_("Installing Theme {download_name}.").format(download_name=download_file.name))

            total_files = len(zf.infolist())
            for file_number, file_info in enumerate(zf.infolist()):
                ## Zips made on Windows can use \ between folders (jimmyhat999's grid themes did).
                zip_name = file_info.filename.replace('\\', '/')
                if zip_name.endswith('/'):
                    continue

                self.callback.progress(_("Installing"), file_number+1, total_files, '%')
                self.callback.message(f"- {zip_name}")

                file_name = theme_dir / zip_name.rsplit('/', 1)[-1]
                with open(file_name, 'wb') as fh:
                    fh.write(zf.read(file_info.filename))

        with open(theme_dir / "theme.md5", 'w') as fh:
            fh.write(hash_file(download_file))

        if do_delete:
            download_file.unlink()

        self.callback.message_box(_("Theme {download_name!r} installed successfully.").format(download_name=download_file.name))

        return 0

    def _install_portmaster(self, download_file, do_delete=False):
        """
        Installs a new version of PortMaster
        """
        logger.info("Installing PortMaster.zip")
        # if HM_TESTING:
        #     logger.error("Unable to install PortMaster.zip in testing environment.")
        #     return 255

        move_bash = self.platform.MOVE_PM_BASH

        ## Check the whole zip before touching anything: a broken download extracted
        ## part way would leave PortMaster half updated.
        try:
            with zipfile.ZipFile(download_file, 'r') as zf:
                bad_file = zf.testzip()

            if bad_file is not None:
                raise zipfile.BadZipFile(f"bad CRC for {bad_file}")

        except (zipfile.BadZipFile, OSError, EOFError) as err:
            logger.error(f"PortMaster.zip is damaged: {err}")
            self.last_install_error = _("PortMaster.zip is damaged, download it again.")
            self.callback.message(self.last_install_error)
            self.callback.message_box(_("Port {download_name} installed failed.").format(download_name="PortMaster"))

            if do_delete:
                download_file.unlink()

            return 255

        try:
            gcd_mode = self.get_gcd_mode()

            # Hahaha... undo this mistake. :D
            if (self.cfg_dir / "PortMaster.sh").is_file():
                (self.cfg_dir / "PortMaster.sh").unlink()

            bash_files = []

            with zipfile.ZipFile(download_file, 'r') as zf:
                self.callback.message(_("Installing {download_name}.").format(download_name="PortMaster"))

                total_files = len(zf.infolist())
                for file_number, file_info in enumerate(zf.infolist()):
                    if file_info.file_size == 0:
                        compress_saving = 100
                    else:
                        compress_saving = file_info.compress_size / file_info.file_size * 100

                    self.callback.progress(_("Installing"), file_number+1, total_files, '%')
                    self.callback.message(f"- {file_info.filename}")

                    dest_file = self.tools_dir / file_info.filename

                    # cprint(f"- <b>{file_info.filename!r}</b> <d>[{nice_size(file_info.file_size)} ({compress_saving:.0f}%)]</d>")
                    if dest_file.name.lower().endswith('.sh') and dest_file.is_file():
                        ## The launcher may be the script running right now (eg: ROCKNIX runs
                        ## PortMaster/PortMaster.sh), bash reads scripts as it goes: write a new file.
                        temp_file = dest_file.with_name(f".{dest_file.name}.new")
                        temp_file.write_bytes(zf.read(file_info))
                        os.replace(str(temp_file), str(dest_file))

                    else:
                        zf.extract(file_info, path=self.tools_dir)

                    if move_bash and dest_file.name.lower().endswith('.sh'):
                        move_bash_dir = self.platform.MOVE_PM_BASH_DIR
                        if move_bash_dir is None or not move_bash_dir.is_dir():
                            move_bash_dir = self.tools_dir

                        self.callback.message(f"- moving {dest_file} to {move_bash_dir / dest_file.name}")
                        shutil.move(dest_file, move_bash_dir / dest_file.name)

                        # Bash file is moved from the PortMaster directory so we need to chmod it separately.
                        bash_files.append(move_bash_dir / dest_file.name)

            self.set_gcd_mode(gcd_mode)

            self.platform.portmaster_install(bash_files)

            self._fix_permissions(self.tools_dir / "PortMaster")
            for bash_file in bash_files:
                self._fix_permissions(bash_file)

            self.callback.message_box(_("Port {download_name!r} installed successfully.").format(download_name="PortMaster"))

        finally:
            if do_delete:
                download_file.unlink()

        return 0

    def _install_rollback(self, undo_data):
        """
        Remove what a failed install added, newest first.
        """
        self._port_attrs_updated = True

        if len(undo_data) == 0:
            return

        logger.error("Installation failed, removing installed files.")
        self.callback.message(_("Installation failed, removing files..."))

        for undo_file in undo_data[::-1]:
            logger.info(f"Removing {str(self._ports_dir_relative_to(undo_file))}")
            self.callback.message(f"- {str(self._ports_dir_relative_to(self.ports_dir))}")

            if undo_file.is_file():
                undo_file.unlink()

            elif undo_file.is_dir():
                shutil.rmtree(undo_file)

    def _install_port(self, download_info, do_delete=False):
        """
        Installs a port.

        We collect a list of top level scripts/directories, this is added to the port.json file.
        """
        undo_data = []
        is_successs = False
        failure_reason = None

        port_nice_name = download_info.get('attr', {}).get('title', download_info['name'])
        if port_nice_name == '':
            port_nice_name = download_info['zip_file'].name

        port_info = {}
        logger.info(f"Installing {port_nice_name}")

        try:
            extra_info = {}
            logger.info(f"Verifying port")
            port_info = check_port(download_info['name'], download_info['zip_file'], extra_info)

            port_reqs = self.match_requirements(port_info)

            if not port_reqs:
                logger.info(f"PORT INFO: {port_info}")
                logger.info(f"MATCH REQS: {port_reqs}")
                logger.info(f"IS_GUI: {self.callback.IS_GUI}")

                if self.callback.IS_GUI:
                    # I forgot this was a thing, spent so long debugging this shit.
                    with self.callback.enable_messagebox():
                        most_likely_an_r36s = _("HELLO.\n\nIT LOOKS LIKE YOU'RE MANUALLY INSTALLING A PORT THAT IS INCOMPATIBLE WITH YOUR DEVICE.\n\nIF YOU HAVE ISSUES, DO NOT REPORT THEM ON DISCORD, YOU WILL BE SUBJECT TO RIDICULE.\n\nARE YOU SURE YOU WANT TO RESUME INSTALLING?")
                        if self.callback.message_box(most_likely_an_r36s, want_cancel=True, cancel_text=_("Okay"), ok_text=_("Cancel")):
                            # HAHA, FUCK YOU.
                            raise HarbourException(_("Not compatible with this device."))

            # Extra fix
            port_info_file_old = None

            if extra_info['port_info_file'] != 'port.json':
                if 'alephone/' not in port_info['items'] and 'alephone' not in port_info['items']:
                    # FUCK THESE GAMES. :D
                    port_info_file_old = self.ports_dir / extra_info['port_info_file']
                    extra_info['port_info_file'] = extra_info['port_info_file'].rsplit('/', 1)[0] + '/port.json'

            port_info_file = self.ports_dir / extra_info['port_info_file']

            with zipfile.ZipFile(download_info['zip_file'], 'r') as zf:
                ## TODO: keep a list of installed files for uninstalling?
                # At this point the port will be installed
                # Extract all the files to the specified directory
                # zf.extractall(self.ports_dir)
                self.callback.message(_("Installing {download_name}.").format(download_name=port_nice_name))

                total_files = len(zf.infolist())

                # Not naming any names, but this is necessary for ports with many files
                count_skip = 1
                if total_files > 400:
                    count_skip = (total_files // 400)

                for file_number, file_info in enumerate(zf.infolist()):
                    if file_info.file_size == 0:
                        compress_saving = 100
                    else:
                        compress_saving = file_info.compress_size / file_info.file_size * 100

                    if (file_number % count_skip) == 0 or (file_number + 1) == total_files:
                        self.callback.progress(_("Installing"), file_number + 1, total_files, '%')
                        self.callback.message(f"- {file_info.filename}")

                    is_script = False
                    fix_path = ""

                    if file_info.filename.count('/') == 0:
                        is_script = file_info.filename.lower().endswith('.sh')
                        if not is_script and file_info.filename.lower() in HM_ACCEPTABLE_NON_BASH_TOP_LEVEL_FILES:
                            fix_path = f"{extra_info['port_dir']}/"

                    dest_file = path = self._ports_dir_file(f"{fix_path}{file_info.filename}", is_script)
                    dest_dir = (is_script and self.scripts_dir or self.ports_dir) / fix_path

                    if dest_file == port_info_file_old:
                        dest_file = port_info_file
                        if not dest_file.exists():
                            add_list_unique(undo_data, dest_file)

                        continue

                    if not file_info.filename.endswith('/'):
                        if not dest_file.parent.is_dir():
                            add_list_unique(undo_data, dest_file.parent)

                    if not dest_file.exists():
                        add_list_unique(undo_data, dest_file)

                    # cprint(f"- <b>{file_info.filename!r}</b> as <b>{fix_path}{file_info.filename}</b> <d>[{nice_size(file_info.file_size)} ({compress_saving:.0f}%)]</d>")

                    logger.debug(f"Extracting {file_info.filename} to {dest_dir}.")
                    zf.extract(file_info, path=dest_dir)

            # print(f"Port Info: {port_info}")
            # print(f"Download Info: {download_info}")

            port_info_merge(port_info, download_info)

            ## These two are always overriden.
            port_info['name'] = name_cleaner(download_info['zip_file'].name)
            port_info['status'] = download_info['status'].copy()
            port_info['status']['status'] = 'Installed'

            # This doesnt need to be stored.
            if 'source' in port_info:
                del port_info['source']

            # Get a list of files/dirs we should fix permissions of.
            fix_perm_files = []

            # Build up this also.
            port_info['files'] = {
                'port.json': str(self._ports_dir_relative_to(port_info_file)),
                }

            # Add all the root dirs/scripts in the port
            for item in port_info['items']:
                if self._ports_dir_exists(item):
                    if item not in get_dict_list(port_info['files'], item):
                        add_dict_list_unique(port_info['files'], item, item)

                    if item.lower().endswith('.sh'):
                        add_pm_signature(self.ports_dir / item, [port_info['name'], item])

                    fix_perm_files.append(self._ports_dir_file(item, item.casefold().endswith('.sh')))

            # And any optional ones.
            for item in get_dict_list(port_info, 'items_opt'):
                if self._ports_dir_exists(item):
                    if item not in get_dict_list(port_info['files'], item):
                        add_dict_list_unique(port_info['files'], item, item)

                    if item.lower().endswith('.sh'):
                        add_pm_signature(self.ports_dir / item, [port_info['name'], item])

                    fix_perm_files.append(self._ports_dir_file(item, item.casefold().endswith('.sh')))
            # print(f"Merged Info: {port_info}")

            if not port_info_file.is_file():
                add_list_unique(undo_data, port_info_file)

            # print(f"-> {port_info_file}")
            with open(port_info_file, 'w') as fh:
                json.dump(port_info, fh, indent=4)

            # Remove the zip file if it is in the self.temp_dir
            is_successs = True

            self.platform.port_install(port_info['name'], port_info, undo_data, fix_perm_files)

            if extra_info['gameinfo_xml'] is not None:
                if self.cfg_data.get('gamelist_update', True):
                    gameinfo_xml = self._ports_dir_file(extra_info['gameinfo_xml'])

                    if gameinfo_xml.is_file():
                        self.platform.gamelist_add(gameinfo_xml)

            self._port_attrs_updated = True

            # Fix permissions
            for fix_perm_file in fix_perm_files:
                self._fix_permissions(fix_perm_file)

        except HarbourException as err:
            is_successs = False
            failure_reason = str(err) or err.__class__.__name__
            logger.error(f"Installing {port_nice_name} failed: {failure_reason}")

        except Exception as err:
            ## Anything else (not a zip, disk full, ...), keep the traceback for the log.
            is_successs = False
            failure_reason = str(err) or err.__class__.__name__
            logger.exception(f"Installing {port_nice_name} failed: {failure_reason}")

        except BaseException:
            ## Cancelled / interrupted part way: undo, then let it carry on up.
            self._install_rollback(undo_data)
            raise

        finally:
            if do_delete:
                download_info['zip_file'].unlink()

        if not is_successs:
            self._install_rollback(undo_data)

            if failure_reason is not None:
                self.callback.message(_("Installation failed: {reason}").format(reason=failure_reason))
                self.last_install_error = failure_reason

            self.callback.message_box(_("Port {download_name} installed failed.").format(download_name=port_nice_name))

            return 255

        # logger.debug(port_info)
        if len(port_info['attr'].get('runtime', [])) > 0:
            runtime_name = runtime_nicename(port_info['attr']['runtime'])

            result = 0
            for runtime in port_info['attr']['runtime']:
                self.callback.progress(None, None, None)
                result += self.check_runtime(runtime, in_install=True)

            if result == 0:
                self.callback.message_box(_("Port {download_name!r} and {runtime_name!r} installed successfully.").format(
                    download_name=port_nice_name,
                    runtime_name=runtime_name))

            else:
                self.callback.message_box(_("Port {download_name!r} installed sucessfully, but {runtime_name!r} failed to install!!\n\nEither reinstall to try again, or check the wiki for help.").format(
                    download_name=port_nice_name,
                    runtime_name=runtime_name))

        else:
            self.callback.message_box(_("Port {download_name!r} installed successfully.").format(download_name=port_nice_name))

        return 0

    def install_port(self, port_name, md5_source=None):
        self.last_install_error = None

        # Special HTTP download code.
        if port_name.startswith('http'):
            if self.config['offline']:
                cprint(f"Unable to download {port_name} when offline")
                self.callback.message_box(_("Unable to download in offline mode."))
                return 255

            download_info = raw_download(self.temp_dir, port_name, callback=self.callback, md5_source=md5_source)

            if download_info is None:
                return 255

            with self.callback.enable_cancellable(False):
                if name_cleaner(download_info['name']).endswith('.theme.zip'):
                    return self._install_theme(download_info['zip_file'], do_delete=True)

                elif name_cleaner(download_info['name']) == 'portmaster.zip':
                    return self._install_portmaster(download_info['zip_file'], do_delete=True)

                else:
                    return self._install_port(download_info, do_delete=True)

        # Special case for a local file.
        if port_name.startswith('./') or port_name.startswith('../') or port_name.startswith('/'):
            port_file = Path(port_name)
            if not port_file.is_file():
                logger.error(f"Unable to find local file {port_name} for installation.")
                self.last_install_error = _("File not found.")
                return 255

            md5_result = hash_file(port_file)
            port_info = port_info_load({})

            port_info['name'] = name_cleaner(port_file.name)
            port_info['zip_file'] = port_file
            port_info['status'] = {
                'source': 'file',
                'md5': md5_result,
                'status': 'downloaded',
                }

            with self.callback.enable_cancellable(False):
                if name_cleaner(port_info['name']).endswith('.theme.zip'):
                    return self._install_theme(port_info['zip_file'])

                elif name_cleaner(port_info['name']) == 'portmaster.zip':
                    return self._install_portmaster(port_info['zip_file'])

                return self._install_port(port_info)

        if '/' in port_name:
            repo, port_name = port_name.split('/', 1)
        else:
            repo = '*'

        # Otherwise:
        for source_prefix, source in self.sources.items():
            if not fnmatch.fnmatch(source_prefix, repo):
                continue

            check_okay = False
            # is it a valid port?
            if not check_okay and (
                    source.clean_name(port_name) in source.ports):
                check_okay = True

            # is it PortMaster.zip from the Official PortMaster repo?
            if not check_okay and (
                    source.name in ("PortMaster", ) and
                    source.clean_name(port_name) == 'portmaster.zip' and
                    source.clean_name(port_name) in source._data):
                check_okay = True

            # is it a theme?
            if not check_okay and (
                    source.clean_name(port_name).endswith('.theme.zip') and
                    source.clean_name(port_name) in source._data):
                check_okay = True

            if not check_okay:
                continue

            if self.config['offline']:
                cprint(f"Unable to download {port_name} when offline")
                self.callback.message_box(_("Unable to download in offline mode."))
                return 255

            download_info = source.download(source.clean_name(port_name))

            if download_info is None:
                return 255

            # print(f"Download Info: {download_info.to_dict()}")
            with self.callback.enable_cancellable(False):
                if source.clean_name(port_name).endswith('.theme.zip'):
                    return self._install_theme(download_info, do_delete=True)

                elif source.clean_name(port_name) == 'portmaster.zip':
                    return self._install_portmaster(download_info, do_delete=True)

                return self._install_port(download_info, do_delete=True)

        self.callback.message_box(_("Unable to find a source for {port_name}").format(port_name=port_name))

        cprint(f"Unable to find a source for <b>{port_name}</b>")
        return 255

    def uninstall_port(self, port_name):
        port_info = self.installed_ports.get(port_name.casefold(), None)
        port_loc = self.installed_ports

        if port_info is None:
            port_info = self.broken_ports.get(port_name.casefold(), None)
            port_loc = self.broken_ports

            if port_info is None:
                self.callback.message_box(_("Unknown port {port_name}").format(port_name=port_name))
                logger.error(f"Unknown port {port_name}")
                return 255

        port_info_name = port_info.get("attr", {}).get("title", port_name)

        all_items = {}

        self._port_attrs_updated = True

        # We need to build up a list of all associated files
        # so we only delete the ones that will no longer be associaed with any ports.
        for item_name, item_info in self.installed_ports.items():
            # Add all the root dirs/scripts in the port
            for item in item_info['files']:
                if item in ('port.json', ):
                    continue

                for name in get_dict_list(item_info['files'], item):
                    add_dict_list_unique(all_items, name, item_name)

        for item_name, item_info in self.broken_ports.items():
            # Add all the root dirs/scripts in the port
            for item in item_info['files']:
                if item in ('port.json', ):
                    continue

                for name in get_dict_list(item_info['files'], item):
                    add_dict_list_unique(all_items, name, item_name)

        # from pprint import pprint
        # pprint(all_items)

        # cprint(f"{all_items}")
        cprint(f"Uninstalling <b>{port_info_name}</b>")
        self.callback.message(_("Removing {port_name}").format(port_name=port_info_name))

        all_port_items = []
        for port_file in port_info['files']:
            all_port_items.extend(get_dict_list(port_info['files'], port_file))

        ports_dir = self.ports_dir

        for item in all_port_items:
            if not is_safe_port_item(item):
                logger.error(f"Not removing {item!r} for {port_name}: it is outside the ports folder.")

        uninstall_items = [
            item
            for item in all_port_items
            # Only delete files/scripts with only 1 owner.
            if len(get_dict_list(all_items, item)) == 1 and is_safe_port_item(item)]

        self.platform.port_uninstall(port_name, port_info, all_port_items)

        try:
            for item in uninstall_items:
                item_path = self.ports_dir / item

                if item_path.exists():
                    cprint(f"- removing {item}")
                    self.callback.message(f"- {item}")

                    if item_path.is_dir():
                        shutil.rmtree(item_path)

                    elif item_path.is_file():
                        item_path.unlink()

                item_path = self.scripts_dir / item

                if item_path.exists():
                    cprint(f"- removing {item}")
                    self.callback.message(f"- {item}")

                    if item_path.is_dir():
                        shutil.rmtree(item_path)

                    elif item_path.is_file():
                        item_path.unlink()

        except OSError as err:
            logger.error(f"Uninstalling {port_info_name} failed: {err}")
            self.callback.message_box(_("Error uninstalling {port_name}\n\n{error}").format(port_name=port_info_name, error=str(err)))
            del port_loc[port_name.casefold()]
            return 1

        self.callback.message_box(_("Successfully uninstalled {port_name}").format(port_name=port_info_name))
        return 0
