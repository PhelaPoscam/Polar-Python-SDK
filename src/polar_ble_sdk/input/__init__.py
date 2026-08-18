"""Input package for non-blocking hotkey and experiment event marker polling."""

from .keyboard import (
    NonBlockingKeyboardReader,
    format_marker_legend,
    parse_marker_specs,
)

__all__ = [
    "NonBlockingKeyboardReader",
    "parse_marker_specs",
    "format_marker_legend",
]
