# SPDX-License-Identifier: MIT
#
# Exceptions and the Callback interface harbourmaster reports progress through.

import contextlib


################################################################################
## Exceptions
class HarbourException(Exception):
    ...


class CancelEvent(HarbourException):
    pass


class Callback:
    """
    This is a simple class that is used by harbourmaster to cooperate with gui code.
    """
    IS_GUI = False

    def __init__(self):
        self.was_cancelled = False

    def progress(self, message, amount, total=None, fmt=None):
        pass

    def messages_begin(self):
        pass

    def messages_end(self):
        pass

    def message(self, message):
        pass

    def message_box(self, message):
        pass

    def do_cancel(self):
        pass

    @contextlib.contextmanager
    def enable_messages(self):
        try:
            self.was_cancelled = False
            yield

        finally:
            pass

    @contextlib.contextmanager
    def enable_cancellable(self, cancellable=False):
        try:
            yield

        finally:
            pass
