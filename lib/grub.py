#!/usr/bin/env python3
# @file lib/grub.py
"""
GRUB configuration generator for LPSS.

Produces a grub.cfg that supports:
- saved_entry / next_entry for trial boots
- Automatic boot (active+enabled, else first enabled)
- Individual entry menu items
"""

import textwrap
from typing import Dict, Set
from lib.config import LPSSConfig


def generate_grub_cfg(config: LPSSConfig, flags: Dict[str, Set[str]], output_path: str) -> None:
    """
    Generate LPSS grub.cfg from config and current flags.

    Parameters:
        config: parsed LPSSConfig object
        flags: dict mapping entry_id -> set of flag names (e.g. {'enabled', 'active'})
        output_path: path to write grub.cfg on the LPSS partition
    """
    entries = list(config.entries.values())  # preserves insertion order
    lpss_uuid = config.uuid

    # Helper to build search command from locator
    def make_search(locator: str) -> str:
        if locator.startswith("partlabel:"):
            label = locator.split(":", 1)[1]
            return f"search --part-label {label} --set=root"
        # Future locator types can be added here
        raise ValueError(f"Unsupported locator type: {locator}")

    # Generate entry boot blocks for automatic menu
    auto_blocks = []
    for entry in entries:
        search_cmd = make_search(entry.locator)
        kernel_params = f"{entry.options} lpss_uuid={lpss_uuid} lpss_entry={entry.id}"
        block = textwrap.dedent(f"""\
            if [ "${{chosen}}" = "{entry.id}" ]; then
                {search_cmd}
                linux {entry.linux} {kernel_params}
                initrd {entry.initrd}
                boot
            fi
        """)
        auto_blocks.append(block)

    # Build the full grub.cfg
    lines = []
    lines.append("# LPSS - generated grub.cfg\n")
    lines.append("set default=\"auto\"\n")
    lines.append("load_env\n")
    lines.append('if [ -n "${next_entry}" ]; then')
    lines.append('    set default="${next_entry}"')
    lines.append("    save_env next_entry")
    lines.append("    set next_entry=")
    lines.append("fi\n")

    # Automatic menu entry
    lines.append("menuentry \"Automatic\" --id=auto {")
    # Loop to find first active+enabled, then first enabled
    lines.append("    set chosen=\"\"")
    # First loop: active+enabled
    lines.append("    for entry in " + " ".join(e.id for e in entries) + "; do")
    lines.append("        if [ -f /flags/${entry}/active -a -f /flags/${entry}/enabled ]; then")
    lines.append("            set chosen=${entry}")
    lines.append("            break")
    lines.append("        fi")
    lines.append("    done")
    # Second loop: first enabled
    lines.append("    if [ -z \"${chosen}\" ]; then")
    lines.append("        for entry in " + " ".join(e.id for e in entries) + "; do")
    lines.append("            if [ -f /flags/${entry}/enabled ]; then")
    lines.append("                set chosen=${entry}")
    lines.append("                break")
    lines.append("            fi")
    lines.append("        done")
    lines.append("    fi")
    # Insert boot blocks
    for block in auto_blocks:
        lines.append(block)
    lines.append("}\n")

    # Individual menu entries for each registered entry
    for entry in entries:
        search_cmd = make_search(entry.locator)
        kernel_params = f"{entry.options} lpss_uuid={lpss_uuid} lpss_entry={entry.id} lpss_trial=1"
        lines.append(f"menuentry \"{entry.id}\" --id=entry_{entry.id} {{")
        lines.append(f"    {search_cmd}")
        lines.append(f"    linux {entry.linux} {kernel_params}")
        lines.append(f"    initrd {entry.initrd}")
        lines.append("}\n")

    # Write the file
    with open(output_path, 'w') as f:
        f.write("\n".join(lines) + "\n")