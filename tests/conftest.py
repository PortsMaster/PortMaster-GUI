# SPDX-License-Identifier: MIT

import atexit
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

from pathlib import Path

import pytest


REPO_DIR = Path(__file__).resolve().parent.parent
PM_DIR = REPO_DIR / "PortMaster"
PYLIB_PATH = PM_DIR / "pylibs"
EXLIB_PATH = PM_DIR / "exlibs"
DATA_DIR = Path(__file__).resolve().parent / "data"


################################################################################
## Environment, this must happen before harbourmaster is imported.
##
## harbourmaster.config works out its directories at import time, and when run
## from a git checkout it would use the repo itself. Point it at a scratch dir.
SESSION_DIR = Path(tempfile.mkdtemp(prefix="pm-tests-"))
atexit.register(shutil.rmtree, str(SESSION_DIR), True)

TEST_ENV = {
    "HM_TOOLS_DIR":   str(SESSION_DIR / "tools"),
    "HM_PORTS_DIR":   str(SESSION_DIR / "ports"),
    "HM_SCRIPTS_DIR": str(SESSION_DIR / "ports"),

    ## hardware.HardwareDetector uses these straight from the environment
    ## instead of running device_info.txt.
    "CFW_NAME":            "default",
    "CFW_VERSION":         "1.0",
    "CFW_GLIBC":           "2.30",
    "DEVICE_NAME":         "Testing",
    "DEVICE_ARCH":         "aarch64",
    "DEVICE_CPU":          "test",
    "DEVICE_RAM":          "1",
    "DISPLAY_WIDTH":       "640",
    "DISPLAY_HEIGHT":      "480",
    "ANALOG_STICKS":       "2",
    "DEVICE_CAPABILITIES": "aarch64 640x480 power opengl",

    ## Run anything SDL headless.
    "SDL_VIDEODRIVER": "dummy",
    "SDL_AUDIODRIVER": "dummy",
    ## The dummy video driver has no accelerated renderer.
    "SDL_RENDER_DRIVER": "software",
    }

## Some SDL builds (eg muOS) have no dummy driver, set PM_TEST_VIDEODRIVER to use
## a real one (an empty value lets SDL pick), eg: PM_TEST_VIDEODRIVER= pytest -m sdl
if "PM_TEST_VIDEODRIVER" in os.environ:
    ## offscreen is headless too, the software renderer stays.
    if os.environ["PM_TEST_VIDEODRIVER"] != "offscreen":
        del TEST_ENV["SDL_RENDER_DRIVER"]
    if os.environ["PM_TEST_VIDEODRIVER"]:
        TEST_ENV["SDL_VIDEODRIVER"] = os.environ["PM_TEST_VIDEODRIVER"]
    else:
        del TEST_ENV["SDL_VIDEODRIVER"]
        os.environ.pop("SDL_VIDEODRIVER", None)

for _dir in ("tools", "ports"):
    (SESSION_DIR / _dir).mkdir()

## Run on a device (eg: by the PortMaster Test Suite port), the environment already
## describes that device and PortMaster (control.txt, device_info.txt, funcs.txt):
## only what TEST_ENV says may count.
_DEVICE_PREFIXES = ("DEVICE_", "CFW_", "DISPLAY_", "ANALOG_", "HM_")
_DEVICE_KEYS = ("controlfolder", "directory", "PORTMASTER_HOME", "PM_FUNCS_VERSION", "PM_SCRIPTNAME", "PM_PORTNAME", "PM_VERSION")
for _key in list(os.environ):
    if _key.startswith(_DEVICE_PREFIXES) or _key in _DEVICE_KEYS:
        del os.environ[_key]

os.environ.update(TEST_ENV)

sys.path.insert(0, str(EXLIB_PATH))
sys.path.insert(0, str(PYLIB_PATH))

import harbourmaster  # noqa: E402
from harbourmaster import source as hm_source  # noqa: E402
from harbourmaster.util import net as hm_net  # noqa: E402


################################################################################
## Helpers
def write_port_zip(zip_path, files):
    """
    files is a dict of {name: str/bytes/dict}, dicts are written as json.
    Names ending in '/' are written as directory entries.
    """
    with zipfile.ZipFile(zip_path, 'w') as zf:
        for name, data in files.items():
            if isinstance(data, dict):
                data = json.dumps(data)

            if name.endswith('/'):
                zf.writestr(zipfile.ZipInfo(name), b"")
            else:
                zf.writestr(name, data)

    return zip_path


