# SPDX-License-Identifier: MIT
#
# Threading helpers for the GUI.
#
# The rule: SDL, scenes and the template data (set_data) belong to the main
# thread. Slow work (downloads, installs, scans) runs on worker threads and
# talks back to the main thread through a MainThreadDispatcher.
#
# Nothing in here imports SDL so it can be tested on its own.

import os
import queue
import threading
import time

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from loguru import logger


def on_main_thread():
    return threading.current_thread() is threading.main_thread()


class _Call:
    __slots__ = ('fn', 'args', 'kwargs', 'done', 'result', 'error')

    def __init__(self, fn, args, kwargs, wait):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.done = threading.Event() if wait else None
        self.result = None
        self.error = None


class MainThreadDispatcher:
    """
    A queue of functions to run on the main thread.

    Workers use post() for fire and forget updates, and call() when they need
    an answer (eg: a message box). The main thread runs drain() once a frame.
    """

    def __init__(self):
        self._queue = queue.Queue()

    def post(self, fn, *args, **kwargs):
        if on_main_thread():
            fn(*args, **kwargs)
            return

        self._queue.put(_Call(fn, args, kwargs, False))

    def call(self, fn, *args, **kwargs):
        """
        Run fn on the main thread and return its result, re-raising any
        exception in the calling thread.
        """
        if on_main_thread():
            return fn(*args, **kwargs)

        item = _Call(fn, args, kwargs, True)
        self._queue.put(item)
        item.done.wait()

        if item.error is not None:
            raise item.error

        return item.result

    def drain(self, max_items=None):
        """
        Run queued functions, returns how many ran.
        """
        count = 0
        while max_items is None or count < max_items:
            try:
                item = self._queue.get_nowait()

            except queue.Empty:
                break

            count += 1
            try:
                item.result = item.fn(*item.args, **item.kwargs)

            except BaseException as err:
                if item.done is None:
                    logger.exception(f"Error in posted call {item.fn!r}")
                else:
                    item.error = err

            finally:
                if item.done is not None:
                    item.done.set()

        return count

    def pending(self):
        return not self._queue.empty()


class Task:
    """
    Runs one function on a worker thread.
    """

    def __init__(self, fn, *args, name=None, **kwargs):
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.result = None
        self.error = None
        self.cancel_requested = threading.Event()
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, name=name or f"task-{getattr(fn, '__name__', 'fn')}", daemon=True)

    def _run(self):
        try:
            self.result = self.fn(*self.args, **self.kwargs)

        except BaseException as err:
            self.error = err

        finally:
            self.done.set()

    def start(self):
        self.thread.start()
        return self

    def cancel(self):
        self.cancel_requested.set()

    def is_worker(self):
        return threading.current_thread() is self.thread

    def get(self):
        """
        Result of the task, re-raising its exception. Only call once done.
        """
        if self.error is not None:
            raise self.error

        return self.result


class FrameStats:
    """
    Opt-in frame timing (PM_PERF=1).

    The interesting number is the gap between frames: work done between two
    frames (eg: unzipping between progress callbacks) shows up there even when
    each frame on its own is quick.
    """

    SLOW_GAP = 0.050

    def __init__(self, enabled, clock=time.perf_counter, log=None):
        self.enabled = enabled
        self.clock = clock
        self.log = log or logger.info
        self.last_frame = None
        self.window_start = None
        self.frames = 0
        self.worst_gap = 0.0
        self.slow_frames = 0

    def frame(self, context=""):
        if not self.enabled:
            return

        now = self.clock()

        if self.last_frame is not None:
            gap = now - self.last_frame
            self.worst_gap = max(self.worst_gap, gap)

            if gap > self.SLOW_GAP:
                self.slow_frames += 1
                self.log(f"PERF slow frame: {gap * 1000:.0f} ms [{context}]")

        else:
            self.window_start = now

        self.last_frame = now
        self.frames += 1

        if now - self.window_start >= 1.0:
            self.log(
                f"PERF {self.frames / (now - self.window_start):.1f} fps, "
                f"worst gap {self.worst_gap * 1000:.0f} ms, "
                f"slow frames {self.slow_frames} [{context}]")

            self.window_start = now
            self.frames = 0
            self.worst_gap = 0.0
            self.slow_frames = 0


