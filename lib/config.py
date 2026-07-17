#!/usr/bin/env python3
# @file lib/config.py
"""
LPSS configuration file (lpss.conf) parser and writer.

Reads and writes the INI-like lpss.conf format. Entries are kept in
insertion order.
"""

import configparser
import os
import sys
from typing import Dict


class LPSSConfigError(Exception):
    """Raised when the LPSS configuration is invalid."""


class EntryDef:
    """Representation of a single LPSS configuration entry.

    The entry identifier is used as a key in LPSSConfig.entries.
    """

    __slots__ = (
        'type',
        'locator',
        'linux',
        'initrd',
        'options',
    )

    def __init__(self, entry_type: str, locator: str = "",
                 linux: str = "", initrd: str = "",
                 options: str = ""):
        self.type = entry_type
        self.locator = locator
        self.linux = linux
        self.initrd = initrd
        self.options = options

    def __repr__(self):
        return (
            f"EntryDef(type={self.type!r}, "
            f"locator={self.locator!r}, "
            f"linux={self.linux!r}, "
            f"initrd={self.initrd!r}, "
            f"options={self.options!r})"
        )


class LPSSConfig:
    """Parsed LPSS configuration.

    Attributes:
        uuid: LPSS partition UUID.
        version: Configuration format version.
        entries: Mapping of entry id to EntryDef.
    """

    def __init__(self, path: str = None):
        self.uuid = ""
        self.version = 1
        self.entries: Dict[str, EntryDef] = {}

        if path:
            self._parse(path)

    def _parse(self, path: str) -> None:
        """Parse configuration from a file."""
        if not os.path.isfile(path):
            raise LPSSConfigError(
                f"Configuration file not found: {path}"
            )

        parser = configparser.ConfigParser()
        parser.read(path)

        if not parser.has_section('lpss'):
            raise LPSSConfigError(
                "Missing [lpss] section in lpss.conf"
            )

        section = parser['lpss']

        self.uuid = section.get('id', '').strip()

        if not self.uuid:
            raise LPSSConfigError(
                "[lpss] section must contain 'id' (UUID)"
            )

        try:
            self.version = int(section.get('version', '1'))
        except ValueError:
            raise LPSSConfigError(
                "[lpss] version must be an integer"
            )

        for section_name in parser.sections():
            if section_name == 'lpss':
                continue

            if section_name.startswith('entry.'):
                print(
                    f"Warning: ignoring legacy section "
                    f"[{section_name}] in {path}",
                    file=sys.stderr,
                )
                continue

            entry_id = section_name
            entry = parser[section_name]

            entry_type = entry.get('type', '').strip()

            if not entry_type:
                print(
                    f"Warning: missing 'type' in section "
                    f"[{entry_id}], skipping",
                    file=sys.stderr,
                )
                continue

            if entry_type not in ('root',):
                print(
                    f"Warning: unknown entry type '{entry_type}' "
                    f"in section [{entry_id}]",
                    file=sys.stderr,
                )

            locator = entry.get('locator', '').strip()
            linux = entry.get('linux', '').strip()
            initrd = entry.get('initrd', '').strip()
            options = entry.get('options', '').strip()

            if entry_type == 'root':
                if not locator:
                    raise LPSSConfigError(
                        f"Entry '{entry_id}' (type=root) "
                        "missing 'locator'"
                    )

                if not linux:
                    raise LPSSConfigError(
                        f"Entry '{entry_id}' (type=root) "
                        "missing 'linux'"
                    )

            self.entries[entry_id] = EntryDef(
                entry_type=entry_type,
                locator=locator,
                linux=linux,
                initrd=initrd,
                options=options,
            )

    def add_entry(self, entry_id: str, entry_type: str,
                  locator: str = "", linux: str = "",
                  initrd: str = "", options: str = "") -> None:
        """Add a new configuration entry."""
        if entry_id in self.entries:
            raise LPSSConfigError(
                f"Entry '{entry_id}' already exists"
            )

        self.entries[entry_id] = EntryDef(
            entry_type=entry_type,
            locator=locator,
            linux=linux,
            initrd=initrd,
            options=options,
        )

    def update_entry(self, entry_id: str, entry_type: str,
                     locator: str = "", linux: str = "",
                     initrd: str = "", options: str = "") -> None:
        """Update an existing entry or create a new one."""
        self.entries[entry_id] = EntryDef(
            entry_type=entry_type,
            locator=locator,
            linux=linux,
            initrd=initrd,
            options=options,
        )

    def save(self, path: str) -> None:
        """Write configuration to an INI file."""
        lines = [
            "[lpss]",
            f"id={self.uuid}",
            f"version={self.version}",
            "",
        ]

        for entry_id, entry in self.entries.items():
            lines.append(f"[{entry_id}]")
            lines.append(f"type={entry.type}")

            if entry.locator:
                lines.append(f"locator={entry.locator}")

            if entry.linux:
                lines.append(f"linux={entry.linux}")

            if entry.initrd:
                lines.append(f"initrd={entry.initrd}")

            if entry.options:
                lines.append(f"options={entry.options}")

            lines.append("")

        with open(path, 'w') as file:
            file.write("\n".join(lines).rstrip("\n") + "\n")


def load_config(path: str) -> LPSSConfig:
    """Load LPSS configuration from a file."""
    return LPSSConfig(path)