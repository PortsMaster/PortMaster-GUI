# SPDX-License-Identifier: MIT
#
# File helpers: PortMaster script signatures, hashing, temp dirs.

import contextlib
import hashlib
import shutil
import re
import subprocess
import tempfile
from pathlib import Path
import pathlib
from loguru import logger
from ..config import HM_TESTING


def load_pm_signature(file_name):
    ## Adds the portmaster signature to a bash script.
    if isinstance(file_name, str):
        file_name = pathlib.Path(file_name)

    elif not isinstance(file_name, pathlib.PurePath):
        raise ValueError(file_name)

    if not file_name.is_file():
        return None

    if file_name.suffix.lower() not in ('.sh', ):
        return None

    try:
        with open(file_name, 'rb') as fh:
            data = fh.read(1024)

            ## Some scripts (eg: makeself installers) have binary data after the header.
            for line in data.decode('utf-8', 'replace').split('\n'):
                if not line.strip().startswith('#'):
                    continue

                if 'PORTMASTER:' not in line:
                    continue

                if ',' not in line.split(':', 1)[1]:
                    continue

                return [
                    item.strip()
                    for item in line.split(':', 1)[1].strip().split(',', 1)]

    except Exception as err:
        # Bad but we will live.
        logger.error(f"Error loading {file_name}: {err}")
        return None

    return None


def add_pm_signature(file_name, info):
    ## Adds the portmaster signature to a bash script.

    if isinstance(file_name, str):
        file_name = pathlib.Path(file_name)

    elif not isinstance(file_name, pathlib.PurePath):
        raise ValueError(file_name)

    if not file_name.is_file():
        return

    if file_name.suffix.lower() not in ('.sh', ):
        return

    # See if it has some info already.
    old_info = load_pm_signature(file_name)

    try:
        if old_info is not None:
            # Info is the same, ignore it
            if old_info == info:
                return

            file_data = [
                line
                for line in file_name.read_text().split('\n')
                if not (line.strip().startswith('#') and 'PORTMASTER:' in line)]

        else:
            file_data = [
                line
                for line in file_name.read_text().split('\n')]

    except UnicodeDecodeError as err:
        logger.error(f"Error loading {file_name}: {err}")
        return

    except Exception as err:
        # Bad but we will live.
        logger.error(f"Error loading {file_name}: {err}")
        return

    file_data.insert(1, f"# PORTMASTER: {', '.join(info)}")

    with file_name.open('w') as fh:
        fh.write("\n".join(file_data))


def remove_pm_signature(file_name):
    ## Removes the portmaster signature to a bash script.

    if isinstance(file_name, str):
        file_name = pathlib.Path(file_name)

    elif not isinstance(file_name, pathlib.PurePath):
        raise ValueError(file_name)

    if not file_name.is_file():
        return

    if file_name.suffix.casefold() not in ('.sh', ):
        return

    # See if it has some info already.
    old_info = load_pm_signature(file_name)
    if old_info is None:
        return

    file_data = [
        line
        for line in file_name.read_text().split('\n')
        if not (line.strip().startswith('#') and 'PORTMASTER:' in line)]

    with file_name.open('w') as fh:
        fh.write("\n".join(file_data))


def hash_file(file_name):
    if isinstance(file_name, str):
        file_name = pathlib.Path(file_name)
    elif not isinstance(file_name, pathlib.PurePath):
        raise ValueError(file_name)

    if not file_name.is_file():
        return None

    md5 = hashlib.md5()
    with file_name.open('rb') as fh:
        for data in iter(lambda: fh.read(1024 * 1024 * 10), b''):
            md5.update(data)

    return md5.hexdigest()


def hash_file_sha(file_name):
    if isinstance(file_name, str):
        file_name = pathlib.Path(file_name)
    elif not isinstance(file_name, pathlib.PurePath):
        raise ValueError(file_name)

    if not file_name.is_file():
        return None

    sha = hashlib.sha1()
    with file_name.open('rb') as fh:
        for data in iter(lambda: fh.read(1024 * 1024 * 10), b''):
            sha.update(data)

    return sha.hexdigest()


def calculate_git_blob_sha_file(file_name):
    """
    Calculates the Git blob SHA-1 hash for a local file.

    Args:
        file_path: The path to the local file.

    Returns:
        The hexadecimal SHA-1 hash string.
    """

    if isinstance(file_name, str):
        file_name = pathlib.Path(file_name)
    elif not isinstance(file_name, pathlib.PurePath):
        raise ValueError(file_name)

    if not file_name.is_file():
        return None

    # Construct the Git blob header
    # The header is "blob <size>\0"
    sha = hashlib.sha1()
    sha.update(f"blob {file_name.stat().st_size}\0".encode('utf-8'))

    with open(file_name, 'rb') as fh:
        for data in iter(lambda: fh.read(1024 * 1024 * 10), b''):
            sha.update(data)

    # Calculate the SHA-1 hash
    return sha.hexdigest()


def calculate_git_blob_sha_data(file_data):
    """
    Calculates the Git blob SHA-1 hash for raw data.

    Args:
        file_data: The path to the local file.

    Returns:
        The hexadecimal SHA-1 hash string.
    """

    if isinstance(file_data, str):
        file_data = file_data.encode('utf-8')
    elif not isinstance(file_data, bytes):
        raise ValueError(file_data)

    # Construct the Git blob header
    # The header is "blob <size>\0"
    sha = hashlib.sha1()
    sha.update(f"blob {len(file_data)}\0".encode('utf-8'))
    sha.update(file_data)

    # Calculate the SHA-1 hash
    return sha.hexdigest()


def get_path_fs(path):
    """
    Get the fs type of the specified path.
    """

    if HM_TESTING:
        return None

    if isinstance(path, pathlib.PurePath):
        if not path.exists():
            return None
    elif isinstance(path, str):
        if not Path(path).exists():
            return None
    else:
        return None

    try:
        lines = subprocess.check_output(['df', '-PT', str(path)]).decode().split('\n')
    except subprocess.CalledProcessError as err:
        return None

    if len(lines) < 2:
        return None

    if lines[1].strip() == '':
        return None

    sections = re.split(r'\s+', lines[1])
    if len(sections) < 2:
        return None

    return sections[1]


@contextlib.contextmanager
def make_temp_directory():
    temp_dir = tempfile.mkdtemp()
    try:
        yield Path(temp_dir)

    finally:
        shutil.rmtree(temp_dir)
