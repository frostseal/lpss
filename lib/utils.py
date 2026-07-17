# @file lib/utils.py
"""
Shared helper functions for LPSS tools.
"""

import glob
import os
import shutil
import subprocess
import sys

# GRUB helpers

def get_grub_subdir(lpss_dir: str) -> str:
    """Return the existing GRUB directory name."""
    for directory in ('grub2', 'grub'):
        if os.path.isdir(os.path.join(lpss_dir, directory)):
            return directory
    return ''


def find_grub_tool(name: str) -> str:
    """Locate a GRUB utility executable."""
    for candidate in (f'grub-{name}', f'grub2-{name}'):
        if shutil.which(candidate):
            return candidate
    return ''


# Kernel helpers

def parse_cmdline(cmdline_path=None):
    """Parse kernel command line for LPSS parameters."""
    path = cmdline_path or os.environ.get(
        'LPSS_CMDLINE_FILE',
        '/proc/cmdline',
    )

    result = {
        'lpss_entry': None,
        'lpss_trial': False,
    }

    try:
        with open(path) as file:
            for param in file.read().split():
                if param == 'lpss_trial=1':
                    result['lpss_trial'] = True
                elif param.startswith('lpss_entry='):
                    result['lpss_entry'] = param.split('=', 1)[1]
    except FileNotFoundError:
        pass

    return result


# GRUB configuration helpers

def menu_entry_exists(grub_cfg_path: str, entry_id: str) -> bool:
    """Check whether a GRUB menu entry exists."""
    if not os.path.exists(grub_cfg_path):
        return False

    with open(grub_cfg_path) as file:
        return f'--id=entry_{entry_id}' in file.read()


# Kernel and initrd discovery

_KERNEL_PATTERNS = [
    'vmlinuz-*',
    'vmlinuz',
    'linux-*',
    'linux',
    'bzImage-*',
    'bzImage',
    'kernel-*',
    'kernel',
]

_INITRD_PATTERNS = [
    'initramfs-{version}.img',
    'initrd-{version}.img',
    'initramfs-{version}',
    'initrd-{version}',
    'initrd.img-{version}',
    'initrd-{version}.gz',
]


def find_kernel_initrd_in_root(root_dir: str):
    """
    Locate the newest kernel and matching initrd in a root filesystem.

    Returns relative paths or (None, None).
    """
    boot_dir = os.path.join(root_dir, 'boot')

    if not os.path.isdir(boot_dir):
        return None, None

    candidates = []

    for pattern in _KERNEL_PATTERNS:
        candidates.extend(
            glob.glob(os.path.join(boot_dir, pattern))
        )

    if not candidates:
        return None, None

    kernel = max(candidates, key=os.path.getmtime)
    name = os.path.basename(kernel)
    version = name

    for prefix in (
        'vmlinuz-',
        'linux-',
        'bzImage-',
        'kernel-',
    ):
        if name.startswith(prefix):
            version = name[len(prefix):]
            break

    initrd = None

    for pattern in _INITRD_PATTERNS:
        path = os.path.join(
            boot_dir,
            pattern.format(version=version),
        )

        if os.path.exists(path):
            initrd = path
            break

    if initrd is None:
        for name in os.listdir(boot_dir):
            if name.startswith('initr') and version in name:
                initrd = os.path.join(boot_dir, name)
                break

    kernel_rel = os.path.relpath(kernel, root_dir)
    initrd_rel = None

    if initrd:
        initrd_rel = os.path.relpath(initrd, root_dir)

    return kernel_rel, initrd_rel


def find_host_kernel(kver: str = None) -> str:
    """Find the current host kernel image."""
    if kver is None:
        kver = os.uname().release

    candidates = [
        f'/boot/vmlinuz-{kver}',
        f'/boot/vmlinux-{kver}',
        f'/boot/kernel-{kver}',
        f'/boot/bzImage-{kver}',
        f'/usr/lib/modules/{kver}/vmlinuz',
    ]

    for path in candidates:
        if os.path.isfile(path):
            return os.path.realpath(path)

    for pattern in (
        f'/boot/*vmlinuz*{kver}*',
        f'/boot/*kernel*{kver}*',
    ):
        matches = sorted(glob.glob(pattern))

        if matches:
            return os.path.realpath(matches[0])

    return ''


def find_host_initrd(kver: str = None) -> str:
    """Find the current host initrd image."""
    if kver is None:
        kver = os.uname().release

    candidates = [
        f'/boot/initrd.img-{kver}',
        f'/boot/initrd-{kver}',
        f'/boot/initramfs-{kver}.img',
        f'/boot/initramfs-{kver}',
        f'/boot/initrd-{kver}.gz',
    ]

    for path in candidates:
        if os.path.isfile(path):
            return os.path.realpath(path)

    for pattern in (
        f'/boot/*initr*{kver}*',
        f'/boot/*initramfs*{kver}*',
    ):
        matches = sorted(glob.glob(pattern))

        if matches:
            return os.path.realpath(matches[0])

    return ''


# Locator helpers

_LOCATOR_DISPATCH = {
    'partlabel':
        'search --no-floppy --part-label {value} --set=root',
    'label':
        'search --no-floppy --label {value} --set=root',
    'fsuuid':
        'search --no-floppy --fs-uuid {value} --set=root',
}


def make_search_command(locator: str) -> str:
    """Convert LPSS locator into a GRUB search command."""
    try:
        kind, value = locator.split(':', 1)
    except ValueError:
        raise ValueError(
            f'Invalid locator format: {locator}'
        )

    template = _LOCATOR_DISPATCH.get(kind)

    if template is None:
        raise ValueError(
            f'Unsupported locator type: {kind}'
        )

    return template.format(value=value)


def validate_locator(locator: str) -> None:
    """Validate LPSS locator syntax."""
    make_search_command(locator)


# Flag helpers

def make_entry_default(flags_dir, config, entry_type, entry_id, *,
                       create, remove, has):
    """
    Make an entry default for its type.

    Enables the entry and removes default flags from other entries.
    """
    if not has(flags_dir, entry_id, 'enabled'):
        create(flags_dir, entry_id, 'enabled')

    create(flags_dir, entry_id, 'default')

    for eid, entry in config.entries.items():
        if entry.type == entry_type and eid != entry_id:
            if has(flags_dir, eid, 'default'):
                remove(flags_dir, eid, 'default')


# Filesystem helpers

def get_mount_uuid(mount_point: str) -> str:
    """Return filesystem UUID mounted at the specified path."""
    try:
        device = subprocess.run(
            [
                'findmnt',
                '-n',
                '-o',
                'SOURCE',
                mount_point,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        result = subprocess.run(
            [
                'blkid',
                '-s',
                'UUID',
                '-o',
                'value',
                device.stdout.strip(),
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        return result.stdout.strip()

    except subprocess.CalledProcessError:
        return ''


def run_command(cmd, desc=None):
    """Run external command and exit on failure."""
    if desc:
        print(desc)

    print(f"Running: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True, text=True)
    except subprocess.CalledProcessError as exc:
        print(
            f"Error: command failed: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1)