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
from lib.config import load_config
from lib.flags import read_flags
from lib.grub import generate_grub_cfg


def get_lpss_dir(args_lpss_dir=None):
    if args_lpss_dir:
        return args_lpss_dir
    return os.environ.get('LPSS_MOUNT', '/mnt/lpss')


def find_kernel_initrd(root_dir):
    """Locate the most recent kernel and initrd in /boot of root_dir."""
    boot_dir = os.path.join(root_dir, 'boot')
    if not os.path.isdir(boot_dir):
        return None, None
    kernels = sorted(glob.glob(os.path.join(boot_dir, 'vmlinuz-*')),
                     key=os.path.getmtime, reverse=True)
    if not kernels:
        return None, None
    kernel = kernels[0]
    version = os.path.basename(kernel).replace('vmlinuz-', '')
    patterns = [
        f'initramfs-{version}.img',
        f'initrd-{version}.img',
        f'initramfs-{version}',
        f'initrd-{version}',
        f'initrd.img-{version}',
    ]
    initrd = None
    for pat in patterns:
        path = os.path.join(boot_dir, pat)
        if os.path.exists(path):
            initrd = path
            break
    if not initrd:
        for name in os.listdir(boot_dir):
            if name.startswith('initr') and version in name:
                initrd = os.path.join(boot_dir, name)
                break
    linux_rel = os.path.relpath(kernel, root_dir) if kernel else None
    initrd_rel = os.path.relpath(initrd, root_dir) if initrd else None
    return linux_rel, initrd_rel


def update_entry_in_config(config_path, entry_id, linux, initrd,
                           options, locator, role):
    """
    Update an existing entry section in lpss.conf.

    Reads the file, modifies the matching [entry.<id>] section,
    and writes it back.
    """
    with open(config_path, 'r') as f:
        lines = f.readlines()

    in_target = False
    new_lines = []
    section_header = f'[entry.{entry_id}]'
    fields = {
        'linux': f'linux=/{linux.lstrip("/")}\n',
        'initrd': f'initrd=/{initrd.lstrip("/")}\n',
        'options': f'options={options}\n',
        'locator': f'locator={locator}\n',
        'role': f'role={role}\n',
    }

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped == section_header:
            in_target = True
            new_lines.append(line)
            i += 1
            while i < len(lines) and not lines[i].startswith('['):
                i += 1
            for key in ['id', 'role', 'locator', 'linux', 'initrd', 'options']:
                if key == 'id':
                    new_lines.append(f'id={entry_id}\n')
                else:
                    new_lines.append(fields[key])
            continue
        else:
            new_lines.append(line)
            i += 1

    if not in_target:
        new_lines.append(f'\n{section_header}\n')
        new_lines.append(f'id={entry_id}\n')
        new_lines.append(f'role={role}\n')
        new_lines.append(f'locator={locator}\n')
        new_lines.append(f'linux=/{linux.lstrip("/")}\n')
        new_lines.append(f'initrd=/{initrd.lstrip("/")}\n')
        new_lines.append(f'options={options}\n')

    with open(config_path, 'w') as f:
        f.writelines(new_lines)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lpss-dir',
                        help='Path to mounted LPSS partition (overrides LPSS_MOUNT)')
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

    lpss_dir = get_lpss_dir(args.lpss_dir)
    config_path = os.path.join(lpss_dir, 'lpss.conf')
    flags_dir = os.path.join(lpss_dir, 'flags')
    grub_cfg_path = os.path.join(lpss_dir, 'grub.cfg')

    if not os.path.isfile(config_path):
        print(f"Error: LPSS not initialised. {config_path} not found.",
              file=sys.stderr)
        sys.exit(1)

    root_dir = args.root.rstrip('/')
    if not root_dir:
        root_dir = '/'

    if not os.path.isdir(root_dir):
        print(f"Error: root directory not found: {root_dir}", file=sys.stderr)
        sys.exit(1)

    linux_path = args.linux
    initrd_path = args.initrd

    if not linux_path or not initrd_path:
        auto_linux, auto_initrd = find_kernel_initrd(root_dir)
        if not linux_path:
            if auto_linux:
                linux_path = auto_linux
                print(f"Auto-detected kernel: {linux_path}")
            else:
                print("Error: could not detect kernel in {}/boot, use --linux",
                      file=sys.stderr)
                sys.exit(1)
        if not initrd_path:
            if auto_initrd:
                initrd_path = auto_initrd
                print(f"Auto-detected initrd: {initrd_path}")
            else:
                print("Error: could not detect initrd in {}/boot, use --initrd",
                      file=sys.stderr)
                sys.exit(1)

    config = load_config(config_path)
    entry_exists = args.id in config.entries

    if entry_exists and not args.update:
        print(f"Error: entry '{args.id}' already exists. "
              "Use --update to modify.",
              file=sys.stderr)
        sys.exit(1)

    if entry_exists and args.update:
        update_entry_in_config(config_path, args.id,
                               linux_path, initrd_path,
                               args.options, args.locator, args.role)
        print(f"Updated entry '{args.id}' in {config_path}:")
        print(f"  linux=/{linux_path.lstrip('/')}")
        print(f"  initrd=/{initrd_path.lstrip('/')}")
        print(f"  options={args.options}")
        print(f"  locator={args.locator}")
    else:
        entry_block = f"""
[entry.{args.id}]
id={args.id}
role={args.role}
locator={args.locator}
linux=/{linux_path.lstrip('/')}
initrd=/{initrd_path.lstrip('/')}
options={args.options}
"""
        with open(config_path, 'a') as f:
            f.write(entry_block)
        print(f"Appended entry '{args.id}' to {config_path}")

    config = load_config(config_path)
    flags = read_flags(flags_dir)
    generate_grub_cfg(config, flags, grub_cfg_path)
    print(f"Regenerated {grub_cfg_path}")
    print("Operation complete.")


if __name__ == '__main__':
    main()