# SPDX-License-Identifier: MIT
#
# HarbourMaster's ports mixin (hm_ports.py): finding installed ports on disk (renamed
# scripts, old port.json names, broken and unknown ports), filtering, sorting and info.

import json

import pytest

from harbourmaster import util

from conftest import basic_port_files, write_port_zip


PORTS_INFO = {
    "items": {
        "Test Port.sh": "testport.zip",
        "testport/": "testport.zip",
        "Abes Adventure.sh": "abes.zip",
        "abes/": "abes.zip",
        "Shared.sh": ["one.zip", "two.zip"],
        "SPROUT.sh": "sprout.zip",
        "sprout": "sprout.zip",
        "sprout/": "sprout.zip",
        },
    "md5": {},
    "ports": {
        "testport.zip": {"date": ["2021-01-01", "2022-01-01"], "file": "testport/port.json", "items": ["Test Port.sh", "testport/"], "name": "testport.zip"},
        "abes.zip": {"date": ["2020-01-01", "2020-01-01"], "file": "abes/abes.port.json", "items": ["Abes Adventure.sh", "abes/"], "name": "abes.zip"},
        "sprout.zip": {"date": ["2025-07-16", "2025-07-16"], "file": "sprout/port.json", "items": ["SPROUT.sh", "sprout/"], "name": "sprout.zip"},
        },
    "portsmd_fix": {"cebion": ["Cebion"]},
    }


def set_ports_info(hm, data=None, **changes):
    data = json.loads(json.dumps(data or PORTS_INFO))
    data.update(changes)
    (hm.cfg_dir / "ports_info.json").write_text(json.dumps(data))
    hm._PORTS_INFO = None
    return data


@pytest.fixture
def ports_dir(hm_dirs):
    return hm_dirs['ports_dir']


def install_files(ports_dir, files):
    """Lays out port files as an install would, without harbourmaster."""
    for name, data in files.items():
        path = ports_dir / name
        if name.endswith('/'):
            path.mkdir(parents=True, exist_ok=True)
            continue

        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, dict):
            data = json.dumps(data)

        path.write_text(data)


def port_json(ports_dir, name="testport", file_name="port.json"):
    return json.loads((ports_dir / name / file_name).read_text())


@pytest.fixture
def installed(hm, hm_dirs):
    """testport.zip installed by harbourmaster."""
    zip_file = write_port_zip(hm_dirs['temp_dir'] / "testport.zip", basic_port_files())
    assert hm.install_port(str(zip_file)) == 0
    hm.load_ports()
    return hm


################################################################################
## load_ports: port.json files
def test_installed_port_found(installed):
    assert list(installed.installed_ports) == ["testport.zip"]
    assert installed.broken_ports == {}
    assert installed.unknown_ports == []


def test_old_port_json_name_is_renamed(hm, ports_dir):
    files = basic_port_files()
    files["testport/testport.port.json"] = files.pop("testport/port.json")
    install_files(ports_dir, files)

    hm.load_ports()

    assert (ports_dir / "testport" / "port.json").is_file()
    assert not (ports_dir / "testport" / "testport.port.json").exists()
    assert list(hm.installed_ports) == ["testport.zip"]


def test_old_port_json_next_to_a_new_one_is_removed(hm, ports_dir):
    files = basic_port_files()
    files["testport/testport.port.json"] = '{"old": true}'
    install_files(ports_dir, files)

    hm.load_ports()

    assert not (ports_dir / "testport" / "testport.port.json").exists()
    assert list(hm.installed_ports) == ["testport.zip"]


def test_two_old_port_jsons_are_left_alone(hm, ports_dir):
    files = basic_port_files()
    pj = files.pop("testport/port.json")
    files["testport/a.port.json"] = pj
    files["testport/b.port.json"] = pj
    install_files(ports_dir, files)

    hm.load_ports()

    assert (ports_dir / "testport" / "a.port.json").is_file()
    assert (ports_dir / "testport" / "b.port.json").is_file()


def test_three_port_jsons_with_a_new_one_are_left_alone(hm, ports_dir):
    files = basic_port_files()
    files["testport/a.port.json"] = files["testport/port.json"]
    files["testport/b.port.json"] = files["testport/port.json"]
    install_files(ports_dir, files)

    hm.load_ports()

    assert (ports_dir / "testport" / "a.port.json").is_file()
    assert list(hm.installed_ports) == ["testport.zip"]


