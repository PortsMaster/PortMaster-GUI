# SPDX-License-Identifier: MIT
#
# A fuzzer for the files that describe ports. Each case mutates real port info (wrong types,
# missing keys, unsafe names, deep nesting, mangled bytes) and pushes it through the ways it
# reaches PortMaster:
#   1. port.json files of installed ports, loaded at startup
#   2. ports.json entries from a source
#   3. port.json inside a port zip being installed
#   4. ports_info.json, port_stats.json and the scripts' PORTMASTER: signatures
#   5. the GUI's ports list and port info screens
# then lists, sorts, filters, prints (the CLI) and uninstalls what loaded. Nothing may raise,
# and every delete, write, rename and mkdir must stay inside the test's tmp dir.
#
# A short run with a fixed seed is part of the suite. For a long one:
#   PM_FUZZ_N=20000 PM_FUZZ_SEED=7 .venv/bin/pytest -q tests/test_fuzz_port_json.py

import json
import os
import random
import shutil
import traceback
from collections import defaultdict
from pathlib import Path

import pytest

from harbourmaster.config import HM_SORT_ORDER
from harbourmaster.util import net as hm_net

from conftest import DATA_DIR, basic_port_files, write_port_zip


## Cases per test (the GUI test does a tenth, at least 20).
N = int(os.environ.get('PM_FUZZ_N', '40'))
SEED = int(os.environ.get('PM_FUZZ_SEED', '1'))

CRASHES = defaultdict(list)
ESCAPES = []


class SandboxEscape(BaseException):
    ## Not an Exception, so harbourmaster's own `except Exception:` can't hide it.
    pass


################################################################################
## Values
def weird_strings(outside):
    return [
        "", " ", "x", "blank", "None", "null", ".", "..", "../", "../..", "a/../..", "./", "/",
        str(outside), str(outside) + "/", "../outside", "../outside/canary.txt", "ports/../../outside",
        "\x00", "a\x00b", "\n", "\t\r", "é", "日本語", "🎮", "\udcff"[:0] + "‮", "%s%n", "{0}", "{port_info.title}",
        "x" * 5000, "Test Port.sh", "testport/", "testport", "TESTPORT.ZIP", "testport.zip", "game.zip",
        "mono.squashfs", "godot", ".squashfs", "2.31", "99.99", "1.2.3.4.5", "abc", "-1", "nan",
        "action", "ACTION", "rtr", "!rtr", "installed", "broken", "aarch64", "x86_64|armhf",
        "<b>", "</b>", "<r>x</r>", "<b,g,>", "<", ">", "<<>>", "<error>", "</", "\x1b[31m",
        ]


def weird_values(rng, outside, depth=0):
    simple = [None, True, False, 0, 1, -1, 2 ** 64, 1.5, float('nan'), float('inf'), -float('inf')]
    pool = simple + weird_strings(outside)
    if depth > 2:
        return rng.choice(pool)

    kind = rng.random()
    if kind < 0.55:
        return rng.choice(pool)

    if kind < 0.8:
        return [weird_values(rng, outside, depth + 1) for _ in range(rng.randint(0, 4))]

    if kind < 0.97:
        keys = ['md5', 'source', 'status', 'name', 'screenshot', 'covers', 'url', 'size', 'date_added',
                'date_updated', 'port.json', 'x', '', 'runtime', 'title']
        return {rng.choice(keys): weird_values(rng, outside, depth + 1) for _ in range(rng.randint(0, 4))}

    ## Deep nesting.
    value = rng.choice(pool)
    for _ in range(rng.randint(10, 200)):
        value = [value] if rng.random() < 0.5 else {'x': value}
    return value


ROOT_KEYS = ['version', 'name', 'items', 'items_opt', 'attr', 'status', 'files', 'source', 'md5', 'changed']
ATTR_KEYS = ['title', 'desc', 'desc_md', 'inst', 'inst_md', 'genres', 'porter', 'image', 'rtr', 'exp',
             'runtime', 'reqs', 'arch', 'min_glibc', 'store', 'availability']


