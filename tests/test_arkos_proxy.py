# SPDX-License-Identifier: MIT

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import quoteattr


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / 'PortMaster/arkos_proxy.py'
spec = importlib.util.spec_from_file_location('arkos_proxy', HELPER)
proxy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(proxy)


class ProxyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name) / 'es_settings.cfg'

    def configure(self, **overrides):
        values = dict(ProxyEnabled='true', ProxyType='http',
                      ProxyHost='192.0.2.10', ProxyPort='7890')
        values.update(overrides)
        self.settings.write_text('<?xml version="1.0"?>\n' + ''.join(
            '<string name=%s value=%s/>\n' % (quoteattr(key), quoteattr(value))
            for key, value in values.items()))

    def test_http_and_multi_root_xml(self):
        self.configure()
        env = proxy.proxy_environment(self.settings, {})
        for key in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY'):
            self.assertEqual(env[key], 'http://192.0.2.10:7890')
        self.assertEqual(env['no_proxy'], 'localhost,127.0.0.1,::1')

    def test_disabled_and_missing_settings(self):
        self.assertEqual(proxy.proxy_environment(self.settings, {}), {})
        self.configure(ProxyEnabled='false')
        self.assertEqual(proxy.proxy_environment(self.settings, {}), {})

    def test_explicit_environment_takes_precedence(self):
        # Existing proxy settings work even when the ArkOS file is malformed.
        self.settings.write_text('<broken>')
        for key in proxy.PROXY_KEYS:
            with self.subTest(key=key):
                inherited = {key: 'http://proxy.example:8080', 'NO_PROXY': '*'}
                self.assertEqual(proxy.proxy_environment(self.settings, inherited), inherited)
        self.assertEqual(proxy.proxy_environment(self.settings, {'https_proxy': ''}),
                         {'https_proxy': ''})

    def test_explicit_bypass_is_preserved(self):
        self.configure(ProxyNoProxy='localhost,.example')
        for key in proxy.BYPASS_KEYS:
            with self.subTest(key=key):
                env = proxy.proxy_environment(self.settings, {key: 'custom.example'})
                self.assertEqual(env['no_proxy'], 'custom.example')
                self.assertEqual(env['NO_PROXY'], 'custom.example')

    def test_malformed_xml(self):
        self.settings.write_text('<broken>')
        with self.assertRaises(proxy.ET.ParseError):
            proxy.proxy_environment(self.settings, {})

    def test_url_host_ipv6_and_credentials(self):
        for host, expected in (
                ('http://proxy.example:8000', 'http://proxy.example:7890'),
                ('[::1]', 'http://[::1]:7890'),
                ('http://user:pass%40word@proxy.example',
                 'http://user:pass%40word@proxy.example:7890')):
            with self.subTest(host=host):
                self.configure(ProxyHost=host)
                self.assertEqual(proxy.proxy_environment(self.settings, {})['http_proxy'],
                                 expected)

    def test_port_in_url(self):
        self.configure(ProxyHost='http://proxy.example:8080', ProxyPort='')
        self.assertEqual(proxy.proxy_environment(self.settings, {})['http_proxy'],
                         'http://proxy.example:8080')

    def test_invalid_settings_are_rejected(self):
        for overrides in (dict(ProxyPort='70000'), dict(ProxyPort='0'),
                          dict(ProxyPort='not-a-port'), dict(ProxyHost=''),
                          dict(ProxyHost='http://proxy.example/path'),
                          dict(ProxyType='socks5'),
                          dict(ProxyNoProxy='localhost\nLD_PRELOAD=bad.so')):
            with self.subTest(overrides=overrides):
                self.configure(**overrides)
                with self.assertRaises(ValueError):
                    proxy.proxy_environment(self.settings, {})

    def test_launcher_passes_values_after_environment_filtering(self):
        self.configure(ProxyNoProxy='localhost,.example')
        env = proxy.proxy_environment(self.settings, {})
        # Execute the actual launch line with a sudo substitute that clears env.
        launcher = (ROOT / 'PortMaster/PortMaster.sh').read_text()
        launch_line = next(line.strip() for line in launcher.splitlines()
                           if line.strip().startswith('$ESUDO env '))
        sudo = Path(self.temp.name) / 'filtered-sudo'
        sudo.write_text('#!/bin/bash\nexec env -i PATH="$PATH" "$@"\n')
        sudo.chmod(0o755)
        pugwash = Path(self.temp.name) / 'pugwash'
        pugwash.write_text('#!' + sys.executable + '\nimport os,json\n'
                           'print(json.dumps(dict(os.environ)))\n')
        pugwash.chmod(0o755)
        # Include metacharacters to establish they are literal argv values.
        env['no_proxy'] = 'localhost;$(touch should-not-exist)'
        payload = ''.join(key + '=' + value + '\n' for key, value in env.items())
        command = ('ESUDO=./filtered-sudo\nPORTMASTER_CMDS=\n'
                   'mapfile -t pm_proxy_env\n' + launch_line)
        bash = os.environ.get('BASH_TEST_EXECUTABLE', 'bash')
        result = subprocess.run([bash, '-c', command], input=payload, text=True,
                                capture_output=True, cwd=self.temp.name, check=True)
        child = json.loads(result.stdout)
        for key, value in env.items():
            self.assertEqual(child[key], value)
        self.assertFalse((Path(self.temp.name) / 'should-not-exist').exists())


if __name__ == '__main__':
    unittest.main()
