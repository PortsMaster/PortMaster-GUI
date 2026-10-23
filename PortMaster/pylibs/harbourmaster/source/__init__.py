# SPDX-License-Identifier: MIT
#
# Port sources. HM_SOURCE_APIS maps the "api" value in *.source.json files to a class,
# PortMasterV3 is the only one left; raw_download handles installs from a plain url.

from gettext import gettext as _
from urllib.parse import urlparse, urlunparse
from loguru import logger
from ..info import port_info_load
from ..util import name_cleaner
from ..util import net
from .base import BaseSource
from .portmaster import PortMasterV3


################################################################################
## Raw Downloader

def raw_download(save_path, file_url, callback=None, file_name=None, md5_source=None):
    """
    This is a bit of a hack, this acts as a source of ports, but for raw urls.
    This only supports downloading so not bothering to add it as a full blown source.
    """
    original_url = file_url
    url_info = urlparse(file_url)

    if file_name is None:
        file_name = url_info.path.rsplit('/', 1)[1]

    if file_name.endswith('.md5') or file_name.endswith('.md5sum'):
        ## If it is an md5 file, we assume the actual zip is sans the md5/md5sum
        md5_source = net.fetch_text(file_url)
        if md5_source is None:
            if callback is not None:
                callback.message_box(_("Unable to download verification file."))
            logger.error(f"Unable to download file: {file_url!r}")
            return None

        md5_source = md5_source.strip().split(' ', 1)[0]

        file_name = file_name.rsplit('.', 1)[0]
        file_url = urlunparse(url_info._replace(path=url_info.path.rsplit('.', 1)[0]))

    if not file_name.endswith('.zip'):
        if callback is not None:
            callback.message_box(_("Unable to download non zip files."))

        logger.error(f"Unable to download file: {file_url!r} [doesn't end with '.zip']")
        return None

    file_name = file_name.replace('%20', '.').replace('+', '.').replace('..', '.')

    md5_result = [None]
    zip_file = net.download(save_path / file_name, file_url, md5_source, md5_result, callback=callback)

    if zip_file is None:
        return None

    zip_info = port_info_load({})

    zip_info['name'] = name_cleaner(zip_file.name)
    zip_info['zip_file'] = zip_file
    zip_info['status'] = {
        'source': 'url',
        'md5': md5_result[0],
        'url': original_url,
        'status': 'downloaded',
        }

    # print(f"-- {zip_info} --")

    # cprint("<b,g,>Success!</b,g,>")
    return zip_info


HM_SOURCE_APIS = {
    'PortMasterV3': PortMasterV3,
    }


__all__ = (
    'BaseSource',
    'raw_download',
    'HM_SOURCE_APIS',
    )
