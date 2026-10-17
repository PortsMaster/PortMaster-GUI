# SPDX-License-Identifier: MIT
#
# Formatting and parsing helpers.

import datetime
import functools
import re
import time
from loguru import logger
from ..config import HM_PERFTEST


def nice_size(size):
    """
    Make nicer data sizes.
    """

    suffixes = ('B', 'KB', 'MB', 'GB', 'TB')
    for suffix in suffixes:
        if size < 768:
            break

        size /= 1024

    if suffix == 'B':
        return f"{size:.0f} {suffix}"

    return f"{size:.02f} {suffix}"


def oc_join(strings):
    """
    Oxford comma join
    """
    if len(strings) == 0:
        return ""

    elif len(strings) == 1:
        return strings[0]

    elif len(strings) == 2:
        return f"{strings[0]} and {strings[1]}"

    else:
        oxford_comma_list = ", ".join(strings[:-1]) + ", and " + strings[-1]
        return oxford_comma_list


@functools.lru_cache(maxsize=512)
def version_parse(version):
    result = []

    i = 0
    while i < len(version):
        number = ""
        suffix = ""
        while i < len(version):
            if not version[i].isnumeric():
                break

            number += version[i]
            i += 1

        if number != "":
            result.append(int(number))

        while i < len(version):
            if version[i].isnumeric():
                break

            c = version[i]
            i += 1

            if c not in '()[],_.-':
                suffix += c

        if suffix != "":
            result.append(suffix)

    return tuple(result)


# Custom Decorator function
def list_to_tuple(function):
    # https://stackoverflow.com/a/60980685
    def wrapper(*args):
        args = [tuple(x) if isinstance(x, list) else x for x in args]
        result = function(*args)
        result = tuple(result) if isinstance(result, list) else result
        return result

    return wrapper


@functools.lru_cache(maxsize=1024)
def name_cleaner(text):
    temp = re.sub(r'[^a-zA-Z0-9 _\-\.]+', '', text.strip().lower())
    return re.sub(r'[ \.]+', '.', temp)


def runtime_nicename(runtime):
    if isinstance(runtime, list):
        return oc_join([
            runtime_nicename(_runtime)
            for _runtime in runtime])

    if runtime.startswith("frt"):
        return ("Godot/FRT {version}").format(version=runtime.split('_', 1)[1].rsplit('.', 1)[0])

    if runtime.startswith("solarus"):
        return ("Solarus {version}").format(version=runtime.split('-', 1)[1].rsplit('.', 1)[0])

    if runtime.startswith("mono"):
        return ("Mono {version}").format(version=runtime.split('-', 1)[1].rsplit('-', 1)[0])

    if runtime.startswith("rlvm"):
        return "RLVM"

    if runtime.startswith("pyxel"):
        return ("Pyxel {version}").format(version=runtime.split('_')[1])

    if runtime.startswith("weston"):
        return ("Weston {version}").format(version=runtime.rsplit('_', 1)[-1])

    if runtime.startswith("mesa"):
        return ("Mesa {version}").format(version=runtime.rsplit('_', 1)[-1])

    if "jdk" in runtime and runtime.startswith("zulu11"):
        return ("JDK {version}").format(version=runtime.split('-')[2][3:])

    if "jre" in runtime and runtime.startswith("zulu11"):
        return ("JRE {version}").format(version=runtime.split('-')[2][3:])

    return runtime


def datetime_compare(time_a, time_b=None):
    if isinstance(time_a, str):
        time_a = datetime.datetime.fromisoformat(time_a)

    if time_b is None:
        time_b = datetime.datetime.now()
    elif isinstance(time_b, str):
        time_b = datetime.datetime.fromisoformat(time_b)

    return (time_b - time_a).total_seconds()


def timeit(func):
    if not HM_PERFTEST:
        return func

    @functools.wraps(func)
    def timeit_wrapper(*args, **kwargs):
        start_time = time.perf_counter()
        result = func(*args, **kwargs)
        end_time = time.perf_counter()
        total_time = end_time - start_time
        logger.debug(f'TIME: {func.__name__}({args}, {kwargs}): Took {total_time:.4f} seconds')
        return result

    return timeit_wrapper
