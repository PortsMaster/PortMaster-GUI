# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

PortMaster is a port manager for Linux handheld devices (ArkOS, ROCKNIX, muOS, Knulli, TrimUI, etc.). It has two halves:

- **Python app**: an SDL2 GUI (the `pugwash` package) plus a CLI (`harbourmaster.cli`), both built on the `harbourmaster` library. All of it lives in `PortMaster/pylibs/`. The device-facing entry points are the extension-less scripts `PortMaster/pugwash` and `PortMaster/harbourmaster`.
- **Device-side shell layer**: `PortMaster/PortMaster.sh`, `control.txt`, `device_info.txt`, `mod_<CFW>.txt`, `libgl_<CFW>.txt` and per-CFW folders (`muos/`, `trimui/`, `batocera/`, `knulli/`, `miyoo/`, `spruce/`, `retrodeck/`). Ports' own launch scripts `source` `control.txt` on the device, so changes here affect every installed port, not just the GUI.

Everything ships as a zip. Bundled binaries (`gptokeyb*`, `xdelta3*`, `7zzs.*`, `innoextract.*`, `sdl2imgshow.*`, ...) are prebuilt; `BUILDING_STUFF.md` documents how to rebuild some of them.

## Commands

There is no build step for the Python code. Code must stay compatible with **Python 3.7** (some CFWs still ship it); all runtime libraries are vendored, and dev tools come from `requirements-dev.txt`.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest                           # all tests except `network`-marked ones
.venv/bin/pytest -m "not sdl"              # skip tests that start SDL headless (dummy video driver)
.venv/bin/pytest tests/test_harbour.py -k install   # single file / test
.venv/bin/pytest --cov --cov-report=term-missing   # with coverage (.coveragerc); CI fails below the floor set in .github/workflows/tests.yaml
python3 PortMaster/pugwash                 # run the GUI locally (windowed)
python3 PortMaster/harbourmaster help      # CLI: list/ports/install/uninstall/runtime_list/device_info/...
flake8 --select=E9,F63,F7,F82 PortMaster/pugwash PortMaster/harbourmaster PortMaster/pylibs/harbourmaster PortMaster/pylibs/pugwash tests   # the lint CI enforces; full flake8 still reports lots of existing style issues
./do_release.sh                            # build PortMaster.zip (+ pylibs.zip inside); `./do_release.sh stable` also builds makeself installers
./do_i18n.sh                               # extract strings with xgettext, sync with Crowdin, compile .mo (needs crowdin CLI)
```

pugwash flags: `--quiet --no-check --debug --no-colour --force-colour --no-log --offline --no-harbour`.

To test on a device: `./do_release.sh`, copy `PortMaster.zip` over, then on the device run `./PortMaster/harbourmaster --no-check install ./PortMaster.zip` (the `./` prefix makes it install a local file).

## Local-dev mode (HM_TESTING)

`harbourmaster/config.py` works out the tools/ports/scripts directories at import time by calling `detect_paths()`, which probes CFW-specific paths. If the cwd (or its parent, after a `chdir` up) contains `.git`, it sets `HM_TESTING=True`. In that mode the tools dir is the repo root, ports install into `./ports/`, the window is not fullscreen, and update checks are skipped. The `HM_TOOLS_DIR` / `HM_PORTS_DIR` / `HM_SCRIPTS_DIR` env vars override the detected directories. `detect_paths(root=...)` can be pointed at a fake filesystem, which is how `tests/test_config.py` covers each CFW.

The scripts skip extracting `pylibs.zip` when run from a git checkout. On a device, a release ships `pylibs.zip`, which the scripts extract over `pylibs/` and `exlibs/` on first launch. This replaces the old directories completely, so renamed modules never leave stale copies behind.

Device info comes from `harbourmaster.hardware.HardwareDetector`, which reads the env file written by the `device_info.txt` shell script, or uses the process environment directly if `DEVICE_NAME` / `DEVICE_CPU` / `CFW_NAME` are set. Set those env vars to emulate another device; the tests rely on this too. The result is memoised in `hardware._CACHED_DICT`.

## Tests

`tests/` (pytest, not shipped). `tests/conftest.py` sets the `HM_*_DIR` and device env vars **before** importing `harbourmaster`, because `config.py` resolves directories at import time. It also blocks `requests`, so no test touches the network; patch `harbourmaster.util.net` to fake downloads (all network calls in `harbourmaster.source` go through it). Key fixtures:
- `make_hm` / `hm`: an offline `HarbourMaster` in tmp dirs.
- `online_hm`: the PortMaster source loaded from `tests/data/ports.json`, with downloads served from generated zips.
- `RecordingCallback`: captures messages and message boxes.
- `pugwash`: the GUI modules (`PortMasterGUI`, scenes) for in-process GUI tests.
- `start_fifo_gui`: runs a `pugwash` script in `fifo_control` mode and drives it the way `PortMasterDialog.txt` does.
- `gui`: one headless `PortMasterGUI` for the whole session. SDL keeps class-level state (the default renderer), so a GUI can't be quit and made again in the same process.
- `log_errors`: loguru ERROR messages logged during a test (pytest's `caplog` doesn't see loguru).
- `port_files_with` / `write_raw_zip`: build broken or unusual port zips.

Installing is covered in `test_install.py` (bad data, layouts, rollback, runtimes, URLs, themes, artwork), `test_fifo_install.py` (fifo_control installs must always answer `OKAY`/`FAIL`, never stay on `WAIT`) and `test_gui_commands.py`.

Guard tests for restructuring:
- `test_release_layout.py` runs both scripts from a `pylibs.zip` layout with no `.git`, which is the on-device bootstrap path.
- `test_api_snapshot.py` checks that every public name in `tests/data/api_snapshot.json` is still reachable. Update its `AREAS` table when code moves.
- `test_i18n_snapshot.py` checks that the set of translatable strings (`tests/data/msgids.txt`) hasn't changed.

Known bugs are pinned as `xfail(strict=True)`, so a test fails once its bug is fixed and the marker should then be removed. pugwash's `main()` is wrapped in `logger.catch`, so it exits 0 even after a crash; check its output for tracebacks rather than relying on the exit code.

## Architecture

**Import setup**: the scripts prepend `pylibs/` and `exlibs/` to `sys.path`. `exlibs/` holds vendored third-party packages (loguru, requests, urllib3, certifi, ...), and `pylibs/` holds the project packages plus vendored `sdl2`, `png` and `pyqrcode`. Don't edit vendored code unless that's the point of the change. There are no star imports and no injected builtins: import names explicitly.

**`harbourmaster` library** (`pylibs/harbourmaster/`):
- `harbour.py`: `HarbourMaster`, the engine both the GUI and CLI drive. It holds `__init__`, config, sources and GCD modes. Its other methods live in mixins grouped by job:
  - `hm_info.py`: PortMaster-Info files
  - `hm_ports.py`: scanning, filtering and listing ports
  - `hm_featured.py`
  - `hm_install.py`: install / uninstall
  - `hm_runtimes.py`
- `source/`: where ports come from. `PortMasterV3` (`source/portmaster.py`) is the only source API, registered in `HM_SOURCE_APIS`. It reads a `ports.json` release asset and keeps port screenshots up to date, incrementally from `images.NNN.zip` where possible and otherwise from `images.zip`. Each `*.source.json` in the config dir is one source; `load_sources` upgrades old official V1/V2 source files to V3. `raw_download` (`source/__init__.py`) installs from a plain URL, and is also how themes install. `BaseSource` (`source/base.py`) holds the shared caching and update-frequency logic, which `pugwash.theme.ThemeDownloader` also uses for the theme list.
- `platform/`: per-CFW hooks, one module per CFW family. These are `PlatformBase` subclasses registered in `HM_PLATFORMS` (in `platform/__init__.py`), keyed by lowercase CFW name, and they handle gamelist.xml updates, moving scripts, ES refresh and similar. A new CFW needs:
  - a module here
  - an entry in `HM_PLATFORMS`
  - a `mod_<CFW>.txt`
  - possibly changes in `control.txt` and `config.detect_paths()`
- `util/`:
  - `callback.py`: the `Callback` progress interface, `CancelEvent`
  - `net.py`: fetch and download
  - `text.py`, `files.py`, `data.py`

  Every name is re-exported from `harbourmaster.util`.
- Also: `hardware.py` (device capabilities, used by `match_requirements`), `info.py` (port.json loading: `port_info_load`/`port_info_merge`), `captain.py` (port zip validation), `config.py`, `console.py` (`cprint`) and `cli.py` (the CLI).

**`pugwash` GUI package** (`pylibs/pugwash/`):
- `__init__.py`: `PYLIB_PATH` and the version info. The `PortMaster/pugwash` script owns the version block and passes it in through `set_version_info()` **before** importing anything else from `pugwash`.
- `main.py`: `main()`, argument parsing and logging.
- `lang.py`: language setup (runs on import); `lang.DEFAULT_LANG`/`lang.CURRENT_LANG`.
- `update.py`: the PortMaster self-update check.
- `util.py`: small helpers.
- `app.py`: `PortMasterGUI`, covering init, the main loop, drawing and the scene stack. It subclasses the mixins in `app_callbacks.py` (the thread-aware `harbourmaster.Callback` implementation and `run_task`), `app_commands.py` (install/uninstall/update front ends), `app_fifo.py` (fifo_control) and `app_ports.py` (port info/size for templates), plus `sdl.GUI` and `harbourmaster.Callback`.
- `scenes/`: screens as `BaseScene` subclasses, one module per screen or group of screens. `scenes/base.py` imports no other scene, which keeps the modules free of import cycles.
- `theme.py`: theme loading. Themes are JSON describing per-scene elements; `pylibs/default_theme/theme.json` is the built-in one. See `THEME.md` for the element/scene spec, inheritance order and text-template tags.
- `tasks.py`: threading helpers (dispatcher, `Task`, `DirectoryScanner`, `FifoReader`, `FrameStats`). It doesn't import SDL.
- `sdl/`: the low-level SDL2 widget and rendering layer. It's pySDL2gui (port_gui), split by class group; `Region` in `sdl/region.py` is the themeable widget.

**FIFO control**: `pugwash fifo_control` and `harbourmaster fifo_control` let shell scripts (e.g. `PortMasterDialog.txt`, used by `PortMaster.sh` for autoinstall) drive dialogs, progress, installs and runtime checks through a named pipe. See `pugwash/app_fifo.py`; a `tasks.FifoReader` thread reads the pipe.

## Threading model (GUI)

- **Main thread only:** SDL calls, scenes, `push_scene`/`pop_scene` and `set_data`. Worker threads hand work to the main thread through `gui.dispatcher` (`tasks.MainThreadDispatcher`): `post()` for fire-and-forget, `call()` when they need the result. `do_update()` drains it every frame.
- **Slow work goes through `gui.run_task(fn, ...)`.** It runs `fn` on a worker while the main loop keeps rendering, then returns the result or re-raises in the caller, so scene code stays synchronous. All HarbourMaster work (install, uninstall, update, runtime checks, startup) goes through it.
  - Only one task runs at a time, because HarbourMaster isn't thread-safe.
  - `run_task` called from the worker just runs inline.
  - Calling it on the main thread while a task is running raises an error.
- **`PortMasterGUI` is `hm.callback`, and its callbacks are thread-aware:**
  - `message`, `progress`, `messages_begin` and `messages_end` are forwarded from the worker. Progress is coalesced to one update per frame.
  - `message_box` blocks the worker until the user answers.
  - Cancel (`do_cancel`) sets a flag on the task. The worker raises `CancelEvent` at its next `progress`/`message`, and only if `gui.cancellable` is true.
- **While a task runs:** only the `messages`/`message_box` layers get input, and lower layers receive their `update_data` after the task. New scene code mustn't read `gui.hm` from the draw path.
- **Other background threads:**
  - `tasks.DirectoryScanner` works out installed port sizes.
  - `ImageManager.enable_async` (`sdl/images.py`) decodes port screenshots (absolute paths) and returns a `PendingImage` until the main thread uploads the texture. Theme images load synchronously.
- **`quit()` order:** it destroys textures, the renderer and the window before `sdl2.ext.quit()`. Garbage collection after `SDL_Quit` segfaults on muOS/Mali.
- **Profiling:** `PM_PERF=1` logs fps and every gap between frames over 50 ms to `pugwash.txt` (`tasks.FrameStats`). Run it on a real device to measure lag.

## Where did it go (Stage 3 restructure)

Use this table to port upstream patches made against the old layout:

| Old | New |
|---|---|
| `PortMaster/pugwash`: `PortMasterGUI` | `pugwash/app.py` and the `app_callbacks.py` / `app_commands.py` / `app_fifo.py` / `app_ports.py` mixins |
| `PortMaster/pugwash`: `main`, languages, `portmaster_check_update`, helpers | `pugwash/main.py`, `lang.py`, `update.py`, `util.py` |
| `PortMaster/harbourmaster` (commands, `ConsoleCallback`, `main`) | `harbourmaster/cli.py` |
| `pylibs/pugscene.py` | `pugwash/scenes/<screen>.py` (`TempMenuScene` is in `startup.py`) |
| `pylibs/pugtheme.py`, `pylibs/pugtask.py` | `pugwash/theme.py`, `pugwash/tasks.py` |
| `pylibs/pySDL2gui.py` | `pugwash/sdl/<group>.py` |
| `pylibs/utility.py` | `harbourmaster/console.py` |
| `harbourmaster/harbour.py` | `harbour.py` plus the `hm_*.py` mixins |
| `harbourmaster/source.py`, `platform.py`, `util.py` | the `source/`, `platform/`, `util/` packages |
| `PortMasterV1`/`V2`, `GitHubRepoV1`, `GitHubRawReleaseV1` | removed. Only `PortMasterV3` remains; `ThemeDownloader` subclasses `BaseSource` directly |
| builtins `PYLIB_PATH`, `PORTMASTER_DEBUG`, `DEFAULT_LANG`, `CURRENT_LANG` | `pugwash.PYLIB_PATH`, `harbourmaster.config.HM_DEBUG`, `pugwash.lang.*` |

## Versioning and releases

The version lives in the `## -- BEGIN PORTMASTER INFO --` block at the top of the `PortMaster/pugwash` script (and the `HARBOURMASTER INFO` block in `harbourmaster/__init__.py`). `tools/pm_release.py` rewrites that block, and `do_release.sh` reads `PORTMASTER_VERSION = '...'` from the script with awk, so keep both in the script. `do_release.sh` backs up and restores pugwash around this, so the committed value stays a placeholder. Releases are built by the manually triggered GitHub workflows in `.github/workflows/` (alpha/beta/stable); `do_beta.sh` / `do_stable.sh` stamp the version and commit.

## Translations

Wrap user-facing strings in `_()` (gettext). `do_i18n.sh` extracts strings from the `pugwash` script and every `.py` under `pylibs/harbourmaster` and `pylibs/pugwash` into `pylibs/locales/messages.pot`; theme strings go into `themes.pot` via `theme_msgfmt.py`. Translations are managed on Crowdin, so don't hand-edit `.po` files for other languages. If you change strings on purpose, regenerate the snapshot with `PM_UPDATE_I18N_SNAPSHOT=1 pytest tests/test_i18n_snapshot.py`.

## Style

Follow `.flake8`: long lines are fine, `##` comments are the house style, and aligned `=` is allowed. Use explicit imports, not star imports.
