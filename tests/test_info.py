# SPDX-License-Identifier: MIT

import json

import pytest

from harbourmaster import port_info_load, port_info_merge
from harbourmaster.info import PORT_INFO_ATTR_ATTRS, PORT_INFO_ROOT_ATTRS


def test_load_empty_dict_fills_defaults():
    info = port_info_load({})

    assert info['version'] == PORT_INFO_ROOT_ATTRS['version']
    assert info['name'] is None
    assert set(info['attr']) == set(PORT_INFO_ATTR_ATTRS)
    assert info['attr']['runtime'] == []
    assert info['attr']['genres'] == []


def test_load_strips_unknown_root_keys_keeps_optional_ones():
    info = port_info_load({
        'version': 4,
        'name': 'game.zip',
        'junk': True,
        'source': {'md5': 'abc'},
        'attr': {'title': 'Game', 'junk_attr': 1},
        })

    assert 'junk' not in info
    ## Unknown attr keys pass through, ports.json relies on this for 'store', 'availability', etc.
    assert info['attr']['junk_attr'] == 1
    assert info['source'] == {'md5': 'abc'}
    assert info['attr']['title'] == 'Game'


def test_load_v1_upgrade():
    info = port_info_load({
        'version': 1,
        'source': 'some/where/game.zip',
        'md5': 'abc',
        'attr': {'title': 'Game', 'runtime': 'mono.squashfs', 'porter': 'someone'},
        })

    assert info['version'] == 4
    assert info['name'] == 'game.zip'
    assert info['status']['md5'] == 'abc'
    assert info['attr']['runtime'] == ['mono.squashfs']
    assert info['attr']['porter'] == ['someone']


def test_load_v3_blank_runtime():
    info = port_info_load({'version': 3, 'attr': {'runtime': 'blank'}})
    assert info['attr']['runtime'] == []


@pytest.mark.parametrize('version', [1, 2, 3, "3"])
@pytest.mark.parametrize('info', [{}, {'attr': {}}, {'attr': {'title': "Game"}}], ids=['no-attr', 'empty-attr', 'no-runtime'])
def test_load_old_version_without_runtime(version, info):
    ## Hand-written port.json files leave these out; this stopped PortMaster starting.
    info = port_info_load(dict(info, version=version))

    assert info['version'] == 4
    assert info['attr']['runtime'] == []
    assert set(info['attr']) == set(PORT_INFO_ATTR_ATTRS)


@pytest.mark.parametrize('runtime, expected', [
    (None, []),
    ("mono.squashfs", ["mono.squashfs"]),
    (["a.squashfs", "b.squashfs"], ["a.squashfs", "b.squashfs"]),
    ])
def test_load_v3_runtime_upgrade(runtime, expected):
    assert port_info_load({'version': 3, 'attr': {'runtime': runtime}})['attr']['runtime'] == expected


VALUES = [None, True, 0, 1.5, "", "x", "blank", [], [None], [1, "a"], ["a"], {}, {"a": 1}]


@pytest.mark.parametrize('version', [None, 1, 2, 3, 4, 5, "3", "x", True, -1, 2.0])
def test_load_never_raises(version):
    ## Every attr and root key with every type of value, at every version.
    infos = [{}, *({'attr': value} for value in VALUES)]
    infos += [{key: value, 'attr': {}} for key in ('name', 'items', 'items_opt', 'status', 'files', 'source', 'md5') for value in VALUES]
    infos += [{'attr': {key: value}} for key in PORT_INFO_ATTR_ATTRS for value in VALUES]

    for info in infos:
        if version is not None:
            info['version'] = version

        for do_default in (True, False):
            loaded = port_info_load(json.loads(json.dumps(info)), do_default=do_default)
            if loaded is not None:
                port_info_merge(port_info_load({}), loaded)


@pytest.mark.parametrize('status', ["Installed", ["Installed"], 1, True])
def test_load_bad_status_is_dropped(status):
    assert 'status' not in port_info_load({'name': 'game.zip', 'status': status})


def test_load_status_values_are_cleaned():
    info = port_info_load({'name': 'game.zip', 'status': {'source': ["x"], 'status': "Installed", 'md5': 5}})
    assert info['status'] == {'status': "Installed", 'md5': None}


@pytest.mark.parametrize('source', ["github", ["x"], 1, None])
def test_load_bad_source_is_dropped(source):
    assert 'source' not in port_info_load({'name': 'game.zip', 'source': source})


def test_load_source_values_are_cleaned():
    ## Sorted by and compared with numbers, so the wrong types would crash the ports list.
    info = port_info_load({'name': 'game.zip', 'source': {
        'md5': None, 'url': "https://x/game.zip", 'size': "100", 'downloads': -1,
        'date_added': None, 'date_updated': "2024-01-01", 'release_id': 7}})

    assert info['source'] == {'url': "https://x/game.zip", 'date_updated': "2024-01-01"}


