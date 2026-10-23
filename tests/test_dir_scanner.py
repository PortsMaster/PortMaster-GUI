# SPDX-License-Identifier: MIT
#
# DirectoryScanner works out installed port sizes on a background thread, and
# FifoReader reads fifo_control commands on one.

import os
import time

import pytest

from pugwash import tasks as pugtask


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "port"
    (root / "a" / "b").mkdir(parents=True)
    (root / "c").mkdir()
    (root / "one.bin").write_bytes(b"x" * 100)
    (root / "a" / "two.bin").write_bytes(b"x" * 200)
    (root / "a" / "b" / "three.bin").write_bytes(b"x" * 300)
    (root / "c" / "four.bin").write_bytes(b"x" * 400)
    return root


@pytest.fixture
def scanner():
    dispatcher = pugtask.MainThreadDispatcher()
    scanner = pugtask.DirectoryScanner(dispatcher)
    yield scanner
    scanner.shutdown()


def wait_for_scans(scanner, timeout=5):
    """Drain the dispatcher like the main loop does until all scans are done."""
    end = time.monotonic() + timeout
    while scanner.scans:
        scanner.dispatcher.drain()
        if time.monotonic() > end:
            raise AssertionError("scanner never finished")

        time.sleep(0.005)


def test_scan_directory_total(scanner, tree):
    results = []
    scanner.callback = lambda scan_dir, size, is_final: results.append((scan_dir, size, is_final, pugtask.on_main_thread()))

    ## First call starts the scan.
    assert scanner.check_directory(tree, False) is None
    assert scanner.check_directory(tree) == "~ 0 B"

    wait_for_scans(scanner)

    assert scanner.check_directory(tree, False) == 1000
    assert scanner.check_directory(tree) == "0.98 KB"

    ## The callback ran on the main thread, ending with the final total.
    assert results[-1] == (tree, 1000, True, True)
    sizes = [size for _, size, _, _ in results]
    assert sizes == sorted(sizes)


def test_scan_multiple_directories(scanner, tree):
    scanner.check_directory(tree / "a", False)
    scanner.check_directory(tree / "c", False)
    wait_for_scans(scanner)

    assert scanner.check_directory(tree / "a", False) == 500
    assert scanner.check_directory(tree / "c", False) == 400


def test_scan_missing_directory(scanner, tmp_path):
    scanner.check_directory(tmp_path / "missing", False)
    wait_for_scans(scanner)

    assert scanner.check_directory(tmp_path / "missing", False) == 0


def test_clear_directory_cancels(scanner, tree):
    results = []
    scanner.callback = lambda *args: results.append(args)

    scanner.check_directory(tree, False)
    scanner.clear_directory(tree)

    ## Whatever the worker posts after the clear is ignored.
    time.sleep(0.1)
    scanner.dispatcher.drain()

    assert scanner.scans == {}
    assert scanner.results == {}
    assert results == []


def test_scan_does_not_block_main_thread(scanner, tmp_path):
    ## Lots of small files, checking the directory must still return straight away.
    root = tmp_path / "big"
    for i in range(50):
        sub = root / f"d{i}"
        sub.mkdir(parents=True)
        for j in range(20):
            (sub / f"f{j}").write_bytes(b"x")

    start = time.monotonic()
    assert scanner.check_directory(root, False) is None
    assert time.monotonic() - start < 0.05

    wait_for_scans(scanner)
    assert scanner.check_directory(root, False) == 1000


################################################################################
## FifoReader
def test_fifo_reader(tmp_path):
    fifo_file = tmp_path / "pipe"
    os.mkfifo(str(fifo_file))

    reader = pugtask.FifoReader(fifo_file)
    try:
        assert reader.get() is None

        ## Writers come and go like the shell scripts do, lines can arrive split.
        with open(str(fifo_file), "w") as fh:
            fh.write("message\1Hello\n")

        with open(str(fifo_file), "w") as fh:
            fh.write("progr")
            fh.flush()
            fh.write("ess\1Working\n")

        lines = []
        end = time.monotonic() + 5
        while len(lines) < 2 and time.monotonic() < end:
            line = reader.get()
            if line is None:
                time.sleep(0.005)
            else:
                lines.append(line)

        assert lines == ["message\1Hello", "progress\1Working"]

    finally:
        reader.close()

    assert not reader.thread.is_alive()


################################################################################
## DoneFile: fifo_control's answer file is never seen half-written.
def test_done_file_is_replaced_whole(tmp_path):
    done = pugtask.DoneFile(tmp_path / "pm_done")
    done.write_text("WAIT")
    inode = (tmp_path / "pm_done").stat().st_ino

    done.write_text("OKAY")

    assert done.read_text() == "OKAY"
    ## A new file renamed over the old one, not the old one truncated and rewritten.
    assert (tmp_path / "pm_done").stat().st_ino != inode
    assert sorted(path.name for path in tmp_path.iterdir()) == ["pm_done"]

    done.unlink()
    assert not done.exists()
