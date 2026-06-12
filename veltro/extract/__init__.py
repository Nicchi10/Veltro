"""
Extractors: turn existing source code into Veltro '.vel' text.

Unlike an LLM, an AST extractor cannot invent types -- it only reports what is
literally in the syntax tree, so the failure mode is omission, never
hallucination.
"""

from veltro.extract.python_ast import extract_project, extract_to_vel

__all__ = ["extract_project", "extract_to_vel"]
