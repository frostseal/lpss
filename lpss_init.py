#!/usr/bin/env python3
# @file lpss_init.py
"""
Initialise an LPSS partition and install GRUB.

Formats a given partition as ext4, generates lpss.conf, flags/,
installs GRUB for UEFI on the EFI System Partition, and registers
an EFI Boot Entry.

The EFI System Partition must already be mounted, or its mount point
given via --esp-dir. The LPSS partition device (e.g., /dev/sda2) is
passed as --device.

All modifications are printed with absolute filesystem paths.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile


def find_grub_tool(name: str) -> str:
    """Locate grub-<name> or grub2-<name> utility."""
    for candidate in [f'grub-{name}', f'grub2-{name}']:
        if shutil.which(candidate):
            return candidate
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


def get_blkid_uuid(device: str) -> str:
    """Return the filesystem UUID of a device using blkid."""
    cmd = ['blkid', '-s', 'UUID', '-o', 'value', device]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error: blkid failed: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--device', required=True,
                        help='Block device for the LPSS partition (e.g., /dev/sda2)')
    parser.add_argument('--esp-dir', required=True,
                        help='Mount point of the EFI System Partition (e.g., /boot/efi)')
    parser.add_argument('--esp-dev', help='EFI system partition device (for efibootmgr, optional)')
    parser.add_argument('--label', default='LPSS',
                        help='Filesystem label for the LPSS partition (default: LPSS)')
    parser.add_argument('--bootloader-id', default='LPSS',
                        help='EFI boot entry name (default: LPSS)')
    parser.add_argument('--repair', action='store_true',
                        help='Repair ESP grub.cfg after UUID change (no formatting)')
    args = parser.parse_args()

    # --- repair mode -------------------------------------------------
    if args.repair:
        print("Repair mode: updating ESP grub.cfg to reflect current LPSS UUID.")
        lpss_device = args.device
        lpss_uuid = get_blkid_uuid(lpss_device)
        if not lpss_uuid:
            print(f"Error: could not read UUID from {lpss_device}", file=sys.stderr)
            sys.exit(1)
        esp_dir = args.esp_dir.rstrip('/')
        if not os.path.isdir(esp_dir):
            print(f"Error: ESP directory not found: {esp_dir}", file=sys.stderr)
            sys.exit(1)
        lpss_esp_cfg = os.path.join(esp_dir, 'EFI', args.bootloader_id, 'grub.cfg')
        lines = [
            f"search --fs-uuid --set=root {lpss_uuid}\n",
            "set prefix=($root)/grub\n",
            "configfile ($root)/grub.cfg\n"
        ]
        with open(lpss_esp_cfg, 'w') as f:
            f.writelines(lines)
        print(f"Updated {lpss_esp_cfg} with UUID {lpss_uuid}")
        # Also update efibootmgr entry? Just show UUID.
        print("Repair complete.")
        return

    # --- full initialisation -----------------------------------------
    lpss_device = args.device
    esp_dir = args.esp_dir.rstrip('/')
    bootloader_id = args.bootloader_id

    if not os.path.isdir(esp_dir):
        print(f"Error: ESP directory not found: {esp_dir}", file=sys.stderr)
        sys.exit(1)

    # 1. Format the LPSS partition
    print(f"Formatting {lpss_device} as ext4...")
    run(['mkfs.ext4', '-F', '-L', args.label, lpss_device],
        desc=f"Creating ext4 filesystem on {lpss_device}")

    # 2. Mount LPSS partition temporarily
    mount_point = tempfile.mkdtemp(prefix='lpss_mnt_')
    try:
        run(['mount', lpss_device, mount_point],
            desc=f"Mounting {lpss_device} at {mount_point}")

        # 3. Install GRUB on LPSS and EFI
        grub_install = find_grub_tool('install')
        if not grub_install:
            print("Error: grub-install or grub2-install not found in PATH", file=sys.stderr)
            sys.exit(1)

        grub_cmd = [
            grub_install,
            '--target=x86_64-efi',
            f'--efi-directory={esp_dir}',
            f'--boot-directory={mount_point}',
            f'--bootloader-id={bootloader_id}',
            '--no-nvram',
        ]
        run(grub_cmd, desc="Installing GRUB (UEFI)")

        # 4. Create lpss.conf
        lpss_uuid = get_blkid_uuid(lpss_device)
        if not lpss_uuid:
            raise RuntimeError("Failed to obtain UUID")
        config_path = os.path.join(mount_point, 'lpss.conf')
        config_content = (
            "[lpss]\n"
            f"id={lpss_uuid}\n"
            "version=1\n"
        )
        with open(config_path, 'w') as f:
            f.write(config_content)
        print(f"Created {config_path}")

        # 5. Create flags directory
        flags_dir = os.path.join(mount_point, 'flags')
        os.makedirs(flags_dir, exist_ok=True)
        print(f"Created directory {flags_dir}")

        # 6. Generate empty main grub.cfg
        grub_cfg_path = os.path.join(mount_point, 'grub.cfg')
        with open(grub_cfg_path, 'w') as f:
            f.write("# LPSS - empty menu (no entries registered yet)\n")
        print(f"Created {grub_cfg_path}")

        # 7. Create empty grubenv
        grubenv_path = os.path.join(mount_point, 'grubenv')
        with open(grubenv_path, 'w') as f:
            pass
        print(f"Created {grubenv_path}")

        # 8. Overwrite ESP grub.cfg with our search logic
        lpss_esp_cfg = os.path.join(esp_dir, 'EFI', bootloader_id, 'grub.cfg')
        os.makedirs(os.path.dirname(lpss_esp_cfg), exist_ok=True)
        lines = [
            f"search --fs-uuid --set=root {lpss_uuid}\n",
            "set prefix=($root)/grub\n",
            "configfile ($root)/grub.cfg\n"
        ]
        with open(lpss_esp_cfg, 'w') as f:
            f.writelines(lines)
        print(f"Created {lpss_esp_cfg} (bootstrap config)")

    finally:
        # 9. Unmount LPSS partition
        run(['umount', mount_point],
            desc="Unmounting LPSS partition")
        os.rmdir(mount_point)

    # 10. Register EFI Boot Entry
    if args.esp_dev:
        efi_device = args.esp_dev
    else:
        # try to guess from mount point
        efi_device = None
        try:
            res = subprocess.run(['findmnt', '-n', '-o', 'SOURCE', esp_dir],
                                 capture_output=True, text=True, check=True)
            efi_device = res.stdout.strip()
        except subprocess.CalledProcessError:
            pass

    if efi_device:
        efibootmgr_cmd = ['efibootmgr', '-c', '-d', efi_device[:8],  # disk
                          '-p', efi_device[8:], '-L', bootloader_id,
                          '-l', f'\\EFI\\{bootloader_id}\\grubx64.efi']
        try:
            subprocess.run(efibootmgr_cmd, check=True)
            print(f"EFI Boot Entry '{bootloader_id}' created.")
        except subprocess.CalledProcessError as e:
            print(f"Warning: efibootmgr failed: {e}", file=sys.stderr)
    else:
        print("Warning: could not determine ESP device, EFI boot entry not created.",
              file=sys.stderr)

    print(f"\nLPSS initialised successfully on {lpss_device}.")
    print(f"LPSS UUID: {lpss_uuid}")
    print("You can now import entries with lpss_import.")


if __name__ == '__main__':
    main()