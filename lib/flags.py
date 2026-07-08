#!/usr/bin/env python3
# @file lib/flags.py
"""
LPSS entry flags management.

Flags are stored as empty files in flags/<entry_id>/<flag_name>.
Provides functions for reading and atomically modifying individual flags.
"""

import os
import tempfile
from typing import Dict, Set


def read_flags(flags_dir: str) -> Dict[str, Set[str]]:
    """
    Read all entry flags from the flags directory.

    Returns a dict mapping entry_id -> set of enabled flag names.
    """
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


def get_flag(flags_dir: str, entry_id: str, flag: str) -> bool:
    """Check if a specific flag is set for an entry."""
    flag_path = os.path.join(flags_dir, entry_id, flag)
    return os.path.isfile(flag_path)


def set_flag(flags_dir: str, entry_id: str, flag: str, value: bool) -> None:
    """
    Atomically set or clear a flag for an entry.

    Creates or removes an empty file flags/<entry_id>/<flag>.
    The entry subdirectory is created if it does not exist.
    """
    entry_dir = os.path.join(flags_dir, entry_id)
    os.makedirs(entry_dir, exist_ok=True)
    flag_path = os.path.join(entry_dir, flag)

    if value:
        # Atomically create the flag file using a temporary file and rename
        try:
            fd, tmpname = tempfile.mkstemp(dir=entry_dir, prefix=f".tmp_{flag}_")
            os.close(fd)
            os.replace(tmpname, flag_path)
        except Exception:
            if os.path.exists(tmpname):
                os.unlink(tmpname)
            raise
    else:
        # Remove the flag file (best effort, not atomic but safe)
        if os.path.lexists(flag_path):
            os.remove(flag_path)