def test_alephone_port_jsons_are_not_renamed(hm, ports_dir):
    ## alephone holds several ports' files in one folder.
    install_files(ports_dir, {"alephone/marathon.port.json": {"name": "marathon.zip", "items": ["Marathon.sh"], "attr": {}}})

    hm.load_ports()

    assert (ports_dir / "alephone" / "marathon.port.json").is_file()


@pytest.mark.parametrize("contents", ["", "{", "[]", "null", '"text"'])
def test_unreadable_port_json_is_skipped(hm, ports_dir, contents):
    files = basic_port_files()
    files["testport/port.json"] = contents
    install_files(ports_dir, files)

    hm.load_ports()

    assert hm.installed_ports == {}
    ## Its script is then a port nobody owns.
    assert hm.unknown_ports == ["Test Port.sh"]


def test_port_json_name_is_lowercased(hm, ports_dir):
    install_files(ports_dir, basic_port_files())
    pj = port_json(ports_dir)
    pj['name'] = "TestPort.ZIP"
    install_files(ports_dir, {"testport/port.json": pj})

    hm.load_ports()

    assert list(hm.installed_ports) == ["testport.zip"]
    assert port_json(ports_dir)['name'] == "testport.zip"


def test_port_json_without_a_title_uses_the_script(hm, ports_dir):
    install_files(ports_dir, basic_port_files(title=""))

    hm.load_ports()

    assert hm.installed_ports["testport.zip"]['attr']['title'] == "Test Port"


def test_port_json_gets_status_and_files(hm, ports_dir):
    install_files(ports_dir, basic_port_files())
    hm.load_ports()

    pj = port_json(ports_dir)
    assert pj['status']['status'] == "Installed"
    assert pj['status']['source'] == "Unknown"
    assert pj['files'] == {"port.json": "testport/port.json", "Test Port.sh": "Test Port.sh", "testport/": "testport/"}


def test_port_json_source_is_dropped(hm, ports_dir):
    files = basic_port_files()
    files["testport/port.json"]["source"] = {"md5": "x"}
    install_files(ports_dir, files)

    hm.load_ports()
    assert 'source' not in port_json(ports_dir)


def test_port_json_porter_string_is_a_list(hm, ports_dir):
    install_files(ports_dir, basic_port_files(porter="Somebody"))
    hm.load_ports()
    assert hm.installed_ports["testport.zip"]['attr']['porter'] == ["Somebody"]


def test_port_json_optional_items(hm, ports_dir):
    files = basic_port_files()
    files["testport/port.json"]["items_opt"] = ["testport-extra/", "missing-extra/"]
    files["testport-extra/"] = ""
    install_files(ports_dir, files)

    hm.load_ports()

    files = hm.installed_ports["testport.zip"]['files']
    assert files["testport-extra/"] == "testport-extra/"
    assert "missing-extra/" not in files


def test_port_json_without_items_is_restored_from_ports_info(hm, ports_dir):
    set_ports_info(hm)
    files = basic_port_files()
    del files["testport/port.json"]["items"]
    install_files(ports_dir, files)

    hm.load_ports()

    assert hm.installed_ports["testport.zip"]['items'] == ["Test Port.sh", "testport/"]


def test_port_json_without_items_unknown_port(hm, ports_dir):
    files = basic_port_files(name="mystery", script="Mystery.sh")
    del files["mystery/port.json"]["items"]
    install_files(ports_dir, files)

    hm.load_ports()
    assert hm.installed_ports == {}


def test_port_json_without_name_or_items(hm, ports_dir):
    install_files(ports_dir, {"testport/port.json": {"attr": {}}})
    hm.load_ports()
    assert hm.installed_ports == {}


def test_port_json_without_name_and_unknown_items(hm, ports_dir):
    set_ports_info(hm)
    install_files(ports_dir, {"thing/port.json": {"items": ["Nobody.sh"], "attr": {}}, "Nobody.sh": "#!/bin/bash\n"})
    hm.load_ports()
    assert hm.installed_ports == {}


@pytest.mark.parametrize("script, port_name", [
    ("Test Port.sh", "testport.zip"),
    ## ports_info.json keeps the script's case.
    ("Abes Adventure.sh", "abes.zip"),
    ])