def basic_port_files(name="testport", title="Test Port", script="Test Port.sh", **attr):
    port_json = {
        "version": 4,
        "name": f"{name}.zip",
        "items": [script, f"{name}/"],
        "items_opt": None,
        "attr": {
            "title": title,
            "desc": "A port for testing.",
            "inst": "Ready to run.",
            "genres": ["puzzle"],
            "porter": ["tester"],
            "rtr": True,
            "runtime": [],
            "reqs": [],
            "arch": ["aarch64"],
            **attr,
            },
        }

    return {
        script: "#!/bin/bash\necho hello\n",
        f"{name}/": "",
        f"{name}/port.json": port_json,
        f"{name}/data.txt": "game data",
        }


def write_raw_zip(zip_path, data):
    """A 'zip' that is whatever bytes you give it (garbage, empty, truncated...)."""
    zip_path.write_bytes(data)
    return zip_path


def port_files_with(name="testport", port_json=None, attr=None, drop=(), extra=None, **kwargs):
    """
    basic_port_files() with port.json changed: `port_json` replaces root keys (or the
    whole file if it is a str), `attr` replaces attr keys, `drop` removes files.
    """
    files = basic_port_files(name=name, **kwargs)
    pj_name = f"{name}/port.json"

    if isinstance(port_json, str):
        files[pj_name] = port_json

    else:
        files[pj_name].update(port_json or {})
        if attr:
            files[pj_name]["attr"].update(attr)

    for item in drop:
        files.pop(item)

    files.update(extra or {})
    return files


class RecordingCallback(harbourmaster.Callback):
    """
    Records everything harbourmaster tells the user, answers message boxes with `answer`.
    """
    def __init__(self, answer=True):
        super().__init__()
        self.answer = answer
        self.messages = []
        self.progress_calls = []
        self.message_boxes = []

    def progress(self, message, amount, total=None, fmt=None):
        self.progress_calls.append((message, amount, total, fmt))

    def message(self, message):
        self.messages.append(message)

    def message_box(self, message, want_cancel=False, ok_text=None, cancel_text=None):
        self.message_boxes.append(message)
        return self.answer


################################################################################
## Driving pugwash's fifo_control mode, the same way PortMasterDialog.txt does.
FIFO_TIMEOUT = 30


class FifoGui:
    def __init__(self, process, pipe_file, done_file):
        self.process = process
        self.pipe_file = pipe_file
        self.done_file = done_file

    def wait_done(self):
        end = time.monotonic() + FIFO_TIMEOUT
        while time.monotonic() < end:
            if self.process.poll() is not None:
                raise AssertionError(f"pugwash exited early:\n{self.process.stdout.read().decode()}")

            if self.done_file.is_file() and self.pipe_file.exists():
                result = self.done_file.read_text()
                if result not in ("", "WAIT"):
                    return result

            time.sleep(0.05)

        raise AssertionError("timed out waiting for pugwash")

    def send(self, *args):
        self.done_file.write_text("WAIT")

        with open(str(self.pipe_file), "w") as fh:
            fh.write("".join(f"{arg}\1" for arg in args) + "\n")

        return self.wait_done()

    def exit(self):
        with open(str(self.pipe_file), "w") as fh:
            fh.write("exit\n")

        try:
            result = self.process.wait(FIFO_TIMEOUT)
            output = self.process.stdout.read().decode()

        finally:
            self.process.stdout.close()

        ## main() is wrapped in logger.catch, so a crash still exits with 0.
        assert "Traceback" not in output, output
        return result

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait()


