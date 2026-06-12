"""
Veltro: a token-frugal language that describes a codebase as a graph of types.

This package contains the parser that turns a '.vel' source file into the
intermediate type-graph model described by 'model.schema.json'.
"""

from veltro.parser import parse_text, parse_file

__all__ = ["parse_text", "parse_file"]
