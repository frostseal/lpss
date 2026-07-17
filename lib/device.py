#!/usr/bin/env python3
# @file lib/device.py
"""
Device information helpers for LPSS.

Provides utilities to query block device attributes (UUID, filesystem
type, label) via blkid.
"""

import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional


def is_block_device(device: str) -> bool:
    """
    Check whether path points to a block device.
    """
    return Path(device).is_block_device()


def get_device_info(device: str) -> Dict[str, Optional[str]]:
    """
    Return filesystem information for a block device.

    Uses blkid to extract UUID, TYPE, and LABEL.

    Returns:
        dict with keys:
            uuid   - filesystem UUID
            fstype - filesystem type
            label  - filesystem label

        Values are None when information is not available.
    """
    info: Dict[str, Optional[str]] = {
        "uuid": None,
        "fstype": None,
        "label": None,
    }

    if not is_block_device(device):
        print(
            f"Warning: {device} is not a block device",
            file=sys.stderr,
        )
        return info

    try:
        result = subprocess.run(
            [
                "blkid",
                "-s", "UUID",
                "-s", "TYPE",
                "-s", "LABEL",
                "-o", "export",
                device,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        print(
            f"Warning: blkid failed for {device}: {exc}",
            file=sys.stderr,
        )
        return info

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line or "=" not in line:
            continue

        key, _, value = line.partition("=")
        value = value.strip() or None

        if key == "UUID":
            info["uuid"] = value
        elif key == "TYPE":
            info["fstype"] = value
        elif key == "LABEL":
            info["label"] = value

    return info


def get_device_uuid(device: str) -> Optional[str]:
    """
    Return filesystem UUID for a block device.
    """
    return get_device_info(device)["uuid"]


def get_device_fstype(device: str) -> Optional[str]:
    """
    Return filesystem type for a block device.
    """
    return get_device_info(device)["fstype"]


def get_device_label(device: str) -> Optional[str]:
    """
    Return filesystem label for a block device.
    """
    return get_device_info(device)["label"]