# SPDX-License-Identifier: MIT
#
# harbourmaster.cli's commands run in-process (test_cli.py runs the script), on
# HarbourMasters made by the fixtures.

import json

import pytest

import harbourmaster
from harbourmaster import cli, console

from conftest import basic_port_files, write_port_zip


@pytest.fixture(autouse=True)
def plain_output():
    console.do_color(False)
    yield
    console.do_cprint_output(None)


@pytest.fixture
def cli_hm(online_hm):
    ## The commands read hm.callback.config, as ConsoleCallback has it.
    online_hm.callback.config = {'quiet': True}
    return online_hm


################################################################################
## ConsoleCallback
@pytest.mark.parametrize("amount, total, fmt, expected", [
    (1024, None, 'data', "1.00 KB"),
    (1024, 2048, 'data', "1.00 KB / 2.00 KB"),
    (50, None, '%', "50.00 %"),
    (250, None, '%', "100.00 %"),
    (1, 4, '%', "25.00 %"),
    (8, 4, '%', "100.00 %"),
    (3, None, None, "3"),
    (3, 9, None, "3 / 9"),
    ])
def test_console_callback_format_progress(amount, total, fmt, expected):
    assert cli.ConsoleCallback({'quiet': False}).format_progress(amount, total, fmt) == expected


def test_console_callback_progress(capsys):
    ccb = cli.ConsoleCallback({'quiet': False})

    ## Only data progress is drawn.
    ccb.progress("Counting", 1, 2, None)
    assert capsys.readouterr().out == ""

    ccb.progress("Downloading", 10, 40, 'data')
    ccb.progress("Downloading", 20, 40, 'data')
    out = capsys.readouterr().out
    assert out.count(" - Downloading") == 1
    assert "[" + "|" * 20 + " " * 20 + "]" in out

    ccb.progress("Downloading", 5, None, 'data')
    assert "?" * 40 in capsys.readouterr().out

    ## None resets the title, so it is printed again.
    ccb.progress(None, 0)
    assert ccb.last_message is None
    ccb.progress("Downloading", 5, 10, 'data')
    assert " - Downloading" in capsys.readouterr().out


def test_console_callback_quiet(capsys):
    cli.ConsoleCallback({'quiet': True}).message("hidden")
    cli.ConsoleCallback({'quiet': False}).message("shown")
    assert capsys.readouterr().out == "shown\n"

    assert cli.ConsoleCallback({'quiet': False}).message_box("ignored") is None


################################################################################
## Commands
def test_list(cli_hm, capsys):
    assert cli.do_list(cli_hm, []) == 0
    out = capsys.readouterr().out

    assert "Available ports:" in out
    for port in ("sprout.zip", "100liljumps.zip", "2048plus.zip"):
        assert port in out

    ## Experimental ports are hidden by default.
    assert "starfighter.zip" not in out
    assert "Filters: " in out and "platformer" in out


def test_list_with_filters(cli_hm, capsys):
    cli.do_list(cli_hm, ["puzzle"])
    out = capsys.readouterr().out

    assert "2048plus.zip" in out
    assert "sprout.zip" not in out
    ## The filters asked for aren't offered again.
    assert "puzzle" not in out.split("Filters: ")[1]


def test_list_unknown_filter(cli_hm, capsys):
    cli.do_list(cli_hm, ["no-such-genre"])
    out = capsys.readouterr().out

    assert ".zip" not in out
    assert "Filters: \n" in out


def test_ports_empty(cli_hm, capsys):
    assert cli.do_ports(cli_hm, []) == 0
    assert "No ports found." in capsys.readouterr().out


def test_ports_installed_unknown_and_broken(cli_hm, hm_dirs, capsys):
    ports_dir = hm_dirs['ports_dir']
    assert cli_hm.install_port(str(write_port_zip(hm_dirs['temp_dir'] / "testport.zip", basic_port_files()))) == 0
    assert cli_hm.install_port(str(write_port_zip(
        hm_dirs['temp_dir'] / "other.zip", basic_port_files(name="other", script="Other.sh")))) == 0

    (ports_dir / "Mystery.sh").write_text("#!/bin/bash\n")
    (ports_dir / "Other.sh").unlink()
    cli_hm.load_ports()

    cli.do_ports(cli_hm, [])
    out = capsys.readouterr().out

    assert "Installed Ports:\n- testport.zip" in out
    assert "Unknown Ports:\n- Mystery.sh" in out
    assert "Broken Ports:\n- other.zip" in out
    assert "No ports found." not in out


