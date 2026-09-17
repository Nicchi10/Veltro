"""
Tests for dependency edges derived from method signatures (issue #11).

Associations are derived from field types. A codebase that wires its
dependencies through constructor or method parameters holds no such field, so
that derivation finds nothing for it. The opt-in derivation reads argument and
return types instead and emits 'depend' edges.

The promises pinned here:

- it is OFF by default, because it changes the graph and therefore the ground
  truth of anything generated from it (the eval subjects, the leaderboard);
- it emits 'depend', never 'assoc', so "uses a" stays distinct from "holds a";
- a pair that already has an edge keeps it: a written row or a field says more
  than a signature does;
- it never invents an edge to a name that is not a type in the model.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text

# Service is wired only through its constructor and a setter, the Spring/NestJS shape
INJECTED = """\
veltro 1

module app
class Service
Service(repository Repository, clock Clock)
setLogger(logger Logger)
load(id int) Entity
class Repository
class Clock
class Logger
class Entity
"""


def edges_from(model: dict, from_id: str) -> list:
    """
    Every edge leaving one node, as (kind, to, derived) triples, sorted
    """
    found = []
    for edge in model["edges"]:
        if edge["from"] == from_id:
            found.append((edge["kind"], edge["to"], bool(edge.get("derived"))))
    return sorted(found)


class TestOffByDefault(unittest.TestCase):

    def test_a_signature_derives_nothing_unless_asked(self):
        model = parse_text(INJECTED)
        self.assertEqual(edges_from(model, "app.Service"), [])


class TestSignaturesBecomeDependencies(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(INJECTED, derive_signatures=True)
        self.edges = edges_from(self.model, "app.Service")

    def test_constructor_parameters_are_dependencies(self):
        self.assertIn(("depend", "app.Repository", True), self.edges)
        self.assertIn(("depend", "app.Clock", True), self.edges)

    def test_method_parameters_are_dependencies(self):
        self.assertIn(("depend", "app.Logger", True), self.edges)

    def test_return_types_are_dependencies(self):
        self.assertIn(("depend", "app.Entity", True), self.edges)

    def test_primitives_and_unknown_names_are_not_edges(self):
        targets = []
        for _kind, target, _derived in self.edges:
            targets.append(target)
        self.assertEqual(len(targets), 4)
        self.assertNotIn("int", targets)

    def test_nothing_is_ever_an_association(self):
        for kind, _target, _derived in self.edges:
            self.assertEqual(kind, "depend")


class TestExistingEdgesWin(unittest.TestCase):

    def test_a_field_keeps_its_association(self):
        source = (
            "veltro 1\n"
            "module app\n"
            "class Service\n"
            "repository Repository\n"
            "save(repository Repository)\n"
            "class Repository\n"
        )
        model = parse_text(source, derive_signatures=True)
        self.assertEqual(edges_from(model, "app.Service"), [("assoc", "app.Repository", True)])

    def test_a_written_row_is_not_duplicated(self):
        source = (
            "veltro 1\n"
            "module app\n"
            "class Handler\n"
            "handle(request Request)\n"
            "class Request\n"
            "rel\n"
            "Handler depend Request\n"
        )
        model = parse_text(source, derive_signatures=True)
        self.assertEqual(edges_from(model, "app.Handler"), [("depend", "app.Request", False)])

    def test_a_type_used_twice_is_one_edge(self):
        source = (
            "veltro 1\n"
            "module app\n"
            "class Service\n"
            "a(x Thing)\n"
            "b() Thing\n"
            "class Thing\n"
        )
        model = parse_text(source, derive_signatures=True)
        self.assertEqual(edges_from(model, "app.Service"), [("depend", "app.Thing", True)])

    def test_a_self_reference_is_not_an_edge(self):
        source = (
            "veltro 1\n"
            "module app\n"
            "class Builder\n"
            "with(name str) Builder\n"
        )
        model = parse_text(source, derive_signatures=True)
        self.assertEqual(edges_from(model, "app.Builder"), [])

    def test_generic_arguments_are_read_inside(self):
        source = (
            "veltro 1\n"
            "module app\n"
            "class Service\n"
            "all() List<Entity>\n"
            "class Entity\n"
        )
        model = parse_text(source, derive_signatures=True)
        self.assertEqual(edges_from(model, "app.Service"), [("depend", "app.Entity", True)])


class TestTheFileIsUnchanged(unittest.TestCase):
    """
    Derived edges are never written back, so the flag must not change what a
    slice or a re-export of the model looks like.
    """

    def test_rendering_ignores_the_derived_dependencies(self):
        from veltro.export.vel import export_vel
        plain = export_vel(parse_text(INJECTED))
        derived = export_vel(parse_text(INJECTED, derive_signatures=True))
        self.assertEqual(plain, derived)


if __name__ == "__main__":
    unittest.main()