def test_port_json_without_name_is_found_by_its_items(hm, ports_dir, script, port_name):
    ## ports_info.json's items are mostly strings: this took the name's first letter.
    set_ports_info(hm)
    folder = port_name[:-4]
    install_files(ports_dir, {
        f"{folder}/port.json": {"items": [script, f"{folder}/"], "attr": {"title": "x"}},
        script: "#!/bin/bash\n",
        })

    hm.load_ports()

    assert list(hm.installed_ports) == [port_name]


################################################################################
## load_ports: scripts and folders
def test_script_gets_a_signature(hm, ports_dir):
    install_files(ports_dir, basic_port_files())
    hm.load_ports()

    assert util.load_pm_signature(ports_dir / "Test Port.sh") == ["testport.zip", "Test Port.sh"]


def test_no_touchy_scripts_are_ignored(hm, ports_dir):
    install_files(ports_dir, {"Mine.sh": "#!/bin/bash\n# PORTMASTER NO TOUCHY\n"})
    hm.load_ports()

    assert hm.unknown_ports == []
    assert util.load_pm_signature(ports_dir / "Mine.sh") is None


@pytest.mark.parametrize("name", ["PortMaster.sh", "gamelist.xml", "images", "videos", "manuals", "ThemeMaster.sh", "harbourmaster"])
def test_frontend_files_are_ignored(hm, ports_dir, name):
    if "." in name:
        install_files(ports_dir, {name: "#!/bin/bash\n"})
    else:
        install_files(ports_dir, {f"{name}/": ""})

    hm.load_ports()
    assert hm.unknown_ports == []


def test_non_scripts_are_ignored(hm, ports_dir):
    install_files(ports_dir, {"readme.txt": "hello", "Game.SH": "#!/bin/bash\n"})
    hm.load_ports()

    ## Upper case .SH still counts as a script.
    assert hm.unknown_ports == ["Game.SH"]


def test_unknown_script(hm, ports_dir):
    install_files(ports_dir, {"Mystery.sh": "#!/bin/bash\n", "mystery/": ""})
    hm.load_ports()

    assert hm.unknown_ports == ["Mystery.sh"]
    assert hm.installed_ports == {}


def test_renamed_script_is_tracked(installed, ports_dir):
    (ports_dir / "Test Port.sh").rename(ports_dir / "My Favourite.sh")
    installed.load_ports()

    assert list(installed.installed_ports) == ["testport.zip"]
    assert installed.installed_ports["testport.zip"]['files']["Test Port.sh"] == "My Favourite.sh"
    assert installed.unknown_ports == []


def test_renamed_and_copied_script(installed, ports_dir):
    ## Both names exist: the port owns both.
    (ports_dir / "Copy.sh").write_bytes((ports_dir / "Test Port.sh").read_bytes())
    installed.load_ports()

    files = installed.installed_ports["testport.zip"]['files']["Test Port.sh"]
    assert sorted(files) == ["Copy.sh", "Test Port.sh"]


def test_renamed_script_found_by_md5(hm, ports_dir):
    ## An unsigned, renamed script: its md5 names the original.
    install_files(ports_dir, basic_port_files())
    script = ports_dir / "Test Port.sh"
    md5 = util.hash_file(script)
    set_ports_info(hm, md5={md5: "Test Port.sh"})
    script.rename(ports_dir / "Renamed.sh")

    hm.load_ports()

    assert hm.unknown_ports == []
    assert util.load_pm_signature(ports_dir / "Renamed.sh") == ["testport.zip", "Test Port.sh"]
    assert hm.installed_ports["testport.zip"]['files']["Test Port.sh"] == "Renamed.sh"


def test_missing_script_means_broken(installed, ports_dir):
    (ports_dir / "Test Port.sh").unlink()
    installed.load_ports()

    assert installed.installed_ports == {}
    assert list(installed.broken_ports) == ["testport.zip"]
    assert port_json(ports_dir)['status']['status'] == "Broken"

    ## And back.
    install_files(ports_dir, {"Test Port.sh": "#!/bin/bash\n"})
    installed.load_ports()
    assert list(installed.installed_ports) == ["testport.zip"]
    assert port_json(ports_dir)['status']['status'] == "Installed"


