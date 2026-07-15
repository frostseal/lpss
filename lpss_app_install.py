#!/usr/bin/env python3
# @file lpss_app_install.py
"""
Install LPSS tools by creating symbolic links.

Creates symlinks in <prefix> for each LPSS script, stripping the .py
extension.

Usage:
  python3 lpss_app_install.py --prefix /usr/local/bin
  python3 lpss_app_install.py --uninstall --prefix /usr/local/bin
"""

import argparse
import os
import sys

TOOLS = ['lpss_install.py', 'lpss_import.py', 'lpss_ctl.py']


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--prefix', default='/usr/local/bin',
                        help='Installation prefix (default: /usr/local/bin)')
    parser.add_argument('--uninstall', action='store_true',
                        help='Remove symlinks instead of creating them')
    parser.add_argument('--app-dir', default=None,
                        help='Directory containing the LPSS scripts '
                             '(default: directory of this script)')
    args = parser.parse_args()

    prefix = args.prefix
    if args.app_dir:
        app_dir = args.app_dir
    else:
        app_dir = os.path.dirname(os.path.abspath(__file__))

    if not os.path.isdir(prefix):
        print(f"Error: prefix directory {prefix} does not exist.",
              file=sys.stderr)
        sys.exit(1)

    for tool in TOOLS:
        src = os.path.join(app_dir, tool)
        link_name = os.path.join(prefix, tool.replace('.py', ''))
        if not os.path.exists(src):
            print(f"Warning: {src} not found, skipping.", file=sys.stderr)
            continue

        if args.uninstall:
            if os.path.islink(link_name):
                os.unlink(link_name)
                print(f"Removed {link_name}")
            elif os.path.exists(link_name):
                print(f"Warning: {link_name} exists and is not a symlink, "
                      "skipping.", file=sys.stderr)
            else:
                print(f"Already absent: {link_name}")
        else:
            if os.path.lexists(link_name):
                if os.path.islink(link_name):
                    os.unlink(link_name)
                else:
                    print(f"Error: {link_name} exists and is not a symlink.",
                          file=sys.stderr)
                    sys.exit(1)
            os.symlink(src, link_name)
            print(f"{link_name} -> {src}")

    print("Done.")


if __name__ == '__main__':
    main()