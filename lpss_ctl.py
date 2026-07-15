#!/usr/bin/env python3
# @file lpss_ctl.py
"""
LPSS control utility.

Manage boot entries, flags, and trial boots.
The LPSS partition can be given via --lpss-dir, LPSS_MOUNT env, or
defaults to /mnt/lpss.

Every modifying operation prints the exact filesystem paths affected.
"""
import os
import sys

# Allow running from copied tools directory (e.g., /mnt/lpss/bin)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

import argparse
import subprocess

from lib.config import load_config
from lib.flags import (read_flags, create_flag, remove_flag, has_flag)
from lib.grub import generate_grub_cfg
from lib.utils import (get_grub_subdir, find_grub_tool,
                       parse_cmdline, menu_entry_exists,
                       make_entry_default)


def _get_lpss_dir(args_lpss_dir=None):
    if args_lpss_dir:
        return args_lpss_dir
    return os.environ.get('LPSS_MOUNT', '/mnt/lpss')


def _check_mount_point(path):
    if not os.path.ismount(path):
        print(f"Warning: {path} is not a mount point. "
              "Make sure the LPSS partition is mounted.",
              file=sys.stderr)


def _read_grubenv_next_entry(grubenv_path):
    editenv = find_grub_tool('editenv')
    if not editenv:
        return None
    try:
        res = subprocess.run([editenv, grubenv_path, 'list'],
                             capture_output=True, text=True, check=True)
        for line in res.stdout.splitlines():
            if line.startswith('next_entry='):
                return line.split('=', 1)[1]
    except subprocess.CalledProcessError:
        return None
    return None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lpss-dir',
                        help='Path to mounted LPSS partition')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('status', help='Show overall LPSS status')
    subparsers.add_parser('list', help='List all registered entries')
    subparsers.add_parser('current',
                          help='Show current booted entry')

    boot_parser = subparsers.add_parser('boot',
                                        help='Set a one-shot trial boot')
    boot_parser.add_argument('entry', help='Entry ID to boot')

    subparsers.add_parser('confirm',
                          help='Confirm a trial boot, making it the default')

    enable_parser = subparsers.add_parser('enable', help='Enable an entry')
    enable_parser.add_argument('entry', help='Entry ID')

    disable_parser = subparsers.add_parser('disable', help='Disable an entry')
    disable_parser.add_argument('entry', help='Entry ID')

    default_parser = subparsers.add_parser('default',
                                           help='Set an entry as the default for its role')
    default_parser.add_argument('entry', help='Entry ID')

    subparsers.add_parser('apply',
                          help='Regenerate grub.cfg from current configuration')

    args = parser.parse_args()
    lpss_dir = _get_lpss_dir(args.lpss_dir)

    # ---- current ---------------------------------------------------------
    if args.command == 'current':
        cmd = parse_cmdline()
        if cmd['lpss_entry']:
            print(cmd['lpss_entry'])
        else:
            print("Not booted under LPSS or lpss_entry missing")
        return

    # ---- validate LPSS environment ---------------------------------------
    _check_mount_point(lpss_dir)
    config_path = os.path.join(lpss_dir, 'lpss.conf')
    if not os.path.isfile(config_path):
        print(f"Error: {lpss_dir} does not appear to be an LPSS partition "
              "(no lpss.conf)", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    flags_dir = os.path.join(lpss_dir, 'flags')

    # GRUB subdirectory
    grub_subdir = get_grub_subdir(lpss_dir)
    if not grub_subdir:
        print("Error: cannot find GRUB directory (grub2 or grub) in "
              f"{lpss_dir}.", file=sys.stderr)
        sys.exit(1)
    grub_cfg_path = os.path.join(lpss_dir, grub_subdir, 'grub.cfg')
    grubenv_path = os.path.join(lpss_dir, grub_subdir, 'grubenv')

    # ---- status ---------------------------------------------------------
    if args.command == 'status':
        flags = read_flags(flags_dir)
        print(f"LPSS UUID: {config.uuid}")
        print(f"Version: {config.version}")
        for eid, entry in config.entries.items():
            f = flags.get(eid, set())
            enabled = 'enabled' in f
            default = 'default' in f
            print(f"\n{eid}")
            print(f"  role: {entry.role}")
            print(f"  enabled: {'yes' if enabled else 'no'}")
            print(f"  default: {'yes' if default else 'no'}")

        next_entry = _read_grubenv_next_entry(grubenv_path)
        if next_entry:
            print(f"\nPending one-shot boot: {next_entry}")

        cmd = parse_cmdline()
        if cmd['lpss_entry']:
            print(f"Current boot entry: {cmd['lpss_entry']}")

    # ---- list ------------------------------------------------------------
    elif args.command == 'list':
        for eid in config.entries:
            print(eid)

    # ---- boot ------------------------------------------------------------
    elif args.command == 'boot':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)

        if not menu_entry_exists(grub_cfg_path, entry_id):
            print(f"Error: grub.cfg does not contain menu entry for "
                  f"'{entry_id}'. Run 'apply' to regenerate.",
                  file=sys.stderr)
            sys.exit(1)

        if not has_flag(flags_dir, entry_id, 'enabled'):
            print(f"Warning: entry '{entry_id}' is not enabled; "
                  "trial boot may fail if it's disabled in menu.",
                  file=sys.stderr)

        next_entry = f'entry_{entry_id}'
        editenv = find_grub_tool('editenv')
        if not editenv:
            print("Error: grub-editenv not found", file=sys.stderr)
            sys.exit(1)

        cmd = [editenv, grubenv_path, 'set', f'next_entry={next_entry}']
        try:
            subprocess.run(cmd, check=True)
            print(f"Updated {grubenv_path}: set next_entry={next_entry}")
            print(f"One-shot boot for '{entry_id}' set. Reboot to test.")
        except subprocess.CalledProcessError as e:
            print(f"{editenv} failed: {e}", file=sys.stderr)
            sys.exit(1)

    # ---- confirm ---------------------------------------------------------
    elif args.command == 'confirm':
        cmd = parse_cmdline()
        if not cmd['lpss_trial']:
            print("Error: current boot is not a trial (lpss_trial=1 missing)",
                  file=sys.stderr)
            sys.exit(1)
        entry_id = cmd['lpss_entry']
        if not entry_id:
            print("Error: lpss_entry missing", file=sys.stderr)
            sys.exit(1)
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not in configuration",
                  file=sys.stderr)
            sys.exit(1)

        role = config.entries[entry_id].role
        make_entry_default(flags_dir, config, role, entry_id,
                           create=create_flag, remove=remove_flag,
                           has=has_flag)
        enabled_path = os.path.join(flags_dir, entry_id, 'enabled')
        default_path = os.path.join(flags_dir, entry_id, 'default')
        print(f"Ensured {enabled_path} exists")
        print(f"Created {default_path}")
        for eid, e in config.entries.items():
            if e.role == role and eid != entry_id:
                if has_flag(flags_dir, eid, 'default'):
                    print(f"Removed {os.path.join(flags_dir, eid, 'default')}")
        print(f"Entry '{entry_id}' confirmed as default for role '{role}'.")

    # ---- enable ---------------------------------------------------------
    elif args.command == 'enable':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        flag_path = os.path.join(flags_dir, entry_id, 'enabled')
        create_flag(flags_dir, entry_id, 'enabled')
        print(f"Created {flag_path}")
        print(f"Entry '{entry_id}' enabled.")

    # ---- disable --------------------------------------------------------
    elif args.command == 'disable':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        if has_flag(flags_dir, entry_id, 'default'):
            print(f"Error: entry '{entry_id}' is the default. "
                  "Change the default first.",
                  file=sys.stderr)
            sys.exit(1)
        flag_path = os.path.join(flags_dir, entry_id, 'enabled')
        if has_flag(flags_dir, entry_id, 'enabled'):
            remove_flag(flags_dir, entry_id, 'enabled')
            print(f"Removed {flag_path}")
        else:
            print(f"{flag_path} already absent")
        print(f"Entry '{entry_id}' disabled.")

    # ---- default (set as default) ---------------------------------------
    elif args.command == 'default':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        if not has_flag(flags_dir, entry_id, 'enabled'):
            print(f"Error: entry '{entry_id}' is not enabled. "
                  "Enable it first or use 'confirm'.",
                  file=sys.stderr)
            sys.exit(1)

        role = config.entries[entry_id].role
        make_entry_default(flags_dir, config, role, entry_id,
                           create=create_flag, remove=remove_flag,
                           has=has_flag)
        default_path = os.path.join(flags_dir, entry_id, 'default')
        print(f"Created {default_path}")
        for eid, e in config.entries.items():
            if e.role == role and eid != entry_id:
                if has_flag(flags_dir, eid, 'default'):
                    print(f"Removed {os.path.join(flags_dir, eid, 'default')}")
        print(f"Entry '{entry_id}' is now the default for role '{role}'.")

    # ---- apply -----------------------------------------------------------
    elif args.command == 'apply':
        generate_grub_cfg(config, grub_cfg_path)
        print(f"Generated {grub_cfg_path}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()