def test_portsmd(cli_hm, capsys):
    assert cli.do_portsmd(cli_hm, ["", "platformer,", ","]) == 0
    out = capsys.readouterr().out

    assert 'Title="-SPROUT- ."' in out
    assert 'Title="100_Lil_Jumps ."' in out
    assert 'runtype="rtr"' in out
    assert 'locat="sprout.zip"' in out
    assert "2048" not in out

    filters = out.split('Filters="')[1]
    assert "installed" not in filters and "platformer" not in filters


def test_portsmd_title_kinds(cli_hm):
    info = cli_hm.port_info("sprout.zip")

    info['attr']['reqs'] = ['opengl']
    assert cli_hm.portmd(info).startswith('<r>Title_F</r>')

    info['attr']['reqs'] = ['power']
    assert cli_hm.portmd(info).startswith('<r>Title_P</r>')

    info['attr']['desc'] = "None"
    info['attr']['runtime'] = "mono-6.12.0.122-aarch64.squashfs"
    md = cli_hm.portmd(info)
    assert '<r>Desc</r>="<y></y>"' in md
    assert '<r>mono</r>="<e>y</e>"' in md


def test_portsjson_to_file(cli_hm, tmp_path):
    out_file = tmp_path / "ports.json"
    assert cli.do_portsjson(cli_hm, [str(out_file)]) == 0

    data = json.loads(out_file.read_text())
    names = [port['name'] for port in data['ports']]
    assert sorted(names) == ["100liljumps.zip", "2048plus.zip", "sprout.zip"]

    sprout = data['ports'][names.index("sprout.zip")]
    assert sprout['download_url'].endswith("/sprout.zip")
    assert sprout['download_size'] == 8159843
    assert set(sprout['attr']['media']) == {"screenshot", "cover", "thumbnail", "video"}
    assert 'status' not in sprout and 'files' not in sprout

    assert "ags_3.6.squashfs" in data['utils']
    assert data['utils']['ags_3.6.squashfs']['download_size'] > 0


def test_portsjson_stdout_rewrites_release_urls(cli_hm, capsys):
    source = cli_hm.sources['pm']
    source._data['sprout.zip']['url'] = "https://github.com/x/PortMaster-Releases/releases/download/2024-01-02_1234/sprout.zip"

    cli.do_portsjson(cli_hm, [])
    data = json.loads(capsys.readouterr().out)

    sprout = [port for port in data['ports'] if port['name'] == "sprout.zip"][0]
    assert sprout['download_url'] == "https://github.com/x/PortMaster-Releases/releases/latest/download/sprout.zip"


def test_install_and_uninstall(cli_hm, hm_dirs):
    assert cli.do_install(cli_hm, ["2048plus.zip"]) == 0
    assert (hm_dirs['ports_dir'] / "2048plus").is_dir()
    ## Quiet is switched off while installing, and back afterwards.
    assert cli_hm.callback.config['quiet'] is True

    ## Each CLI run is one command: installing doesn't reload the installed ports.
    cli_hm.load_ports()

    assert cli.do_uninstall(cli_hm, ["2048plus.zip"]) == 0
    assert not (hm_dirs['ports_dir'] / "2048plus").exists()
    assert cli_hm.callback.config['quiet'] is True


def test_install_stops_at_the_first_failure(cli_hm, hm_dirs):
    assert cli.do_install(cli_hm, ["missing.zip", "2048plus.zip"]) != 0
    assert not (hm_dirs['ports_dir'] / "2048plus").exists()
    assert cli_hm.callback.config['quiet'] is True


def test_uninstall_unknown_port(cli_hm):
    assert cli.do_uninstall(cli_hm, ["missing.zip"]) != 0
    assert cli_hm.callback.config['quiet'] is True


@pytest.mark.parametrize("command", [cli.do_install, cli.do_uninstall, cli.do_runtime_check])
def test_commands_without_arguments_show_their_help(cli_hm, command, capsys):
    assert command(cli_hm, []) == 0
    out = capsys.readouterr().out

    assert out.startswith("Missing arguments.")
    assert command.__name__[3:] in out


