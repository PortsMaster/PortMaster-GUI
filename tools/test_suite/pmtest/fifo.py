# SPDX-License-Identifier: MIT
#
# A client for pugwash's fifo_control, the protocol PortMasterDialog.txt speaks: one
# command per line on a named pipe, arguments separated by \1, the answer in a "done"
# file that says WAIT until the command has finished.
#
# Every call returns None instead of raising when pugwash isn't running, so the test
# suite carries on (and still writes its report) without a screen.

import errno
import os
import subprocess
import sys
import time
from pathlib import Path


class Dialog:
    def __init__(self, controlfolder, run_dir, log=None, python=None, env=None):
        self.pugwash = Path(controlfolder) / "pugwash"
        self.env = env
        self.pipe = Path(run_dir) / "pm_input"
        self.done = Path(run_dir) / "pm_done"
        self.proc = None
        self.log = log or (lambda text: None)
        self.python = python or sys.executable

    @property
    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def start(self, *options, timeout=180):
        """
        Starts `pugwash fifo_control`, options as for PortMasterDialogInit
        (eg: "--no-check", "--no-harbour"). True once it answers.
        """
        self.stop()

        self.done.parent.mkdir(parents=True, exist_ok=True)
        for path in (self.pipe, self.done):
            if path.exists():
                path.unlink()

        self.done.write_text("WAIT")

        if self.env is not None:
            env = dict(self.env)
        else:
            ## As PortMasterDialog.txt does.
            env = dict(os.environ)
            env.setdefault("PYSDL2_DLL_PATH", "/usr/lib")

        command = [self.python, str(self.pugwash), "--quiet", *options, "fifo_control", str(self.pipe), str(self.done)]
        self.log("dialog: " + " ".join(command))

        try:
            self.proc = subprocess.Popen(
                command, cwd=str(self.pugwash.parent), env=env,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        except OSError as err:
            self.log(f"dialog: unable to start pugwash: {err}")
            self.proc = None
            return False

        if not self._wait(self.pipe.exists, timeout) or self._wait_done(timeout) is None:
            self.log("dialog: pugwash never answered")
            self.stop()
            return False

        return True

    def stop(self):
        """Asks pugwash to quit, then makes sure it has."""
        if self.proc is None:
            return

        if self.running:
            self.send("exit", timeout=15)

            try:
                self.proc.wait(5)

            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()

        self.proc = None

    def send(self, *args, timeout=None):
        """Sends one command, returns what pugwash answered (DONE, OKAY, TRUE, ...) or None."""
        if not self.running:
            return None

        self.done.write_text("WAIT")
        line = ("\1".join(str(arg) for arg in args) + "\1\n").encode("utf-8")

        ## Never block on a pipe nobody reads: pugwash may have died.
        deadline = time.monotonic() + 10
        while True:
            try:
                fd = os.open(str(self.pipe), os.O_WRONLY | os.O_NONBLOCK)
                break

            except OSError as err:
                if err.errno not in (errno.ENXIO, errno.ENOENT) or time.monotonic() > deadline or not self.running:
                    self.log(f"dialog: unable to send {args[0]}: {err}")
                    return None

                time.sleep(0.1)

        try:
            os.write(fd, line)

        finally:
            os.close(fd)

        return self._wait_done(timeout)

    def _wait(self, test, timeout):
        deadline = None if timeout is None else time.monotonic() + timeout
        while not test():
            if not self.running or (deadline is not None and time.monotonic() > deadline):
                return False

            time.sleep(0.1)

        return True

    def _wait_done(self, timeout):
        result = []

        def answered():
            try:
                text = self.done.read_text().strip()

            except OSError:
                return False

            if text == "WAIT":
                return False

            result.append(text)
            return True

        if not self._wait(answered, timeout):
            return None

        return result[0]

    ## The commands.
    @staticmethod
    def _escape(text):
        return str(text).replace("\n", "\\n")

    def messages_begin(self):
        return self.send("messages_begin")

    def messages_end(self):
        return self.send("messages_end")

    def message(self, text):
        return self.send("message", self._escape(text))

    def progress(self, text, amount, total):
        return self.send("progress", text, str(int(amount)), str(int(total)))

    def progress_clear(self):
        return self.send("progress_clear")

    def message_box(self, text, want_cancel=False, ok_text=None, cancel_text=None):
        """True for A (ok), False for B (cancel), None without a screen."""
        args = ["message_box"]
        if want_cancel:
            args.append("--want-cancel")

        if ok_text:
            args += ["--ok-text", ok_text]

        if cancel_text:
            args += ["--cancel-text", cancel_text]

        args += ["--", self._escape(text)]
        answer = self.send(*args)
        if answer is None:
            return None

        return answer == "TRUE"

    def install(self, zip_file, timeout=1800):
        """True if pugwash installed it (fifo `install`)."""
        answer = self.send("install", str(zip_file), timeout=timeout)
        return None if answer is None else answer == "OKAY"

    def selection_list(self, register, entries, ok_text="Done"):
        """
        Shows entries ([(key, title, description), ...]) as a list with a description
        pane, until A. Returns the selected key or None.
        """
        self.send("register_clear", register)
        for key, title, description in entries:
            self.send("register_set_info", register, key, "title:" + title, "description:" + self._escape(description))

        return self.send("selection_list", f"--ok-text={ok_text}", f"--register={register}", "--want-description")
