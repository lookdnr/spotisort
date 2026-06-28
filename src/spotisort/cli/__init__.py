"""The command-line interface package.

This is the only layer permitted to use :func:`print`/:func:`input`.
"""

from __future__ import annotations

from spotisort.cli.app import Application, build_parser, main

__all__ = ["Application", "build_parser", "main"]