def test_runtime_list(cli_hm, capsys):
    (cli_hm.libs_dir / "gmtoolkit.squashfs").write_bytes(b"x")

    assert cli.do_runtime_list(cli_hm, []) == 0
    out = capsys.readouterr().out.splitlines()

    assert out[0] == "Available Runtimes:"
    assert "- gmtoolkit.squashfs (installed)" in out
    assert "- ags_3.6.squashfs" in out
    ## Listed once each, sorted.
    assert out[1:] == sorted(set(out[1:]))


def test_runtime_check_restores_quiet(cli_hm, monkeypatch):
    monkeypatch.setattr(cli_hm, "check_runtime", lambda name: 42)

    assert cli.do_runtime_check(cli_hm, ["gmtoolkit.squashfs"]) == 42
    assert cli_hm.callback.config['quiet'] is True


def test_reload(cli_hm, hm_dirs):
    assert cli_hm.install_port(str(write_port_zip(hm_dirs['temp_dir'] / "testport.zip", basic_port_files()))) == 0
    cli_hm.installed_ports = {}

    assert cli.do_reload(cli_hm, []) == 0
    assert list(cli_hm.installed_ports) == ["testport.zip"]


def test_update_sources(cli_hm, capsys, monkeypatch):
    updated = []
    for prefix, source in cli_hm.sources.items():
        monkeypatch.setattr(source, "update", lambda prefix=prefix: updated.append(prefix))

    assert cli.do_update(cli_hm, []) == 0
    assert sorted(updated) == ['pm', 'pmmv']

    updated.clear()
    assert cli.do_update(cli_hm, ["ALL"]) == 0
    assert sorted(updated) == ['pm', 'pmmv']

    updated.clear()
    assert cli.do_update(cli_hm, ["pmmv", "nope"]) == 0
    assert updated == ['pmmv']
    assert "Unknown source nope" in capsys.readouterr().out


def test_auto_update(cli_hm, monkeypatch):
    called = []
    for prefix, source in cli_hm.sources.items():
        monkeypatch.setattr(source, "auto_update", lambda prefix=prefix: called.append(prefix))

    assert cli.do_auto_update(cli_hm, []) == 0
    assert sorted(called) == ['pm', 'pmmv']


def test_device_info(cli_hm, tmp_path, capsys, monkeypatch):
    ## hardware.DEVICES is an empty shim since device_info.txt took over.
    monkeypatch.setattr(harbourmaster, "DEVICES", {
        "rg35xx": {'device': "rg35xx", 'manufacturer': "Anbernic", 'cfw': ["muOS", "Knulli"]}})

    out_file = tmp_path / "devices.json"
    cli.do_device_info(cli_hm, [str(out_file)])
    data = json.loads(out_file.read_text())

    assert list(data) == ["rg35xx"]
    assert sorted(data["rg35xx"]) == ["Knulli", "muOS"]
    info = data["rg35xx"]["muOS"]
    assert info['name'] == "muos" and info['manufacturer'] == "Anbernic"
    assert info['version'] == "N/A"
    assert 'capabilities' in info and 'resolution' in info

    cli.do_device_info(cli_hm, [])
    assert json.loads(capsys.readouterr().out) == data


def test_help(cli_hm, capsys):
    assert cli.do_help(cli_hm, []) == 0
    out = capsys.readouterr().out
    assert "All available commands:" in out
    assert "--offline" in out

    assert cli.do_help(cli_hm, ["LIST"]) == 0
    assert "List available ports" in capsys.readouterr().out

    assert cli.do_help(cli_hm, ["nope"]) == 255
    out = capsys.readouterr().out
    assert "unknown help command nope" in out
    assert "All available commands:" in out


def test_every_command_has_help(cli_hm, capsys):
    ## `help device_info` crashed: it had no docstring.
    for name, command in cli.all_commands.items():
        assert cli.do_help(cli_hm, [name]) == 0, name
        assert "{command}" not in capsys.readouterr().out


################################################################################
## fifo_control
def test_fifo_control_needs_two_paths(cli_hm):
    assert cli.do_fifo_control(cli_hm, ["one"]) == 0


