# SPDX-License-Identifier: MIT
#
# Scene logic tested against a fake gui, nothing is drawn.

from types import SimpleNamespace

import pytest

import harbourmaster


pytestmark = pytest.mark.sdl


@pytest.fixture(scope="module")
def pugscene():
    from pugwash import scenes as pugscene
    return pugscene


class FakeOptionList:
    def __init__(self):
        self.options = []

    def reset_options(self):
        self.options.clear()

    def add_option(self, option_id, text, description=None):
        self.options.append(option_id)

    def list_select(self, index):
        pass

    def selected_option(self):
        return None


def fake_hm_for(cfw_name, monkeypatch, tmp_path):
    """
    A minimal stand-in for HarbourMaster, with device info from hardware.py and
    the platform name worked out the same way HarbourMaster does.
    """
    monkeypatch.setenv("CFW_NAME", cfw_name)
    harbourmaster.hardware._CACHED_DICT = None
    device = harbourmaster.device_info()

    return SimpleNamespace(
        device=device,
        platform_name=device['name'].lower(),
        platform=SimpleNamespace(gamelist_file=lambda: None),
        cfg_data={},
        tools_dir=tmp_path,
        get_gcd_modes=lambda: [],
        )


@pytest.fixture
def option_ids(pugscene, monkeypatch, tmp_path):
    def _option_ids(cfw_name):
        option_list = FakeOptionList()

        def fake_load_regions(self, section, required_tags):
            self.tags['option_list'] = option_list

        monkeypatch.setattr(pugscene.OptionScene, "load_regions", fake_load_regions)
        monkeypatch.setattr(pugscene.OptionScene, "set_buttons", lambda self, buttons: None)
        ## Pretend there is a second SD card, the muOS ports location option needs one.
        monkeypatch.setattr(pugscene.options.subprocess, "getoutput", lambda args: "/dev/mmcblk1p1 /mnt/sdcard")

        gui = SimpleNamespace(
            hm=fake_hm_for(cfw_name, monkeypatch, tmp_path),
            themes=SimpleNamespace(get_theme_schemes_list=lambda: []),
            sounds=SimpleNamespace(music_is_disabled=False, sound_is_disabled=False),
            )

        pugscene.OptionScene(gui)
        return option_list.options

    return _option_ids


def test_muos_options(option_ids):
    options = option_ids("muOS")

    assert 'muos-port-mode-toggle' in options
    assert 'trimui-port-mode-toggle' not in options
    assert 'restore-portmaster' not in options


def test_trimui_options(option_ids):
    options = option_ids("TrimUI")

    assert 'trimui-port-mode-toggle' in options
    assert 'muos-port-mode-toggle' not in options
    assert 'restore-portmaster' not in options


def test_other_cfw_options(option_ids):
    options = option_ids("ArkOS")

    assert 'muos-port-mode-toggle' not in options
    assert 'trimui-port-mode-toggle' not in options
    assert 'restore-portmaster' in options


################################################################################
## Button layout from the platform (normal GUI and fifo_control both use this)
@pytest.fixture
def restore_buttons(gui):
    events = gui.events
    saved = (dict(events.BUTTON_MAP), dict(events.KEY_MAP), events.XBOX_FIXED, gui.SWAP_BUTTONS, gui.hm)
    yield gui
    events.BUTTON_MAP.clear()
    events.BUTTON_MAP.update(saved[0])
    events.KEY_MAP.clear()
    events.KEY_MAP.update(saved[1])
    events.XBOX_FIXED, gui.SWAP_BUTTONS, gui.hm = saved[2:]


@pytest.mark.parametrize("platform_name, xbox_fix, swap", [
    ("default", False, False),
    ("knulli", True, False),
    ("knulli", False, True),
    ("retrodeck", False, False),
    ])
def test_apply_button_mapping(restore_buttons, platform_name, xbox_fix, swap):
    import sdl2
    gui = restore_buttons
    platform = SimpleNamespace(WANT_XBOX_FIX=xbox_fix, WANT_SWAP_BUTTONS=swap)
    gui.hm = SimpleNamespace(platform=platform, platform_name=platform_name)

    gui.apply_button_mapping()
    gui.apply_button_mapping()  # twice is the same as once

    a_button = gui.events.BUTTON_MAP[sdl2.SDL_CONTROLLER_BUTTON_A]
    assert a_button == ('B' if xbox_fix else 'A')
    assert gui.SWAP_BUTTONS is swap
    assert (gui.events.KEY_MAP.get(sdl2.SDLK_q) == 'START') is (platform_name == 'retrodeck')
