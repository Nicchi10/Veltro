"""
Tests for the PlantUML and Mermaid exporters.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text
from veltro.export.plantuml import export_plantuml
from veltro.export.mermaid import export_mermaid
from veltro.export.d2 import export_d2


SOURCE = """\
veltro 1
module M
enum Color = Red, Green
interface Shape
area() float
class Circle
radius float
items List<Point>
$make() Circle
class Point
x int

rel
Circle extend Shape
"""


class TestExporters(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(SOURCE)
        self.puml = export_plantuml(self.model)
        self.mmd = export_mermaid(self.model)
        self.d2 = export_d2(self.model)

    def test_plantuml_kinds(self):
        self.assertIn("enum Color {", self.puml)
        self.assertIn("interface Shape {", self.puml)
        self.assertIn("class Circle {", self.puml)

    def test_plantuml_members(self):
        self.assertIn("+ items : List<Point>", self.puml)
        self.assertIn("+ {static} make()", self.puml)

    def test_plantuml_written_edge_only(self):
        self.assertIn("Shape <|-- Circle", self.puml)
        # the Circle -> Point association is derived: it must NOT be an arrow
        self.assertNotIn("Circle --> Point", self.puml)

    def test_mermaid_kinds(self):
        self.assertIn("<<enumeration>>", self.mmd)
        self.assertIn("<<interface>>", self.mmd)

    def test_mermaid_groups_types_into_namespaces(self):
        # The module must appear so "which module is X in?" is answerable.
        self.assertIn("namespace M {", self.mmd)

    def test_plantuml_groups_types_into_packages(self):
        self.assertIn("package M {", self.puml)

    def test_d2_keys_carry_the_module(self):
        # The dotted id 'M.Circle' embeds the module so it stays answerable.
        self.assertIn("M.Circle: {", self.d2)
        self.assertIn("shape: class", self.d2)

    def test_d2_members_and_generics(self):
        self.assertIn("+items: List<Point>", self.d2)
        self.assertIn("+make(): Circle", self.d2)

    def test_d2_written_edge_only(self):
        self.assertIn("M.Circle -> M.Shape: extends", self.d2)
        # the Circle -> Point association is derived: it must NOT be an arrow
        self.assertNotIn("M.Circle -> M.Point", self.d2)

    def test_mermaid_generics_and_static(self):
        self.assertIn("List~Point~", self.mmd)        # angle brackets -> tilde
        self.assertIn("make() Circle$", self.mmd)     # static -> trailing $

    def test_mermaid_written_edge_only(self):
        self.assertIn("Shape <|-- Circle", self.mmd)
        self.assertNotIn("Circle --> Point", self.mmd)


if __name__ == "__main__":
    unittest.main()