def mutate(rng, info, outside):
    info = json.loads(json.dumps(info))

    for _ in range(rng.randint(1, 4)):
        where = rng.random()
        if where < 0.3:
            target, keys = info, ROOT_KEYS
        else:
            if not isinstance(info.get('attr'), dict):
                info['attr'] = {}
            target, keys = info['attr'], ATTR_KEYS

        key = rng.choice(keys)
        action = rng.random()
        if action < 0.15:
            target.pop(key, None)

        elif action < 0.3 and isinstance(target.get(key), list) and target[key]:
            ## Change one element of a list.
            target[key][rng.randrange(len(target[key]))] = weird_values(rng, outside, 2)

        elif action < 0.4 and isinstance(target.get(key), dict) and target[key]:
            sub = rng.choice(list(target[key]))
            target[key][sub] = weird_values(rng, outside, 2)

        else:
            target[key] = weird_values(rng, outside)

    return info


def to_bytes(rng, info):
    """The port.json file's bytes, sometimes mangled the way an SD card or an editor would."""
    try:
        text = json.dumps(info, indent=rng.choice([None, 2]))
    except (ValueError, RecursionError):
        text = "{}"

    data = text.encode('utf-8', 'surrogatepass')
    roll = rng.random()
    if roll < 0.80:
        return data
    if roll < 0.84:
        return b'\xef\xbb\xbf' + data
    if roll < 0.87:
        return data[:rng.randrange(len(data) + 1)]
    if roll < 0.90:
        data = bytearray(data)
        for _ in range(rng.randint(1, 5)):
            if data:
                data[rng.randrange(len(data))] = rng.randrange(256)
        return bytes(data)
    if roll < 0.92:
        return text.encode('utf-16')
    if roll < 0.94:
        return text.encode('latin-1', 'replace').replace(b'"', b"'")
    return rng.choice([b'', b'null', b'[]', b'"x"', b'1', b'NaN', b'{"attr": NaN}', b'\x00' * 64,
                       b'[' * 100000, b'{"a":' * 50000, b'{}{}', b'{"name": "a", "name": 1}'])


################################################################################
## Harness
@pytest.fixture
def guard(tmp_path, monkeypatch):
    """Every delete must stay inside tmp_path."""
    root = tmp_path.resolve()

    def check(path):
        path = Path(os.path.abspath(os.fspath(path)))
        if root != path and root not in path.parents:
            ESCAPES.append((str(path), traceback.format_stack(limit=8)))
            raise SandboxEscape(f"OUTSIDE SANDBOX: {path}")

    real_rmtree, real_remove, real_unlink, real_rmdir = shutil.rmtree, os.remove, os.unlink, os.rmdir
    real_path_unlink, real_path_rmdir = Path.unlink, Path.rmdir

    def rmtree(path, *a, **kw):
        check(path)
        return real_rmtree(path, *a, **kw)

    def remove(path, *a, **kw):
        if kw.get('dir_fd') is None:
            ## (With dir_fd it is rmtree inside a tree already checked.)
            check(path)
        return real_remove(path, *a, **kw)

    def unlink(path, *a, **kw):
        if kw.get('dir_fd') is None:
            ## (With dir_fd it is rmtree inside a tree already checked.)
            check(path)
        return real_unlink(path, *a, **kw)

    def rmdir(path, *a, **kw):
        if kw.get('dir_fd') is None:
            ## (With dir_fd it is rmtree inside a tree already checked.)
            check(path)
        return real_rmdir(path, *a, **kw)

    def path_unlink(self, *a, **kw):
        check(self)
        return real_path_unlink(self, *a, **kw)

    def path_rmdir(self, *a, **kw):
        check(self)
        return real_path_rmdir(self, *a, **kw)

    import builtins
    import io
    real_open, real_rename, real_replace, real_mkdir = builtins.open, os.rename, os.replace, os.mkdir

    def guarded_open(file, mode='r', *a, **kw):
        if isinstance(file, (str, bytes, os.PathLike)) and any(c in mode for c in 'wax+'):
            check(file)
        return real_open(file, mode, *a, **kw)

    def rename(src, dst, *a, **kw):
        if kw.get('src_dir_fd') is None:
            check(src)
            check(dst)
        return real_rename(src, dst, *a, **kw)

    def replace(src, dst, *a, **kw):
        if kw.get('src_dir_fd') is None:
            check(src)
            check(dst)
        return real_replace(src, dst, *a, **kw)

    def mkdir(path, *a, **kw):
        if kw.get('dir_fd') is None:
            check(path)
        return real_mkdir(path, *a, **kw)

    monkeypatch.setattr(builtins, 'open', guarded_open)
    monkeypatch.setattr(io, 'open', guarded_open)
    monkeypatch.setattr(os, 'rename', rename)
    monkeypatch.setattr(os, 'replace', replace)
    monkeypatch.setattr(os, 'mkdir', mkdir)
    monkeypatch.setattr(shutil, 'rmtree', rmtree)
    monkeypatch.setattr(os, 'remove', remove)
    monkeypatch.setattr(os, 'unlink', unlink)
    monkeypatch.setattr(os, 'rmdir', rmdir)
    monkeypatch.setattr(Path, 'unlink', path_unlink)
    monkeypatch.setattr(Path, 'rmdir', path_rmdir)


