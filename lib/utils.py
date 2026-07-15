#!/usr/bin/env python3
# @file lib/utils.py
"""
Shared helper functions for LPSS tools.
"""
import os
import subprocess
import glob


# ---- GRUB directory detection -------------------------------------------

def get_grub_subdir(lpss_dir: str) -> str:
    """Return the GRUB subdirectory that exists ('grub2' or 'grub')."""
    for d in ('grub2', 'grub'):
        if os.path.isdir(os.path.join(lpss_dir, d)):
            return d
    return ''


# ---- GRUB tool discovery ------------------------------------------------

def find_grub_tool(name: str) -> str:
    """Locate a GRUB utility ('install', 'editenv', …)."""
    import shutil
    for candidate in [f'grub-{name}', f'grub2-{name}']:
        if shutil.which(candidate):
            return candidate
    return ''


# ---- Kernel command line helpers ----------------------------------------

def parse_cmdline(cmdline_path=None):
    """Parse kernel command line for LPSS parameters."""
    path = cmdline_path or os.environ.get('LPSS_CMDLINE_FILE', '/proc/cmdline')
    result = {'lpss_entry': None, 'lpss_trial': False}
    try:
        with open(path) as f:
            for param in f.read().split():
                if param == 'lpss_trial=1':
                    result['lpss_trial'] = True
                elif param.startswith('lpss_entry='):
                    result['lpss_entry'] = param.split('=', 1)[1]
    except FileNotFoundError:
        pass
    return result


# ---- grub.cfg validation ------------------------------------------------

def menu_entry_exists(grub_cfg_path: str, entry_id: str) -> bool:
    """Check whether a menu entry for the given id is present in grub.cfg."""
    if not os.path.exists(grub_cfg_path):
        return False
    with open(grub_cfg_path) as f:
        return f'--id=entry_{entry_id}' in f.read()


# ---- Kernel/initrd detection in a root filesystem -----------------------

_KERNEL_PATTERNS = [
    "vmlinuz-*", "vmlinuz", "linux-*", "linux",
    "bzImage-*", "bzImage", "kernel-*", "kernel",
]
_INITRD_PATTERNS = [
    "initramfs-{version}.img",
    "initrd-{version}.img",
    "initramfs-{version}",
    "initrd-{version}",
    "initrd.img-{version}",
    "initrd-{version}.gz",
]


def find_kernel_initrd_in_root(root_dir: str):
    """
    Locate the most recent kernel and matching initrd in root_dir/boot.

    Returns (relative_kernel_path, relative_initrd_path) or (None, None).
    """
    boot_dir = os.path.join(root_dir, 'boot')
    if not os.path.isdir(boot_dir):
        return None, None

    candidates = []
    for pattern in _KERNEL_PATTERNS:
        candidates.extend(glob.glob(os.path.join(boot_dir, pattern)))
    if not candidates:
        return None, None

    kernel = max(candidates, key=os.path.getmtime)
    base = os.path.basename(kernel)
    # try to extract version
    for prefix in ('vmlinuz-', 'linux-', 'bzImage-', 'kernel-'):
        if base.startswith(prefix):
            version = base[len(prefix):]
            break
    else:
        version = base

    initrd = None
    for pattern in _INITRD_PATTERNS:
        candidate = os.path.join(boot_dir, pattern.format(version=version))
        if os.path.exists(candidate):
            initrd = candidate
            break
    if not initrd:
        for name in os.listdir(boot_dir):
            if name.startswith('initr') and version in name:
                initrd = os.path.join(boot_dir, name)
                break

    linux_rel = os.path.relpath(kernel, root_dir) if kernel else None
    initrd_rel = os.path.relpath(initrd, root_dir) if initrd else None
    return linux_rel, initrd_rel


# ---- Host kernel/initrd discovery ---------------------------------------

def find_host_kernel(kver: str = None) -> str:
    """
    Find the current host kernel image.
    Returns absolute path or empty string if not found.
    """
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
    for pattern in [f'/boot/*vmlinuz*{kver}*', f'/boot/*kernel*{kver}*']:
        matches = sorted(glob.glob(pattern))
        if matches:
            return os.path.realpath(matches[0])
    return ''


def find_host_initrd(kver: str = None) -> str:
    """
    Find the current host initrd/initramfs image.
    Returns absolute path or empty string if not found.
    """
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
    for pattern in [f'/boot/*initr*{kver}*', f'/boot/*initramfs*{kver}*']:
        matches = sorted(glob.glob(pattern))
        if matches:
            return os.path.realpath(matches[0])
    return ''


# ---- Locator dispatch ---------------------------------------------------

_LOCATOR_DISPATCH = {
    "partlabel": "search --no-floppy --part-label {value} --set=root",
    "label":     "search --no-floppy --label {value} --set=root",
    "fsuuid":    "search --no-floppy --fs-uuid {value} --set=root",
}


def make_search_command(locator: str) -> str:
    """Translate a locator string into the corresponding GRUB command."""
    try:
        kind, value = locator.split(":", 1)
    except ValueError:
        raise ValueError(f"Invalid locator format: {locator}")
    template = _LOCATOR_DISPATCH.get(kind)
    if template is None:
        raise ValueError(f"Unsupported locator type: {kind}")
    return template.format(value=value)


def validate_locator(locator: str) -> None:
    """Raise ValueError if locator is not recognised."""
    make_search_command(locator)


# ---- Flag manipulation helpers ------------------------------------------

def activate_role(flags_dir, config, role, entry_id, *, create, remove, has):
    """Make *entry_id* the active entry for *role*."""
    if not has(flags_dir, entry_id, 'enabled'):
        create(flags_dir, entry_id, 'enabled')
    create(flags_dir, entry_id, 'active')
    for eid, entry in config.entries.items():
        if entry.role == role and eid != entry_id:
            if has(flags_dir, eid, 'active'):
                remove(flags_dir, eid, 'active')


# ---- Filesystem helpers -------------------------------------------------

def get_mount_uuid(mount_point: str) -> str:
    """Return the filesystem UUID of the device mounted at mount_point."""
    try:
        dev = subprocess.run(
            ['findmnt', '-n', '-o', 'SOURCE', mount_point],
            capture_output=True, text=True, check=True)
        uuid_out = subprocess.run(
            ['blkid', '-s', 'UUID', '-o', 'value', dev.stdout.strip()],
            capture_output=True, text=True, check=True)
        return uuid_out.stdout.strip()
    except subprocess.CalledProcessError:
        return ''