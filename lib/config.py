#!/usr/bin/env python3
# @file lib/config.py
"""
LPSS configuration file parser.

Reads and validates lpss.conf (INI-like format).
Provides read-only access to LPSS id, version, and entry definitions.
"""

import configparser
import os
import re
from typing import Dict, Optional


class LPSSConfigError(Exception):
    """Raised when the configuration is invalid."""


class EntryDef:
    """Immutable representation of a single entry from lpss.conf."""

    __slots__ = ('id', 'role', 'locator', 'linux', 'initrd', 'options')

    def __init__(self, entry_id: str, role: str, locator: str,
                 linux: str, initrd: str, options: str = ""):
        self.id = entry_id
        self.role = role
        self.locator = locator
        self.linux = linux
        self.initrd = initrd
        self.options = options

    def __repr__(self):
        return (f"EntryDef(id={self.id!r}, role={self.role!r}, "
                f"locator={self.locator!r}, linux={self.linux!r}, "
                f"initrd={self.initrd!r}, options={self.options!r})")


class LPSSConfig:
    """
    Parsed lpss.conf.

    Provides:
      - uuid: LPSS partition UUID (string)
      - version: configuration version (int)
      - entries: dict mapping entry_id -> EntryDef
    """

    def __init__(self, path: str):
        self._path = path
        self.uuid: str = ""
        self.version: int = 1
        self.entries: Dict[str, EntryDef] = {}
        self._parse()

    def _parse(self) -> None:
        if not os.path.isfile(self._path):
            raise LPSSConfigError(f"Configuration file not found: {self._path}")

        parser = configparser.ConfigParser()
        parser.read(self._path)

        # [lpss] section
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

        # Entry sections
        entry_pattern = re.compile(r'^entry\.(.+)$')
        for section_name in parser.sections():
            m = entry_pattern.match(section_name)
            if not m:
                continue
            entry_id = m.group(1)
            sect = parser[section_name]

            # Mandatory fields
            role = sect.get('role', 'root').strip()
            locator = sect.get('locator', '').strip()
            linux = sect.get('linux', '').strip()
            initrd = sect.get('initrd', '').strip()

            if not locator:
                raise LPSSConfigError(
                    f"Entry '{entry_id}' missing 'locator'")
            if not linux:
                raise LPSSConfigError(
                    f"Entry '{entry_id}' missing 'linux' kernel path")
            if not initrd:
                raise LPSSConfigError(
                    f"Entry '{entry_id}' missing 'initrd' path")

            options = sect.get('options', '').strip()

            self.entries[entry_id] = EntryDef(
                entry_id=entry_id,
                role=role,
                locator=locator,
                linux=linux,
                initrd=initrd,
                options=options,
            )

    def get_entry(self, entry_id: str) -> Optional[EntryDef]:
        """Return the EntryDef for a given id, or None."""
        return self.entries.get(entry_id)


def load_config(path: str) -> LPSSConfig:
    """Load and validate lpss.conf from a given path."""
    return LPSSConfig(path)


# Simple test when run directly
if __name__ == '__main__':
    import sys
    if len(sys.argv) != 2:
        print("Usage: config.py <path/to/lpss.conf>")
        sys.exit(1)
    try:
        cfg = load_config(sys.argv[1])
        print(f"LPSS UUID: {cfg.uuid}")
        print(f"Version: {cfg.version}")
        print("Entries:")
        for eid, entry in cfg.entries.items():
            print(f"  {eid}: role={entry.role}, locator={entry.locator}, "
                  f"linux={entry.linux}, initrd={entry.initrd}, "
                  f"options={entry.options}")
    except LPSSConfigError as e:
        print(f"Error: {e}")
        sys.exit(1)
