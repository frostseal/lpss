#!/usr/bin/env python3
# @file lpss_install.py
"""
Install LPSS infrastructure using the system's GRUB.

Runs grub-install (or grub2-install) with user-supplied parameters,
then locates the installed grub.cfg and overwrites it with the
LPSS-themed configuration. The LPSS partition and ESP must already
be mounted.

No partitioning or formatting is performed.
"""
import argparse
import os
import re
import shlex
import subprocess
import sys

from lib.config import load_config
from lib.grub import generate_grub_cfg
from lib.utils import find_grub_tool, get_grub_subdir, get_mount_uuid


def _run(cmd, desc=None):
    if desc:
        print(desc)
    print(f"  Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True, text=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: command failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lpss-dir', required=True,
                        help='Mount point of the LPSS partition')
    parser.add_argument('--esp-dir', required=True,
                        help='Mount point of the EFI System Partition')
    parser.add_argument('--lpss-uuid',
                        help='UUID of the LPSS filesystem '
                             '(auto-detected if omitted)')
    parser.add_argument('--bootloader-id', default='LPSS',
                        help='GRUB bootloader ID (default: LPSS)')
    parser.add_argument('--grub-install-extra', type=str, default='',
                        help='Extra arguments passed verbatim to grub-install '
                             '(e.g., "--removable --no-nvram")')
    parser.add_argument('--grub-install', type=str,
                        help='Path to grub-install or grub2-install '
                             '(auto-detected if omitted)')
    args = parser.parse_args()

    lpss_dir = os.path.abspath(args.lpss_dir)
    esp_dir = os.path.abspath(args.esp_dir)

    if not re.fullmatch(r'^[A-Za-z0-9._-]+$', args.bootloader_id):
        print("Error: --bootloader-id must contain only A-Z, a-z, 0-9, "
              "'.', '_', '-'", file=sys.stderr)
        sys.exit(1)

    grub_install = args.grub_install or find_grub_tool('install')
    if not grub_install:
        print("Error: grub-install or grub2-install not found. "
              "Specify with --grub-install.", file=sys.stderr)
        sys.exit(1)

    if not os.path.ismount(lpss_dir):
        print(f"Warning: {lpss_dir} is not a mount point.", file=sys.stderr)
    if not os.path.ismount(esp_dir):
        print(f"Warning: {esp_dir} is not a mount point.", file=sys.stderr)

    lpss_uuid = args.lpss_uuid or get_mount_uuid(lpss_dir)
    if not lpss_uuid:
        print("Error: could not determine LPSS UUID. "
              "Use --lpss-uuid to specify it.", file=sys.stderr)
        sys.exit(1)
    print(f"LPSS UUID: {lpss_uuid}")

    config_path = os.path.join(lpss_dir, 'lpss.conf')
    if os.path.exists(config_path):
        print(f"Error: {config_path} already exists. "
              "LPSS appears to be already installed.", file=sys.stderr)
        sys.exit(1)

    with open(config_path, 'w') as f:
        f.write(f"[lpss]\nid={lpss_uuid}\nversion=1\n")
    print(f"Created {config_path}")

    flags_dir = os.path.join(lpss_dir, 'flags')
    os.makedirs(flags_dir, exist_ok=True)
    print(f"Created directory {flags_dir}")

    extra_args = shlex.split(args.grub_install_extra) if args.grub_install_extra else []
    grub_cmd = [
        grub_install,
        '--target=x86_64-efi',
        f'--efi-directory={esp_dir}',
        f'--boot-directory={lpss_dir}',
        f'--bootloader-id={args.bootloader_id}',
    ] + extra_args
    _run(grub_cmd, desc="Installing GRUB using distribution's grub-install")

    grub_subdir = get_grub_subdir(lpss_dir)
    if not grub_subdir:
        print("Error: grub-install did not create a 'grub' or 'grub2' "
              "directory.", file=sys.stderr)
        sys.exit(1)

    grub_cfg_path = os.path.join(lpss_dir, grub_subdir, 'grub.cfg')
    if not os.path.exists(grub_cfg_path):
        # Some GRUB installations do not create grub.cfg (e.g., --no-nvram);
        # we create an empty file that will be overwritten.
        open(grub_cfg_path, 'w').close()
        print(f"Note: {grub_cfg_path} was missing, created empty file.")

    print(f"GRUB directory found: {os.path.dirname(grub_cfg_path)}")
    print(f"GRUB prefix will be: ($root)/{grub_subdir}")
    print(f"Main grub.cfg path: {grub_cfg_path}")

    config = load_config(config_path)
    generate_grub_cfg(config, grub_cfg_path)
    print(f"LPSS grub.cfg written to {grub_cfg_path}")

    print(f"\nLPSS installed successfully on {lpss_dir}.")
    print("You can now import Linux systems with 'lpss_import'.")


if __name__ == '__main__':
    main()