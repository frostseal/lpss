#!/usr/bin/env python3
# @file lib/host_install.py
"""
Installation steps for LPSS host integration.

Each function performs a single step and returns True on success.
"""

import os
import sys

TOOLS = ['lpss_install.py', 'lpss_import.py', 'lpss_ctl.py']


def install_tools(prefix, app_dir, dry_run=False):
    """Create symlinks for LPSS scripts in the given prefix."""
    if dry_run:
        print(f"Would create symlinks in {prefix}")
        return True
    if not os.path.isdir(prefix):
        print(f"Error: prefix directory {prefix} does not exist.",
              file=sys.stderr)
        return False
    ok = True
    for tool in TOOLS:
        src = os.path.join(app_dir, tool)
        link_name = os.path.join(prefix, tool.replace('.py', ''))
        if not os.path.exists(src):
            print(f"Warning: {src} not found, skipping.", file=sys.stderr)
            continue
        if os.path.lexists(link_name):
            if os.path.islink(link_name):
                os.unlink(link_name)
            else:
                print(f"Error: {link_name} exists and is not a symlink.",
                      file=sys.stderr)
                ok = False
                continue
        try:
            os.symlink(src, link_name)
            print(f"{link_name} -> {src}")
        except OSError as exc:
            print(f"Error: cannot create symlink {link_name}: {exc}",
                  file=sys.stderr)
            ok = False
    return ok


def uninstall_tools(prefix, dry_run=False):
    """Remove symlinks for LPSS scripts from the given prefix."""
    if dry_run:
        print(f"Would remove symlinks from {prefix}")
        return True
    if not os.path.isdir(prefix):
        print(f"Error: prefix directory {prefix} does not exist.",
              file=sys.stderr)
        return False
    ok = True
    for tool in TOOLS:
        link_name = os.path.join(prefix, tool.replace('.py', ''))
        if os.path.islink(link_name):
            os.unlink(link_name)
            print(f"Removed {link_name}")
        elif os.path.exists(link_name):
            print(f"Warning: {link_name} exists and is not a symlink, "
                  "skipping.", file=sys.stderr)
        else:
            print(f"Already absent: {link_name}")
    return ok


def install_mountpoint(path, dry_run=False):
    """Create the LPSS mount point directory if it does not exist."""
    if dry_run:
        print(f"Would create mount point {path}")
        return True
    if os.path.exists(path):
        if os.path.isdir(path):
            print(f"Mount point ready: {path}")
            return True
        print(f"Error: {path} exists and is not a directory.",
              file=sys.stderr)
        return False
    try:
        os.makedirs(path, exist_ok=True)
        print(f"Mount point ready: {path}")
        return True
    except OSError as exc:
        print(f"Error: cannot create mount point {path}: {exc}",
              file=sys.stderr)
        return False