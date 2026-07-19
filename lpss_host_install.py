#!/usr/bin/env python3
# @file lpss_host_install.py
"""
Integrate LPSS with the current host Linux.

Performs independent installation steps:

* tools       – create symbolic links for LPSS commands
* mountpoint  – create the LPSS mount point directory
* fstab       – add an /etc/fstab entry for the LPSS partition

The LPSS partition can be specified via --lpss-device (e.g., /dev/sda2),
--lpss-uuid, or --lpss-mount (an already mounted LPSS directory).
If no source is given, the fstab step is skipped.

By default, all implemented steps are executed.
Individual steps can be enabled or disabled with --install-* and
--skip-* flags.

Examples:
  # Full integration using a device
  sudo lpss_host_install --lpss-device /dev/sda2

  # Only update fstab
  sudo lpss_host_install --install-fstab --lpss-device /dev/nvme0n1p3

  # Only tools
  lpss_host_install --install-tools --prefix /usr/local/bin

  # Dry-run
  lpss_host_install --dry-run --lpss-device /dev/sda2
"""

import argparse
import os
import sys

from lib.device import get_device_uuid
from lib.fstab import add_entry as install_fstab_entry
from lib.host_install import (
    install_tools,
    uninstall_tools,
    install_mountpoint,
)
from lib.utils import get_mount_uuid


def _resolve_lpss_uuid(args):
    """Return (uuid, description) from --lpss-device, --lpss-mount, or --lpss-uuid."""
    if args.lpss_uuid:
        return args.lpss_uuid, "command line"
    if args.lpss_device:
        uuid = get_device_uuid(args.lpss_device)
        if uuid:
            return uuid, f"device {args.lpss_device}"
        print(f"Warning: cannot determine UUID for {args.lpss_device}",
              file=sys.stderr)
        return None, None
    if args.lpss_mount:
        uuid = get_mount_uuid(args.lpss_mount)
        if uuid:
            return uuid, f"mount point {args.lpss_mount}"
        print(f"Warning: cannot determine UUID for mount {args.lpss_mount}",
              file=sys.stderr)
        return None, None
    return None, None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    src_group = parser.add_argument_group("LPSS partition source")
    src_group.add_argument('--lpss-device', metavar='DEVICE',
                           help='Block device of the LPSS partition '
                                '(e.g., /dev/sda2)')
    src_group.add_argument('--lpss-uuid', metavar='UUID',
                           help='Filesystem UUID of the LPSS partition')
    src_group.add_argument('--lpss-mount', metavar='PATH',
                           help='Mount point of an already mounted LPSS partition')

    parser.add_argument('--lpss-mountpoint', default='/boot/lpss',
                        help='LPSS mount point path (default: /boot/lpss)')

    step_group = parser.add_argument_group("Installation steps")
    step_group.add_argument('--all', action='store_true',
                            help='Run all implemented steps (default)')
    step_group.add_argument('--install-tools', action='store_true',
                            help='Install command symlinks')
    step_group.add_argument('--install-mountpoint', action='store_true',
                            help='Create the mount point directory')
    step_group.add_argument('--install-fstab', action='store_true',
                            help='Add fstab entry')
    step_group.add_argument('--skip-tools', action='store_true',
                            help='Skip tools step')
    step_group.add_argument('--skip-mountpoint', action='store_true',
                            help='Skip mountpoint step')
    step_group.add_argument('--skip-fstab', action='store_true',
                            help='Skip fstab step')

    parser.add_argument('--prefix', default='/usr/local/bin',
                        help='Installation prefix for tools (default: /usr/local/bin)')
    parser.add_argument('--app-dir', default=None,
                        help='Directory containing the LPSS application bundle '
                             '(default: directory of this script)')
    parser.add_argument('--uninstall', action='store_true',
                        help='Remove symlinks (tools only)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be done, without making changes')

    args = parser.parse_args()
    dry_run = args.dry_run

    app_dir = args.app_dir or os.path.dirname(os.path.abspath(__file__))

    # Uninstall mode
    if args.uninstall:
        if args.install_tools or args.install_mountpoint or args.install_fstab:
            parser.error("--uninstall cannot be combined with installation steps")
        if dry_run:
            print("Dry-run: would uninstall tools")
        success = uninstall_tools(args.prefix, dry_run=dry_run)
        if not success and not dry_run:
            print("Uninstall completed with warnings.")
            sys.exit(1)
        print("Done.")
        return

    # Determine steps
    any_step = args.install_tools or args.install_mountpoint or args.install_fstab
    run_all = not any_step

    steps = {}
    if run_all:
        steps['tools'] = not args.skip_tools
        steps['mountpoint'] = not args.skip_mountpoint
        steps['fstab'] = not args.skip_fstab
    else:
        steps['tools'] = args.install_tools
        steps['mountpoint'] = args.install_mountpoint
        steps['fstab'] = args.install_fstab

    # Resolve UUID for fstab
    uuid = None
    if steps.get('fstab'):
        uuid, source_desc = _resolve_lpss_uuid(args)
        if uuid is None:
            if run_all:
                print("Warning: LPSS partition UUID not available; "
                      "fstab step will be skipped.", file=sys.stderr)
                steps['fstab'] = False
            else:
                print("Error: LPSS UUID is required for fstab installation.",
                      file=sys.stderr)
                sys.exit(1)
        else:
            print(f"Using LPSS UUID from {source_desc}: {uuid}")

    # Execute steps
    results = {}
    final_exit = 0

    if dry_run:
        print("Dry-run mode: no changes will be made.\n")

    if steps.get('tools'):
        ok = install_tools(args.prefix, app_dir, dry_run=dry_run)
        results['tools'] = "[OK]" if ok else "[FAIL]"
        if not ok and not run_all:
            final_exit = 1
    else:
        results['tools'] = "[SKIP]"

    if steps.get('mountpoint'):
        ok = install_mountpoint(args.lpss_mountpoint, dry_run=dry_run)
        results['mountpoint'] = "[OK]" if ok else "[FAIL]"
        if not ok and not run_all:
            final_exit = 1
    else:
        results['mountpoint'] = "[SKIP]"

    if steps.get('fstab'):
        ok = install_fstab_entry(uuid, args.lpss_mountpoint, dry_run=dry_run)
        if ok:
            results['fstab'] = "[OK]"
        else:
            results['fstab'] = "[WARN] skipped"
            if not run_all:
                final_exit = 1
    else:
        results['fstab'] = "[SKIP]"

    if dry_run:
        print("\nDry-run completed. No changes made.")
    else:
        print("\nLPSS host integration completed\n")

    print("Installed:")
    for step in ('tools', 'mountpoint', 'fstab'):
        status = results.get(step, "[SKIP]")
        print(f" {status:6s} {step}")

    if final_exit != 0:
        if not dry_run:
            print("\nSome mandatory steps failed.")
        sys.exit(final_exit)

    if not dry_run:
        print("Done.")


if __name__ == '__main__':
    main()