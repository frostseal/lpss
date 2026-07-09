#!/usr/bin/env python3
# @file lpss_ctl.py
"""
LPSS control utility.

Manage boot entries, flags, and trial boots.
The LPSS partition can be given via --lpss-dir, LPSS_MOUNT env, or
defaults to /mnt/lpss.

Every modifying operation prints the exact filesystem paths affected.
"""
import argparse
import os
import sys
import shutil
import subprocess
from lib.config import load_config
from lib.flags import read_flags, get_flag, set_flag
from lib.grub import generate_grub_cfg


def get_lpss_dir(args_lpss_dir=None):
    if args_lpss_dir:
        return args_lpss_dir
    return os.environ.get('LPSS_MOUNT', '/mnt/lpss')


def find_grub_tool(name: str) -> str:
    """Locate grub-<name> or grub2-<name> utility."""
    for candidate in [f'grub-{name}', f'grub2-{name}']:
        if shutil.which(candidate):
            return candidate
    return None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--lpss-dir',
                        help='Path to mounted LPSS partition (overrides LPSS_MOUNT)')
    subparsers = parser.add_subparsers(dest='command', required=True)

    subparsers.add_parser('status', help='Show overall LPSS status')
    subparsers.add_parser('list', help='List all registered entries')
    subparsers.add_parser('current',
                          help='Show current booted entry (from /proc/cmdline)')

    boot_parser = subparsers.add_parser('boot',
                                        help='Set a one-shot trial boot')
    boot_parser.add_argument('entry', help='Entry ID to boot')

    subparsers.add_parser('confirm',
                          help='Confirm a trial boot, making it permanent')

    enable_parser = subparsers.add_parser('enable', help='Enable an entry')
    enable_parser.add_argument('entry', help='Entry ID')

    disable_parser = subparsers.add_parser('disable', help='Disable an entry')
    disable_parser.add_argument('entry', help='Entry ID')

    activate_parser = subparsers.add_parser('activate',
                                            help='Activate an entry')
    activate_parser.add_argument('entry', help='Entry ID')

    subparsers.add_parser('apply',
                          help='Regenerate grub.cfg from current configuration')

    args = parser.parse_args()
    lpss_dir = get_lpss_dir(args.lpss_dir)

    if args.command == 'current':
        cmdline = open('/proc/cmdline').read()
        lpss_entry = None
        for param in cmdline.split():
            if param.startswith('lpss_entry='):
                lpss_entry = param.split('=', 1)[1]
                break
        if lpss_entry:
            print(lpss_entry)
        else:
            print("Not booted under LPSS or lpss_entry missing")
        return

    config_path = os.path.join(lpss_dir, 'lpss.conf')
    flags_dir = os.path.join(lpss_dir, 'flags')
    grubenv_path = os.path.join(lpss_dir, 'grubenv')
    grub_cfg_path = os.path.join(lpss_dir, 'grub.cfg')

    if not os.path.isfile(config_path):
        print(f"Error: {lpss_dir} does not appear to be an LPSS partition "
              "(no lpss.conf)", file=sys.stderr)
        sys.exit(1)

    config = load_config(config_path)
    flags = read_flags(flags_dir)

    if args.command == 'status':
        print(f"LPSS UUID: {config.uuid}")
        print(f"Version: {config.version}")
        print("Entries:")
        for eid, entry in config.entries.items():
            f = flags.get(eid, set())
            enabled = 'enabled' in f
            active = 'active' in f
            print(f"  {eid}: enabled={enabled}, active={active}, role={entry.role}")
        if os.path.exists('/proc/cmdline'):
            cmdline = open('/proc/cmdline').read()
            for param in cmdline.split():
                if param.startswith('lpss_entry='):
                    print(f"Current boot entry: {param.split('=', 1)[1]}")
                    break

    elif args.command == 'list':
        for eid in config.entries:
            print(eid)

    elif args.command == 'boot':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        if not get_flag(flags_dir, entry_id, 'enabled'):
            print(f"Warning: entry '{entry_id}' is not enabled; "
                  "trial boot may fail if it's disabled in menu.",
                  file=sys.stderr)

        next_entry = f'entry_{entry_id}'
        editenv_cmd = find_grub_tool('editenv')
        if not editenv_cmd:
            print("Error: neither grub-editenv nor grub2-editenv found in PATH",
                  file=sys.stderr)
            sys.exit(1)

        cmd = [editenv_cmd, grubenv_path, 'set', f'next_entry={next_entry}']
        try:
            subprocess.run(cmd, check=True)
            print(f"Updated {grubenv_path}: set next_entry={next_entry}")
            print(f"One-shot boot for '{entry_id}' set. Reboot to test.")
        except subprocess.CalledProcessError as e:
            print(f"{editenv_cmd} failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'confirm':
        cmdline = open('/proc/cmdline').read()
        trial = False
        lpss_entry = None
        for param in cmdline.split():
            if param == 'lpss_trial=1':
                trial = True
            elif param.startswith('lpss_entry='):
                lpss_entry = param.split('=', 1)[1]
        if not trial:
            print("Error: current boot is not a trial (lpss_trial=1 missing)",
                  file=sys.stderr)
            sys.exit(1)
        if not lpss_entry:
            print("Error: lpss_entry missing from kernel command line",
                  file=sys.stderr)
            sys.exit(1)
        if lpss_entry not in config.entries:
            print(f"Error: entry '{lpss_entry}' not in configuration",
                  file=sys.stderr)
            sys.exit(1)

        role = config.entries[lpss_entry].role
        for eid, entry in config.entries.items():
            if entry.role == role and eid != lpss_entry:
                flag_path = os.path.join(flags_dir, eid, 'active')
                if get_flag(flags_dir, eid, 'active'):
                    set_flag(flags_dir, eid, 'active', False)
                    print(f"Removed {flag_path}")

        enabled_flag = os.path.join(flags_dir, lpss_entry, 'enabled')
        active_flag = os.path.join(flags_dir, lpss_entry, 'active')
        if not get_flag(flags_dir, lpss_entry, 'enabled'):
            set_flag(flags_dir, lpss_entry, 'enabled', True)
            print(f"Created {enabled_flag}")
        else:
            set_flag(flags_dir, lpss_entry, 'enabled', True)
            print(f"Ensured {enabled_flag} exists")
        set_flag(flags_dir, lpss_entry, 'active', True)
        print(f"Created {active_flag}")
        print(f"Entry '{lpss_entry}' confirmed as active for role '{role}'.")

    elif args.command == 'enable':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        flag_path = os.path.join(flags_dir, entry_id, 'enabled')
        set_flag(flags_dir, entry_id, 'enabled', True)
        print(f"Created {flag_path}")
        print(f"Entry '{entry_id}' enabled.")

    elif args.command == 'disable':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        if get_flag(flags_dir, entry_id, 'active'):
            print(f"Error: entry '{entry_id}' is active. Deactivate it first.",
                  file=sys.stderr)
            sys.exit(1)
        flag_path = os.path.join(flags_dir, entry_id, 'enabled')
        if os.path.exists(flag_path):
            set_flag(flags_dir, entry_id, 'enabled', False)
            print(f"Removed {flag_path}")
        else:
            print(f"{flag_path} already absent")
        print(f"Entry '{entry_id}' disabled.")

    elif args.command == 'activate':
        entry_id = args.entry
        if entry_id not in config.entries:
            print(f"Error: entry '{entry_id}' not found", file=sys.stderr)
            sys.exit(1)
        if not get_flag(flags_dir, entry_id, 'enabled'):
            print(f"Error: entry '{entry_id}' is not enabled. "
                  "Enable it first or use 'confirm'.",
                  file=sys.stderr)
            sys.exit(1)

        role = config.entries[entry_id].role
        for eid, entry in config.entries.items():
            if entry.role == role and eid != entry_id:
                flag_path = os.path.join(flags_dir, eid, 'active')
                if get_flag(flags_dir, eid, 'active'):
                    set_flag(flags_dir, eid, 'active', False)
                    print(f"Removed {flag_path}")

        active_flag = os.path.join(flags_dir, entry_id, 'active')
        set_flag(flags_dir, entry_id, 'active', True)
        print(f"Created {active_flag}")
        print(f"Entry '{entry_id}' activated for role '{role}'.")

    elif args.command == 'apply':
        generate_grub_cfg(config, flags, grub_cfg_path)
        print(f"Generated {grub_cfg_path}")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()