@pytest.fixture(autouse=True)
def no_crashes():
    """Fails the test with a summary of every distinct crash and sandbox escape."""
    CRASHES.clear()
    ESCAPES.clear()
    yield

    lines = [f"{len(ESCAPES)} file operations outside the sandbox, {len(CRASHES)} distinct crashes (N={N}, seed={SEED})"]
    for path, stack in ESCAPES[:5]:
        lines.append(f"OUTSIDE SANDBOX: {path}\n" + "".join(stack))

    for key in sorted(CRASHES):
        lines.append(f"{len(CRASHES[key]):5d}  {key}\n         e.g. {CRASHES[key][0]!r}"[:600])

    assert not ESCAPES and not CRASHES, "\n".join(lines)


def where(err):
    frames = traceback.extract_tb(err.__traceback__)
    ours = [f for f in frames if '/pylibs/' in f.filename]
    frame = (ours or frames)[-1]
    return f"{type(err).__name__} @ {frame.filename.split('/pylibs/')[-1]}:{frame.lineno} ({frame.name}): {str(err)[:80]}"


def record(stage, err, case):
    key = f"[{stage}] {where(err)}"
    CRASHES[key].append(case)


def run_cli(hm, command, argv):
    import contextlib
    import io
    from harbourmaster import cli

    with contextlib.redirect_stdout(io.StringIO()):
        getattr(cli, command)(hm, argv)


def exercise(hm, names, stage, case):
    """Everything the GUI and CLI do with loaded ports."""
    portsjson = str(hm.temp_dir / "ports-out.json")
    steps = [
        ('cli_list', lambda: run_cli(hm, 'do_list', [])),
        ('cli_ports', lambda: run_cli(hm, 'do_ports', [])),
        ('cli_portsmd', lambda: run_cli(hm, 'do_portsmd', [])),
        ('cli_portsjson', lambda: run_cli(hm, 'do_portsjson', [portsjson])),
        ('cli_runtime_list', lambda: run_cli(hm, 'do_runtime_list', [])),
        ('list_ports', lambda: [hm.list_ports_new(filters=f, sort_by=s) for f in ([], ['installed'], ['rtr'], ['!rtr'], ['action'], ['update available'], ['broken']) for s in HM_SORT_ORDER]),
        ('list_ports_names', lambda: hm.list_ports_names_new(['installed'])),
        ('list_ports_old', lambda: [hm.list_ports(filters=f, sort_by=s) for f in ([], ['installed']) for s in HM_SORT_ORDER]),
        ('list_utils', lambda: hm.list_utils()),
        ]
    for name in names:
        steps += [
            ('port_info', lambda name=name: hm.port_info(name)),
            ('port_info_installed', lambda name=name: hm.port_info(name, installed=True)),
            ('portmd', lambda name=name: hm.port_info(name) and hm.portmd(hm.port_info(name))),
            ('match_requirements', lambda name=name: hm.port_info(name) and hm.match_requirements(hm.port_info(name))),
            ('port_images', lambda name=name: hm.port_images(name)),
            ('port_download_size', lambda name=name: hm.port_download_size(name)),
            ('port_download_url', lambda name=name: hm.port_download_url(name)),
            ]

    for step, fn in steps:
        try:
            fn()
        except (AssertionError, SandboxEscape):
            raise
        except Exception as err:
            record(f"{stage}:{step}", err, case)


