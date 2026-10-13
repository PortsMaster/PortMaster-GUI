# SPDX-License-Identifier: MIT
#
# Installing ports: bad data, layouts, failures part way, runtimes, gamelists,
# themes and the artwork of ports that are not in any source.

import hashlib
import io
import json
import zipfile

from types import SimpleNamespace

import pytest

import harbourmaster
from harbourmaster import hm_install, hm_runtimes

from conftest import basic_port_files, port_files_with, write_port_zip, write_raw_zip


def zip_bytes(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as zf:
        for name, data in files.items():
            zf.writestr(name, json.dumps(data) if isinstance(data, dict) else data)

    return buffer.getvalue()


def ports_left(hm_dirs):
    return sorted(p.name for p in hm_dirs['ports_dir'].iterdir())


def failure_reasons(callback):
    return [m for m in callback.messages if m.startswith("Installation failed:")]


################################################################################
## Bad data that can't be installed: rejected, nothing left behind, and the reason
## is logged and reported (message boxes are disabled in fifo/autoinstall mode).
UNUSABLE = {
    'not_a_zip':      lambda t: write_raw_zip(t / "testport.zip", b"this is not a zip file"),
    'empty_file':     lambda t: write_raw_zip(t / "testport.zip", b""),
    'truncated_zip':  lambda t: write_raw_zip(t / "testport.zip", zip_bytes(basic_port_files())[:200]),
    'json_invalid':   lambda t: write_port_zip(t / "testport.zip", port_files_with(port_json="{nope")),
    'json_list':      lambda t: write_port_zip(t / "testport.zip", port_files_with(port_json="[1, 2]")),
    'version_text':   lambda t: write_port_zip(t / "testport.zip", port_files_with(port_json={"version": "abc"})),
    'version_future': lambda t: write_port_zip(t / "testport.zip", port_files_with(port_json={"version": 99})),
    'attr_list':      lambda t: write_port_zip(t / "testport.zip", port_files_with(port_json={"attr": [1, 2]})),
    'no_script':      lambda t: write_port_zip(t / "testport.zip", port_files_with(drop=["Test Port.sh"])),
    'no_directory':   lambda t: write_port_zip(t / "testport.zip", {"Test Port.sh": "#!/bin/bash\n"}),
    'path_traversal': lambda t: write_port_zip(t / "testport.zip", port_files_with(extra={"../evil.sh": "x"})),
    }


@pytest.mark.parametrize("case", sorted(UNUSABLE))
def test_unusable_port_is_rejected(case, hm, hm_dirs, tmp_path, callback):
    zip_file = UNUSABLE[case](tmp_path)

    assert hm.install_port(str(zip_file)) == 255
    assert ports_left(hm_dirs) == []
    assert callback.message_boxes[-1] == "Port testport.zip installed failed."

    hm.load_ports()
    assert hm.installed_ports == {}


@pytest.mark.parametrize("case", sorted(UNUSABLE))
def test_unusable_port_reason_is_reported(case, hm, tmp_path, callback, log_errors):
    zip_file = UNUSABLE[case](tmp_path)

    hm.install_port(str(zip_file))

    assert log_errors, "nothing was logged"
    reasons = failure_reasons(callback)
    assert len(reasons) == 1 and len(reasons[0]) > len("Installation failed: ")


################################################################################
## Odd but recoverable port.json types: installed, normalised, and the port still
## works in the ports list / filters afterwards.
ODD_TYPES = {
    'items_text':    {"port_json": {"items": "Test Port.sh"}},
    'genres_text':   {"attr": {"genres": "puzzle"}},
    'porter_number': {"attr": {"porter": 5}},
    'runtime_number': {"attr": {"runtime": 5}},
    'reqs_text':     {"attr": {"reqs": "opengl"}},
    'arch_text':     {"attr": {"arch": "aarch64"}},
    'title_none':    {"attr": {"title": None}},
    'desc_number':   {"attr": {"desc": 42}},
    'image_text':    {"attr": {"image": "screenshot.png"}},
    'genres_mixed':  {"attr": {"genres": ["puzzle", 7, None]}},
    }

@pytest.mark.parametrize("case", sorted(ODD_TYPES))
def test_odd_port_json_types(case, hm, hm_dirs, tmp_path):
    zip_file = write_port_zip(tmp_path / "testport.zip", port_files_with(**ODD_TYPES[case]))

    assert hm.install_port(str(zip_file)) == 0
    hm.load_ports()

    ## The ports list, filters and port info all have to cope with it.
    ports = hm.list_ports_new(['installed'])
    assert list(ports) == ["testport.zip"]
    hm.list_ports_names_new(['puzzle'])

    attr = ports["testport.zip"]['attr']
    for key in ('genres', 'porter', 'runtime', 'reqs', 'arch'):
        assert isinstance(attr[key], list) and all(isinstance(v, str) for v in attr[key]), (key, attr[key])

    for key in ('title', 'desc', 'inst'):
        assert isinstance(attr[key], str), (key, attr[key])

    assert isinstance(attr['image'], dict)


################################################################################
## Zip layouts
def test_top_level_port_json_and_gameinfo_go_into_the_port_dir(hm, hm_dirs, tmp_path):
    files = basic_port_files()
    files["port.json"] = files.pop("testport/port.json")
    files["gameinfo.xml"] = "<gameList />"

    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", files))) == 0

    ports_dir = hm_dirs['ports_dir']
    assert ports_left(hm_dirs) == ["Test Port.sh", "testport"]
    assert (ports_dir / "testport" / "port.json").is_file()
    assert (ports_dir / "testport" / "gameinfo.xml").is_file()


def test_named_port_json_is_renamed(hm, hm_dirs, tmp_path):
    files = basic_port_files()
    files["testport/testport.port.json"] = files.pop("testport/port.json")

    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", files))) == 0

    port_dir = hm_dirs['ports_dir'] / "testport"
    assert (port_dir / "port.json").is_file()
    assert not (port_dir / "testport.port.json").exists()

    hm.load_ports()
    assert list(hm.installed_ports) == ["testport.zip"]


def test_separate_scripts_dir(tmp_path, callback):
    ## Like muOS / JELOS, where the scripts and the port data live apart.
    dirs = {name: tmp_path / name for name in ('tools', 'ports', 'scripts', 'temp')}
    for path in dirs.values():
        path.mkdir()

    hm = harbourmaster.HarbourMaster(
        {'offline': True, 'no-check': True}, callback=callback,
        tools_dir=dirs['tools'], ports_dir=dirs['ports'], scripts_dir=dirs['scripts'], temp_dir=dirs['temp'])

    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())
    assert hm.install_port(str(zip_file)) == 0

    assert sorted(p.name for p in dirs['scripts'].iterdir()) == ["Test Port.sh"]
    assert sorted(p.name for p in dirs['ports'].iterdir()) == ["testport"]

    hm.load_ports()
    assert list(hm.installed_ports) == ["testport.zip"]

    assert hm.uninstall_port("testport.zip") == 0
    assert list(dirs['scripts'].iterdir()) == []
    assert list(dirs['ports'].iterdir()) == []


