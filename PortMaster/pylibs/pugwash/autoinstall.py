# SPDX-License-Identifier: MIT
#
# Autoinstall: installs everything dropped into the autoinstall directories, called by
# the launcher through `fifo_control` (the "autoinstall" command, see app_fifo.py).
#
# Order matters: PortMaster.zip first (it may fix how the rest install), then runtimes
# (ports check for them), then ports.

import os
import shutil
import zipfile
from pathlib import Path
from loguru import logger
from gettext import gettext as _


class AutoinstallResult:
    def __init__(self, name, ok, reason=None):
        self.name = name
        self.ok = ok
        self.reason = reason

    def __repr__(self):
        return f"AutoinstallResult({self.name!r}, {self.ok!r}, {self.reason!r})"


def find_autoinstall_files(dirs):
    """
    Returns the files to install from `dirs` as a dict of lists of Paths, in install order:
    portmaster (at most one), runtimes, squashfs, ports.
    """
    files = {
        'portmaster': [],
        'runtimes': [],
        'squashfs': [],
        'ports': [],
        }

    seen = set()
    for autoinstall_dir in dirs:
        autoinstall_dir = Path(autoinstall_dir)
        if not autoinstall_dir.is_dir():
            continue

        ## spruce passes the same directory twice.
        real_dir = os.path.realpath(str(autoinstall_dir))
        if real_dir in seen:
            continue

        seen.add(real_dir)

        for file_name in sorted(autoinstall_dir.iterdir(), key=lambda path: path.name.casefold()):
            if not file_name.is_file():
                continue

            lower_name = file_name.name.casefold()

            if lower_name == 'portmaster.zip':
                if len(files['portmaster']) == 0:
                    files['portmaster'].append(file_name)

            elif lower_name.startswith('runtimes') and lower_name.endswith('.zip'):
                files['runtimes'].append(file_name)

            elif lower_name.endswith('.squashfs'):
                files['squashfs'].append(file_name)

            elif lower_name.endswith('.zip'):
                files['ports'].append(file_name)

    return files


def has_autoinstall_files(dirs):
    return any(len(file_list) > 0 for file_list in find_autoinstall_files(dirs).values())


def runtimes_zip_arch(zip_file):
    """
    The architecture a runtimes zip is for, from the first word of its comment
    (runtimes.full.aarch64.zip and friends). None for old zips without one.
    """
    with zipfile.ZipFile(zip_file, 'r') as zf:
        comment = zf.comment.decode('utf-8', 'replace').strip()

    if comment == '':
        return None

    return comment.splitlines()[-1].split()[0]


def _install_zip(hm, file_name):
    try:
        result = hm.install_port(str(file_name.resolve()))

    except Exception as err:
        logger.exception(f"autoinstall: installing {file_name} failed")
        return AutoinstallResult(file_name.name, False, str(err) or err.__class__.__name__)

    if result != 0:
        return AutoinstallResult(file_name.name, False, hm.last_install_error or _("Installation failed, see log.txt for details."))

    return AutoinstallResult(file_name.name, True)


def _install_runtimes(hm, callback, file_name):
    try:
        zip_arch = runtimes_zip_arch(file_name)

    except (zipfile.BadZipFile, OSError) as err:
        logger.error(f"autoinstall: {file_name} is not a zip: {err}")
        return AutoinstallResult(file_name.name, False, _("This is not a valid zip file."))

    device_arch = hm.device['primary_arch']
    if zip_arch is None:
        ## Old runtimes.zip has no architecture comment, newer ones must have one.
        if file_name.name.casefold() != 'runtimes.zip':
            zip_arch = '?'

    if zip_arch is not None and zip_arch != device_arch:
        logger.error(f"autoinstall: {file_name} is for {zip_arch}, device is {device_arch}")
        file_name.unlink()
        return AutoinstallResult(file_name.name, False, _("It is for the wrong architecture ({zip_arch}, this device is {device_arch}), it was deleted.").format(
            zip_arch=zip_arch, device_arch=device_arch))

    callback.message(_("Installing {download_name}.").format(download_name=file_name.name))
    try:
        with zipfile.ZipFile(file_name, 'r') as zf:
            members = zf.infolist()
            for number, member in enumerate(members):
                callback.progress(_("Installing"), number + 1, len(members), '%')
                callback.message(f"- {member.filename}")
                zf.extract(member, path=str(hm.libs_dir))

    except (zipfile.BadZipFile, OSError) as err:
        logger.exception(f"autoinstall: extracting {file_name} failed")
        return AutoinstallResult(file_name.name, False, str(err) or err.__class__.__name__)

    finally:
        callback.progress(None, None, None)

    file_name.unlink()
    return AutoinstallResult(file_name.name, True)


def _install_squashfs(hm, callback, file_name):
    try:
        shutil.move(str(file_name), str(hm.libs_dir / file_name.name))

    except OSError as err:
        logger.exception(f"autoinstall: moving {file_name} failed")
        return AutoinstallResult(file_name.name, False, str(err) or err.__class__.__name__)

    callback.message(_("Installed {download_name}.").format(download_name=file_name.name))
    return AutoinstallResult(file_name.name, True)


def run_autoinstall(hm, callback, dirs):
    """
    Installs everything found in `dirs`, returns a list of AutoinstallResult.

    Files that installed are deleted, files that failed stay so they can be looked at
    (except runtimes for the wrong architecture, which can never install).
    """
    files = find_autoinstall_files(dirs)
    results = []

    callback.message(_("Auto-installation"))

    for file_name in files['portmaster']:
        result = _install_zip(hm, file_name)
        if result.ok:
            file_name.unlink()

        results.append(result)

    for file_name in files['runtimes']:
        results.append(_install_runtimes(hm, callback, file_name))

    for file_name in files['squashfs']:
        results.append(_install_squashfs(hm, callback, file_name))

    for file_name in files['ports']:
        result = _install_zip(hm, file_name)
        if result.ok and file_name.is_file():
            file_name.unlink()

        results.append(result)

    for result in results:
        if result.ok:
            callback.message(_("- SUCCESS: {name}").format(name=result.name))
        else:
            callback.message(_("- FAILURE: {name}").format(name=result.name))

    return results


def summary_register(results):
    """
    The selection_list register for the summary page: a totals line, then each file.
    """
    installed = sum(1 for result in results if result.ok)
    failed = len(results) - installed

    register = {}
    if failed > 0:
        total_desc = _("Some files failed to install, select them to see why. They were left in the autoinstall directory.")
    else:
        total_desc = _("Everything installed successfully.")

    register['#total'] = {
        'title': _("{installed} installed, {failed} failed").format(installed=installed, failed=failed),
        'description': total_desc,
        }

    for number, result in enumerate(results):
        if result.ok:
            title = _("OK: {name}").format(name=result.name)
            description = _("{name} installed successfully.").format(name=result.name)
        else:
            title = _("FAILED: {name}").format(name=result.name)
            description = _("{name} failed to install:\n\n{reason}").format(name=result.name, reason=result.reason)

        register[f"{number}"] = {
            'title': title,
            'description': description,
            }

    return register