def outside_intact(outside):
    assert (outside / "canary.txt").is_file(), "canary outside the ports dir was deleted"
    assert (outside / "dir" / "keep.txt").is_file(), "canary dir outside the ports dir was deleted"


def make_outside(tmp_path):
    outside = tmp_path / "outside"
    (outside / "dir").mkdir(parents=True, exist_ok=True)
    (outside / "canary.txt").write_text("keep")
    (outside / "dir" / "keep.txt").write_text("keep")
    return outside


def base_infos():
    with open(DATA_DIR / "ports.json") as fh:
        data = json.load(fh)

    infos = []
    for info in data['ports'].values():
        info = dict(info)
        source = info.pop('source', None)
        info['status'] = {'source': "PortMaster", 'md5': (source or {}).get('md5'), 'status': "Installed"}
        infos.append(info)

    files = basic_port_files()
    infos.append(files["testport/port.json"])
    return data, infos


################################################################################
## 1. Installed port.json files, loaded at startup
def test_fuzz_installed(tmp_path, make_hm, hm_dirs, guard):
    rng = random.Random(SEED)
    _, infos = base_infos()
    ports_dir = hm_dirs['ports_dir']
    outside = make_outside(tmp_path)

    for case_no in range(N):
        info = mutate(rng, rng.choice(infos), outside)
        raw = to_bytes(rng, info)
        case = raw[:300]

        shutil.rmtree(ports_dir)
        ports_dir.mkdir()
        files = basic_port_files()
        files.pop("testport/port.json")
        for name, data in files.items():
            path = ports_dir / name
            if name.endswith('/'):
                path.mkdir(parents=True, exist_ok=True)
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(data)

        (ports_dir / "testport" / "port.json").write_bytes(raw)
        if rng.random() < 0.2:
            ## Port folders as symlinks to the outside.
            try:
                (ports_dir / "linked").symlink_to(outside, target_is_directory=True)
            except OSError:
                ## No symlinks on this file system (exFAT on a device).
                pass

        try:
            hm = make_hm()
        except (AssertionError, SandboxEscape):
            raise
        except Exception as err:
            record("installed:startup", err, case)
            continue

        names = list(hm.installed_ports) + list(hm.broken_ports) + ["testport.zip"]
        exercise(hm, names, "installed", case)

        for name in names:
            try:
                hm.uninstall_port(name)
            except AssertionError:
                raise
            except Exception as err:
                record("installed:uninstall", err, case)

            outside_intact(outside)

        try:
            hm.load_ports()
        except Exception as err:
            record("installed:reload", err, case)


