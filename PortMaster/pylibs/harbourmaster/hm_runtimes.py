# SPDX-License-Identifier: MIT

import hashlib
from harbourmaster.i18n import _
from loguru import logger
from .console import cprint
from .util import download, hash_file


class RuntimesMixin:
    """
    HarbourMaster methods: Runtime (squashfs) management.
    """

    def list_runtimes(self):
        result = []
        changed = False
        for runtime_name, runtime_data in self.runtimes_info.items():
            runtime_file = self.libs_dir / runtime_name

            # FIX IT
            if 'remote' in runtime_data and 'name' in runtime_data['remote']:
                temp = runtime_data['remote']
                runtime_data['remote'] = {}
                runtime_data['remote']['aarch64'] = temp
                changed = True

            local_info = runtime_data.get('local')
            if not isinstance(local_info, dict) or (local_info.get('status') == 'Not Installed' and runtime_file.is_file()):
                ## Never checked, or copied in since (by hand, autoinstall): check it now.
                runtime_data.pop('local', None)

            if 'local' not in runtime_data:
                changed = True
                runtime_file = (self.libs_dir / runtime_name)
                runtime_md5 = None
                runtime_md5_file = (self.libs_dir / (runtime_name + '.md5'))
                runtime_local_arch = None

                if runtime_file.is_file():
                    runtime_status = 'Unverified'

                    runtime_md5_check = hash_file(runtime_file)

                    if runtime_md5_file.is_file():
                        runtime_md5 = runtime_md5_file.read_text().strip().split(' ')[0]
                        if runtime_md5_check == runtime_md5:
                            runtime_status = 'Verified'
                            runtime_local_arch = 'aarch64'

                    else:
                        for runtime_arch in runtime_data['remote']:
                            runtime_md5 = runtime_data['remote'][runtime_arch]['md5']

                            if runtime_md5_check == runtime_md5:

                                runtime_status = 'Verified'
                                runtime_local_arch = runtime_arch
                                break

                        else:
                            runtime_status = 'Broken'

                else:
                    runtime_status = 'Not Installed'

                runtime_data['local'] = {
                    'status': runtime_status,
                    'md5': runtime_md5,
                    'arch': runtime_local_arch,
                    }

            else:
                ## Only when it changes: this runs on every start.
                if not runtime_file.is_file() and runtime_data['local'].get('status') != 'Not Installed':
                    changed = True
                    runtime_data['local'] = {
                        'status': 'Not Installed',
                        'md5': None,
                        'arch': None,
                        }

            result.append((runtime_name, runtime_data))

        if changed:
            self.save_config()

        return result

    def check_runtime(self, runtime, port_name=None, in_install=False):
        if not isinstance(runtime, str):
            return 255

        if '/' in runtime:
            if not in_install:
                self.callback.message_box(_("Port {runtime} contains a bad runtime, game may not run correctly.").format(
                    runtime=runtime))

            logger.error(f"Bad runtime {runtime}")
            return 255

        if not self.libs_dir.is_dir():
            self.libs_dir.mkdir(0o777)

        if not runtime.endswith('.squashfs'):
            runtime += '.squashfs'

        if runtime not in self.runtimes_info:
            if not in_install:
                self.callback.message_box(_("Port {runtime} contains an unknown runtime, game may not run correctly.").format(
                    runtime=runtime))

            logger.error(f"Unknown runtime {runtime}")
            return 255

        # Fixes some stuff.
        self.list_runtimes()

        runtime_info = self.runtimes_info[runtime]
        runtime_name = runtime_info['name']
        runtime_file = (self.libs_dir / runtime)
        runtime_md5 = runtime_info.get('local', {}).get('md5', None)
        runtime_status = 'Not Installed'
        runtime_md5sum = None

        status_language = {
            'Not Installed':    _('Not Installed'),
            'Update Available': _('Update Available'),
            'Verified':         _('Verified'),
            'Unverified':       _('Unverified'),
            'Broken':           _('Broken'),
            }

        logger.info(f"Installing {runtime_name}")

        if self.config['offline']:
            ## Nothing can be checked or downloaded, an installed runtime is the best we can do.
            if runtime_file.is_file():
                return 0

            cprint(f"Unable to download {runtime} when offline")
            self.callback.message_box(_("Unable do download a runtime when in offline mode."))
            return 255

        if runtime_file.is_file():
            runtime_status = 'Unverified'

            self.callback.message(_("Verifying runtime {runtime}").format(
                runtime=runtime_name))

            with open(runtime_file, 'rb') as fh:
                total_size = runtime_file.stat().st_size
                process_size = 0

                md5obj = hashlib.md5()

                self.callback.progress(_('Verifying'), process_size, total_size)

                for data in iter(lambda: fh.read(1024 * 1024 * 10), b''):
                    self.callback.progress(_('Verifying'), process_size, total_size)
                    process_size += len(data)
                    md5obj.update(data)

                self.callback.progress(None, None, None)

                runtime_md5sum = md5obj.hexdigest()

            if runtime_md5 is None:
                # runtime_md5.write_text(runtime_md5sum)
                runtime_status = 'Unverified'

            elif runtime_md5 == runtime_md5sum:
                runtime_status = 'Verified'

            else:
                runtime_status = 'Broken'

            runtime_info['local']['status'] = runtime_status

        else:
            runtime_status = 'Not Installed'

        if runtime not in self.runtimes_info:
            if not in_install:
                self.callback.message_box(_("Unable to find a download for {runtime}.").format(runtime=runtime))

            logger.error(f"Unable to find suitable source for {runtime}.")
            return 255

        if self.device['primary_arch'] not in self.runtimes_info[runtime]['remote']:
            self.callback.message_box(_("Unable to download {runtime} in {device_arch}.").format(
                runtime=runtime_name,
                device_arch=self.device['primary_arch']))

            logger.error(f"Unable to download {runtime} in {self.device['primary_arch']}.")
            return 255

        runtime_remote_info = self.runtimes_info[runtime]['remote'][self.device['primary_arch']]

        if runtime_remote_info['md5'] == runtime_md5sum:
            runtime_status = 'Verified'

        else:
            runtime_status = {
                'Verified': 'Update Available',
                'Unverified': 'Broken',
                'Broken': 'Broken',
                'Not Installed': 'Not Installed',
                }.get(runtime_status, runtime_status)

        if runtime_status == 'Verified':
            if not in_install:
                self.callback.message_box(_("Verified {runtime} successfully.").format(
                    runtime=runtime_name))
            else:
                self.callback.message(_("Verified {runtime}.").format(
                    runtime=runtime_name))

            return 0

        elif runtime_status == 'Update Available':
            self.callback.message(_("Updating {runtime}.").format(
                    runtime=runtime_name))

        elif runtime_status == 'Broken':
            self.callback.message(_("Runtime {runtime} is broken, reinstalling.").format(
                    runtime=runtime_name))

        else:
            self.callback.message(_("Downloading runtime {runtime}.").format(
                runtime=runtime_name))

        download_successfull = False
        try:
            with self.callback.enable_cancellable(True):
                md5_result = [None]
                runtime_url = runtime_remote_info['url']
                runtime_md5 = runtime_remote_info['md5']

                ## download() returns None when it fails (http error, md5 mismatch, ...)
                if download(runtime_file, runtime_url, md5_source=runtime_md5, callback=self.callback) is not None:
                    self.runtimes_info[runtime]['local'] = {
                        "arch": self.device['primary_arch'],
                        "md5": runtime_md5,
                        "status": "Verified"
                        }

                    download_successfull = True

                    self.platform.runtime_install(runtime, [runtime_file])

                    self.save_config()

            if self.callback.was_cancelled or not download_successfull:
                if runtime_file.is_file():
                    runtime_file.unlink()

                if not in_install:
                    self.callback.message_box(_("Unable to download {runtime}, game may not run correctly.").format(runtime=runtime))

                return 255

        except Exception as err:
            ## We need to catch any errors and delete the file if it fails,
            ## here we are not using the temp file auto deletion.
            logger.error(err)

            if not in_install:
                self.callback.message_box(_("Unable to download {runtime}, game may not run correctly.").format(runtime=runtime))

            return 255

        finally:
            if not download_successfull and runtime_file.is_file():
                runtime_file.unlink()

        if not in_install:
            self.callback.message_box(_("Successfully downloaded {runtime}.").format(runtime=runtime))

        return 0
