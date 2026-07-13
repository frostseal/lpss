#!/usr/bin/env python3
# @file lib/grub.py
"""
GRUB configuration generator for LPSS.

Produces a themed grub.cfg that uses only widely supported GRUB commands
(if, [ -f ]). Trial boot logic (load_env/save_env) is disabled by default
for maximum compatibility; enable with include_trial=True when the target
GRUB build supports envblk.

The generated config always begins by setting $root to the LPSS partition
via search --fs-uuid, so that flag file checks work reliably.

Automatically adds root= kernel parameter derived from the locator.
"""

from lib.config import LPSSConfig
from lib.utils import make_search_command


# ---- Templates ----------------------------------------------------------

HEADER = """\
# LPSS Boot Manager – generated grub.cfg
# Green Forest theme
set menu_color_normal=light-green/black
set menu_color_highlight=green/black
set timeout=10

search --fs-uuid {lpss_uuid} --set=root
set default="auto"
"""

TITLE_ENTRY = """\
menuentry "=== LPSS Boot Manager ===" --class lpss-title --unrestricted {
    true
}
"""

AUTO_HEADER = """\
menuentry "Automatic" --id=auto --class lpss-auto {
    set chosen=""
"""

CHECK_ACTIVE_ENABLED = """\
    if [ -z "${{chosen}}" ]; then
        if [ -f ($root)/flags/{entry_id}/active ]; then
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

AUTO_FOOTER = """\
    if [ -z "${chosen}" ]; then
        echo "No bootable LPSS entries configured."
    fi
}
"""

SLOT_ENTRY = """\
menuentry "{id}" --id=entry_{id} --class lpss-slot {{
    {search}
    linux {linux} {params}
    initrd {initrd}
}}
"""


# ---- helpers ------------------------------------------------------------

# Mapping from locator type to root= kernel parameter format
_ROOT_PARAM_MAP = {
    "label":     "root=LABEL={value}",
    "partlabel": "root=PARTLABEL={value}",
    "fsuuid":    "root=UUID={value}",
    "partuuid":  "root=PARTUUID={value}",
}


def _make_root_param(locator: str) -> str:
    """Derive a root= kernel parameter from a locator string."""
    try:
        kind, value = locator.split(":", 1)
    except ValueError:
        raise ValueError(f"Invalid locator format: {locator}")
    template = _ROOT_PARAM_MAP.get(kind)
    if template is None:
        raise ValueError(f"Unsupported locator type for root=: {kind}")
    return template.format(value=value)


def _kernel_params(entry, lpss_uuid: str, trial: bool = False) -> str:
    """Build the kernel command-line for a given entry."""
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
                      include_trial: bool = False) -> None:
    """
    Generate LPSS grub.cfg from config.

    Parameters:
        config: parsed LPSSConfig object
        output_path: path to write grub.cfg on the LPSS partition
        include_trial: if True, add load_env/save_env and next_entry logic
                       (requires GRUB with envblk module)
    """
    entries = list(config.entries.values())
    lpss_uuid = config.uuid

    cfg = HEADER.format(lpss_uuid=lpss_uuid)

    if include_trial:
        cfg += ("\nload_env\n"
                "if [ -n \"${next_entry}\" ]; then\n"
                "    set default=\"${next_entry}\"\n"
                "    set next_entry=\n"
                "    save_env next_entry\n"
                "fi\n")

    cfg += TITLE_ENTRY

    # Automatic entry
    auto = AUTO_HEADER
    for e in entries:
        auto += CHECK_ACTIVE_ENABLED.format(entry_id=e.id)
    for e in entries:
        auto += CHECK_ENABLED.format(entry_id=e.id)
    for e in entries:
        search_cmd = make_search_command(e.locator)
        params = _kernel_params(e, lpss_uuid, trial=False)
        auto += BOOT_BLOCK.format(entry_id=e.id, search=search_cmd,
                                  linux=e.linux, params=params,
                                  initrd=e.initrd)
    auto += AUTO_FOOTER
    cfg += auto

    # Individual slot entries
    for e in entries:
        search_cmd = make_search_command(e.locator)
        params = _kernel_params(e, lpss_uuid, trial=False)
        cfg += SLOT_ENTRY.format(id=e.id, search=search_cmd,
                                 linux=e.linux, params=params,
                                 initrd=e.initrd)

    with open(output_path, 'w') as f:
        f.write(cfg)