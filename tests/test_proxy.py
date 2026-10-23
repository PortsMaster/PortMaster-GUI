# SPDX-License-Identifier: MIT
#
# HTTP proxy settings from EmulationStation's es_settings.cfg (ArkOS4Clone's Wi-Fi
# settings), set up by pugwash and harbourmaster after sudo.

from pathlib import Path
from types import SimpleNamespace
from xml.sax.saxutils import quoteattr

import pytest

from harbourmaster.util import proxy


PROXY = 'http://192.0.2.10:7890'

## conftest's no_real_proxy_settings swaps it out during tests.
es_settings_files = proxy.es_settings_files


def capture_log(level):
    from loguru import logger

    messages = []
    handler_id = logger.add(lambda message: messages.append(message.record["message"]), level=level)
    return messages, handler_id


@pytest.fixture
def log_warnings():
    from loguru import logger

    messages, handler_id = capture_log("WARNING")
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def log_messages():
    from loguru import logger

    messages, handler_id = capture_log("DEBUG")
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def settings(tmp_path):
    settings_file = tmp_path / "home" / ".emulationstation" / "es_settings.cfg"
    settings_file.parent.mkdir(parents=True)

    def write(**overrides):
        values = dict(ProxyEnabled='true', ProxyType='http', ProxyHost='192.0.2.10', ProxyPort='7890')
        values.update(overrides)
        settings_file.write_text('<?xml version="1.0"?>\n' + ''.join(
            f'<string name={quoteattr(key)} value={quoteattr(value)} />\n'
            for key, value in values.items() if value is not None))
        return settings_file

    write.path = settings_file
    return write


def setup_with(environ, *files):
    return proxy.setup_proxy(environ, settings_files=list(files))


################################################################################
## es_settings.cfg
def test_http_proxy(settings):
    env = proxy.es_proxy_settings(settings())

    for key in ('http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY'):
        assert env[key] == PROXY
    assert env['no_proxy'] == env['NO_PROXY'] == 'localhost,127.0.0.1,::1'


def test_settings_in_a_config_root(settings):
    ## Some ES builds write one <config> root, others several top-level nodes.
    settings.path.write_text(
        '<?xml version="1.0"?>\n<config>\n'
        '\t<bool name="ProxyEnabled" value="true" />\n'
        '\t<string name="ProxyHost" value="proxy.lan" />\n'
        '\t<string name="ProxyPort" value="3128" />\n'
        '</config>\n')

    assert proxy.es_proxy_settings(settings.path)['http_proxy'] == 'http://proxy.lan:3128'


@pytest.mark.parametrize('enabled', ['false', '', None])
def test_proxy_disabled(settings, enabled):
    assert proxy.es_proxy_settings(settings(ProxyEnabled=enabled)) == {}


@pytest.mark.parametrize('host, expected', [
    ('http://proxy.example:8000', 'http://proxy.example:7890'),
    ('[::1]', 'http://[::1]:7890'),
    ('http://user:pass%40word@proxy.example', 'http://user:pass%40word@proxy.example:7890'),
    ])
def test_proxy_hosts(settings, host, expected):
    assert proxy.es_proxy_settings(settings(ProxyHost=host))['http_proxy'] == expected


def test_port_from_the_host(settings):
    assert proxy.es_proxy_settings(settings(ProxyHost='http://proxy.example:8080', ProxyPort=''))['http_proxy'] == 'http://proxy.example:8080'


def test_default_port(settings):
    assert proxy.es_proxy_settings(settings(ProxyPort=''))['http_proxy'] == 'http://192.0.2.10:80'


def test_no_proxy_from_the_settings(settings):
    assert proxy.es_proxy_settings(settings(ProxyNoProxy='localhost,.lan'))['no_proxy'] == 'localhost,.lan'


@pytest.mark.parametrize('overrides', [
    dict(ProxyPort='70000'), dict(ProxyPort='0'), dict(ProxyPort='not-a-port'),
    dict(ProxyHost=''), dict(ProxyHost='http://proxy.example/path'), dict(ProxyHost='proxy.example:abc'),
    dict(ProxyHost='https://proxy.example'), dict(ProxyType='socks5'),
    dict(ProxyHost='proxy\nLD_PRELOAD=bad.so'), dict(ProxyNoProxy='localhost\nLD_PRELOAD=bad.so'),
    ], ids=lambda overrides: ','.join(overrides))
def test_bad_settings(settings, overrides):
    with pytest.raises(ValueError):
        proxy.es_proxy_settings(settings(**overrides))


