# Part of pySDL2gui, Copyright (C) 2020, Michael C Palmer, with PortMaster changes.
# See the notice in pugwash/sdl/__init__.py and licenses/LICENSE-port_gui.txt.
#
# Exceptions.




class GUIException(Exception):
    '''
    The root of all GUI runtime exceptions.
    '''
    pass


class GUIValueError(GUIException, ValueError):
    pass


class GUIRuntimeError(GUIException, RuntimeError):
    '''
    General runtime exception.
    '''
    pass


class GUIThemeError(GUIRuntimeError):
    '''
    This is an exception that is thrown during Region creation.
    '''
    pass