def test_reinstall_upgrades_files(hm, hm_dirs, tmp_path):
    v1 = port_files_with(extra={"testport/data.txt": "v1", "testport/old.txt": "only in v1"})
    v2 = port_files_with(extra={"testport/data.txt": "v2", "testport/new.txt": "only in v2"})

    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", v1))) == 0
    (tmp_path / "testport.zip").unlink()
    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", v2))) == 0

    port_dir = hm_dirs['ports_dir'] / "testport"
    assert (port_dir / "data.txt").read_text() == "v2"
    assert (port_dir / "new.txt").is_file()
    ## Files removed from a port are left alone (ports are installed over the top).
    assert (port_dir / "old.txt").is_file()

    hm.load_ports()
    assert list(hm.installed_ports) == ["testport.zip"]


def test_permissions_fixed_on_linux_filesystems(hm, tmp_path, monkeypatch):
    chmods = []
    monkeypatch.setattr(hm_install, "get_path_fs", lambda path: "ext4")
    monkeypatch.setattr(hm_install.subprocess, "check_output", lambda args: chmods.append(args))

    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", basic_port_files()))) == 0

    fixed = sorted(args[-1].rsplit('/', 1)[-1] for args in chmods)
    assert all(args[:3] == ['chmod', '-R', '777'] for args in chmods)
    assert fixed == ["Test Port.sh", "testport"]


def test_permissions_left_alone_on_fat(hm, tmp_path, monkeypatch):
    chmods = []
    monkeypatch.setattr(hm_install, "get_path_fs", lambda path: "vfat")
    monkeypatch.setattr(hm_install.subprocess, "check_output", lambda args: chmods.append(args))

    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", basic_port_files()))) == 0
    assert chmods == []


################################################################################
## Failing part way through
@pytest.fixture
def failing_extract(monkeypatch):
    real_extract = zipfile.ZipFile.extract
    calls = []

    def extract(self, member, path=None, pwd=None):
        calls.append(member)
        if len(calls) == 3:
            raise OSError(28, "No space left on device")

        return real_extract(self, member, path, pwd)

    monkeypatch.setattr(zipfile.ZipFile, "extract", extract)
    return calls


