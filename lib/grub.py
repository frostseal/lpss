#!/usr/bin/env python3
# @file lib/grub.py
"""
GRUB configuration generator for LPSS.

Generates a themed grub.cfg with LPSS boot menu entries.
"""

import sys

from lib.config import LPSSConfig
from lib.generator_config import load_generator_config
from lib.utils import make_search_command

# Default values when generator.conf is absent or section is missing
_DEFAULT_GRUB_SETTINGS = {
    "timeout": "10",
    "menu_color_normal": "green/black",
    "menu_color_highlight": "black/green",
}

# GRUB configuration templates

HEADER = """\
# LPSS Boot Manager - generated grub.cfg
# Green Forest theme
set menu_color_normal={menu_color_normal}
set menu_color_highlight={menu_color_highlight}
set timeout={timeout}

search --fs-uuid {lpss_uuid} --set=root
load_env
if [ -n "${{next_entry}}" ]; then
    set default="${{next_entry}}"
    save_env next_entry
    set next_entry=
    save_env next_entry
else
    set default="default"
fi
"""

TITLE_ENTRY = """\
menuentry "=-_ Linux Partition Slot System _-=" \
--class lpss-title --unrestricted {
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
menuentry "Try to switch to: {id}" --id=entry_{id} \
--class lpss-trial {{
    {search}
    linux {linux} {params}
{initrd_line}\
}}
"""

SEPARATOR = """\
menuentry "--------------------------" \
--class lpss-sep --unrestricted {
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


# Kernel parameters

_ROOT_PARAM_MAP = {
    "label": "root=LABEL={value}",
    "partlabel": "root=PARTLABEL={value}",
    "fsuuid": "root=UUID={value}",
    "partuuid": "root=PARTUUID={value}",
}


def _make_root_param(locator: str) -> str:
    try:
        kind, value = locator.split(":", 1)
    except ValueError:
        raise ValueError(f"Invalid locator format: {locator}")

    template = _ROOT_PARAM_MAP.get(kind)
    if template is None:
        raise ValueError(
            f"Unsupported locator type for root=: {kind}"
        )

    return template.format(value=value)


def _kernel_params(entry, entry_id: str, lpss_uuid: str,
                   trial: bool = False) -> str:
    params = [
        _make_root_param(entry.locator),
        entry.options,
        f"lpss_uuid={lpss_uuid}",
        f"lpss_entry={entry_id}",
    ]

    if trial:
        params.append("lpss_trial=1")

    return " ".join(p for p in params if p)


def _initrd_line(entry) -> str:
    """Return GRUB initrd command when initrd exists."""
    if entry.initrd:
        return f"        initrd {entry.initrd}\n"

    return ""


# Public API

def generate_grub_cfg(config: LPSSConfig,
                      output_path: str,
                      include_trial: bool = True,
                      lpss_dir: str = None) -> None:
    """Generate grub.cfg from LPSS configuration.

    lpss_dir – path to LPSS partition; used to read generator.conf.
    If omitted, only default settings are applied.
    """

    lpss_uuid = config.uuid

    # Load generator settings for grub
    grub_settings = _DEFAULT_GRUB_SETTINGS.copy()
    if lpss_dir:
        gen_config = load_generator_config(lpss_dir)
        grub_settings.update(gen_config.get("grub", {}))

    root_entries = []
    other_entries = []

    for eid, entry in config.entries.items():
        if entry.type == "root":
            root_entries.append((eid, entry))
        else:
            other_entries.append((eid, entry))

    for eid, entry in other_entries:
        print(
            f"Warning: entry '{eid}' has unsupported type "
            f"'{entry.type}', it will not appear in the GRUB menu.",
            file=sys.stderr
        )

    cfg = HEADER.format(
        lpss_uuid=lpss_uuid,
        timeout=grub_settings["timeout"],
        menu_color_normal=grub_settings["menu_color_normal"],
        menu_color_highlight=grub_settings["menu_color_highlight"],
    )
    cfg += TITLE_ENTRY

    if root_entries:
        default_cfg = DEFAULT_ENTRY

        for eid, entry in root_entries:
            default_cfg += CHECK_DEFAULT_ENABLED.format(
                entry_id=eid
            )

        for eid, entry in root_entries:
            default_cfg += CHECK_ENABLED.format(
                entry_id=eid
            )

        for eid, entry in root_entries:
            default_cfg += BOOT_BLOCK.format(
                entry_id=eid,
                search=make_search_command(entry.locator),
                linux=entry.linux,
                params=_kernel_params(
                    entry, eid, lpss_uuid
                ),
                initrd_line=_initrd_line(entry)
            )

        default_cfg += DEFAULT_FOOTER
        cfg += default_cfg
    else:
        cfg += (
            'menuentry "Default boot" '
            '{ echo "No bootable entries configured." }\n'
        )

    if root_entries:
        cfg += SEPARATOR

    for eid, entry in root_entries:
        cfg += BOOT_ONCE_ENTRY.format(
            id=eid,
            search=make_search_command(entry.locator),
            linux=entry.linux,
            params=_kernel_params(
                entry, eid, lpss_uuid
            ),
            initrd_line=_initrd_line(entry)
        )

    if root_entries:
        cfg += SEPARATOR

    if include_trial:
        for eid, entry in root_entries:
            cfg += TRIAL_ENTRY.format(
                id=eid,
                search=make_search_command(entry.locator),
                linux=entry.linux,
                params=_kernel_params(
                    entry, eid, lpss_uuid, trial=True
                ),
                initrd_line=_initrd_line(entry)
            )

    cfg += SEPARATOR
    cfg += REBOOT_ENTRY
    cfg += UEFI_ENTRY

    with open(output_path, "w") as f:
        f.write(cfg)
