#!/usr/bin/env python3
# @file lpss_install.py
"""
Install LPSS infrastructure.

Two independent operations:
1. Setup the LPSS runtime (grub.cfg, lpss.conf, flags/) on the LPSS partition.
2. Install the LPSS application bundle into <lpss-dir>/app.

By default both are executed. Use --app-only or --grub-only to run only one.
"""
import argparse
import os
import re
import shlex
import shutil
import sys

from lib.config import load_config
from lib.grub import generate_grub_cfg
from lib.utils import (
    find_grub_tool,
    get_grub_subdir,
    get_mount_uuid,
    run_command,
)

_APP_FILES = [
    'lpss_ctl.py',
    'lpss_import.py',
    'lpss_install.py',
    'lpss_host_install.py',
]


def install_app_bundle(lpss_dir):
    """Copy the LPSS application bundle into <lpss>/app."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = script_dir
    app_dst = os.path.join(lpss_dir, 'app')
    os.makedirs(app_dst, exist_ok=True)

    for fname in _APP_FILES:
        src = os.path.join(project_root, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(app_dst, fname))

    lib_src = os.path.join(project_root, 'lib')
    lib_dst = os.path.join(app_dst, 'lib')
    if os.path.isdir(lib_src):
        if os.path.exists(lib_dst):
            shutil.rmtree(lib_dst)
        shutil.copytree(lib_src, lib_dst)

    for sub in ['example', 'test']:
        sub_src = os.path.join(project_root, sub)
        sub_dst = os.path.join(app_dst, sub)
        if os.path.isdir(sub_src):
            if os.path.exists(sub_dst):
                shutil.rmtree(sub_dst)
            shutil.copytree(sub_src, sub_dst)

    print(f"Application bundle installed to {app_dst}")


def setup_runtime(args, lpss_dir):
    """Install/update the LPSS runtime: GRUB, lpss.conf, flags, grub.cfg."""
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
    if not os.path.ismount(lpss_dir):
        print(f"Warning: {lpss_dir} is not a mount point.", file=sys.stderr)

    lpss_uuid = args.lpss_uuid or get_mount_uuid(lpss_dir)
    if not lpss_uuid:
        print("Error: could not determine LPSS UUID. "
              "Use --lpss-uuid to specify it.", file=sys.stderr)
        sys.exit(1)
    print(f"LPSS UUID: {lpss_uuid}")

    config_path = os.path.join(lpss_dir, 'lpss.conf')
    if not os.path.exists(config_path):
        with open(config_path, 'w') as f:
            f.write(f"[lpss]\nid={lpss_uuid}\nversion=1\n")
        print(f"Created {config_path}")

    flags_dir = os.path.join(lpss_dir, 'flags')
    os.makedirs(flags_dir, exist_ok=True)

    extra_args = (
        shlex.split(args.grub_install_extra)
        if args.grub_install_extra
        else []
    )
    grub_cmd = [
        grub_install,
        '--target=x86_64-efi',
        f'--efi-directory={esp_dir}',
        f'--boot-directory={lpss_dir}',
        f'--bootloader-id={args.bootloader_id}',
    ] + extra_args
    run_command(grub_cmd,
                desc="Installing GRUB using distribution's grub-install")

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


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lpss-dir', required=True,
                        help='Mount point of the LPSS partition')
    parser.add_argument('--esp-dir',
                        help='Mount point of the EFI System Partition '
                             '(required for runtime installation)')
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
    parser.add_argument('--app-only', action='store_true',
                        help='Only deploy the application bundle, '
                             'skip runtime installation')
    parser.add_argument('--grub-only', action='store_true',
                        help='Only install/update the LPSS runtime, '
                             'skip application bundle')
    args = parser.parse_args()

    do_app = not args.grub_only
    do_runtime = not args.app_only

    if do_runtime and not args.esp_dir:
        print("Error: --esp-dir is required for runtime installation",
              file=sys.stderr)
        sys.exit(1)

    lpss_dir = os.path.abspath(args.lpss_dir)

    if do_app:
        install_app_bundle(lpss_dir)

    if do_runtime:
        setup_runtime(args, lpss_dir)

    parts = []
    if do_app:
        parts.append("application bundle")
    if do_runtime:
        parts.append("runtime")
    if parts:
        print(f"LPSS installation completed: {', '.join(parts)}")

    if do_app:
        print("Application bundle ready in <lpss>/app.")
        print("To make LPSS commands available in this host, run:"
              " lpss_host_install --prefix /usr/local/bin")
    if do_runtime:
        print("You can now import Linux systems with 'lpss_import'.")


if __name__ == '__main__':
    main()