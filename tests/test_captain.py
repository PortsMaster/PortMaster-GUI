# SPDX-License-Identifier: MIT

import pytest

from harbourmaster import check_port
from harbourmaster.captain import BadPort

from conftest import basic_port_files, write_port_zip


def test_good_port(tmp_path):
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())
    extra_info = {}

    port_info = check_port("testport.zip", zip_file, extra_info)

    assert port_info['name'] == "testport.zip"
    assert sorted(port_info['items']) == ["Test Port.sh", "testport/"]
    assert port_info['attr']['title'] == "Test Port"
    assert extra_info == {
        'port_info_file': "testport/port.json",
        'gameinfo_xml': None,
        'port_dir': "testport",
        }


def test_port_without_port_json(tmp_path):
    files = basic_port_files()
    del files["testport/port.json"]
    zip_file = write_port_zip(tmp_path / "Test Port.zip", files)
    extra_info = {}

    port_info = check_port("Test Port.zip", zip_file, extra_info)

    assert port_info['name'] == "test.port.zip"
    assert extra_info['port_info_file'] == "testport/port.json"


def test_top_level_port_json_and_gameinfo_are_moved_into_port_dir(tmp_path):
    files = basic_port_files()
    files["port.json"] = files.pop("testport/port.json")
    files["gameinfo.xml"] = "<gameList />"
    zip_file = write_port_zip(tmp_path / "testport.zip", files)
    extra_info = {}

    check_port("testport.zip", zip_file, extra_info)

    assert extra_info['port_info_file'] == "testport/port.json"
    assert extra_info['gameinfo_xml'] == "testport/gameinfo.xml"


@pytest.mark.parametrize("bad_files", [
    pytest.param({"/etc/evil.sh": "x"}, id="absolute-path"),
    pytest.param({"../evil.sh": "x"}, id="parent-path"),
    pytest.param({"testport/../../evil.sh": "x"}, id="nested-parent-path"),
    ])
def test_rejects_path_traversal(tmp_path, bad_files):
    files = basic_port_files()
    files.update(bad_files)
    zip_file = write_port_zip(tmp_path / "testport.zip", files)

    with pytest.raises(BadPort):
        check_port("testport.zip", zip_file)


def test_rejects_no_directories(tmp_path):
    zip_file = write_port_zip(tmp_path / "testport.zip", {"Game.sh": "#!/bin/bash\n"})

    with pytest.raises(BadPort):
        check_port("testport.zip", zip_file)


def test_rejects_no_scripts(tmp_path):
    zip_file = write_port_zip(tmp_path / "testport.zip", {"testport/data.txt": "x"})

    with pytest.raises(BadPort):
        check_port("testport.zip", zip_file)


def test_rejects_broken_port_json(tmp_path):
    files = basic_port_files()
    files["testport/port.json"] = "{not json"
    zip_file = write_port_zip(tmp_path / "testport.zip", files)

    with pytest.raises(BadPort):
        check_port("testport.zip", zip_file)
