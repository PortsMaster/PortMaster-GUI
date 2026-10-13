# Developing for PortMaster

The easiest way to develop and test PortMaster is not on the device but your local machine. 

## Setting up the environment

Have Python 3.9 or newer, install [pysdl2-dll](https://pypi.org/project/pysdl2-dll/) for your platform via pip/brew/apt.

Thats it, everything else is included.

## Running PortMaster

PortMaster is the bash script that runs on the device, this is not needed for development. Instead you're better off running the pugwash script directly

```bash
python3 PortMaster/pugwash
```

If you have made changes and want to test it on your device, make a test build. It is numbered `YYYY-MM-DD_XX69` (`2026-10-13_0069`, then `_0169`, ...), which never clashes with a release and shows it is a test build. Your checkout is left as it is, and only files git knows about go in (so no logs, `config/` or installed ports).

```bash
./do_release.sh test
```

From there you can just ssh `dist/PortMaster.zip` onto the device and use harbourmaster to install this local version of PortMaster.

```bash
scp dist/PortMaster.zip ark@rg353v.local:/roms2/tools
```

Then on device:

```bash
cd /roms2/tools
./PortMaster/harbourmaster --no-check install ./PortMaster.zip
```

The `./PortMaster.zip` is important as it will make harbourmaster use the local file.


## Running the tests

The tests live in `tests/` and are not shipped with PortMaster. They need Python 3.7 or newer.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                 # everything except network tests
.venv/bin/pytest -m "not sdl"    # skip the tests that start SDL (headless)
.venv/bin/pytest tests/test_harbour.py -k install   # a single file / test
```

The tests never touch your real PortMaster install or the network: they point `HM_TOOLS_DIR`, `HM_PORTS_DIR` and `HM_SCRIPTS_DIR` at temporary directories, and fake the device with environment variables (see `tests/conftest.py`).

## Tips and Tricks

Device information comes from the `device_info.txt` shell script, but if `DEVICE_NAME`, `DEVICE_CPU` or `CFW_NAME` are set in the environment those values are used instead. You can use that to run PortMaster as if it was a different device, which is useful for testing themes too.

```bash
DEVICE_NAME=RG353V CFW_NAME=ArkOS DEVICE_ARCH=aarch64 DISPLAY_WIDTH=640 DISPLAY_HEIGHT=480 \
    DEVICE_CAPABILITIES="aarch64 640x480 power opengl" python3 PortMaster/pugwash
```

To force a particular window resolution, set `pretend_resolution` in `PortMasterGUI.__init__` in `PortMaster/pylibs/pugwash/app.py`.
