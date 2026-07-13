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
import argparse
import os
import sys
import glob

from lib.config import load_config, LPSSConfigError
from lib.grub import generate_grub_cfg
from lib.utils import (get_grub_subdir, validate_locator)


# ---- kernel / initrd detection ------------------------------------------

KERNEL_PATTERNS = [
    "vmlinuz-*",
    "vmlinuz",
    "linux-*",
    "linux",
    "bzImage-*",
    "bzImage",
]

INITRD_PATTERNS = [
    "initramfs-{version}.img",
    "initrd-{version}.img",
    "initramfs-{version}",
    "initrd-{version}",
    "initrd.img-{version}",
    "initrd-{version}.gz",
]


def find_kernel_initrd(root_dir):
    """Locate the most recent kernel and matching initrd in root_dir/boot."""
    boot_dir = os.path.join(root_dir, 'boot')
    if not os.path.isdir(boot_dir):
        return None, None

    # collect all possible kernels
    candidates = []
    for pattern in KERNEL_PATTERNS:
        candidates.extend(glob.glob(os.path.join(boot_dir, pattern)))
    if not candidates:
        return None, None

    # pick the most recently modified
    kernel = max(candidates, key=os.path.getmtime)
    # extract version string
    base = os.path.basename(kernel)
    # common prefixes
    for prefix in ('vmlinuz-', 'linux-', 'bzImage-'):
        if base.startswith(prefix):
            version = base[len(prefix):]
            break
    else:
        version = base  # fallback

    # try to find matching initrd
    initrd = None
    for pattern in INITRD_PATTERNS:
        candidate = os.path.join(boot_dir, pattern.format(version=version))
        if os.path.exists(candidate):
            initrd = candidate
            break

    # fallback: any initr* containing version
    if not initrd:
        for name in os.listdir(boot_dir):
            if name.startswith('initr') and version in name:
                initrd = os.path.join(boot_dir, name)
                break

    linux_rel = os.path.relpath(kernel, root_dir) if kernel else None
    initrd_rel = os.path.relpath(initrd, root_dir) if initrd else None
    return linux_rel, initrd_rel


# ---- CLI ----------------------------------------------------------------

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
    parser.add_argument('--role', default='root',
                        help='Entry role (default: root)')
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

    if not linux_path or not initrd_path:
        auto_linux, auto_initrd = find_kernel_initrd(root_dir)
        if not linux_path:
            if auto_linux:
                linux_path = auto_linux
                print(f"Auto-detected kernel: {linux_path}")
            else:
                print("Error: could not detect kernel in {}/boot. "
                      "Use --linux.", file=sys.stderr)
                sys.exit(1)
        if not initrd_path:
            if auto_initrd:
                initrd_path = auto_initrd
                print(f"Auto-detected initrd: {initrd_path}")
            else:
                print("Error: could not detect initrd in {}/boot. "
                      "Use --initrd.", file=sys.stderr)
                sys.exit(1)

    # ---- validate files exist inside root_dir ----------------------------
    for desc, rel in [('kernel', linux_path), ('initrd', initrd_path)]:
        abs_path = os.path.join(root_dir, rel.lstrip('/'))
        if not os.path.isfile(abs_path):
            print(f"Error: {desc} not found: {abs_path}", file=sys.stderr)
            sys.exit(1)

    # ---- modify configuration --------------------------------------------
    config = load_config(config_path)
    entry_exists = args.id in config.entries

    if entry_exists and not args.update:
        print(f"Error: entry '{args.id}' already exists. "
              "Use --update to modify.", file=sys.stderr)
        sys.exit(1)

    try:
        if entry_exists and args.update:
            config.update_entry(
                entry_id=args.id,
                role=args.role,
                locator=args.locator,
                linux=f'/{linux_path.lstrip("/")}',
                initrd=f'/{initrd_path.lstrip("/")}',
                options=args.options,
            )
            print(f"Updated entry '{args.id}' in memory.")
        else:
            config.add_entry(
                entry_id=args.id,
                role=args.role,
                locator=args.locator,
                linux=f'/{linux_path.lstrip("/")}',
                initrd=f'/{initrd_path.lstrip("/")}',
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