################################################################################
## 2. ports.json entries from a source
def test_fuzz_source(tmp_path, make_hm, monkeypatch, guard):
    rng = random.Random(SEED + 1)
    data, _ = base_infos()
    outside = make_outside(tmp_path)

    for case_no in range(N):
        fuzzed = json.loads(json.dumps(data))
        names = list(fuzzed['ports'])
        for _ in range(rng.randint(1, 3)):
            name = rng.choice(names)
            entry = mutate(rng, fuzzed['ports'][name], outside)
            if rng.random() < 0.3:
                entry['source'] = weird_values(rng, outside)
            elif isinstance(entry.get('source'), dict) and rng.random() < 0.5:
                entry['source'][rng.choice(['md5', 'url', 'size', 'date_added', 'date_updated', 'release_id'])] = weird_values(rng, outside)
            fuzzed['ports'][name] = entry

        if rng.random() < 0.1:
            fuzzed['ports'][rng.choice(['', '../x.zip', 'UPPER.ZIP', 'noext'])] = rng.choice(list(fuzzed['ports'].values()))
        if rng.random() < 0.05:
            fuzzed['ports'] = weird_values(rng, outside)
        if rng.random() < 0.05:
            fuzzed['utils'] = weird_values(rng, outside)

        case = json.dumps(fuzzed, default=str)[:300]
        monkeypatch.setattr(hm_net, "fetch_json", lambda url, fuzzed=fuzzed: json.loads(json.dumps(fuzzed)))

        def fake_download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
            files = basic_port_files(name=file_name.name.rsplit('.', 1)[0])
            return write_port_zip(file_name, files)

        monkeypatch.setattr(hm_net, "download", fake_download)

        try:
            hm = make_hm(offline=False)
            hm.sources['pm'].update()
        except (AssertionError, SandboxEscape):
            raise
        except Exception as err:
            record("source:load", err, case)
            continue

        names = list(fuzzed['ports']) if isinstance(fuzzed['ports'], dict) else []
        exercise(hm, names, "source", case)

        for name in names[:2]:
            try:
                hm.install_port(name)
            except AssertionError:
                raise
            except Exception as err:
                record("source:install", err, case)

            try:
                hm.uninstall_port(name)
            except AssertionError:
                raise
            except Exception as err:
                record("source:uninstall", err, case)

            outside_intact(outside)

        ## And again from the cache.
        try:
            make_hm(offline=True)
        except Exception as err:
            record("source:cached", err, case)


################################################################################
## 3. port.json inside a port zip
def test_fuzz_zip(tmp_path, make_hm, hm_dirs, guard):
    rng = random.Random(SEED + 2)
    _, infos = base_infos()
    outside = make_outside(tmp_path)
    hm = make_hm()

    for case_no in range(N):
        files = basic_port_files()
        info = mutate(rng, files["testport/port.json"] if rng.random() < 0.5 else rng.choice(infos), outside)
        files["testport/port.json"] = to_bytes(rng, info)
        case = files["testport/port.json"][:300]
        zip_file = write_port_zip(hm_dirs['temp_dir'] / "testport.zip", files)

        try:
            hm.install_port(str(zip_file))
        except (AssertionError, SandboxEscape):
            raise
        except Exception as err:
            record("zip:install", err, case)

        try:
            hm.load_ports()
        except Exception as err:
            record("zip:load_ports", err, case)
            hm = make_hm()
            continue

        names = list(hm.installed_ports) + list(hm.broken_ports)
        exercise(hm, names, "zip", case)
        for name in names:
            try:
                hm.uninstall_port(name)
            except AssertionError:
                raise
            except Exception as err:
                record("zip:uninstall", err, case)

            outside_intact(outside)


################################################################################
## 4. The rest of what load_ports reads: ports_info.json, port_stats.json, script signatures
PORTS_INFO = {
    "items": {
        "Test Port.sh": "testport.zip", "testport/": "testport.zip",
        "Abes Adventure.sh": "abes.zip", "abes/": "abes.zip",
        "Shared.sh": ["one.zip", "two.zip"],
        "SPROUT.sh": "sprout.zip", "sprout/": "sprout.zip",
        },
    "md5": {},
    "ports": {
        "testport.zip": {"date": ["2021-01-01", "2022-01-01"], "file": "testport/port.json", "items": ["Test Port.sh", "testport/"], "name": "testport.zip"},
        "abes.zip": {"date": ["2020-01-01", "2020-01-01"], "file": "abes/abes.port.json", "items": ["Abes Adventure.sh", "abes/"], "name": "abes.zip"},
        "sprout.zip": {"date": ["2025-07-16", "2025-07-16"], "file": "sprout/port.json", "items": ["SPROUT.sh", "sprout/"], "name": "sprout.zip"},
        },
    "portsmd_fix": {"cebion": ["Cebion"]},
    }