def test_failure_part_way_rolls_back(failing_extract, hm, hm_dirs, tmp_path, callback):
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())

    assert hm.install_port(str(zip_file)) == 255
    assert len(failing_extract) == 3
    assert ports_left(hm_dirs) == []
    assert callback.message_boxes[-1] == "Port testport.zip installed failed."


def test_failure_part_way_is_reported(failing_extract, hm, tmp_path, callback, log_errors):
    zip_file = write_port_zip(tmp_path / "testport.zip", basic_port_files())

    hm.install_port(str(zip_file))

    assert any("No space left on device" in e for e in log_errors)
    assert any("No space left on device" in m for m in failure_reasons(callback))


################################################################################
## Ports that don't match the device
class GuiCallback(harbourmaster.Callback):
    IS_GUI = True

    def __init__(self, answer):
        super().__init__()
        self.answer = answer
        self.messages = []
        self.message_boxes = []

    def message(self, message):
        self.messages.append(message)

    def message_box(self, message, want_cancel=False, ok_text=None, cancel_text=None):
        self.message_boxes.append(message)
        return self.answer

    from contextlib import contextmanager

    @contextmanager
    def enable_messagebox(self):
        yield


@pytest.mark.parametrize("answer, expected", [(True, 255), (False, 0)])
def test_incompatible_port_asks_first_in_the_gui(answer, expected, hm_dirs, tmp_path):
    ## The "OK" button of that box is labelled Cancel, so True means "don't install".
    callback = GuiCallback(answer)
    hm = harbourmaster.HarbourMaster({'offline': True, 'no-check': True}, callback=callback, **hm_dirs)
    zip_file = write_port_zip(tmp_path / "testport.zip", port_files_with(attr={"arch": ["x86_64"]}))

    assert hm.install_port(str(zip_file)) == expected
    assert "INCOMPATIBLE WITH YOUR DEVICE" in callback.message_boxes[0]
    assert bool(ports_left(hm_dirs)) is (expected == 0)


################################################################################
## Runtimes
RUNTIME = "dotnet-8.0.12.squashfs"


@pytest.fixture
def runtime_port(tmp_path):
    return write_port_zip(tmp_path / "testport.zip", port_files_with(attr={"runtime": [RUNTIME], "title": "Runtime Port"}))


@pytest.fixture
def runtime_server(online_hm, monkeypatch):
    """Serves the runtime download, `result` can be set to None to fail it."""
    server = SimpleNamespace(data=b"runtime data", result="ok", downloads=[])

    def download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        server.downloads.append(file_url)
        if server.result is None:
            return None

        file_name.write_bytes(server.data)
        return file_name

    monkeypatch.setattr(hm_runtimes, "download", download)
    online_hm.runtimes_info[RUNTIME]['remote']['aarch64']['md5'] = hashlib.md5(server.data).hexdigest()
    return server


def test_runtime_downloaded_with_port(online_hm, runtime_port, runtime_server, callback):
    assert online_hm.install_port(str(runtime_port)) == 0

    assert len(runtime_server.downloads) == 1
    assert (online_hm.libs_dir / RUNTIME).read_bytes() == b"runtime data"
    assert online_hm.runtimes_info[RUNTIME]['local']['status'] == "Verified"
    assert "installed successfully" in callback.message_boxes[-1]


def test_runtime_already_verified_is_not_downloaded(online_hm, runtime_port, runtime_server, callback):
    (online_hm.libs_dir / RUNTIME).write_bytes(b"runtime data")

    assert online_hm.install_port(str(runtime_port)) == 0

    assert runtime_server.downloads == []
    assert any(m.startswith("Verified ") for m in callback.messages)


def test_runtime_download_failure_is_reported(online_hm, runtime_port, runtime_server, callback):
    runtime_server.result = None

    assert online_hm.install_port(str(runtime_port)) == 0

    assert not (online_hm.libs_dir / RUNTIME).exists()
    assert online_hm.runtimes_info[RUNTIME].get('local', {}).get('status') != "Verified"
    assert "failed to install" in callback.message_boxes[-1]


def test_unknown_runtime(online_hm, tmp_path, callback, log_errors):
    zip_file = write_port_zip(tmp_path / "testport.zip", port_files_with(attr={"runtime": ["nothing.squashfs"], "arch": []}))

    ## The port itself installs, the runtime part fails.
    assert online_hm.install_port(str(zip_file)) == 0
    assert "failed to install" in callback.message_boxes[-1]
    assert any("Unknown runtime" in e for e in log_errors)