def test_missing_folder_means_broken(installed, ports_dir):
    import shutil
    shutil.move(str(ports_dir / "testport" / "port.json"), str(ports_dir / "port.json.keep"))
    shutil.rmtree(str(ports_dir / "testport"))
    (ports_dir / "testport").mkdir()
    shutil.move(str(ports_dir / "port.json.keep"), str(ports_dir / "testport" / "port.json"))
    (ports_dir / "testport").rename(ports_dir / "renamed")

    installed.load_ports()

    ## The port.json moved with its folder, the folder item is missing.
    assert list(installed.broken_ports) == ["testport.zip"]


def test_shared_script_belongs_to_nobody_new(hm, ports_dir):
    ## Two ports in ports_info claim it: no port.json is made up.
    set_ports_info(hm)
    install_files(ports_dir, {"Shared.sh": "#!/bin/bash\n"})

    hm.load_ports()

    assert hm.installed_ports == {}
    assert hm.unknown_ports == []


################################################################################
## load_ports: ports without a port.json (installed by old PortMasters)
def test_port_json_is_made_for_a_known_script(online_hm, ports_dir):
    set_ports_info(online_hm)
    install_files(ports_dir, {"SPROUT.sh": "#!/bin/bash\n", "sprout/": ""})

    online_hm.load_ports()

    assert list(online_hm.installed_ports) == ["sprout.zip"]
    pj = port_json(ports_dir, "sprout")
    ## Filled in from the source.
    assert pj['attr']['title'] == "-SPROUT-"
    assert pj['status'] == {"source": "Unknown", "md5": None, "status": "Installed"}
    assert pj['files']["port.json"] == "sprout/port.json"


def test_port_json_is_made_without_a_source(hm, ports_dir):
    set_ports_info(hm)
    install_files(ports_dir, {"Test Port.sh": "#!/bin/bash\n", "testport/": ""})

    hm.load_ports()

    pj = port_json(ports_dir)
    assert pj['name'] == "testport.zip"
    ## No title anywhere: the script's name.
    assert pj['attr']['title'] == "Test Port"
    assert pj['attr']['porter'] == []


def test_port_json_made_for_renamed_script(hm, ports_dir):
    set_ports_info(hm)
    install_files(ports_dir, {"Renamed.sh": "#!/bin/bash\n", "testport/": ""})
    util.add_pm_signature(ports_dir / "Renamed.sh", ["testport.zip", "Test Port.sh"])

    hm.load_ports()

    assert list(hm.installed_ports) == ["testport.zip"]
    assert hm.installed_ports["testport.zip"]['files']["Test Port.sh"] == "Renamed.sh"
    ## It was listed as an unknown port too.
    assert hm.unknown_ports == []


def test_port_json_cant_be_made_without_its_folder(hm, ports_dir, log_errors):
    ## ports_info says the port.json lives in a folder that isn't there.
    set_ports_info(hm)
    install_files(ports_dir, {"Test Port.sh": "#!/bin/bash\n"})

    hm.load_ports()

    assert list(hm.broken_ports) == ["testport.zip"]
    assert not (ports_dir / "testport").exists()


################################################################################
## Separate scripts folder (eg: ROMS/Ports and ports/)
def test_scripts_dir_separate(make_hm, hm_dirs, tmp_path):
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    hm_dirs['scripts_dir'] = scripts_dir
    hm = make_hm()

    zip_file = write_port_zip(hm_dirs['temp_dir'] / "testport.zip", basic_port_files())
    assert hm.install_port(str(zip_file)) == 0
    hm.load_ports()

    assert (scripts_dir / "Test Port.sh").is_file()
    assert list(hm.installed_ports) == ["testport.zip"]
    assert hm._ports_dir_is_file("Test Port.sh")
    assert hm._ports_dir_is_dir("testport")
    assert not hm._ports_dir_is_file("testport")
    assert not hm._ports_dir_is_dir("nothing")
    assert hm._ports_dir_relative_to(scripts_dir / "a.sh").as_posix() == "a.sh"
    assert hm._ports_dir_relative_to(hm_dirs['ports_dir'] / "b" / "c").as_posix() == "b/c"
    assert hm._ports_dir_file("x.sh", is_script=True) == scripts_dir / "x.sh"
    assert hm._ports_dir_file("x/") == hm_dirs['ports_dir'] / "x"


def test_get_pm_signature_non_script(hm, ports_dir):
    assert hm._get_pm_signature(ports_dir / "thing.txt") is None


################################################################################
## Attributes and filters
def make_info(name="x.zip", **attr):
    info = {"name": name, "attr": {"genres": [], "porter": [], **attr}}
    return info