def test_fifo_control_commands(cli_hm, tmp_path, monkeypatch):
    import threading

    fifo = tmp_path / "hm_input"
    done = tmp_path / "hm_done"
    out_file = tmp_path / "ports.md"
    ## Left over from a previous run.
    fifo.write_text("stale")
    done.write_text("stale")

    reloaded = []
    monkeypatch.setitem(cli.fifo_commands, 'reload', lambda hm, argv: reloaded.append(argv))

    result = []
    thread = threading.Thread(target=lambda: result.append(cli.do_fifo_control(cli_hm, [str(fifo), str(done)])))
    thread.start()

    import time
    end = time.monotonic() + 10
    while not (fifo.exists() and not fifo.is_file()) and time.monotonic() < end:
        time.sleep(0.01)

    with open(str(fifo), 'w') as fh:
        fh.write("\n")                       ## blank: skipped
        fh.write("onlyone\n")                ## no output file part: skipped
        fh.write(f"portsmd:{out_file}:puzzle\n")
        fh.write("RELOAD::a:b\n")
        fh.write("exit\n")

    thread.join(10)
    assert not thread.is_alive()
    assert result == [0]

    assert '2048plus.zip' in out_file.read_text()
    assert 'sprout.zip' not in out_file.read_text()
    assert reloaded == [['a', 'b']]
    assert done.is_file()
    ## The pipe is removed afterwards.
    assert not fifo.exists()


################################################################################
## main()
@pytest.fixture
def run_main(hm_dirs, callback, monkeypatch):
    made = []

    def make_hm(config, temp_dir=None, callback=None):
        hm = harbourmaster.HarbourMaster(config, temp_dir=temp_dir, callback=callback, **{
            key: value for key, value in hm_dirs.items() if key != 'temp_dir'})
        made.append((config, hm))
        return hm

    monkeypatch.setattr(cli, "HarbourMaster", make_hm)

    def run(*args):
        result = cli.main(["harbourmaster", *args])
        return result, (made[-1][0] if made else None)

    return run


def test_main_no_command_shows_help(run_main, capsys):
    result, config = run_main("--offline")

    assert result == 1
    assert config['offline'] and config['no-check']
    assert "All available commands:" in capsys.readouterr().out


def test_main_help_flag(run_main, capsys):
    result, config = run_main("--offline", "--help", "install")

    assert result == 1
    assert "Install a port" in capsys.readouterr().out


def test_main_nothing(run_main, capsys):
    assert run_main("--offline", "nothing")[0] == 0
    assert "All available commands:" not in capsys.readouterr().out


def test_main_unknown_command(run_main, capsys):
    assert run_main("--offline", "frobnicate")[0] == 2
    assert "Command frobnicate not found." in capsys.readouterr().out


def test_main_unknown_flag_is_dropped(run_main, capsys):
    result, config = run_main("--offline", "--frobnicate", "ports")

    assert result == 0
    assert 'frobnicate' not in config
    assert "No ports found." in capsys.readouterr().out


def test_main_double_dash_ends_flags(run_main, capsys):
    ## After `--` a flag-looking word is an argument: here a help topic.
    result, config = run_main("--offline", "help", "--", "--quiet")

    assert result == 255
    assert config['quiet'] is False
    assert "unknown help command --quiet" in capsys.readouterr().out


def test_main_command_is_case_insensitive(run_main, capsys):
    assert run_main("--offline", "PORTS")[0] == 0
    assert "No ports found." in capsys.readouterr().out


def test_main_colour_flags(run_main, monkeypatch):
    modes = []
    monkeypatch.setattr(cli.console, "do_color", lambda mode=None: modes.append(mode))

    run_main("--offline", "--no-colour", "nothing")
    run_main("--offline", "--force-colour", "nothing")
    ## no-colour wins.
    run_main("--offline", "--force-colour", "--no-colour", "nothing")

    assert modes == [False, True, False]


def test_main_debug_flag_file(run_main, monkeypatch, tmp_path):
    flag_dir = tmp_path / "flagtools"
    (flag_dir / "PortMaster").mkdir(parents=True)
    (flag_dir / "PortMaster" / "debug_all_the_things_flag").write_text("")
    monkeypatch.setattr(harbourmaster, "HM_TOOLS_DIR", flag_dir)

    removed = []
    monkeypatch.setattr(cli.logger, "remove", lambda handler=None: removed.append(handler))
    monkeypatch.setattr(cli.logger, "add", lambda *args, **kwargs: 99)

    result, config = run_main("--offline", "nothing")

    assert result == 0
    assert config['debug'] is True
    assert removed == [0]