def test_runtime_missing_while_offline(online_hm, runtime_port, runtime_server, callback):
    online_hm.config['offline'] = True

    assert online_hm.install_port(str(runtime_port)) == 0

    assert runtime_server.downloads == []
    assert "failed to install" in callback.message_boxes[-1]


################################################################################
## gameinfo.xml -> the CFW's gamelist
@pytest.mark.parametrize("enabled", [True, False])
def test_gameinfo_added_to_gamelist(enabled, hm, hm_dirs, tmp_path, monkeypatch):
    added = []
    monkeypatch.setattr(hm.platform, "gamelist_add", lambda path: added.append(path))
    hm.cfg_data['gamelist_update'] = enabled

    files = port_files_with(extra={"testport/gameinfo.xml": "<gameList />"})
    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", files))) == 0

    expected = [hm_dirs['ports_dir'] / "testport" / "gameinfo.xml"] if enabled else []
    assert added == expected


################################################################################
## From a source, and themes
def test_source_download_failure_installs_nothing(online_hm, hm_dirs, monkeypatch):
    from harbourmaster.util import net
    monkeypatch.setattr(net, "download", lambda *args, **kwargs: None)

    assert online_hm.install_port("100liljumps.zip") == 255
    assert ports_left(hm_dirs) == []


def test_install_theme(hm, tmp_path, callback):
    theme_zip = write_port_zip(tmp_path / "Shiny.theme.zip", {
        "Shiny/theme.json": json.dumps({"#info": {"name": "Shiny"}}),
        "Shiny/background.png": b"png",
        })

    assert hm.install_port(str(theme_zip)) == 0

    ## The theme folder is named after the zip, case kept.
    theme_dir = hm.themes_dir / "Shiny"
    assert sorted(p.name for p in theme_dir.iterdir()) == ["background.png", "theme.json", "theme.md5"]
    assert (theme_dir / "theme.md5").read_text() == hashlib.md5(theme_zip.read_bytes()).hexdigest()
    assert "installed successfully" in callback.message_boxes[-1]


################################################################################
## Artwork of ports that are not in any source (testing ports): real port zips ship
## <port dir>/screenshot.png but their own port.json has an empty "image".
@pytest.mark.parametrize("image_name", ["screenshot.png", "screenshot.jpg"])
def test_testing_port_screenshot(image_name, hm, hm_dirs, tmp_path):
    files = port_files_with(attr={"image": {}}, extra={f"testport/{image_name}": b"image data"})
    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", files))) == 0
    hm.load_ports()

    images = hm.port_images("testport.zip")

    assert images == {'screenshot': hm_dirs['ports_dir'] / "testport" / image_name}


def test_testing_port_screenshot_from_port_json(hm, hm_dirs, tmp_path):
    files = port_files_with(attr={"image": {"screenshot": "art/shot.png"}}, extra={"testport/art/shot.png": b"image data"})
    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", files))) == 0
    hm.load_ports()

    assert hm.port_images("testport.zip")['screenshot'] == hm_dirs['ports_dir'] / "testport" / "art" / "shot.png"


def test_testing_port_without_screenshot(hm, tmp_path):
    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", basic_port_files()))) == 0
    hm.load_ports()

    assert hm.port_images("testport.zip") is None


def test_source_port_keeps_the_source_screenshot(online_hm, hm_dirs):
    source = online_hm.sources['pm']
    source_image = source._images_dir / "100liljumps.screenshot.png"
    source_image.write_bytes(b"from the source")
    source.images["100liljumps.zip"] = {"screenshot": source_image.name}

    assert online_hm.install_port("100liljumps.zip") == 0
    (hm_dirs['ports_dir'] / "100liljumps" / "screenshot.png").write_bytes(b"from the port")
    online_hm.load_ports()

    assert online_hm.port_images("100liljumps.zip") == {'screenshot': source_image}


def test_gui_shows_testing_port_screenshot(hm, hm_dirs, tmp_path):
    from pugwash.app_ports import PortInfoMixin

    files = port_files_with(extra={"testport/screenshot.png": b"image data"})
    assert hm.install_port(str(write_port_zip(tmp_path / "testport.zip", files))) == 0
    hm.load_ports()

    gui = SimpleNamespace(hm=hm)
    assert PortInfoMixin.get_port_image(gui, "testport.zip") == hm_dirs['ports_dir'] / "testport" / "screenshot.png"