def test_load_size_must_be_a_number():
    assert port_info_load({'source': {'size': True}})['source'] == {}
    assert port_info_load({'source': {'size': 10}})['source'] == {'size': 10}


@pytest.mark.parametrize('files', ["port.json", ["port.json"], 1])
def test_load_bad_files_are_emptied(files):
    assert port_info_load({'name': 'game.zip', 'files': files})['files'] == {}


def test_load_unsafe_files_are_dropped():
    ## Uninstalling deletes the values, and muOS makes folders from the keys.
    info = port_info_load({'name': 'game.zip', 'files': {
        'port.json': "game/port.json",
        'Game.sh': ["Game.sh", "../Other.sh", None],
        '../../escape.sh': "escape.sh",
        'game/': "/etc",
        'data/': {"a": 1},
        'more/': ["more/", "also/"],
        }})

    assert info['files'] == {'port.json': "game/port.json", 'Game.sh': "Game.sh", 'more/': ["more/", "also/"]}


@pytest.mark.parametrize('name', [1, ["game.zip"], "", "  "])
def test_load_bad_name_is_none(name):
    assert port_info_load({'name': name})['name'] is None


@pytest.mark.parametrize('min_glibc, expected', [
    ("2.31", "2.31"), (" 2.35 ", " 2.35 "), ("2", "2"), ("abc", ""), ("2.a", ""), ("2.31-r1", ""), (2.31, "2.31"), (None, "")])
def test_load_min_glibc_must_be_a_version(min_glibc, expected):
    ## It is compared with the device's glibc: "abc" crashed the ports list.
    assert port_info_load({'attr': {'min_glibc': min_glibc}})['attr']['min_glibc'] == expected


def test_load_runtimes_are_file_names():
    info = port_info_load({'attr': {'runtime': ["mono.squashfs", "../../x.squashfs", "a/b.squashfs", "", "x" * 300, "a\x00b"]}})
    assert info['attr']['runtime'] == ["mono.squashfs"]


@pytest.mark.parametrize('item, safe', [
    ("Game.sh", True), ("game/", True), ("game/data", True),
    ("a\x00b", False), ("x" * 256, False), ("x" * 255, True), ("game/" + "x" * 256, False), ("日" * 86, False)])
def test_safe_port_item_names(item, safe):
    from harbourmaster.info import is_safe_port_item
    assert is_safe_port_item(item) == safe


def test_load_string_version_and_reqs_dict():
    info = port_info_load({'version': '4', 'attr': {'reqs': {'opengl': True, 'power': True}}})

    assert info['version'] == 4
    assert sorted(info['attr']['reqs']) == ['opengl', 'power']


def test_load_rejects_newer_version():
    assert port_info_load({'version': 99}) is None
    assert port_info_load({'version': 99}, do_default=True)['version'] == 4


def test_load_drops_unsafe_items():
    info = port_info_load({
        'items': ['Game.sh', '/etc/passwd', '../escape', 'game/../../escape', 'game/'],
        'items_opt': ['/abs'],
        })

    assert info['items'] == ['Game.sh', 'game/']
    assert info['items_opt'] is None


def test_load_filters_unknown_genres():
    info = port_info_load({'attr': {'genres': ['Puzzle', 'not-a-genre']}})
    assert info['attr']['genres'] == ['puzzle']


def test_load_from_path(tmp_path):
    port_json = tmp_path / "port.json"
    port_json.write_text(json.dumps({'version': 4, 'name': 'game.zip'}))

    assert port_info_load(port_json)['name'] == 'game.zip'


def test_load_from_path_string(tmp_path):
    port_json = tmp_path / "port.json"
    port_json.write_text(json.dumps({'version': 4, 'name': 'game.zip'}))

    assert port_info_load(str(port_json))['name'] == 'game.zip'


def test_load_from_bad_path(tmp_path):
    port_json = tmp_path / "port.json"
    port_json.write_text("{not json")

    assert port_info_load(port_json) is None
    assert port_info_load(port_json, do_default=True)['name'] is None


def test_load_from_json_string():
    assert port_info_load('{"version": 4, "name": "game.zip"}')['name'] == 'game.zip'


def test_merge_fills_blanks_only():
    port_info = port_info_load({'name': 'game.zip', 'attr': {'title': 'Mine', 'desc': ''}})
    other = port_info_load({
        'name': 'other.zip',
        'source': {'md5': 'abc'},
        'attr': {'title': 'Theirs', 'desc': 'From source', 'runtime': ['mono.squashfs'], 'rtr': True},
        })

    port_info_merge(port_info, other)

    assert port_info['name'] == 'game.zip'
    assert port_info['attr']['title'] == 'Mine'
    assert port_info['attr']['desc'] == 'From source'
    assert port_info['attr']['runtime'] == ['mono.squashfs']
    assert port_info['attr']['rtr'] is True
    assert port_info['source'] == {'md5': 'abc'}
