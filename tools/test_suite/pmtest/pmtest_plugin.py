# SPDX-License-Identifier: MIT
#
# pytest plugin for the PortMaster Test Suite: writes "<done> <total> <test id>" to the
# file in $PMTEST_PROGRESS as tests finish, for the progress bar on screen.

import os

_STATE = {'total': 0, 'done': 0}


def _write(nodeid=""):
    path = os.environ.get("PMTEST_PROGRESS")
    if not path:
        return

    try:
        with open(path + ".new", "w") as fh:
            fh.write(f"{_STATE['done']} {_STATE['total']} {nodeid}\n")

        os.replace(path + ".new", path)

    except OSError:
        pass


def pytest_collection_finish(session):
    _STATE['total'] = len(session.items)
    _write()


def pytest_runtest_logfinish(nodeid, location):
    _STATE['done'] += 1
    _write(nodeid)
