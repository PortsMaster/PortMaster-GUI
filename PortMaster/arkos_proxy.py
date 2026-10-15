# SPDX-License-Identifier: MIT

"""Print proxy environment assignments for PortMaster's sudo launch."""

import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit


PROXY_KEYS = ('http_proxy', 'https_proxy', 'all_proxy',
              'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY')
BYPASS_KEYS = ('no_proxy', 'NO_PROXY')


def check_value(value):
    # Each assignment is one line consumed by Bash's mapfile, never eval.
    if any(ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError('control character in proxy setting')
    return value


def proxy_environment(settings_file, environ):
    """Prefer explicit proxy variables, otherwise import ArkOS HTTP settings."""
    inherited = {key: check_value(environ[key])
                 for key in PROXY_KEYS + BYPASS_KEYS if key in environ}
    if any(key in inherited for key in PROXY_KEYS):
        return inherited

    settings_file = Path(settings_file)
    if not settings_file.is_file():
        return inherited

    # ES settings can contain an XML declaration and multiple top-level nodes.
    text = re.sub(r'<\?xml[^>]*\?>', '', settings_file.read_text())
    root = ET.fromstring('<settings>' + text + '</settings>')
    settings = {node.get('name'): node.get('value', '') for node in root.iter()}
    if settings.get('ProxyEnabled', '').lower() != 'true':
        return inherited
    if settings.get('ProxyType', 'http').strip().lower() != 'http':
        raise ValueError('only HTTP proxies are supported by this importer')

    raw = check_value(settings.get('ProxyHost', '').strip())
    parsed = urlsplit(raw if '://' in raw else 'http://' + raw)
    host = parsed.hostname
    if (parsed.scheme != 'http' or not host or
            any(char.isspace() for char in host) or
            parsed.path not in ('', '/') or parsed.query or parsed.fragment):
        raise ValueError('invalid HTTP proxy host')
    port = int(settings.get('ProxyPort', '').strip() or parsed.port or 80)
    if not 1 <= port <= 65535:
        raise ValueError('invalid HTTP proxy port')
    if ':' in host:
        host = '[' + host + ']'
    credentials = parsed.netloc.rsplit('@', 1)[0] + '@' if '@' in parsed.netloc else ''
    proxy = 'http://' + credentials + host + ':' + str(port)
    bypass = check_value(inherited.get('no_proxy', inherited.get('NO_PROXY',
                         settings.get('ProxyNoProxy', 'localhost,127.0.0.1,::1'))))
    result = {key: proxy for key in ('http_proxy', 'https_proxy',
                                   'HTTP_PROXY', 'HTTPS_PROXY')}
    result.update({key: bypass for key in BYPASS_KEYS})
    result.update(inherited)
    return result


def main():
    settings_file = Path.home() / '.emulationstation/es_settings.cfg'
    # A root launch may retain neither the user's HOME nor SUDO_USER.
    if not settings_file.is_file():
        settings_file = Path('/home/ark/.emulationstation/es_settings.cfg')
    try:
        environment = proxy_environment(settings_file, os.environ)
    except (OSError, ValueError, ET.ParseError) as err:
        # Do not include configuration values or proxy credentials in logs.
        print('PortMaster: unable to import proxy settings (%s).' %
              type(err).__name__, file=sys.stderr)
        return
    for key, value in environment.items():
        print(key + '=' + value)


if __name__ == '__main__':
    main()
