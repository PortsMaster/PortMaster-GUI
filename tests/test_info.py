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
