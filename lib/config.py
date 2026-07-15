#!/usr/bin/env python3
# @file lib/config.py
"""
LPSS configuration file (lpss.conf) parser and writer.

Reads and writes lpss.conf (INI-like format).  Entries are kept in
insertion order.

initrd may be empty for configurations that do not use one.
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

        entry_pattern = re.compile(r'^entry\.(.+)$')
        for section_name in parser.sections():
            m = entry_pattern.match(section_name)
            if not m:
                continue
            entry_id = m.group(1)
            sect = parser[section_name]

            role = sect.get('role', 'root').strip()
            locator = sect.get('locator', '').strip()
            linux = sect.get('linux', '').strip()
            initrd = sect.get('initrd', '').strip()  # may be empty

            if not locator:
                raise LPSSConfigError(
                    f"Entry '{entry_id}' missing 'locator'")
            if not linux:
                raise LPSSConfigError(
                    f"Entry '{entry_id}' missing 'linux' kernel path")

            options = sect.get('options', '').strip()

            self.entries[entry_id] = EntryDef(
                entry_id=entry_id,
                role=role,
                locator=locator,
                linux=linux,
                initrd=initrd,
                options=options,
            )

    # ---- mutation --------------------------------------------------------

    def add_entry(self, entry_id: str, role: str, locator: str,
                  linux: str, initrd: str, options: str = "") -> None:
        """Add a new entry. Raises LPSSConfigError if id already exists."""
        if entry_id in self.entries:
            raise LPSSConfigError(f"Entry '{entry_id}' already exists")
        self.entries[entry_id] = EntryDef(
            entry_id=entry_id,
            role=role,
            locator=locator,
            linux=linux,
            initrd=initrd,
            options=options,
        )

    def update_entry(self, entry_id: str, role: str, locator: str,
                     linux: str, initrd: str, options: str = "") -> None:
        """Update an existing entry.  Creates it if not present."""
        self.entries[entry_id] = EntryDef(
            entry_id=entry_id,
            role=role,
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
            lines.append(f"[entry.{eid}]")
            lines.append(f"id={entry.id}")
            lines.append(f"role={entry.role}")
            lines.append(f"locator={entry.locator}")
            lines.append(f"linux={entry.linux}")
            if entry.initrd:                           # <-- вот это условие
                lines.append(f"initrd={entry.initrd}")
            if entry.options:
                lines.append(f"options={entry.options}")
            lines.append("")

        with open(path, 'w') as f:
            f.write("\n".join(lines).rstrip("\n") + "\n")

def load_config(path: str) -> LPSSConfig:
    """Load and validate lpss.conf from a given path."""
    return LPSSConfig(path)