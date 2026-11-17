# SPDX-License-Identifier: MIT
#
# pugwash's SoundManager without a sound card: SDL_mixer's calls are faked, the way they
# fail on a device (a NULL pointer, not None).

import ctypes
from pathlib import Path
from types import SimpleNamespace

import sdl2.sdlmixer

from pugwash.sdl.sound import SoundManager


NULL_MUSIC = ctypes.POINTER(sdl2.sdlmixer.Mix_Music)()
NULL_CHUNK = ctypes.POINTER(sdl2.sdlmixer.Mix_Chunk)()


class FakeMixer:
    def __init__(self, monkeypatch, bad=()):
        self.bad = set(bad)
        self.playing = []
        self.freed = []
        for name, fake in (
                ("Mix_LoadMUS", self.load_music), ("Mix_PlayMusic", self.play_music),
                ("Mix_FreeMusic", self.freed.append), ("Mix_VolumeMusic", lambda volume: 0),
                ("Mix_LoadWAV", self.load_wav), ("Mix_VolumeChunk", lambda chunk, volume: 0),
                ("Mix_GetError", lambda: b"Unsupported codec"), ("Mix_GetMusicPosition", lambda music: 0.0),
                ("Mix_HaltChannel", lambda channel: 0), ("Mix_FreeChunk", lambda chunk: None)):
            monkeypatch.setattr(sdl2.sdlmixer, name, fake)
        ## No real SDL_mixer calls when the fakes are collected.
        monkeypatch.setattr(SoundManager, "__del__", lambda self: None)

    def load_music(self, path):
        path = path.decode()
        return NULL_MUSIC if path in self.bad else SimpleNamespace(path=path)

    def play_music(self, music, loops):
        self.playing.append(music.path)
        return 0

    def load_wav(self, path):
        path = path.decode()
        return NULL_CHUNK if path in self.bad else SimpleNamespace(path=path)


def manager(theme_dir):
    sounds = SoundManager.__new__(SoundManager)
    sounds.gui = SimpleNamespace(resources=SimpleNamespace(find=lambda name: Path(theme_dir[0]) / name))
    sounds.sounds = {}
    sounds.song = None
    sounds.filename = None
    sounds.is_init = True
    sounds.init_failed = False
    sounds.sound_is_disabled = False
    sounds._music_is_disabled = False
    sounds.music_position = {}
    return sounds


def test_music_that_does_not_load_does_not_silence_the_next_theme(monkeypatch):
    ## Every preview theme had its own music.ogg; one that SDL_mixer couldn't play
    ## (a cover picture as a video stream) left the next themes silent.
    mixer = FakeMixer(monkeypatch, bad={"/themes/b/music.ogg"})
    theme_dir = ["/themes/a"]
    sounds = manager(theme_dir)

    sounds.easy_music("music.ogg")
    assert mixer.playing == ["/themes/a/music.ogg"]

    for theme in ("b", "c"):
        sounds.unload_all()
        theme_dir[0] = f"/themes/{theme}"
        sounds.easy_music("music.ogg")

    assert mixer.playing == ["/themes/a/music.ogg", "/themes/c/music.ogg"]
    assert sounds.filename == "music.ogg" and sounds.song.path == "/themes/c/music.ogg"


def test_music_that_does_not_load_stops_the_old_song(monkeypatch):
    mixer = FakeMixer(monkeypatch, bad={"/themes/a/broken.ogg"})
    sounds = manager(["/themes/a"])

    sounds.easy_music("good.ogg")
    good = sounds.song
    assert sounds.easy_music("broken.ogg") is None

    assert mixer.freed == [good]
    assert sounds.song is None and sounds.filename is None

    sounds.easy_music("good.ogg")
    assert mixer.playing == ["/themes/a/good.ogg", "/themes/a/good.ogg"]


def test_sound_that_does_not_load_is_not_kept(monkeypatch):
    FakeMixer(monkeypatch, bad={"/themes/a/broken.wav"})
    sounds = manager(["/themes/a"])

    assert sounds.load("broken.wav", "click") is None
    assert sounds.load("fine.wav", "tick") == "tick"
    assert list(sounds.sounds) == ["tick"]
