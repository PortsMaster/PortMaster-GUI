# SPDX-License-Identifier: MIT
#
# PortMasterGUI CallbackMixin.

import contextlib
import harbourmaster
import requests
from pugwash import tasks
from loguru import logger
from pugwash.scenes import MessageBoxScene, MessageWindowScene
from harbourmaster.i18n import _
from pugwash.util import format_progress


class CallbackMixin:
    """
    PortMasterGUI methods: harbourmaster.Callback for the GUI: thread aware messages, progress, message boxes and cancelling, plus run_task().
    """

    ## Threading
    def run_task(self, fn, *args, **kwargs):
        """
        Run fn on a worker thread while the GUI keeps running, returns its result or
        re-raises its exception here.

        Callbacks from the worker (message, progress, message_box, ...) are handed to the
        main thread, see the callback methods below. Only one task runs at a time, as
        HarbourMaster is not thread safe.
        """
        if not tasks.on_main_thread() or self.task is not None:
            ## Already inside a task (eg: do_runtime_check during an install), just run it.
            if self.task is not None and tasks.on_main_thread():
                raise RuntimeError("run_task called on the main thread while a task is running")

            return fn(*args, **kwargs)

        task = tasks.Task(fn, *args, **kwargs)
        self.task = task
        task.start()

        try:
            while not task.done.is_set():
                self.do_loop()

            self.dispatcher.drain()

        finally:
            self.task = None
            self.updated = True

        return task.get()

    def check_task_cancel(self):
        """
        Called from the worker, raises CancelEvent if the user cancelled.
        """
        task = self.task
        if task is not None and task.cancel_requested.is_set() and self.cancellable is True:
            task.cancel_requested.clear()
            raise harbourmaster.CancelEvent()

    def _apply_pending_progress(self):
        with self.pending_progress_lock:
            pending, self.pending_progress = self.pending_progress, None

        if pending is not None:
            self.progress(*pending)

    ## Messagebox / Callback stuff
    def callback_update(self):
        self.updated = True
        if self.message_box_scene:
            page_size = max(self.message_box_scene.tags['message_text'].page_size, 12) + 1
            self.message_box_scene.tags['message_text'].text = '\n'.join(self.callback_messages[-int(page_size):])

            if self.task is not None:
                ## run_task is already running the main loop.
                return

            old_in_callback_loop = self.in_callback_loop
            self.in_callback_loop = True
            try:
                self.do_loop(no_delay=True)

            finally:
                self.in_callback_loop = old_in_callback_loop

    def progress(self, message, amount, total=None, fmt=None):
        if not tasks.on_main_thread():
            self.check_task_cancel()

            ## Only the latest progress matters, so only post it once per frame.
            with self.pending_progress_lock:
                need_post = self.pending_progress is None
                self.pending_progress = (message, amount, total, fmt)

            if need_post:
                self.dispatcher.post(self._apply_pending_progress)

            return

        if message is None:
            self.callback_progress = None
            self.callback_amount = 0
            self.spinner = 0
            self.set_data("system.progress_text", "")
            self.set_data("system.progress_amount", "")

            self.set_data('system.progress_perc_5', "0")
            self.set_data('system.progress_perc_10', "0")
            self.set_data('system.progress_perc_20', "0")
            self.set_data('system.progress_perc_25', "0")
            self.set_data('system.progress_spinner_5',  "0")
            self.set_data('system.progress_spinner_10', "0")
            self.set_data('system.progress_spinner_20', "0")
            self.set_data('system.progress_spinner_25', "0")
            self.set_data('system.progress_perc_5_or_spinner',  "0")
            self.set_data('system.progress_perc_10_or_spinner', "0")
            self.set_data('system.progress_perc_20_or_spinner', "0")
            self.set_data('system.progress_perc_25_or_spinner', "0")

        else:
            self.spinner += 1
            self.set_data('system.progress_perc', "0")
            self.set_data('system.progress_spinner_5',  f"{(((self.spinner % 20) + 1) *  5)}")
            self.set_data('system.progress_spinner_10', f"{(((self.spinner % 10) + 1) * 10)}")
            self.set_data('system.progress_spinner_20', f"{(((self.spinner %  5) + 1) * 20)}")
            self.set_data('system.progress_spinner_25', f"{(((self.spinner %  4) + 1) * 25)}")

            if total is not None:
                percent = amount / total * 100
                self.set_data('system.progress_perc',    f"{int(percent)}")
                self.set_data('system.progress_perc_5',  f"{int(percent //  5 *  5)}")
                self.set_data('system.progress_perc_10', f"{int(percent // 10 * 10)}")
                self.set_data('system.progress_perc_20', f"{int(percent // 20 * 20)}")
                self.set_data('system.progress_perc_25', f"{int(percent // 25 * 25)}")
                self.set_data('system.progress_perc_5_or_spinner', f"{int(percent //  5 *  5)}")
                self.set_data('system.progress_perc_10_or_spinner', f"{int(percent // 10 * 10)}")
                self.set_data('system.progress_perc_20_or_spinner', f"{int(percent // 20 * 20)}")
                self.set_data('system.progress_perc_25_or_spinner', f"{int(percent // 25 * 25)}")
                self.callback_amount = int(percent)

            else:
                self.set_data('system.progress_perc', "0")
                self.set_data('system.progress_perc_5', "0")
                self.set_data('system.progress_perc_10', "0")
                self.set_data('system.progress_perc_20', "0")
                self.set_data('system.progress_perc_25', "0")
                self.set_data('system.progress_perc_5_or_spinner',  f"{(((self.spinner % 20) + 1) *  5)}")
                self.set_data('system.progress_perc_10_or_spinner', f"{(((self.spinner % 10) + 1) * 10)}")
                self.set_data('system.progress_perc_20_or_spinner', f"{(((self.spinner %  5) + 1) * 20)}")
                self.set_data('system.progress_perc_25_or_spinner', f"{(((self.spinner %  4) + 1) * 25)}")
                self.callback_amount = 0

            self.set_data("system.progress_text", message)
            self.set_data("system.progress_amount", format_progress(amount, total, fmt))

        self.callback_update()

    def message(self, message):
        if not tasks.on_main_thread():
            self.check_task_cancel()
            self.dispatcher.post(self.message, message)
            return

        self.callback_messages.append(message)
        self.callback_update()

    def message_box(self, message, want_cancel=False, ok_text=None, cancel_text=None):
        """
        Display a message box
        """
        if not tasks.on_main_thread():
            ## Blocks the worker until the user answers.
            return self.dispatcher.call(
                self.message_box, message, want_cancel=want_cancel, ok_text=ok_text, cancel_text=cancel_text)

        if ok_text is None:
            ok_text = _("Okay")

        if cancel_text is None:
            cancel_text = _("Cancel")

        if self.message_box_disable:
            ## Nobody gets to see the box (eg: fifo_control installs), but the messages window still can.
            self.message(message)

            if want_cancel:
                return False

            return True

        ## This fixes a bug :D
        self.events.handle_events()

        ## During a task the worker owns `cancellable`, changing it here could let the
        ## user cancel a part that must not be cancelled.
        with (self.enable_cancellable(True) if self.task is None else contextlib.nullcontext()):
            self.push_scene('message_box', MessageBoxScene(
                self, message, want_cancel=want_cancel, ok_text=ok_text, cancel_text=cancel_text))

            self.updated = True
            try:
                while True:
                    if self.events.was_pressed('A'):
                        return True

                    if want_cancel and self.events.was_pressed('B'):
                        if want_cancel:
                            return False

                        return True

                    self.do_loop()

            finally:
                self.pop_scene()

    def messages_begin(self, *, internal=False):
        """
        Show messages window.

        Deprecated, use `with gui.enable_messages():` instead
        """

        if not tasks.on_main_thread():
            return self.dispatcher.call(self.messages_begin, internal=internal)

        if not internal:
            logger.error("Using old messages begin/end api is deprecated.")

        if self.message_box_depth < 0:
            self.message_box_depth = 0
            self.callback_messages.clear()

        if self.message_box_depth == 0:
            self.message_box_scene = MessageWindowScene(self)
            self.push_scene('messages', self.message_box_scene)

        self.message_box_depth += 1

    def messages_end(self, *, internal=False):
        """
        Hide messages window.

        Deprecated, use `with gui.enable_messages():` instead
        """
        if not tasks.on_main_thread():
            ## Let any queued messages / progress show first.
            return self.dispatcher.call(self.messages_end, internal=internal)

        if not internal:
            logger.error("Using old messages begin/end api is deprecated.")

        self.message_box_depth -= 1
        if self.message_box_depth <= 0 and self.message_box_scene:
            self.message_box_depth = 0
            self.callback_messages.clear()
            self.message_box_scene = None
            self.callback_progress = None
            self.pop_scene()

    @contextlib.contextmanager
    def enable_messages(self):
        """
        Shows and hides the messages window.
        """
        try:
            self.messages_begin(internal=True)

            yield

            ## Fix a bug
            self.progress(None, None, None)

        finally:
            self.messages_end(internal=True)

    @contextlib.contextmanager
    def disable_messagebox(self):
        """
        Disables displaying the messagebox, should be used in conjunction with enable_cancellable(False)
        """
        old_message_state = self.message_box_disable
        try:
            self.message_box_disable = True

            yield

        finally:
            self.message_box_disable = old_message_state

    @contextlib.contextmanager
    def enable_messagebox(self):
        """
        Enables displaying the messagebox.
        """
        old_message_state = self.message_box_disable
        try:
            self.message_box_disable = False

            yield

        finally:
            self.message_box_disable = old_message_state

    ## Cancelling code.
    def do_cancel(self):
        """
        Cancel if it is possible
        """
        if self.task is not None:
            ## The worker raises CancelEvent at its next progress/message.
            if self.cancellable is True:
                self.task.cancel()

            return

        if self.cancellable is True:
            raise harbourmaster.CancelEvent()

    @contextlib.contextmanager
    def enable_cancellable(self, cancellable=False):
        """
        Controls whether you
        """
        old_cancellable = self.cancellable
        self.cancellable = cancellable
        self.was_cancelled = False

        try:
            yield

        except requests.exceptions.ConnectionError as err:
            # self.do_popup_message(f"Connection Error: {err}")
            logger.error(f"Connection Error: {err}")
            self.was_cancelled = True

        except harbourmaster.CancelEvent:
            self.was_cancelled = True

        finally:
            self.cancellable = old_cancellable
