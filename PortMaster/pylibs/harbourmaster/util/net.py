# SPDX-License-Identifier: MIT
#
# Network helpers: fetching and downloading.

import hashlib
import sys
from gettext import gettext as _
import requests
from loguru import logger
from ..console import cprint
from .callback import CancelEvent
from .text import nice_size


def fetch(url):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code != 200:
            logger.error(f"Failed to download {url!r}: {r.status_code}")
            return None

    except requests.exceptions.ConnectionError as err:
        logger.error(f"Failed to download {url!r}: {err}")
        return None

    return r


def fetch_data(url):
    r = fetch(url)
    if r is None:
        return None

    return r.content


def fetch_json(url):
    r = fetch(url)
    if r is None:
        return None

    return r.json()


def fetch_text(url):
    r = fetch(url)
    if r is None:
        return None

    # fixes a weird bug
    r.encoding = 'utf-8'

    return r.text


def download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
    """
    Download a file from file_url into file_name, checks the md5sum of the file against md5_source if given.

    returns file_name if successful, otherwise None.
    """
    if md5_result is None:
        md5_result = [None]

    try:
        r = requests.get(file_url, stream=True, timeout=(30, 10))

        if r.status_code != 200:
            if callback is not None:
                callback.message_box(_("Unable to download file. [{status_code}]").format(status_code=r.status_code))

            logger.error(f"Unable to download file: {file_url!r} [{r.status_code}]")
            return None

        total_length = r.headers.get('content-length')
        if total_length is None:
            total_length = None
            total_length_mb = "???? MB"
        else:
            total_length = int(total_length)
            total_length_mb = nice_size(total_length)

        md5 = hashlib.md5()

        if callback is not None:
            callback.message(_("Downloading {file_url} - ({total_length_mb})").format(file_url=file_url, total_length_mb=total_length_mb))
        else:
            cprint(f"Downloading <b>{file_url!r}</b> - <b>{total_length_mb}</b>")

        length = 0
        with file_name.open('wb') as fh:
            for data in r.iter_content(chunk_size=104096, decode_unicode=False):
                md5.update(data)
                fh.write(data)
                length += len(data)

                if callback is not None:
                    callback.progress(_("Downloading file."), length, total_length, 'data')
                else:
                    if total_length is None:
                        sys.stdout.write(f"\r[{'?' * 40}] - {nice_size(length)} / {total_length_mb} ")
                    else:
                        amount = int(length / total_length * 40)
                        sys.stdout.write(f"\r[{'|' * amount}{' ' * (40 - amount)}] - {nice_size(length)} / {total_length_mb} ")

                    sys.stdout.flush()

            if callback is None:
                cprint("\n")

            if callback is not None:
                callback.progress(_("Downloading file."), length, total_length, 'data')

    except CancelEvent as err:
        if file_name.is_file():
            file_name.unlink()

        logger.error(f"Requests error: {err}")

        raise

    except requests.RequestException as err:
        if file_name.is_file():
            file_name.unlink()

        logger.error(f"Requests error: {err}")

        if callback is not None:
            callback.message_box(_("Download failed: {err}").format(err=str(err)))

        return None

    md5_file = md5.hexdigest()
    if not no_check:
        if md5_source is not None:
            if md5_file != md5_source:
                file_name.unlink()
                logger.error(f"File doesn't match the md5 file: {md5_file} != {md5_source}")

                if callback is not None:
                    callback.message_box(_("Download validation failed."))

                return None

            else:
                if callback is not None:
                    callback.message(_("Passed file validation."))
                else:
                    cprint(f"<b,g,>Passed md5 check.</b,g,>")
        else:
            if callback is not None:
                callback.message(_("Unable to validate download."))

            logger.warning(f"No md5 to check against: {md5_file}")

    if callback is not None:
        callback.progress(None, None, None)

    md5_result[0] = md5_file

    return file_name
