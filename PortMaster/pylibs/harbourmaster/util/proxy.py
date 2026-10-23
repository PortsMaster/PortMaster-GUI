# SPDX-License-Identifier: MIT
#
# HTTP proxy settings from EmulationStation (ArkOS4Clone's Wi-Fi settings).
#
# EmulationStation keeps the proxy in es_settings.cfg and uses it for its own requests,
# without exporting http_proxy & co, and sudo drops those anyway. PortMaster reads it
# itself after sudo, so the GUI, autoinstall and the CLI all use it (requests honours
# the variables).

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from loguru import logger


PROXY_KEYS = ('http_proxy', 'https_proxy', 'all_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')
NO_PROXY_KEYS = ('no_proxy', 'NO_PROXY')

DEFAULT_NO_PROXY = "localhost,127.0.0.1,::1"


def es_settings_files(environ):
    """
    Where es_settings.cfg may be. PortMaster runs as root through sudo, so the
    frontend user's home comes first: SUDO_USER's, then HOME, then ArkOS' ark.
    """
    homes = []

    sudo_user = environ.get('SUDO_USER')
    if sudo_user:
        try:
            import pwd
            homes.append(pwd.getpwnam(sudo_user).pw_dir)
        except (ImportError, KeyError):
            pass

    if environ.get('HOME'):
        homes.append(environ['HOME'])

    homes.append('/home/ark')

    files = []
    for home in homes:
        settings_file = Path(home) / '.emulationstation' / 'es_settings.cfg'
        if settings_file not in files:
            files.append(settings_file)

    return files


def _check_value(value):
    ## These end up in the environment of everything PortMaster runs.
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('control character in proxy setting')

    return value


def es_proxy_settings(settings_file):
    """
    {key: value} to add to the environment for es_settings.cfg's HTTP proxy, or {} when
    it has none enabled. Raises ValueError (or ET.ParseError, OSError) for bad settings.
    """
    ## ES settings can have an XML declaration and several top-level nodes.
    text = re.sub(r'<\?xml[^>]*\?>', '', Path(settings_file).read_text())
    root = ET.fromstring('<settings>' + text + '</settings>')
    settings = {node.get('name'): node.get('value', '') for node in root.iter()}

    if settings.get('ProxyEnabled', '').strip().lower() != 'true':
        return {}

    ## SOCKS would need PySocks, which isn't bundled.
    if settings.get('ProxyType', 'http').strip().lower() != 'http':
        raise ValueError('only HTTP proxies are supported')

    raw = _check_value(settings.get('ProxyHost', '').strip())
    parsed = urlsplit(raw if '://' in raw else 'http://' + raw)
    host = parsed.hostname
    if (parsed.scheme != 'http' or not host or
            any(char.isspace() for char in host) or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('invalid HTTP proxy host')

    ## (.port raises ValueError for a bad one, eg: "proxy:abc", even when ProxyPort is set.)
    host_port = parsed.port
    port = int(settings.get('ProxyPort', '').strip() or host_port or 80)
    if not 1 <= port <= 65535:
        raise ValueError('invalid HTTP proxy port')

    if ':' in host:
        host = '[' + host + ']'

    credentials = parsed.netloc.rsplit('@', 1)[0] + '@' if '@' in parsed.netloc else ''
    proxy = 'http://' + credentials + host + ':' + str(port)
    no_proxy = _check_value(settings.get('ProxyNoProxy', DEFAULT_NO_PROXY).strip())

    result = {key: proxy for key in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY')}
    result.update({key: no_proxy for key in NO_PROXY_KEYS})
    return result


def setup_proxy(environ=None, settings_files=None):
    """
    Adds EmulationStation's HTTP proxy to `environ` (os.environ), unless a proxy is set
    there already (even an empty one). A no_proxy already set is kept. Returns True when
    a proxy was added. Never raises, and never logs the proxy (it can hold a password).
    """
    if environ is None:
        environ = os.environ

    if any(key in environ for key in PROXY_KEYS):
        return False

    if settings_files is None:
        settings_files = es_settings_files(environ)

    for settings_file in settings_files:
        try:
            if not settings_file.is_file():
                continue

            settings = es_proxy_settings(settings_file)

        except (OSError, ValueError, ET.ParseError) as err:
            logger.warning(f"Unable to use the proxy settings in {settings_file} ({type(err).__name__}).")
            return False

        if not settings:
            ## The frontend's settings say no proxy.
            return False

        explicit_no_proxy = next((environ[key] for key in NO_PROXY_KEYS if key in environ), None)
        for key, value in settings.items():
            if key in NO_PROXY_KEYS and explicit_no_proxy is not None:
                value = explicit_no_proxy

            environ[key] = value

        logger.info(f"Using the HTTP proxy from {settings_file}.")
        return True

    return False
