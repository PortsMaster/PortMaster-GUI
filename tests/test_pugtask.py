# SPDX-License-Identifier: MIT

import threading
import time

import pytest

from pugwash import tasks as pugtask


def run_in_thread(fn):
    """Run fn on a worker thread, returns the Task."""
    return pugtask.Task(fn).start()


def drain_until(dispatcher, task, timeout=5):
    end = time.monotonic() + timeout
    while not task.done.is_set():
        dispatcher.drain()
        if time.monotonic() > end:
            raise AssertionError("task never finished")

        time.sleep(0.001)

    dispatcher.drain()


################################################################################
## MainThreadDispatcher
def test_post_from_worker_runs_on_main_in_order():
    dispatcher = pugtask.MainThreadDispatcher()
    seen = []

    def record(value):
        seen.append((value, pugtask.on_main_thread()))

    def work():
        for i in range(5):
            dispatcher.post(record, i)

    task = run_in_thread(work)
    task.done.wait(5)

    assert seen == []
    assert dispatcher.drain() == 5
    assert seen == [(i, True) for i in range(5)]


def test_post_on_main_runs_immediately():
    dispatcher = pugtask.MainThreadDispatcher()
    seen = []

    dispatcher.post(seen.append, 1)

    assert seen == [1]
    assert not dispatcher.pending()


def test_call_returns_result_to_worker():
    dispatcher = pugtask.MainThreadDispatcher()

    task = run_in_thread(lambda: dispatcher.call(lambda a, b: (a + b, pugtask.on_main_thread()), 2, b=3))
    drain_until(dispatcher, task)

    assert task.get() == (5, True)


def test_call_reraises_in_worker():
    dispatcher = pugtask.MainThreadDispatcher()

    def fail():
        raise KeyError("boom")

    task = run_in_thread(lambda: dispatcher.call(fail))
    drain_until(dispatcher, task)

    with pytest.raises(KeyError):
        task.get()


def test_call_blocks_worker_until_answered():
    dispatcher = pugtask.MainThreadDispatcher()
    reached = threading.Event()

    def work():
        answer = dispatcher.call(lambda: "yes")
        reached.set()
        return answer

    task = run_in_thread(work)

    ## Nothing drains the queue, so the worker must still be waiting.
    assert not reached.wait(0.2)

    drain_until(dispatcher, task)
    assert task.get() == "yes"


def test_posted_errors_do_not_break_drain():
    dispatcher = pugtask.MainThreadDispatcher()
    seen = []

    def work():
        dispatcher.post(lambda: 1 / 0)
        dispatcher.post(seen.append, "after")

    run_in_thread(work).done.wait(5)
    dispatcher.drain()

    assert seen == ["after"]


def test_drain_limit():
    dispatcher = pugtask.MainThreadDispatcher()

    def work():
        for i in range(10):
            dispatcher.post(lambda: None)

    run_in_thread(work).done.wait(5)

    assert dispatcher.drain(max_items=4) == 4
    assert dispatcher.pending()
    assert dispatcher.drain() == 6


################################################################################
## Task
def test_task_result_and_thread():
    task = pugtask.Task(lambda: pugtask.on_main_thread()).start()
    task.done.wait(5)

    assert task.get() is False


def test_task_error_reraised():
    def fail():
        raise ValueError("bad")

    task = pugtask.Task(fail).start()
    task.done.wait(5)

    with pytest.raises(ValueError):
        task.get()


def test_task_cancel_flag_and_is_worker():
    started = threading.Event()
    results = {}

    def work():
        results['is_worker'] = task.is_worker()
        started.set()
        task.cancel_requested.wait(5)
        return "cancelled"

    task = pugtask.Task(work)
    assert not task.is_worker()
    task.start()

    started.wait(5)
    task.cancel()
    task.done.wait(5)

    assert task.get() == "cancelled"
    assert results['is_worker'] is True


################################################################################
## FrameStats
class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def test_frame_stats_reports_slow_gaps_and_summary():
    clock = FakeClock()
    lines = []
    stats = pugtask.FrameStats(True, clock=clock, log=lines.append)

    ## One slow 200 ms frame among 30 ms ones, adding up to just over a second.
    for gap in [0.0, 0.03, 0.03, 0.2] + [0.03] * 28:
        clock.now += gap
        stats.frame("root")

    assert lines[0] == "PERF slow frame: 200 ms [root]"
    assert lines[1].startswith("PERF ")
    assert "worst gap 200 ms" in lines[1]
    assert "slow frames 1" in lines[1]


def test_frame_stats_disabled_does_nothing():
    lines = []
    stats = pugtask.FrameStats(False, log=lines.append)

    stats.frame("root")
    stats.frame("root")

    assert lines == []
    assert stats.frames == 0