class DirectoryScanner:
    """
    Works out directory sizes on a background thread.

    All state lives on the main thread, the worker only posts size updates back
    through the dispatcher, so `callback(scan_dir, size, is_final)` runs on the
    main thread.
    """

    REPORT_INTERVAL = 0.25

    def __init__(self, dispatcher, max_workers=1):
        self.dispatcher = dispatcher
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="dir-scan")
        ## scan_dir -> [size so far, cancel Event]
        self.scans = {}
        self.results = {}
        self.callback = None

    def _scan(self, scan_dir, cancel):
        total_size = 0
        last_report = time.monotonic()
        stack = [str(scan_dir)]

        try:
            while stack:
                if cancel.is_set():
                    return

                path = stack.pop()
                try:
                    with os.scandir(path) as entries:
                        for entry in entries:
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)

                            elif entry.is_file(follow_symlinks=False):
                                total_size += entry.stat(follow_symlinks=False).st_size

                except NotADirectoryError:
                    total_size += os.stat(path).st_size

                except OSError as err:
                    logger.debug(f"dir-scan: {err}")

                now = time.monotonic()
                if now - last_report >= self.REPORT_INTERVAL:
                    last_report = now
                    self.dispatcher.post(self._update, scan_dir, cancel, total_size, False)

        finally:
            if not cancel.is_set():
                self.dispatcher.post(self._update, scan_dir, cancel, total_size, True)

    def _update(self, scan_dir, cancel, size, is_final):
        scan = self.scans.get(scan_dir)
        if scan is None or scan[1] is not cancel:
            ## Cleared or restarted since this was posted.
            return

        scan[0] = size
        if is_final:
            del self.scans[scan_dir]
            self.results[scan_dir] = size

        if self.callback:
            self.callback(scan_dir, size, is_final)

    def check_directory(self, directory, nice_size=True):
        """
        Size of a directory if known, otherwise start scanning it.

        With nice_size it returns a string, "~ size" while scanning. Without it
        returns the size in bytes, or None while scanning.
        """
        from harbourmaster import nice_size as _nice_size

        if directory in self.results:
            if nice_size:
                return _nice_size(self.results[directory])

            return self.results[directory]

        if directory not in self.scans:
            cancel = threading.Event()
            self.scans[directory] = [0, cancel]
            self.executor.submit(self._scan, directory, cancel)

        if nice_size:
            return f"~ {_nice_size(self.scans[directory][0])}"

        return None

    def clear_directory(self, directory):
        """
        Forget about a directory, cancelling any scan in progress.
        """
        scan = self.scans.pop(directory, None)
        if scan is not None:
            scan[1].set()

        self.results.pop(directory, None)

    def clear_all(self):
        """
        Cancel all scans in progress.
        """
        for scan in self.scans.values():
            scan[1].set()

        self.scans.clear()

    def shutdown(self):
        self.clear_all()
        self.executor.shutdown(wait=False)


class DoneFile:
    """
    fifo_control's answer file. Written whole (a temp file renamed over it), so the
    shell scripts polling it never read it empty halfway through a write and take
    that as the answer.
    """

    def __init__(self, path):
        self.path = Path(path)

    def write_text(self, text):
        temp_file = self.path.with_name(self.path.name + ".tmp")
        temp_file.write_text(text)
        os.replace(str(temp_file), str(self.path))

    def read_text(self):
        return self.path.read_text()

    def exists(self):
        return self.path.exists()

    def unlink(self):
        self.path.unlink()

    def __str__(self):
        return str(self.path)


class FifoReader:
    """
    Reads lines from a named pipe on a background thread.

    The pipe is opened read/write, so we never see EOF when the shell scripts
    writing to it come and go, and opening it doesn't block.
    """

    _STOP = b"\0pugwash-fifo-stop\n"

    def __init__(self, fifo_file):
        self.fd = os.open(str(fifo_file), os.O_RDWR)
        self.lines = queue.Queue()
        self.thread = threading.Thread(target=self._run, name="fifo-reader", daemon=True)
        self.thread.start()

    def _run(self):
        buffer = b""

        while True:
            try:
                data = os.read(self.fd, 4096)

            except OSError:
                return

            if not data:
                return

            buffer += data
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                if line + b"\n" == self._STOP:
                    return

                self.lines.put(line.decode("utf-8", "replace"))

    def get(self):
        """
        Next line, or None if nothing is waiting.
        """
        try:
            return self.lines.get_nowait()

        except queue.Empty:
            return None

    def close(self):
        try:
            os.write(self.fd, self._STOP)
            self.thread.join(1)

        finally:
            os.close(self.fd)


__all__ = (
    'DirectoryScanner',
    'FifoReader',
    'FrameStats',
    'MainThreadDispatcher',
    'Task',
    'on_main_thread',
    )
