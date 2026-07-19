#!/usr/bin/env python3
# @file lib/paths.py
"""
Standard LPSS paths and path resolution.

Provides the default LPSS directory and a function to resolve
the effective LPSS directory from command-line arguments or
environment variables.
"""

import os

DEFAULT_LPSS_DIR = "/boot/lpss"

_ENV_VAR = "LPSS_DIR"


def get_lpss_dir(value: str | None = None) -> str:
    """Return the LPSS directory to use.

    Resolution order:
    1. Explicit *value* (usually from --lpss-dir).
    2. Environment variable LPSS_DIR.
    3. Default /boot/lpss.
    """
    if value:
        return value

    env_value = os.environ.get(_ENV_VAR)
    if env_value:
        return env_value

    return DEFAULT_LPSS_DIR