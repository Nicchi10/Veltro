"""
Tests for the '.vel' exporter: model -> Veltro text.

Its contract is the round trip. SPEC design law 4 asks for one canonical
serialization per model, so parsing what we wrote must give back the model we
started from -- otherwise a slice handed to an LLM would quietly differ from the
architecture it claims to show.

Run with:  python -m unittest discover tests
"""

import json
import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.export.vel import export_vel, render_node
from veltro.parser import parse_text


# One fixture exercising every surface feature the SPEC defines.
EVERYTHING = """\
veltro 1

module Core.Models
> documents the session
class abstract Session
token str
- _secret str
# protected_note str
@ package_note str
$counter int = 0
expires int?
tags List<str>
+ module str
Refresh(ttl int)
- helper()
$Make(raw Dict<str,Any>) Session
Route(ILlmInvocation)
interface IValidator
Validate(value str) bool
enum Role = System, User, Assistant
class User
name str

module Other
class Widget
owner User

rel
Session impl IValidator
Widget depend Session
"""


def canonical(model: dict):
    """
    A model reduced to comparable facts, order-independent
    """
    nodes = []
    for node in model["nodes"]:
        nodes.append(json.dumps(node, sort_keys=True))
    edges = []
    for edge in model["edges"]:
        edges.append(json.dumps(edge, sort_keys=True))
    return sorted(nodes), sorted(edges)


class TestRoundTrip(unittest.TestCase):

    def test_every_feature_survives_a_round_trip(self):
        original = parse_text(EVERYTHING)
        reparsed = parse_text(export_vel(original))
        self.assertEqual(canonical(original), canonical(reparsed))

    def test_exporting_twice_is_stable(self):
        once = export_vel(parse_text(EVERYTHING))
        twice = export_vel(parse_text(once))
        self.assertEqual(once, twice)

    def test_a_real_example_survives_a_round_trip(self):
        path = os.path.join(REPO_ROOT, "examples", "nest.vel")
        with open(path, encoding="utf-8") as handle:
            original = parse_text(handle.read())
        reparsed = parse_text(export_vel(original))
        self.assertEqual(canonical(original), canonical(reparsed))


class TestCanonicalForm(unittest.TestCase):

    def setUp(self):
        self.text = export_vel(parse_text(EVERYTHING))

    def test_public_is_implicit(self):
        self.assertIn("\ntoken str\n", self.text)
        self.assertNotIn("+ token", self.text)

    def test_a_member_named_like_a_keyword_keeps_its_plus(self):
        # without the '+', 'module str' would read as a module declaration
        self.assertIn("+ module str", self.text)

    def test_markers_and_static_are_kept(self):
        self.assertIn("- _secret str", self.text)
        self.assertIn("# protected_note str", self.text)
        self.assertIn("@ package_note str", self.text)
        self.assertIn("$counter int = 0", self.text)

    def test_modifiers_come_before_the_name(self):
        self.assertIn("class abstract Session", self.text)

    def test_a_void_method_has_no_return_type(self):
        self.assertIn("\nRefresh(ttl int)\n", self.text)

    def test_a_type_only_argument_stays_type_only(self):
        self.assertIn("Route(ILlmInvocation)", self.text)

    def test_enums_stay_on_one_line(self):
        self.assertIn("enum Role = System, User, Assistant", self.text)

    def test_doc_lines_are_preserved(self):
        self.assertIn("> documents the session", self.text)

    def test_derived_associations_are_not_written(self):
        # 'owner User' already encodes it, so writing it would duplicate a fact the file carries and cost tokens (SPEC design law 2)
        self.assertNotIn("Widget assoc User", self.text)
        self.assertIn("Widget depend Session", self.text)

    def test_it_is_flat(self):
        for line in self.text.splitlines():
            self.assertEqual(line, line.lstrip(), "canonical form carries no indentation")


class TestRenderNode(unittest.TestCase):

    def test_one_node_renders_to_its_own_block(self):
        model = parse_text(EVERYTHING)
        node = {n["name"]: n for n in model["nodes"]}["IValidator"]
        self.assertEqual(render_node(node), ["interface IValidator", "Validate(value str) bool"])


class TestAmbiguousReferences(unittest.TestCase):

    def test_a_repeated_name_is_written_qualified(self):
        source = (
            "veltro 1\n"
            "module a\n"
            "class Ping\n"
            "module b\n"
            "class Ping\n"
            "class Base\n"
            "\n"
            "rel\n"
            "a.Ping extend Base\n"
            "b.Ping extend Base\n"
        )
        original = parse_text(source)
        text = export_vel(original)
        self.assertIn("a.Ping extend Base", text)
        self.assertIn("b.Ping extend Base", text)
        self.assertEqual(canonical(original), canonical(parse_text(text)))


if __name__ == "__main__":
    unittest.main()
