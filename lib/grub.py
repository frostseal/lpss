#!/usr/bin/env python3
# @file lib/grub.py
"""
GRUB configuration generator for LPSS.

Generates a themed grub.cfg with the following menu structure:

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
        initrd {initrd}
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
    initrd {initrd}
}}
"""

TRIAL_ENTRY = """\
menuentry "Try to switch to: {id}" --id=entry_{id} --class lpss-trial {{
    {search}
    linux {linux} {params}
    initrd {initrd}
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


def _kernel_params(entry, lpss_uuid: str, trial: bool = False) -> str:
    root_param = _make_root_param(entry.locator)
    params = [
        root_param,
        entry.options,
        f"lpss_uuid={lpss_uuid}",
        f"lpss_entry={entry.id}",
    ]
    if trial:
        params.append("lpss_trial=1")
    return " ".join(p for p in params if p)


# ---- public API ---------------------------------------------------------

def generate_grub_cfg(config: LPSSConfig,
                      output_path: str,
                      include_trial: bool = True) -> None:
    entries = list(config.entries.values())
    lpss_uuid = config.uuid

    cfg = HEADER.format(lpss_uuid=lpss_uuid)
    cfg += TITLE_ENTRY

    # Default boot
    dflt = DEFAULT_ENTRY
    for e in entries:
        dflt += CHECK_DEFAULT_ENABLED.format(entry_id=e.id)
    for e in entries:
        dflt += CHECK_ENABLED.format(entry_id=e.id)
    for e in entries:
        search_cmd = make_search_command(e.locator)
        params = _kernel_params(e, lpss_uuid, trial=False)
        dflt += BOOT_BLOCK.format(entry_id=e.id, search=search_cmd,
                                  linux=e.linux, params=params,
                                  initrd=e.initrd)
    dflt += DEFAULT_FOOTER
    cfg += dflt

    if entries:
        cfg += SEPARATOR

    # Boot once (no trial)
    for e in entries:
        search_cmd = make_search_command(e.locator)
        params = _kernel_params(e, lpss_uuid, trial=False)
        cfg += BOOT_ONCE_ENTRY.format(id=e.id, search=search_cmd,
                                      linux=e.linux, params=params,
                                      initrd=e.initrd)

    if entries:
        cfg += SEPARATOR

    # Try to switch to (trial)
    for e in entries:
        search_cmd = make_search_command(e.locator)
        params = _kernel_params(e, lpss_uuid, trial=True)
        cfg += TRIAL_ENTRY.format(id=e.id, search=search_cmd,
                                  linux=e.linux, params=params,
                                  initrd=e.initrd)

    cfg += SEPARATOR
    cfg += REBOOT_ENTRY
    cfg += UEFI_ENTRY

    with open(output_path, 'w') as f:
        f.write(cfg)