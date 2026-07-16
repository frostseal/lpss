#!/usr/bin/env python3
# @file lpss_import.py
"""
Import or update an existing Linux installation in LPSS.

Scans a mounted root filesystem, extracts kernel/initrd info,
and registers a new entry in lpss.conf, or updates an existing one.
Regenerates grub.cfg.

The LPSS partition can be specified via --lpss-dir, LPSS_MOUNT
environment variable, or defaults to /mnt/lpss.
"""
import os
import sys

# Allow running from copied tools directory (e.g., /mnt/lpss/bin)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

import argparse

from lib.config import load_config, LPSSConfigError
from lib.grub import generate_grub_cfg
from lib.utils import (get_grub_subdir, validate_locator,
                       find_kernel_initrd_in_root)


def _get_lpss_dir(args_lpss_dir=None):
    if args_lpss_dir:
        return args_lpss_dir
    return os.environ.get('LPSS_MOUNT', '/mnt/lpss')


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lpss-dir',
                        help='Path to mounted LPSS partition')
    parser.add_argument('--root', required=True,
                        help='Path to mounted root filesystem of the Linux installation')
    parser.add_argument('--id', required=True,
                        help='Entry ID to register or update (e.g., arch, opensuse)')
    parser.add_argument('--locator', required=True,
                        help='Locator string (e.g., partlabel:root.b)')
    parser.add_argument('--linux',
                        help='Path to kernel relative to root (auto-detected if omitted)')
    parser.add_argument('--initrd',
                        help='Path to initrd relative to root (auto-detected if omitted)')
    parser.add_argument('--options', default='ro quiet',
                        help='Kernel command line options (default: "ro quiet")')
    parser.add_argument('--type', default='root',
                        help='Entry type (default: root)')
    parser.add_argument('--update', '-u', action='store_true',
                        help='Update an existing entry instead of failing')
    args = parser.parse_args()

    # ---- validate inputs -------------------------------------------------
    lpss_dir = _get_lpss_dir(args.lpss_dir)
    config_path = os.path.join(lpss_dir, 'lpss.conf')
    if not os.path.isfile(config_path):
        print(f"Error: LPSS not initialised. {config_path} not found.",
              file=sys.stderr)
        sys.exit(1)

    root_dir = os.path.abspath(args.root)
    if not os.path.isdir(root_dir):
        print(f"Error: root directory not found: {root_dir}", file=sys.stderr)
        sys.exit(1)

    try:
        validate_locator(args.locator)
    except ValueError as e:
        print(f"Error: invalid locator '{args.locator}': {e}", file=sys.stderr)
        sys.exit(1)

    # ---- kernel / initrd detection ---------------------------------------
    linux_path = args.linux
    initrd_path = args.initrd

    if not linux_path:
        auto_linux, auto_initrd = find_kernel_initrd_in_root(root_dir)
        if auto_linux:
            linux_path = auto_linux
            print(f"Auto-detected kernel: {linux_path}")
        else:
            print("Error: could not detect kernel in {}/boot. "
                  "Use --linux.", file=sys.stderr)
            sys.exit(1)
        # initrd is optional; only override if not explicitly given
        if initrd_path is None and auto_initrd:
            initrd_path = auto_initrd
            print(f"Auto-detected initrd: {initrd_path}")

    # ---- validate files exist inside root_dir ----------------------------
    abs_linux = os.path.join(root_dir, linux_path.lstrip('/'))
    if not os.path.isfile(abs_linux):
        print(f"Error: kernel not found: {abs_linux}", file=sys.stderr)
        sys.exit(1)

    if initrd_path:
        abs_initrd = os.path.join(root_dir, initrd_path.lstrip('/'))
        if not os.path.isfile(abs_initrd):
            print(f"Error: initrd not found: {abs_initrd}", file=sys.stderr)
            sys.exit(1)
    else:
        print("No initrd specified; entry will be created without one.")

    # ---- modify configuration --------------------------------------------
    config = load_config(config_path)
    entry_exists = args.id in config.entries

    if entry_exists and not args.update:
        print(f"Error: entry '{args.id}' already exists. "
              "Use --update to modify.", file=sys.stderr)
        sys.exit(1)

    # Use empty string if initrd_path is None
    initrd_normalized = f'/{initrd_path.lstrip("/")}' if initrd_path else ''

    try:
        if entry_exists and args.update:
            config.update_entry(
                entry_id=args.id,
                entry_type=args.type,
                locator=args.locator,
                linux=f'/{linux_path.lstrip("/")}',
                initrd=initrd_normalized,
                options=args.options,
            )
            print(f"Updated entry '{args.id}' in memory.")
        else:
            config.add_entry(
                entry_id=args.id,
                entry_type=args.type,
                locator=args.locator,
                linux=f'/{linux_path.lstrip("/")}',
                initrd=initrd_normalized,
                options=args.options,
            )
            print(f"Added entry '{args.id}' to configuration.")
    except LPSSConfigError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    # ---- save and regenerate grub.cfg ------------------------------------
    config.save(config_path)
    print(f"Written {config_path}")

    grub_subdir = get_grub_subdir(lpss_dir)
    if not grub_subdir:
        print("Error: cannot find GRUB directory (grub2 or grub) in "
              f"{lpss_dir}.", file=sys.stderr)
        sys.exit(1)
    grub_cfg_path = os.path.join(lpss_dir, grub_subdir, 'grub.cfg')
    generate_grub_cfg(config, grub_cfg_path)
    print(f"Regenerated {grub_cfg_path}")
    print("Operation complete.")


if __name__ == '__main__':
    main()