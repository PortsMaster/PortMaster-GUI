# SPDX-License-Identifier: MIT
#
# JSON, dict/list and port sorting helpers, requirement matching.

import json
from loguru import logger
from ..config import HM_SORT_ORDER


################################################################################
## Utils
def json_safe_loads(*args):
    try:
        return json.loads(*args)
    except json.JSONDecodeError as err:
        logger.error(f"Unable to load json_data {err.doc}:{err.pos}:{err.lineno}:{err.colno}")
        return None


def json_safe_load(*args):
    try:
        return json.load(*args)
    except json.JSONDecodeError as err:
        logger.error(f"Unable to load json_data {err.doc}:{err.pos}:{err.lineno}:{err.colno}")
        return None


def add_list_unique(base_list, value):
    if value not in base_list:
        base_list.append(value)


def add_dict_list_unique(base_dict, key, value):
    if key not in base_dict:
        base_dict[key] = value
        return

    if isinstance(base_dict[key], str):
        if base_dict[key] == value:
            return

        base_dict[key] = [base_dict[key]]

    if value not in base_dict[key]:
        base_dict[key].append(value)


def get_dict_list(base_dict, key):
    if key not in base_dict:
        return []

    result = base_dict[key]
    if isinstance(result, str):
        return [result]

    if result is None:
        ## CEBION STRIKES AGAIN
        return []

    return result


def remove_dict_list(base_dict, key, value):
    if key not in base_dict:
        return

    result = base_dict[key]
    if isinstance(result, str):
        if value == result:
            del base_dict[key]

        return

    if value in result:
        result.remove(value)

        if len(result) == 0:
            del base_dict[key]

        elif len(result) == 1:
            base_dict[key] = result[0]


def port_sort_alphabetical(port_info):
    return port_info.get('attr', {}).get('title', port_info['name']).casefold()


def port_sort_date_added(port_info):
    return port_info.get('source', {}).get('date_added', '1970-01-01')


def port_sort_date_updated(port_info):
    return port_info.get('source', {}).get('date_updated', '1970-01-01')


def port_sort_download_count(port_info):
    return port_info.get('source', {}).get('downloads', 0)


PORT_SORT_FUNCS = {
    'alphabetical':     port_sort_alphabetical,
    'recently_added':   port_sort_date_added,
    'recently_updated': port_sort_date_updated,
    'total_downloads':  port_sort_download_count,
    }


for sort_by in HM_SORT_ORDER:
    if sort_by not in PORT_SORT_FUNCS:
        raise RuntimeError(f'{sort_by} missing.')


def match_requirements(capabilities, requirements):
    """
    Matches hardware capabilities to port requirements.
    """
    if len(requirements) == 0:
        return True

    passed = True
    for requirement in requirements:
        match_not = True

        ## Fixes empty requirement bug
        if requirement == "":
            continue

        if requirement.startswith('!'):
            match_not = False
            requirement = requirement[1:]

        if '|' in requirement:
            passed = any(
                req in capabilities
                for req in requirement.split('|')) == match_not

        else:
            if requirement in capabilities:
                passed = match_not
            else:
                passed = not match_not

        if not passed:
            break

    return passed
