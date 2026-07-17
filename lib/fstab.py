#!/usr/bin/env python3
# @file lib/fstab.py
"""
Fstab manipulation helpers for LPSS host integration.

Provides idempotent addition of an LPSS partition entry to /etc/fstab.
"""

import os
import sys


def add_entry(uuid, mountpoint, dry_run=False):
    """Add an /etc/fstab entry for the LPSS partition.

    The entry is added only if no existing line references the same UUID
    or mount point.  Comment lines are ignored.  Returns True on success
    or if already present.
    """
    fstab_path = "/etc/fstab"
    target_line = f"UUID={uuid}  {mountpoint}  auto  defaults,nofail  0 0\n"

    if dry_run:
        print(f"Would append to {fstab_path}:\n  {target_line.strip()}")
        return True

    # Read existing content
    try:
        with open(fstab_path, "r") as fh:
            lines = fh.readlines()
    except (OSError, IOError) as exc:
        print(f"Warning: cannot read {fstab_path}: {exc}",
              file=sys.stderr)
        return False

    # Check for existing entry, ignoring comments
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = stripped.split()
        if len(fields) >= 2:
            source, target = fields[0], fields[1]
            # Normalize possible quotes around UUID
            source_clean = source.strip('"').strip("'")
            if source_clean == f"UUID={uuid}":
                print(f"fstab entry for UUID={uuid} already present.")
                return True
            if target == mountpoint:
                print("Warning: fstab already contains an entry for "
                      f"mount point {mountpoint}, skipping.",
                      file=sys.stderr)
                return False  # conflict, do not touch

    # Append entry
    try:
        with open(fstab_path, "a") as fh:
            if lines and not lines[-1].endswith("\n"):
                fh.write("\n")
            fh.write("# LPSS entry\n")
            fh.write(target_line)
        print(f"Added fstab entry: UUID={uuid} -> {mountpoint}")
        return True
    except (OSError, IOError) as exc:
        print(f"Warning: cannot write {fstab_path}: {exc}",
              file=sys.stderr)
        return False