################################################################################
## setup_proxy
def test_setup_adds_the_proxy(settings):
    environ = {}

    assert setup_with(environ, settings()) is True
    assert environ['https_proxy'] == PROXY
    assert environ['no_proxy'] == 'localhost,127.0.0.1,::1'


@pytest.mark.parametrize('key', proxy.PROXY_KEYS)
@pytest.mark.parametrize('value', ['http://other:8080', ''])
def test_a_proxy_already_set_wins(settings, key, value):
    ## Even an empty one: that's someone saying no proxy. The settings aren't even read.
    settings.path.write_text('<broken')
    environ = {key: value}

    assert setup_with(environ, settings.path) is False
    assert environ == {key: value}


@pytest.mark.parametrize('key', proxy.NO_PROXY_KEYS)
def test_no_proxy_already_set_is_kept(settings, key):
    environ = {key: 'custom.example'}

    setup_with(environ, settings(ProxyNoProxy='localhost'))

    assert environ['no_proxy'] == environ['NO_PROXY'] == 'custom.example'
    assert environ['http_proxy'] == PROXY


def test_no_settings_file(tmp_path):
    environ = {}
    assert setup_with(environ, tmp_path / "missing.cfg") is False
    assert environ == {}


def test_disabled_proxy_stops_looking(settings, tmp_path):
    ## The first settings file found is the frontend's: a later one isn't used.
    other = tmp_path / "other.cfg"
    other.write_text(settings(ProxyHost='other.example').read_text())
    settings(ProxyEnabled='false')

    environ = {}
    assert setup_with(environ, settings.path, other) is False
    assert environ == {}


@pytest.mark.parametrize('contents', ['<broken', '\xff\xfe', None])
def test_bad_settings_file_is_logged_without_the_proxy(settings, contents, log_warnings):
    if contents is None:
        settings(ProxyHost='http://user:secret@proxy.example', ProxyPort='99999')
    else:
        settings.path.write_bytes(contents.encode('latin-1'))

    environ = {}
    assert setup_with(environ, settings.path) is False
    assert environ == {}
    assert len(log_warnings) == 1
    assert 'secret' not in log_warnings[0] and 'proxy.example' not in log_warnings[0]


def test_unreadable_settings_file(settings, monkeypatch, log_warnings):
    settings()
    monkeypatch.setattr(Path, "read_text", lambda self, *args, **kwargs: (_ for _ in ()).throw(PermissionError(13, "denied")))

    assert setup_with({}, settings.path) is False
    assert "PermissionError" in log_warnings[0]


def test_the_proxy_isnt_logged(settings, log_messages):
    setup_with({}, settings(ProxyHost='http://user:secret@proxy.example'))

    assert log_messages
    assert not any('secret' in message or 'proxy.example' in message for message in log_messages)


################################################################################
## Where es_settings.cfg is
def test_settings_files_sudo_user_first(monkeypatch):
    import pwd
    monkeypatch.setattr(pwd, "getpwnam", lambda name: SimpleNamespace(pw_dir=f"/home/{name}"))

    files = es_settings_files({'SUDO_USER': 'ark', 'HOME': '/root'})

    assert files == [Path('/home/ark/.emulationstation/es_settings.cfg'), Path('/root/.emulationstation/es_settings.cfg')]


def test_settings_files_unknown_sudo_user(monkeypatch):
    import pwd

    def missing(name):
        raise KeyError(name)

    monkeypatch.setattr(pwd, "getpwnam", missing)

    files = es_settings_files({'SUDO_USER': 'nobody-here', 'HOME': '/root'})

    assert files == [Path('/root/.emulationstation/es_settings.cfg'), Path('/home/ark/.emulationstation/es_settings.cfg')]


def test_settings_files_root_without_a_home():
    files = es_settings_files({})
    assert files == [Path('/home/ark/.emulationstation/es_settings.cfg')]


def test_requests_uses_it(settings, monkeypatch):
    ## The point of it all: the bundled requests picks the proxy up from the environment.
    import os
    import requests

    for key in proxy.PROXY_KEYS + proxy.NO_PROXY_KEYS:
        monkeypatch.setenv(key, "")
        monkeypatch.delenv(key)

    settings()
    monkeypatch.setattr(proxy, "es_settings_files", lambda environ: [settings.path])

    assert proxy.setup_proxy() is True
    assert os.environ['https_proxy'] == PROXY
    assert requests.utils.get_environ_proxies("https://github.com/PortsMaster")['https'] == PROXY
    assert requests.utils.get_environ_proxies("http://localhost:8000/") == {}