@pytest.mark.parametrize("runtime, expected", [
    ("frt_3.5.2.squashfs", ["godot"]),
    (["mono-6.12.0.122-aarch64.squashfs"], ["mono"]),
    (["jdk11.squashfs", "weston_pkg_0.2.squashfs", "mesa_pkg_0.1.squashfs"], ["jre", "weston", "mesa"]),
    (["solarus-1.6.5.squashfs", "rlvm.squashfs"], ["rlvm", "solarus"]),
    (["dotnet-8.0.12.squashfs"], []),
    ])
def test_port_info_attrs_runtimes(hm, runtime, expected):
    attrs = hm.port_info_attrs(make_info(runtime=runtime))
    assert [attr for attr in attrs if attr not in ("!rtr",)] == expected


def test_port_info_attrs(hm):
    attrs = hm.port_info_attrs(make_info(genres=["Puzzle", "RPG"], porter=["Klops"], rtr=True, exp=True))
    assert attrs == ["puzzle", "rpg", "klops", "rtr", "exp"]


def test_port_info_attrs_minimal(hm):
    assert hm.port_info_attrs({"name": "x.zip"}) == ["!rtr"]


def test_port_info_attrs_installed_and_broken(hm):
    hm.installed_ports = {"a.zip": {}}
    hm.broken_ports = {"b.zip": {}}

    assert "installed" in hm.port_info_attrs({"name": "A.zip"})
    assert {"installed", "broken"} <= set(hm.port_info_attrs({"name": "b.zip"}))


@pytest.mark.parametrize("source_md5, status_md5, update", [
    ("aaa", "bbb", True),
    ("aaa", "aaa", False),
    ("aaa", None, False),
    (None, "bbb", True),
    ])
def test_port_info_attrs_update_available(hm, source_md5, status_md5, update):
    info = make_info(source={})
    info['source'] = {"md5": source_md5}
    info['status'] = {"md5": status_md5}

    assert ("update available" in hm.port_info_attrs(info)) is update


def test_match_filters(hm):
    info = make_info(genres=["puzzle"], rtr=True)

    assert hm.match_filters([], info)
    assert hm.match_filters(["PUZZLE", "rtr"], info)
    assert not hm.match_filters(["puzzle", "rpg"], info)


def test_match_filters_experimental(hm):
    info = make_info(exp=True)

    hm.cfg_data['show_experimental'] = False
    assert not hm.match_filters([], info)

    hm.cfg_data['show_experimental'] = True
    assert hm.match_filters(["exp"], info)


################################################################################
## Requirements
@pytest.mark.parametrize("attr, expected", [
    ({}, True),
    ({"reqs": None}, True),
    ({"reqs": ["opengl"]}, True),
    ({"reqs": ["!opengl"]}, False),
    ({"reqs": ["vulkan"]}, False),
    ({"reqs": ["vulkan|opengl"]}, True),
    ({"arch": ["x86_64"]}, False),
    ({"arch": ["x86_64", "aarch64"]}, True),
    ({"arch": "aarch64"}, True),
    ({"min_glibc": "2.30"}, True),
    ({"min_glibc": " 2.29 "}, True),
    ({"min_glibc": "2.31"}, False),
    ({"min_glibc": None}, True),
    ({"min_glibc": 3}, True),
    ])
def test_match_requirements(hm, attr, expected):
    assert hm.match_requirements({"name": "x.zip", "attr": attr}) is expected


def test_match_requirements_runtime_arch(hm):
    hm.runtimes_info = {
        "arm.squashfs": {"remote": {"aarch64": {}}},
        "pc.squashfs": {"remote": {"x86_64": {}}},
        }

    assert hm.match_requirements({"name": "a", "attr": {"runtime": ["arm"]}})
    assert not hm.match_requirements({"name": "b", "attr": {"runtime": ["pc.squashfs"]}})
    ## The runtime's arch wins over the port's own.
    assert hm.match_requirements({"name": "c", "attr": {"runtime": ["arm.squashfs"], "arch": ["x86_64"]}})
    ## An unknown runtime adds an empty requirement, which passes.
    assert hm.match_requirements({"name": "d", "attr": {"runtime": ["unknown"]}})


def test_match_requirements_show_all(hm):
    hm.cfg_data['show_all'] = True
    assert hm.match_requirements({"name": "x", "attr": {"reqs": ["vulkan"], "min_glibc": ""}})
    ## glibc is checked first.
    assert not hm.match_requirements({"name": "x", "attr": {"min_glibc": "9.0"}})


