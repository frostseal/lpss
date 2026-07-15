#!/usr/bin/env python3
# @file lpss_install.py
"""
Install LPSS infrastructure using the system's GRUB.

Runs grub-install (or grub2-install) with user-supplied parameters,
then locates the installed grub.cfg and overwrites it with the
LPSS-themed configuration. The LPSS partition and ESP must already
be mounted.

Additionally, copies the entire LPSS project into <lpss-dir>/app
so that all tools are available from within any booted system.

Options:
  --tools-only    Only copy LPSS tools, skip GRUB installation.
  --grub-only     Only install/update GRUB, skip tools copy.
"""
import argparse
import os
import re
import shlex
import shutil
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
    parser.add_argument('--esp-dir',
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
    parser.add_argument('--tools-only', action='store_true',
                        help='Only copy LPSS tools, skip GRUB installation')
    parser.add_argument('--grub-only', action='store_true',
                        help='Only install/update GRUB, skip tools copy')
    args = parser.parse_args()

    do_tools = not args.grub_only
    do_grub = not args.tools_only

    if not do_grub and not args.esp_dir:
        print("Error: --esp-dir is required for GRUB installation",
              file=sys.stderr)
        sys.exit(1)

    lpss_dir = os.path.abspath(args.lpss_dir)

    # ------------------------------------------------------------------
    # Common validations
    # ------------------------------------------------------------------
    if not os.path.ismount(lpss_dir):
        print(f"Warning: {lpss_dir} is not a mount point.", file=sys.stderr)

    lpss_uuid = args.lpss_uuid or get_mount_uuid(lpss_dir)
    if not lpss_uuid:
        print("Error: could not determine LPSS UUID. "
              "Use --lpss-uuid to specify it.", file=sys.stderr)
        sys.exit(1)
    print(f"LPSS UUID: {lpss_uuid}")

    # ------------------------------------------------------------------
    # Install LPSS tools
    # ------------------------------------------------------------------
    if do_tools:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = script_dir
        app_dst = os.path.join(lpss_dir, 'app')
        os.makedirs(app_dst, exist_ok=True)

        # Python scripts
        for fname in ['lpss_ctl.py', 'lpss_import.py', 'lpss_install.py',
                      'lpss_app_install.py']:
            src = os.path.join(project_root, fname)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(app_dst, fname))

        # lib/
        lib_src = os.path.join(project_root, 'lib')
        lib_dst = os.path.join(app_dst, 'lib')
        if os.path.isdir(lib_src):
            if os.path.exists(lib_dst):
                shutil.rmtree(lib_dst)
            shutil.copytree(lib_src, lib_dst)

        # example/ and test/
        for sub in ['example', 'test']:
            sub_src = os.path.join(project_root, sub)
            sub_dst = os.path.join(app_dst, sub)
            if os.path.isdir(sub_src):
                if os.path.exists(sub_dst):
                    shutil.rmtree(sub_dst)
                shutil.copytree(sub_src, sub_dst)

        # convenience symlink bin -> app
        bin_link = os.path.join(lpss_dir, 'bin')
        if os.path.lexists(bin_link):
            os.remove(bin_link)
        os.symlink('app', bin_link)

        print(f"Copied LPSS tools to {app_dst}")

    # ------------------------------------------------------------------
    # Install / update GRUB
    # ------------------------------------------------------------------
    if do_grub:
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

        if not os.path.ismount(esp_dir):
            print(f"Warning: {esp_dir} is not a mount point.", file=sys.stderr)

        # Create lpss.conf if missing (e.g., after --grub-only on existing)
        config_path = os.path.join(lpss_dir, 'lpss.conf')
        if not os.path.exists(config_path):
            with open(config_path, 'w') as f:
                f.write(f"[lpss]\nid={lpss_uuid}\nversion=1\n")
            print(f"Created {config_path}")

        # Create flags/ if missing
        flags_dir = os.path.join(lpss_dir, 'flags')
        os.makedirs(flags_dir, exist_ok=True)

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
            open(grub_cfg_path, 'w').close()
            print(f"Note: {grub_cfg_path} was missing, created empty file.")

        print(f"GRUB directory found: {os.path.dirname(grub_cfg_path)}")
        print(f"GRUB prefix will be: ($root)/{grub_subdir}")
        print(f"Main grub.cfg path: {grub_cfg_path}")

        config = load_config(config_path)
        generate_grub_cfg(config, grub_cfg_path)
        print(f"LPSS grub.cfg written to {grub_cfg_path}")

    # ------------------------------------------------------------------
    print(f"\nLPSS {'tools' if do_tools else ''}{' and ' if do_tools and do_grub else ''}{'GRUB' if do_grub else ''} installed successfully on {lpss_dir}.")
    if do_tools:
        print("Use 'LPSS_DIR/app/lpss_app_install.py' to install the tools.")
    if do_grub:
        print("You can now import Linux systems with 'lpss_import'.")


if __name__ == '__main__':
    main()