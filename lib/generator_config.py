#!/usr/bin/env python3
# @file lib/generator_config.py
"""
Loader for LPSS generator configuration.

Reads generator.conf from the LPSS directory and returns
generator-specific configuration sections.
"""

import configparser
from pathlib import Path


def load_generator_config(
    lpss_dir: str,
) -> dict[str, dict[str, str]]:
    """Load <lpss_dir>/generator.conf.

    Missing configuration file returns an empty dictionary.
    Invalid configuration raises configparser.Error.
    """
    config_path = Path(lpss_dir) / "generator.conf"

    if not config_path.is_file():
        return {}

    parser = configparser.ConfigParser()
    parser.read(config_path)

    return {
        section: dict(parser.items(section))
        for section in parser.sections()
    }


def get_generator_section(
    config: dict[str, dict[str, str]],
    name: str,
) -> dict[str, str]:
    """Return generator configuration section."""
    return config.get(name, {})