def test_match_requirements_debug_prints_once(hm, monkeypatch, capsys):
    from harbourmaster import config as hm_config
    monkeypatch.setattr(hm_config, "HM_DEBUG", True)
    hm.runtimes_info = {"arm.squashfs": {"remote": {"aarch64": {}}}}

    hm.match_requirements({"name": "x", "attr": {"runtime": ["arm"]}})
    hm.match_requirements({"name": "x", "attr": {"runtime": ["arm"]}})
    hm.match_requirements({"name": "y", "attr": {}})

    out = capsys.readouterr().out
    assert out.count("x: ") == 1
    assert "y: " not in out


################################################################################
## Listing and sorting
def titles(ports):
    return [info['attr']['title'] for info in ports.values()]


def test_list_ports(online_hm):
    ports = online_hm.list_ports()
    assert titles(ports) == ["-SPROUT-", "100 Lil Jumps", "2048 Plus"]


def test_list_ports_unknown_sort_is_alphabetical(online_hm):
    assert list(online_hm.list_ports(sort_by="nope")) == list(online_hm.list_ports())


def test_list_ports_reverse(online_hm):
    assert titles(online_hm.list_ports(reverse=True)) == ["2048 Plus", "100 Lil Jumps", "-SPROUT-"]


@pytest.mark.parametrize("lister", ["list_ports", "list_ports_new"])
def test_list_ports_recently_added_is_newest_first(online_hm, ports_json_data, lister):
    ports = getattr(online_hm, lister)(sort_by="recently_added")
    dates = [ports_json_data['ports'][name]['source']['date_added'] for name in ports]
    assert dates == sorted(dates, reverse=True)


@pytest.mark.parametrize("lister", ["list_ports", "list_ports_new"])
def test_list_ports_recently_updated(online_hm, ports_json_data, lister):
    ports = getattr(online_hm, lister)(sort_by="recently_updated")
    dates = [ports_json_data['ports'][name]['source']['date_updated'] for name in ports]
    assert dates == sorted(dates, reverse=True)


def test_list_ports_new_total_downloads(online_hm):
    (online_hm.cfg_dir / "port_stats.json").write_text(json.dumps({"ports": {"2048plus.zip": 50, "sprout.zip": 7}}))
    online_hm._PORTS_DOWNLOAD = None
    online_hm._PORT_INFO_CACHE.clear()

    ports = online_hm.list_ports_new(sort_by="total_downloads")
    assert list(ports)[:2] == ["2048plus.zip", "sprout.zip"]


def test_list_ports_filters(online_hm):
    assert list(online_hm.list_ports(["puzzle"])) == ["2048plus.zip"]
    assert list(online_hm.list_ports(["puzzle", "platformer"])) == []


def test_list_ports_experimental(online_hm):
    assert "starfighter.zip" not in online_hm.list_ports()

    online_hm.cfg_data['show_experimental'] = True
    online_hm._port_attrs_updated = True
    ## Its "!lowres" requirement passes at 640x480.
    assert "starfighter.zip" in online_hm.list_ports()
    assert "starfighter.zip" in online_hm.list_ports_new()


def test_list_ports_new_matches_list_ports(online_hm):
    for filters in ([], ["puzzle"], ["platformer"], ["rtr"], ["!rtr"]):
        assert sorted(online_hm.list_ports_new(filters)) == sorted(online_hm.list_ports(filters)), filters


def test_list_ports_installed_filters(online_hm, hm_dirs):
    assert online_hm.install_port("2048plus.zip") == 0
    online_hm.load_ports()
    online_hm._port_attrs_updated = True

    for lister in (online_hm.list_ports, online_hm.list_ports_new):
        assert list(lister(["installed"])) == ["2048plus.zip"]
        assert sorted(lister(["not installed"])) == ["100liljumps.zip", "sprout.zip"]

    ## Both at once: nothing.
    assert online_hm.list_ports_new(["installed", "not installed"]) == {}


