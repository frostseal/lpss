#!/usr/bin/env python3
# @file lpss_install.py
"""
Install LPSS infrastructure on an existing partition.

Creates lpss.conf, flags/, empty grub.cfg and grubenv on the LPSS
partition, installs GRUB for UEFI, and writes a bootstrap grub.cfg
in the EFI System Partition. The LPSS partition and ESP must already
be formatted and mounted.

No partitioning or formatting is performed.
"""
import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys


def find_grub_tool(name: str) -> str:
    """Locate grub-<name> or grub2-<name> utility."""
    for candidate in [f'grub-{name}', f'grub2-{name}']:
        if shutil.which(candidate):
            return candidate
    return None


def get_lpss_uuid(lpss_dir):
    """Try to determine the filesystem UUID of the device mounted at lpss_dir."""
    try:
        dev = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', lpss_dir],
                             capture_output=True, text=True, check=True)
        device = dev.stdout.strip()
        uuid = subprocess.run(['blkid', '-s', 'UUID', '-o', 'value', device],
                              capture_output=True, text=True, check=True)
        return uuid.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def run(cmd, desc=None):
    """Run a command, print it, and exit on failure."""
    if desc:
        print(desc)
    print(f"  Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error: command failed: {e}", file=sys.stderr)
        sys.exit(1)


def check_mount_point(path):
    """Return True if path is a mount point, else print a warning."""
    try:
        subprocess.run(['findmnt', '-n', path], capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        print(f"Warning: {path} does not appear to be a mount point.",
              file=sys.stderr)
        return False


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
                        help='EFI boot entry name (default: LPSS)')
    parser.add_argument('--grub-install-extra', type=str, default='',
                        help='Extra arguments passed verbatim to grub-install '
                             '(e.g., "--removable --no-nvram")')
    args = parser.parse_args()

    lpss_dir = os.path.abspath(args.lpss_dir)
    esp_dir = os.path.abspath(args.esp_dir)

    # 0. Validate bootloader-id
    if not re.match(r'^[A-Za-z0-9._-]+$', args.bootloader_id):
        print("Error: --bootloader-id must contain only A-Z, a-z, 0-9, "
              "'.', '_', '-'", file=sys.stderr)
        sys.exit(1)

    # 1. Early dependency checks
    for tool in ['findmnt', 'blkid']:
        if not shutil.which(tool):
            print(f"Error: required system utility '{tool}' not found in PATH",
                  file=sys.stderr)
            sys.exit(1)

    grub_install = find_grub_tool('install')
    if not grub_install:
        print("Error: grub-install or grub2-install not found in PATH",
              file=sys.stderr)
        sys.exit(1)

    editenv_cmd = find_grub_tool('editenv')
    if not editenv_cmd:
        print("Error: grub-editenv or grub2-editenv is required",
              file=sys.stderr)
        sys.exit(1)

    # 2. Mount point checks (warn only)
    check_mount_point(lpss_dir)
    check_mount_point(esp_dir)

    # 3. Determine LPSS UUID
    lpss_uuid = args.lpss_uuid or get_lpss_uuid(lpss_dir)
    if not lpss_uuid:
        print("Error: could not determine LPSS UUID. "
              "Use --lpss-uuid to specify it.", file=sys.stderr)
        sys.exit(1)
    print(f"LPSS UUID: {lpss_uuid}")

    # 4. Create lpss.conf
    config_path = os.path.join(lpss_dir, 'lpss.conf')
    if os.path.exists(config_path):
        print(f"Error: {config_path} already exists. "
              "LPSS appears to be already installed.", file=sys.stderr)
        sys.exit(1)
    config_content = (
        "[lpss]\n"
        f"id={lpss_uuid}\n"
        "version=1\n"
    )
    with open(config_path, 'w') as f:
        f.write(config_content)
    print(f"Created {config_path}")

    # 5. Create flags directory
    flags_dir = os.path.join(lpss_dir, 'flags')
    os.makedirs(flags_dir, exist_ok=True)
    print(f"Created directory {flags_dir}")

    # 6. Create empty grubenv
    grubenv_path = os.path.join(lpss_dir, 'grubenv')
    run([editenv_cmd, grubenv_path, 'create'],
        desc="Initialising grubenv")

    # 7. Run grub-install
    extra_args = shlex.split(args.grub_install_extra) if args.grub_install_extra else []
    grub_cmd = [
        grub_install,
        '--target=x86_64-efi',
        f'--efi-directory={esp_dir}',
        f'--boot-directory={lpss_dir}',
        f'--bootloader-id={args.bootloader_id}',
    ] + extra_args

    run(grub_cmd, desc="Installing GRUB (UEFI)")

    # 8. Overwrite main grub.cfg (guarantee LPSS version)
    grub_cfg_path = os.path.join(lpss_dir, 'grub.cfg')
    with open(grub_cfg_path, 'w') as f:
        f.write("# LPSS - empty menu (no entries registered yet)\n")
    print(f"Created (overwritten) {grub_cfg_path}")

    # 9. Write bootstrap grub.cfg in ESP
    lpss_esp_cfg = os.path.join(esp_dir, 'EFI', args.bootloader_id, 'grub.cfg')
    os.makedirs(os.path.dirname(lpss_esp_cfg), exist_ok=True)
    with open(lpss_esp_cfg, 'w') as f:
        f.write(f"search --fs-uuid --set=root {lpss_uuid}\n")
        f.write("set prefix=($root)/grub\n")
        f.write("configfile ($root)/grub.cfg\n")
    print(f"Created {lpss_esp_cfg}")

    print(f"\nLPSS installed successfully on {lpss_dir}.")
    print("You can now import Linux systems with 'lpss_import'.")


if __name__ == '__main__':
    main()