def mutate_any(rng, value, outside, depth=0):
    """Mutate somewhere in a nested json value."""
    value = json.loads(json.dumps(value))
    if rng.random() < 0.15 or depth > 4 or not isinstance(value, (dict, list)) or not value:
        return weird_values(rng, outside)

    if isinstance(value, dict):
        key = rng.choice(list(value) + ['new-key'])
        roll = rng.random()
        if roll < 0.15:
            value.pop(key, None)
        elif roll < 0.25:
            value[rng.choice(weird_strings(outside))] = value.get(key, weird_values(rng, outside))
        else:
            value[key] = mutate_any(rng, value.get(key), outside, depth + 1)
    else:
        index = rng.randrange(len(value))
        value[index] = mutate_any(rng, value[index], outside, depth + 1)

    return value


def test_fuzz_ports_dir(tmp_path, make_hm, hm_dirs, guard):
    rng = random.Random(SEED + 3)
    ports_dir = hm_dirs['ports_dir']
    outside = make_outside(tmp_path)
    hm = make_hm()

    for case_no in range(N):
        ports_info = PORTS_INFO
        for _ in range(rng.randint(1, 4)):
            ports_info = mutate_any(rng, ports_info, outside)

        shutil.rmtree(ports_dir)
        ports_dir.mkdir()

        layout = {}
        for script, folder in (("Test Port.sh", "testport"), ("Abes Adventure.sh", "abes"), ("SPROUT.sh", "sprout"), ("Shared.sh", None), ("Unknown.sh", "unknown")):
            if rng.random() < 0.2:
                continue

            header = "#!/bin/bash\n"
            if rng.random() < 0.5:
                sig = [rng.choice(weird_strings(outside) + ["testport.zip", "abes.zip", "sprout.zip"]) for _ in range(rng.randint(0, 3))]
                header += "# PORTMASTER: " + ", ".join(sig).replace("\n", " ") + "\n"
            layout[script] = header + "echo\n"

            if folder:
                layout[f"{folder}/"] = ""
                if rng.random() < 0.5:
                    files = basic_port_files(name=folder, script=script)
                    info = files[f"{folder}/port.json"]
                    if rng.random() < 0.6:
                        info = mutate(rng, info, outside)
                    json_name = rng.choice(["port.json", f"{folder}.port.json"])
                    layout[f"{folder}/{json_name}"] = to_bytes(rng, info)
                    if rng.random() < 0.1:
                        layout[f"{folder}/other.port.json"] = to_bytes(rng, mutate(rng, info, outside))

        if rng.random() < 0.3:
            ## A script renamed by the user, signed with its old name.
            layout["Renamed.sh"] = "#!/bin/bash\n# PORTMASTER: testport.zip, Test Port.sh\necho\n"

        for name, data in layout.items():
            path = ports_dir / name
            if name.endswith('/'):
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode('utf-8', 'surrogatepass'))

        (hm.cfg_dir / "ports_info.json").write_bytes(to_bytes(rng, ports_info))
        stats = {"ports": {"testport.zip": 10, "sprout.zip": 3}}
        if rng.random() < 0.5:
            stats = mutate_any(rng, stats, outside)
        (hm.cfg_dir / "port_stats.json").write_bytes(to_bytes(rng, stats))

        hm._PORTS_INFO = None
        hm._PORTS_DOWNLOAD = None
        case = (json.dumps(ports_info, default=str)[:300], sorted(layout))

        try:
            hm.load_ports()
        except (AssertionError, SandboxEscape):
            raise
        except Exception as err:
            record("ports_dir:load_ports", err, case)
            continue

        names = list(hm.installed_ports) + list(hm.broken_ports)
        exercise(hm, names, "ports_dir", case)
        for name in names:
            try:
                hm.uninstall_port(name)
            except AssertionError:
                raise
            except Exception as err:
                record("ports_dir:uninstall", err, case)

            outside_intact(outside)


