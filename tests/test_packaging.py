"""
Tests for what an installed 'veltro' actually contains.

Two promises are pinned here, and both are the kind that break silently:

- the schemas travel WITH the code. They used to sit at the repository root,
  which works from a checkout and produces a validator with no contract from a
  wheel. They now live in 'veltro/schemas/' and pyproject ships them.
- the core stays thin. Reading a '.vel' - parse, validate, query, slice, export -
  must cost one dependency ('jsonschema') and no more, because that is the
  promise the extras exist to keep. A new 'import requests' in parser.py would
  break it without breaking any other test.

Run with:  python -m unittest discover tests
"""

import ast
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.__main__ import load_schema, schema_path

PACKAGE_DIR = os.path.join(REPO_ROOT, "veltro")
SCHEMAS_DIR = os.path.join(PACKAGE_DIR, "schemas")

# The extractors that need a parser generator are an extra ('pip install veltro[extract]'), so they are allowed a dependency the core is not
EXTRA_MODULES = ("tree_sitter_csharp.py", "tree_sitter_typescript.py")

CORE_DEPENDENCIES = {"jsonschema"}


def core_source_files():
    """

    Every '.py' of the package that a core install has to be able to import.

    Returns:
        list[str]: absolute paths, the tree-sitter extractors left out

    """
    found = []
    for directory, _subdirs, files in os.walk(PACKAGE_DIR):
        if "__pycache__" in directory:
            continue
        for name in files:
            if not name.endswith(".py") or name in EXTRA_MODULES:
                continue
            found.append(os.path.join(directory, name))
    return found


def imported_root_modules(path: str):
    """

    The top-level module names a file imports, at any nesting depth.

    Function-level imports count: an 'import matplotlib' inside a function is
    still a dependency, it just fails later and with a worse message.

    Args:
        path (str): the '.py' file to read

    Returns:
        set[str]: the root of every imported module ('a.b.c' -> 'a')

    """
    with open(path, encoding="utf-8") as source_file:
        tree = ast.parse(source_file.read(), filename=path)

    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            # a relative import ('from . import x') has no module to name
            if node.level == 0 and node.module:
                roots.add(node.module.split(".")[0])
    return roots


class TestSchemasShipWithTheCode(unittest.TestCase):

    def test_both_schemas_are_inside_the_package(self):
        for name in ("model.schema.json", "index.schema.json"):
            self.assertTrue(os.path.exists(os.path.join(SCHEMAS_DIR, name)), f"{name} is not in veltro/schemas/")

    def test_schema_path_finds_the_packaged_copy(self):
        self.assertEqual(schema_path(), os.path.join(SCHEMAS_DIR, "model.schema.json"))

    def test_unknown_schema_is_not_invented(self):
        self.assertIsNone(schema_path("nope.schema.json"))

    def test_the_loaded_schema_is_the_type_graph_contract(self):
        schema = load_schema()
        self.assertIsNotNone(schema)
        self.assertIn("nodes", schema["properties"])
        self.assertIn("edges", schema["properties"])

    def test_pyproject_ships_them(self):
        with open(os.path.join(REPO_ROOT, "pyproject.toml"), encoding="utf-8") as pyproject_file:
            pyproject = pyproject_file.read()
        self.assertIn('veltro = ["schemas/*.json"]', pyproject)


class TestCoreStaysThin(unittest.TestCase):

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "needs Python 3.10+ to know what the stdlib is")
    def test_core_imports_nothing_but_the_stdlib_and_jsonschema(self):
        allowed = set(sys.stdlib_module_names) | CORE_DEPENDENCIES | {"veltro"}
        for path in core_source_files():
            extra = imported_root_modules(path) - allowed
            self.assertEqual(extra, set(), f"{os.path.relpath(path, REPO_ROOT)} imports {sorted(extra)}, which the core does not install")


if __name__ == "__main__":
    unittest.main()