def start_fifo_gui(pm_dir, cwd, env, tmp_path, args=("--offline", "--no-check", "--no-log")):
    """
    Start pm_dir/pugwash in fifo_control mode and wait until it is ready.
    """
    pipe_file = tmp_path / "pm_pipe"
    done_file = tmp_path / "pm_done"
    done_file.write_text("WAIT")

    process = subprocess.Popen(
        [sys.executable, str(pm_dir / "pugwash"), *args, "fifo_control", str(pipe_file), str(done_file)],
        cwd=str(cwd), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    gui = FifoGui(process, pipe_file, done_file)

    try:
        ## pugwash writes DONE once the pipe is ready.
        assert gui.wait_done() == "DONE"

    except BaseException:
        gui.kill()
        raise

    return gui


################################################################################
## Skip sdl tests when the SDL2 libraries are missing.
def _sdl_missing():
    """
    Why the sdl tests can't run here, or None if they can. On devices the GUI also
    needs SDL2_image/mixer/ttf, and some SDL builds (muOS, AmberELEC, knulli) have no
    dummy video driver.
    """
    try:
        import sdl2
        import sdl2.ext  # noqa: F401
        import sdl2.sdlimage  # noqa: F401
        import sdl2.sdlmixer  # noqa: F401
        import sdl2.sdlttf  # noqa: F401

    except ImportError as err:
        return f"SDL2 not available ({err}), pip install pysdl2-dll"

    if sdl2.SDL_VideoInit(None) != 0:
        error = sdl2.SDL_GetError().decode('utf-8', 'replace')
        return f"SDL video driver {os.environ.get('SDL_VIDEODRIVER')!r} unavailable ({error}), try PM_TEST_VIDEODRIVER="

    sdl2.SDL_VideoQuit()
    return None


def pytest_collection_modifyitems(config, items):
    if not any(item.get_closest_marker("sdl") for item in items):
        return

    reason = _sdl_missing()
    if reason is None:
        return

    skip_sdl = pytest.mark.skip(reason=reason)
    for item in items:
        if item.get_closest_marker("sdl"):
            item.add_marker(skip_sdl)


@pytest.fixture(scope="session")
def pugwash():
    """The GUI modules (importing them does not start the GUI)."""
    from types import SimpleNamespace
    import pugwash.app
    import pugwash.scenes
    return SimpleNamespace(**{**vars(pugwash.scenes), **vars(pugwash.app)})


@pytest.fixture(scope="session")
def gui(pugwash):
    """
    One headless PortMasterGUI for the whole test run. SDL keeps some state at class
    level (eg: the default renderer), so the GUI can't be quit and made again.
    """
    gui = pugwash.PortMasterGUI(first_scene=pugwash.BlankScene, force_theme="default_theme")
    yield gui
    gui.quit()


################################################################################
## Fixtures
@pytest.fixture
def hm_dirs(tmp_path):
    dirs = {
        'tools_dir': tmp_path / "tools",
        'ports_dir': tmp_path / "ports",
        'scripts_dir': tmp_path / "ports",
        'temp_dir': tmp_path / "temp",
        }

    for value in dirs.values():
        value.mkdir(parents=True, exist_ok=True)

    return dirs


@pytest.fixture
def callback():
    return RecordingCallback()


@pytest.fixture
def log_errors():
    """Every ERROR (or worse) loguru message logged during the test."""
    from loguru import logger

    messages = []
    handler_id = logger.add(lambda message: messages.append(message.record["message"]), level="ERROR")
    yield messages
    logger.remove(handler_id)


@pytest.fixture
def make_hm(hm_dirs, callback):
    def _make_hm(**config):
        config = {'offline': True, 'no-check': True, **config}
        return harbourmaster.HarbourMaster(config, callback=callback, **hm_dirs)

    return _make_hm


@pytest.fixture
def hm(make_hm):
    return make_hm()


@pytest.fixture
def online_hm(make_hm, ports_json_data, monkeypatch, tmp_path):
    """
    A HarbourMaster that thinks it is online, with the PortMaster source loaded
    from tests/data/ports.json and downloads served from local zips.
    """
    monkeypatch.setattr(hm_net, "fetch_json", lambda url: json.loads(json.dumps(ports_json_data)))

    downloads = []

    def fake_download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        downloads.append(file_url)
        name = file_name.name.rsplit('.', 1)[0]
        port = ports_json_data['ports'][file_name.name]
        files = basic_port_files(name=name, title=port['attr']['title'], script=port['items'][0])
        return write_port_zip(file_name, files)

    monkeypatch.setattr(hm_net, "download", fake_download)

    hm = make_hm(offline=False)
    hm.sources['pm'].update()
    hm.downloads = downloads
    return hm


@pytest.fixture
def ports_json_data():
    with open(DATA_DIR / "ports.json") as fh:
        return json.load(fh)


class NetworkBlocked(Exception):
    pass


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    if request.node.get_closest_marker("network"):
        return

    import requests

    def blocked(*args, **kwargs):
        raise NetworkBlocked(f"network access in a test: {args!r}")

    monkeypatch.setattr(requests, "get", blocked)
    monkeypatch.setattr(requests.Session, "request", blocked)


@pytest.fixture(autouse=True)
def reset_hardware_cache():
    """hardware.py memoises device info globally, start each test fresh."""
    harbourmaster.hardware._CACHED_DICT = None
    yield
    harbourmaster.hardware._CACHED_DICT = None


@pytest.fixture(autouse=True)
def no_real_proxy_settings(monkeypatch):
    """main() reads EmulationStation's proxy settings: never the real ones (devices run the suite too)."""
    from harbourmaster.util import proxy
    monkeypatch.setattr(proxy, "es_settings_files", lambda environ: [])