################################################################################
## 5. The GUI's ports list and port info screens, drawn with fuzzed ports
@pytest.mark.sdl
def test_fuzz_gui(gui, tmp_path, make_hm, hm_dirs, monkeypatch):
    from pugwash import scenes

    rng = random.Random(SEED + 4)
    data, infos = base_infos()
    outside = make_outside(tmp_path)
    ports_dir = hm_dirs['ports_dir']
    saved_scenes = list(gui.scenes)
    monkeypatch.setattr(gui, "message_box", lambda *a, **kw: True)

    def fake_download(file_name, file_url, md5_source=None, md5_result=None, callback=None, no_check=False):
        return write_port_zip(file_name, basic_port_files(name=file_name.name.rsplit('.', 1)[0]))

    monkeypatch.setattr(hm_net, "download", fake_download)

    try:
        for case_no in range(max(N // 10, 20)):
            fuzzed = json.loads(json.dumps(data))
            for name in rng.sample(list(fuzzed['ports']), rng.randint(1, len(fuzzed['ports']))):
                fuzzed['ports'][name] = mutate(rng, fuzzed['ports'][name], outside)
                if rng.random() < 0.3:
                    ## Text that looks like theme template tags.
                    attr = fuzzed['ports'][name].setdefault('attr', {})
                    if isinstance(attr, dict):
                        attr[rng.choice(['title', 'desc', 'inst'])] = rng.choice([
                            "{port_info.title}", "{", "}", "{{}}", "{0}", "{if:port_info.title}", "{endif}",
                            "{port_info.description}" * 50, "\n" * 200, "x" * 20000, "\t\x00\u202e",
                            "\n", " \n ", "\r", "\t", "\u200b", "\ufeff", "\x00", "a\x00b", "\U0001F3AE",
                            "x" * 500 + " " + "y" * 500, "\n\n\nx", "\u65e5\u672c\u8a9e" * 300])

            monkeypatch.setattr(hm_net, "fetch_json", lambda url, fuzzed=fuzzed: json.loads(json.dumps(fuzzed)))

            shutil.rmtree(ports_dir)
            ports_dir.mkdir()
            files = basic_port_files()
            files["testport/port.json"] = to_bytes(rng, mutate(rng, files["testport/port.json"], outside))
            for name, value in files.items():
                path = ports_dir / name
                if name.endswith('/'):
                    path.mkdir(parents=True, exist_ok=True)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(value if isinstance(value, bytes) else value.encode('utf-8'))

            case = json.dumps(fuzzed, default=str)[:300]
            try:
                hm = make_hm(offline=False)
                hm.sources['pm'].update()
            except Exception as err:
                record("gui:hm", err, case)
                continue

            gui.hm = hm
            gui.clear_port_sizes()
            try:
                for mode, options in (('install', {'mode': 'install', 'name': None}),
                                      ('uninstall', {'mode': 'uninstall', 'base_filters': ['installed']})):
                    gui.scenes = list(saved_scenes)
                    list_scene = scenes.PortsListScene(gui, options)
                    gui.push_scene('ports', list_scene)
                    gui.do_loop(no_delay=True)

                    for index, port_name in enumerate(list(list_scene.port_list)):
                        list_scene.tags['ports_list'].selected = index
                        gui.do_loop(no_delay=True)

                        gui.push_scene('port_info', scenes.PortInfoScene(gui, port_name, mode, list_scene))
                        gui.do_loop(no_delay=True)
                        gui.pop_scene()
                        gui.do_loop(no_delay=True)

            except (AssertionError, SandboxEscape):
                raise
            except Exception as err:
                record("gui:screens", err, case)

    finally:
        gui.scenes = saved_scenes
        gui.hm = None
        gui.clear_port_sizes()
