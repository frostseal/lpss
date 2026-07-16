#!/usr/bin/env python3
# @file lib/config.py
"""
LPSS configuration file (lpss.conf) parser and writer.

Reads and writes lpss.conf (INI-like format).  Entries are kept in
insertion order.

"""

import configparser
import os
import re
import sys
from typing import Dict, Optional


class LPSSConfigError(Exception):
    """Raised when the configuration is invalid."""


class EntryDef:
    """Immutable representation of a single entry from lpss.conf.

    The entry identifier is the key in LPSSConfig.entries dict.
    """

    __slots__ = ('type', 'locator', 'linux', 'initrd', 'options')

    def __init__(self, entry_type: str, locator: str = "",
                 linux: str = "", initrd: str = "", options: str = ""):
        self.type = entry_type
        self.locator = locator
        self.linux = linux
        self.initrd = initrd
        self.options = options

    def __repr__(self):
        return (f"EntryDef(type={self.type!r}, locator={self.locator!r}, "
                f"linux={self.linux!r}, initrd={self.initrd!r}, "
                f"options={self.options!r})")


class LPSSConfig:
    """
    Parsed lpss.conf.

    Provides:
      - uuid: LPSS partition UUID (string)
      - version: configuration version (int)
      - entries: dict mapping entry_id -> EntryDef  (insertion ordered)
    """

    def __init__(self, path: str = None):
        self.uuid: str = ""
        self.version: int = 1
        self.entries: Dict[str, EntryDef] = {}
        if path:
            self._parse(path)

    # ---- parsing ---------------------------------------------------------

    def _parse(self, path: str) -> None:
        if not os.path.isfile(path):
            raise LPSSConfigError(f"Configuration file not found: {path}")

        parser = configparser.ConfigParser()
        parser.read(path)

        if not parser.has_section('lpss'):
            raise LPSSConfigError("Missing [lpss] section in lpss.conf")

        lpss = parser['lpss']
        self.uuid = lpss.get('id', '').strip()
        if not self.uuid:
            raise LPSSConfigError("[lpss] section must contain 'id' (UUID)")

        try:
            self.version = int(lpss.get('version', '1'))
        except ValueError:
            raise LPSSConfigError("[lpss] version must be an integer")

        for section_name in parser.sections():
            if section_name == 'lpss' or section_name.startswith('entry.'):
                # skip old-style [entry.xxx] sections (no migration)
                if section_name.startswith('entry.'):
                    print(f"Warning: ignoring legacy section [{section_name}] "
                          f"in {path}", file=sys.stderr)
                continue
            entry_id = section_name
            sect = parser[section_name]

            entry_type = sect.get('type', '').strip()
            if not entry_type:
                print(f"Warning: missing 'type' in section [{entry_id}], "
                      f"skipping", file=sys.stderr)
                continue
            if entry_type not in ('root',):   # known types
                print(f"Warning: unknown entry type '{entry_type}' "
                      f"in section [{entry_id}]", file=sys.stderr)
                # still parse the entry, no strict rejection

            locator = sect.get('locator', '').strip()
            linux = sect.get('linux', '').strip()
            initrd = sect.get('initrd', '').strip()
            options = sect.get('options', '').strip()

            # Basic validation for managed root entries
            if entry_type == 'root':
                if not locator:
                    raise LPSSConfigError(
                        f"Entry '{entry_id}' (type=root) missing 'locator'")
                if not linux:
                    raise LPSSConfigError(
                        f"Entry '{entry_id}' (type=root) missing 'linux'")

            self.entries[entry_id] = EntryDef(
                entry_type=entry_type,
                locator=locator,
                linux=linux,
                initrd=initrd,
                options=options,
            )

    # ---- mutation --------------------------------------------------------

    def add_entry(self, entry_id: str, entry_type: str, locator: str = "",
                  linux: str = "", initrd: str = "",
                  options: str = "") -> None:
        """Add a new entry. Raises LPSSConfigError if id already exists."""
        if entry_id in self.entries:
            raise LPSSConfigError(f"Entry '{entry_id}' already exists")
        self.entries[entry_id] = EntryDef(
            entry_type=entry_type,
            locator=locator,
            linux=linux,
            initrd=initrd,
            options=options,
        )

    def update_entry(self, entry_id: str, entry_type: str, locator: str = "",
                     linux: str = "", initrd: str = "",
                     options: str = "") -> None:
        """Update an existing entry.  Creates it if not present."""
        self.entries[entry_id] = EntryDef(
            entry_type=entry_type,
            locator=locator,
            linux=linux,
            initrd=initrd,
            options=options,
        )

    # ---- serialization ---------------------------------------------------

    def save(self, path: str) -> None:
        """Write the configuration back to an INI file."""
        lines = []
        lines.append("[lpss]")
        lines.append(f"id={self.uuid}")
        lines.append(f"version={self.version}")
        lines.append("")

        for eid, entry in self.entries.items():
            lines.append(f"[{eid}]")
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

        with open(path, 'w') as f:
            f.write("\n".join(lines).rstrip("\n") + "\n")


def load_config(path: str) -> LPSSConfig:
    """Load and validate lpss.conf from a given path."""
    return LPSSConfig(path)
