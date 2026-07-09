#!/usr/bin/env python3
# @file lib/flags.py
"""
LPSS entry flags management.

Flags are stored as empty files in flags/<entry_id>/<flag_name>.
Provides atomic creation, removal, and querying of individual flags.
"""

import os
import tempfile
from typing import Dict, Set


def read_flags(flags_dir: str) -> Dict[str, Set[str]]:
    """Return a dict mapping entry_id -> set of flag names."""
    result: Dict[str, Set[str]] = {}
    if not os.path.isdir(flags_dir):
        return result
    for entry_id in os.listdir(flags_dir):
        entry_path = os.path.join(flags_dir, entry_id)
        if not os.path.isdir(entry_path):
            continue
        flags = set()
        for flag_name in os.listdir(entry_path):
            flag_path = os.path.join(entry_path, flag_name)
            if os.path.isfile(flag_path):
                flags.add(flag_name)
        if flags:
            result[entry_id] = flags
    return result


def has_flag(flags_dir: str, entry_id: str, flag: str) -> bool:
    """Check if a flag file exists."""
    return os.path.isfile(os.path.join(flags_dir, entry_id, flag))


def create_flag(flags_dir: str, entry_id: str, flag: str) -> None:
    """Atomically create an empty flag file."""
    _set_flag(flags_dir, entry_id, flag, True)


def remove_flag(flags_dir: str, entry_id: str, flag: str) -> None:
    """Remove a flag file (if it exists)."""
    _set_flag(flags_dir, entry_id, flag, False)


def _set_flag(flags_dir: str, entry_id: str, flag: str, value: bool) -> None:
    """Internal: atomically set or clear a flag."""
    entry_dir = os.path.join(flags_dir, entry_id)
    os.makedirs(entry_dir, exist_ok=True)
    flag_path = os.path.join(entry_dir, flag)

    if value:
        try:
            fd, tmpname = tempfile.mkstemp(dir=entry_dir,
                                           prefix=f".tmp_{flag}_")
            os.close(fd)
            os.replace(tmpname, flag_path)
        except Exception:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
            raise
    else:
        if os.path.lexists(flag_path):
            os.remove(flag_path)


# Legacy aliases kept for compatibility within the project
get_flag = has_flag
set_flag = _set_flag