def test_list_ports_installed_includes_broken(online_hm, hm_dirs):
    assert online_hm.install_port("2048plus.zip") == 0
    (hm_dirs['ports_dir'] / "2048 Plus.sh").unlink()
    online_hm.load_ports()
    online_hm._port_attrs_updated = True

    assert list(online_hm.list_ports(["installed"])) == ["2048plus.zip"]
    assert list(online_hm.list_ports_new(["installed"])) == ["2048plus.zip"]
    assert list(online_hm.list_ports_new(["broken"])) == ["2048plus.zip"]
    assert list(online_hm.list_ports_new(["installed", "broken"])) == ["2048plus.zip"]


def test_list_ports_new_incompatible_ports_are_skipped(online_hm):
    online_hm.device['capabilities'] = ["x86_64"]
    online_hm._port_attrs_updated = True

    assert sorted(online_hm.list_ports_new()) == ["2048plus.zip"]


def test_list_utils(online_hm):
    assert online_hm.list_utils() == ['gameinfo.zip', 'ags_3.6.squashfs', 'dotnet-8.0.12.squashfs', 'gmtoolkit.squashfs']


################################################################################
## Port info, sizes, images
def test_port_info_unknown(online_hm):
    assert online_hm.port_info("missing.zip") is None
    ## Cached, None included.
    assert ("missing.zip", False) in online_hm._PORT_INFO_CACHE


def test_port_info_is_cached(online_hm):
    first = online_hm.port_info("sprout.zip")
    assert online_hm.port_info("SPROUT.zip") is first


def test_port_info_downloads(online_hm):
    (online_hm.cfg_dir / "port_stats.json").write_text(json.dumps({"ports": {"sprout.zip": 99}}))
    online_hm._PORTS_DOWNLOAD = None

    assert online_hm.port_info("sprout.zip")['source']['downloads'] == 99


def test_port_info_installed_merges_the_source(online_hm):
    assert online_hm.install_port("2048plus.zip") == 0
    online_hm.load_ports()

    info = online_hm.port_info("2048plus.zip", installed=True)
    assert info['status']['status'] == "Installed"
    assert info['source']['md5']

    info = online_hm.port_info("2048plus.zip", installed=False)
    assert info['status']['status'] == "Installed"


def test_port_info_installed_only(installed):
    info = installed.port_info("testport.zip", installed=True)
    assert info['attr']['title'] == "Test Port"
    assert installed.port_info("testport.zip", installed=False) is None


def test_port_download_size_and_url(online_hm, ports_json_data):
    assert online_hm.port_download_size("2048plus.zip") == ports_json_data['ports']['2048plus.zip']['source']['size']
    assert online_hm.port_download_url("2048plus.zip") == ports_json_data['ports']['2048plus.zip']['source']['url']

    assert online_hm.port_download_size("gmtoolkit.squashfs") > 0
    assert online_hm.port_download_url("gmtoolkit.squashfs")

    assert online_hm.port_download_size("missing.zip") == 0
    assert online_hm.port_download_url("missing.zip") is None


def test_port_images_from_the_source(online_hm):
    source = online_hm.sources['pm']
    (source._images_dir / "sprout.screenshot.png").write_bytes(b"png")
    source._load_images()

    images = online_hm.port_images("sprout.zip")
    assert images == {"screenshot": source._images_dir / "sprout.screenshot.png"}


def test_port_images_none(online_hm):
    assert online_hm.port_images("sprout.zip") is None
    assert online_hm.port_images("missing.zip") is None


@pytest.mark.parametrize("image, files, expected", [
    ({}, ["screenshot.png"], "screenshot.png"),
    ({}, ["screenshot.jpg"], "screenshot.jpg"),
    ({"screenshot": "shot.png"}, ["shot.png", "screenshot.png"], "shot.png"),
    ({"screenshot": "missing.png"}, ["screenshot.png"], "screenshot.png"),
    ({"screenshot": "/etc/passwd"}, [], None),
    ({"screenshot": "../Test Port.sh"}, [], None),
    ({"screenshot": 5}, [], None),
    ({}, [], None),
    ])
def test_installed_port_images(installed, ports_dir, image, files, expected):
    for name in files:
        (ports_dir / "testport" / name).write_bytes(b"img")

    installed.installed_ports["testport.zip"]['attr']['image'] = image

    result = installed.port_images("testport.zip")
    if expected is None:
        assert result is None
    else:
        assert result == {"screenshot": ports_dir / "testport" / expected}


def test_installed_port_images_bad_port_json_entry(installed):
    installed.installed_ports["testport.zip"]['files']['port.json'] = ["a", "b"]
    assert installed.port_images("testport.zip") is None
