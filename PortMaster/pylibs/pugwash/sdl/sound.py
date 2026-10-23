# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Music and sound effects.

import sdl2
import sdl2.ext
import sdl2.sdlmixer


class SoundManager():
    '''
    The SoundManager class loads and plays sound files.
    '''
    def __init__(self, gui):
        self.gui = gui
        self.sounds = {}
        self.song = None
        self.filename = None
        self.is_init = False
        self.init_failed = False

        self.sound_is_disabled = False
        self._music_is_disabled = False
        self.music_position = {}

        self.init()

    def init(self):
        '''
        Initialize the sound system
        '''
        if not self.is_init and not self.init_failed:
            if sdl2.SDL_Init(sdl2.SDL_INIT_AUDIO) != 0:
                print("Cannot initialize audio system: {}".format(sdl2.SDL_GetError()))
                self.init_failed = True
                return

            # if (sdl2.sdlmixer.Mix_Linked_Version()[0].minor < 6):
            #     print(f'SDL Mixer is too old.')
            #     self.init_failed = True
            #     return

            total_audio_devices = sdl2.SDL_GetNumAudioDevices(0)
            # print(f"Audio Devices: {total_audio_devices}")
            for i in range(total_audio_devices):
                # print(f"- {i}: {sdl2.SDL_GetAudioDeviceName(i, 0)}")
                pass

            if sdl2.sdlmixer.Mix_OpenAudio(44100, sdl2.sdlmixer.MIX_DEFAULT_FORMAT, 2, 1024):
                # print(f'Cannot open mixed audio: {sdl2.sdlmixer.Mix_GetError()}')
                self.init_failed = True
                return

            self.is_init = True

            # print(f"SoundManager: Current Volume {self.volume}")

    def load(self, filename, name=None, volume=128):
        '''
        Load a given sound file into the Sound Manager

        :param filename: filename for sound file to load
        :param name: alternate name to use to play the sound instead of its filename
        :param volume: default volume level to play the sound at, from 0 to 128
        '''
        if not self.is_init:
            return None

        res_filename = self.gui.resources.find(filename)

        if res_filename is None:
            # print(f"SOUND: unable to find {filename}")
            return None

        sample = sdl2.sdlmixer.Mix_LoadWAV(
                sdl2.ext.compat.byteify(str(res_filename), 'utf-8'))

        if name is None:
            name = res_filename.name

        if sample is None:
            return None
            # raise GUIRuntimeError(f'Cannot open audio file: {sdl2.Mix_GetError()}')

        sdl2.sdlmixer.Mix_VolumeChunk(sample, (int(max(0, min(volume, 128)))))
        self.sounds[name] = sample
        return name

    def easy_music(self, filename, loops=-1, volume=128):
        if filename == self.filename:
            sdl2.sdlmixer.Mix_VolumeMusic(int(max(0, min(volume, 128))))
            return

        if self.song is not None:
            try:
                self.music_position[self.filename] = sdl2.sdlmixer.Mix_GetMusicPosition(self.song)
            except RuntimeError as err:
                # No music resumption for you
                pass

        if filename is None:
            self.stop()
            return

        self.music(filename, loops, volume)

    def music(self, filename, loops=-1, volume=128):
        '''
        Loads a music file and plays immediately plays it

        :param filename: path to music file to load and play
        :param loops: number of times to play song, or loop forever by default
        :param volume: volume level to play music, between 0 to 128
        '''
        if not self.is_init:
            return None

        if self.music_is_disabled:
            return None

        if filename is None:
            return None

        res_filename = self.gui.resources.find(filename)

        if res_filename is None:
            # print(f"MUSIC: unable to find {filename}")
            return None

        sdl2.sdlmixer.Mix_VolumeMusic(int(max(0, min(volume, 128))))
        music = sdl2.sdlmixer.Mix_LoadMUS(
                    sdl2.ext.compat.byteify(str(res_filename), 'utf-8'))

        if music is None:
            return None
            # raise GUIRuntimeError(f'Cannot open audio file: {sdl2.Mix_GetError()}')

        sdl2.sdlmixer.Mix_PlayMusic(music, loops)
        if filename in self.music_position:
            sdl2.sdlmixer.Mix_SetMusicPosition(self.music_position[filename])
            del self.music_position[filename]

        if self.song:
            sdl2.sdlmixer.Mix_FreeMusic(self.song)

        self.filename = filename
        self.song = music

        return self.song

    def stop(self):
        if self.song:
            sdl2.sdlmixer.Mix_FreeMusic(self.song)
            self.song = None
            self.filename = None

    @property
    def music_is_disabled(self):
        return self._music_is_disabled

    @music_is_disabled.setter
    def music_is_disabled(self, value):
        if bool(value):
            self._music_is_disabled = True
            self.stop()

        else:
            self._music_is_disabled = False

    @property
    def volume(self):
        if not self.is_init:
            return

        return sdl2.sdlmixer.Mix_MasterVolume(-1)

    @volume.setter
    def volume(self, v):
        'Set master volume level between 0 and 128'
        if not self.is_init:
            return

        sdl2.sdlmixer.Mix_MasterVolume(int(max(0, min(v, 128))))

    def play(self, name, volume=128):
        '''
        Play a loaded sound with the given name

        :param name: name of sound, either the filename(without extension) or
            an alternate name provided to the load() method
        :param volume: volume to play sound at, from 0.0 to 1.
        '''
        if not self.is_init:
            return

        if self.sound_is_disabled:
            return

        if name is None:
            return

        sample = self.sounds.get(name)
        if not sample:
            # print(f"PLAY: unable to find {name}")
            return

        channel = sdl2.sdlmixer.Mix_PlayChannel(-1, sample, 0)
        if channel == -1:
            # RAN OUT OF CHANNELS YO
            # logger.debug(f"Cannot play sample {name}: {sdl2.sdlmixer.Mix_GetError()}")
            return

        sdl2.sdlmixer.Mix_Volume(channel, int(max(0, min(volume, 128))))

    def __del__(self):
        if not self.is_init:
            return

        for i, s in enumerate(self.sounds.values()):
            # print(f"self.sounds[{i}]: {s}")
            sdl2.sdlmixer.Mix_FreeChunk(s)

        if self.song:
            # print(f"self.song: {self.song}")
            sdl2.sdlmixer.Mix_FreeMusic(self.song)

        sdl2.sdlmixer.Mix_CloseAudio()
