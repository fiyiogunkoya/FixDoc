#!/usr/bin/env python3
"""
FixDoc - Capture and search infrastructure fixes for cloud engineers.

This is the main entry point for the fixdoc CLI tool.
"""

import sys

from .cli import create_cli


def main():
    """Main entry point for fixdoc."""
    cli = create_cli()
    cli()


if __name__ == "__main__":
    sys.exit(main())
