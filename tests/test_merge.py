"""
Tests for merging duplicate type declarations into a single node.

A type can legitimately be declared more than once (C# 'partial class',
TypeScript interface merging, a module split across files). The parser must
fold those declarations into ONE node carrying every member, so a consumer
never sees a type with only part of its members.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text


PARTIAL = """\
veltro 1
module Orleans.Runtime
class Silo
- messageCenter MessageCenter
Start()
class Silo
- logger ILogger
Stop()
class MessageCenter
class ILogger
"""


class TestPartialDeclarationsMerge(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(PARTIAL)
        self.nodes = {node["id"]: node for node in self.model["nodes"]}

    def test_one_node_per_id(self):
        ids = [node["id"] for node in self.model["nodes"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids.count("Orleans.Runtime.Silo"), 1)

    def test_members_are_unioned(self):
        silo = self.nodes["Orleans.Runtime.Silo"]
        field_names = [f["name"] for f in silo["fields"]]
        method_names = [m["name"] for m in silo["methods"]]
        self.assertEqual(field_names, ["messageCenter", "logger"])
        self.assertEqual(method_names, ["Start", "Stop"])

    def test_association_from_a_later_fragment_is_derived(self):
        # 'logger' lives in the second fragment: before merging it was dropped, so the edge to ILogger did not exist at all
        derived = [e for e in self.model["edges"] if e.get("derived")]
        self.assertIn(
            {"from": "Orleans.Runtime.Silo", "kind": "assoc",
             "to": "Orleans.Runtime.ILogger", "derived": True},
            derived,
        )


class TestMergeKeepsItDeterministic(unittest.TestCase):

    def test_identical_members_collapse(self):
        # the same file linked into two projects: identical copies, not fragments
        source = (
            "veltro 1\n"
            "module M\n"
            "class Copy\n"
            "value int\n"
            "run()\n"
            "class Copy\n"
            "value int\n"
            "run()\n"
        )
        node = parse_text(source)["nodes"][0]
        self.assertEqual([f["name"] for f in node["fields"]], ["value"])
        self.assertEqual([m["name"] for m in node["methods"]], ["run"])

    def test_overloads_are_kept_apart(self):
        source = (
            "veltro 1\n"
            "module M\n"
            "class Server\n"
            "listen(port int)\n"
            "class Server\n"
            "listen(port int, host str)\n"
        )
        node = parse_text(source)["nodes"][0]
        self.assertEqual(len(node["methods"]), 2)

    def test_modifiers_and_docs_are_unioned(self):
        source = (
            "veltro 1\n"
            "module M\n"
            "> first half\n"
            "class abstract Widget\n"
            "a int\n"
            "> second half\n"
            "class Widget\n"
            "b int\n"
        )
        node = parse_text(source)["nodes"][0]
        self.assertEqual(node.get("modifiers"), ["abstract"])
        self.assertIn("first half", node["doc"])
        self.assertIn("second half", node["doc"])

    def test_enum_values_are_unioned(self):
        source = (
            "veltro 1\n"
            "module M\n"
            "enum Color = Red, Green\n"
            "enum Color = Green, Blue\n"
        )
        node = parse_text(source)["nodes"][0]
        self.assertEqual(node["values"], ["Red", "Green", "Blue"])

    def test_a_name_declared_twice_is_no_longer_ambiguous(self):
        # before merging, 'Silo' was carried by two nodes, so build_name_index refused to map the simple name and the rel row stayed unresolved
        source = (
            "veltro 1\n"
            "module M\n"
            "class Silo\n"
            "class Silo\n"
            "class Base\n"
            "\n"
            "rel\n"
            "Silo extend Base\n"
        )
        model = parse_text(source)
        written = [e for e in model["edges"] if not e.get("derived")]
        self.assertEqual(written, [{"from": "M.Silo", "kind": "extend", "to": "M.Base"}])


class TestDistinctTypesAreNotMerged(unittest.TestCase):

    def test_same_name_in_different_modules_stays_separate(self):
        source = (
            "veltro 1\n"
            "module A\n"
            "class Ping\n"
            "a int\n"
            "module B\n"
            "class Ping\n"
            "b int\n"
        )
        model = parse_text(source)
        ids = sorted(node["id"] for node in model["nodes"])
        self.assertEqual(ids, ["A.Ping", "B.Ping"])


if __name__ == "__main__":
    unittest.main()
