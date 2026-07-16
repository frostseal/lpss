#!/usr/bin/env python3
# @file lib/grub.py
"""
GRUB configuration generator for LPSS.

Generates a themed grub.cfg.  Menu structure:

    === LPSS Boot Manager ===
    Default boot
    ──────────────────────────
    Boot once: <entry-id>    (no trial flag)
    ──────────────────────────
    Try to switch to: <entry-id>   (trial, adds lpss_trial=1)
    ──────────────────────────
    Reboot
    UEFI Firmware Setup
"""

import sys
from lib.config import LPSSConfig
from lib.utils import make_search_command


# ---- Templates ----------------------------------------------------------

HEADER = """\
# LPSS Boot Manager – generated grub.cfg
# Green Forest theme
set menu_color_normal=green/black
set menu_color_highlight=black/green
set timeout=10

search --fs-uuid {lpss_uuid} --set=root
set default="default"
"""

TITLE_ENTRY = """\
menuentry "=-_ Linux Partition Slot System _-=" --class lpss-title --unrestricted {
    true
}
"""

DEFAULT_ENTRY = """\
menuentry "Default boot" --id=default --class lpss-default {
    set chosen=""
"""

CHECK_DEFAULT_ENABLED = """\
    if [ -z "${{chosen}}" ]; then
        if [ -f ($root)/flags/{entry_id}/default ]; then
            if [ -f ($root)/flags/{entry_id}/enabled ]; then
                set chosen={entry_id}
            fi
        fi
    fi
"""

CHECK_ENABLED = """\
    if [ -z "${{chosen}}" ]; then
        if [ -f ($root)/flags/{entry_id}/enabled ]; then
            set chosen={entry_id}
        fi
    fi
"""

BOOT_BLOCK = """\
    if [ "${{chosen}}" = "{entry_id}" ]; then
        {search}
        linux {linux} {params}
{initrd_line}\
        boot
    fi
"""

DEFAULT_FOOTER = """\
    if [ -z "${chosen}" ]; then
        echo "No bootable LPSS entries configured."
    fi
}
"""

BOOT_ONCE_ENTRY = """\
menuentry "Boot once: {id}" --id=once_{id} --class lpss-once {{
    {search}
    linux {linux} {params}
{initrd_line}\
}}
"""

TRIAL_ENTRY = """\
menuentry "Try to switch to: {id}" --id=entry_{id} --class lpss-trial {{
    {search}
    linux {linux} {params}
{initrd_line}\
}}
"""

SEPARATOR = """\
menuentry "──────────────────────────" --class lpss-sep --unrestricted {
    true
}
"""

REBOOT_ENTRY = """\
menuentry "Reboot" --class lpss-reboot {
    reboot
}
"""

UEFI_ENTRY = """\
menuentry "UEFI Firmware Setup" --class lpss-uefi {
    fwsetup
}
"""


# ---- helpers ------------------------------------------------------------

_ROOT_PARAM_MAP = {
    "label":     "root=LABEL={value}",
    "partlabel": "root=PARTLABEL={value}",
    "fsuuid":    "root=UUID={value}",
    "partuuid":  "root=PARTUUID={value}",
}


def _make_root_param(locator: str) -> str:
    try:
        kind, value = locator.split(":", 1)
    except ValueError:
        raise ValueError(f"Invalid locator format: {locator}")
    template = _ROOT_PARAM_MAP.get(kind)
    if template is None:
        raise ValueError(f"Unsupported locator type for root=: {kind}")
    return template.format(value=value)


def _kernel_params(entry, entry_id: str, lpss_uuid: str,
                   trial: bool = False) -> str:
    root_param = _make_root_param(entry.locator)
    params = [
        root_param,
        entry.options,
        f"lpss_uuid={lpss_uuid}",
        f"lpss_entry={entry_id}",
    ]
    if trial:
        params.append("lpss_trial=1")
    return " ".join(p for p in params if p)


def _initrd_line(entry) -> str:
    """Return a GRUB initrd command if the entry has an initrd, else empty."""
    if entry.initrd:
        return f"        initrd {entry.initrd}\n"
    return ""


# ---- public API ---------------------------------------------------------

def generate_grub_cfg(config: LPSSConfig,
                      output_path: str,
                      include_trial: bool = True) -> None:
    lpss_uuid = config.uuid

    # Separate entries by type
    root_entries = []
    other_entries = []
    for eid, entry in config.entries.items():
        if entry.type == 'root':
            root_entries.append((eid, entry))
        else:
            other_entries.append((eid, entry))

    # Warn about unsupported entry types
    for eid, entry in other_entries:
        print(f"Warning: entry '{eid}' has unsupported type "
              f"'{entry.type}', it will not appear in the GRUB menu.",
              file=sys.stderr)

    # ---- Build configuration --------------------------------------------
    cfg = HEADER.format(lpss_uuid=lpss_uuid)
    cfg += TITLE_ENTRY

    # Default boot (only root entries)
    if root_entries:
        dflt = DEFAULT_ENTRY
        for eid, entry in root_entries:
            dflt += CHECK_DEFAULT_ENABLED.format(entry_id=eid)
        for eid, entry in root_entries:
            dflt += CHECK_ENABLED.format(entry_id=eid)
        for eid, entry in root_entries:
            search_cmd = make_search_command(entry.locator)
            params = _kernel_params(entry, eid, lpss_uuid, trial=False)
            dflt += BOOT_BLOCK.format(entry_id=eid, search=search_cmd,
                                      linux=entry.linux, params=params,
                                      initrd_line=_initrd_line(entry))
        dflt += DEFAULT_FOOTER
        cfg += dflt
    else:
        cfg += 'menuentry "Default boot" { echo "No bootable entries configured." }\n'

    if root_entries:
        cfg += SEPARATOR

    # Boot once (currently only root, but designed for extension)
    for eid, entry in root_entries:
        search_cmd = make_search_command(entry.locator)
        params = _kernel_params(entry, eid, lpss_uuid, trial=False)
        cfg += BOOT_ONCE_ENTRY.format(id=eid, search=search_cmd,
                                      linux=entry.linux, params=params,
                                      initrd_line=_initrd_line(entry))

    if root_entries:
        cfg += SEPARATOR

    # Trial boot (only root)
    for eid, entry in root_entries:
        search_cmd = make_search_command(entry.locator)
        params = _kernel_params(entry, eid, lpss_uuid, trial=True)
        cfg += TRIAL_ENTRY.format(id=eid, search=search_cmd,
                                  linux=entry.linux, params=params,
                                  initrd_line=_initrd_line(entry))

    cfg += SEPARATOR
    cfg += REBOOT_ENTRY
    cfg += UEFI_ENTRY

    with open(output_path, 'w') as f:
        f.write(cfg)
