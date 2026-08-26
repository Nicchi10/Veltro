"""
Tests for the query layer and its CLI.

The contract that matters is BOUNDED output: an agent asks a question and gets
an answer proportional to the question, never the whole graph. That is the whole
token argument, so the slicing tests check what is left OUT as much as what is
kept in.

Run with:  python -m unittest discover tests
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.__main__ import main, normalise_argv
from veltro.parser import parse_text
from veltro.query import (edges_of, find_types, neighbourhood_ids, nodes_by_id,
                          resolve_one, slice_vel, sub_model)


GRAPH = """\
veltro 1

module app.core
class Session
user User
class User
name str

module app.web
class Controller
session Session
class Helper
note str

module other
class Helper
flag bool

rel
Controller depend Session
"""
# 'Helper' is deliberately declared twice: a bare 'Helper' cannot identify a type, which is what the ambiguity tests below are about. 
# Everything used in a relation is uniquely named, so those edges resolve.


class QueryFixture(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(GRAPH)


class TestFind(QueryFixture):

    def test_a_substring_matches_the_simple_name(self):
        found = find_types(self.model, "user")
        self.assertEqual([n["id"] for n in found], ["app.core.User"])

    def test_an_empty_pattern_matches_everything(self):
        self.assertEqual(len(find_types(self.model, "")), len(self.model["nodes"]))

    def test_a_module_filter_narrows_by_prefix(self):
        found = find_types(self.model, "", None, "app.web")
        self.assertEqual([n["name"] for n in found], ["Controller", "Helper"])

    def test_a_kind_filter_narrows_by_kind(self):
        self.assertEqual(find_types(self.model, "", "enum"), [])


class TestResolveOne(QueryFixture):

    def test_a_full_id_always_resolves(self):
        node, candidates = resolve_one(self.model, "other.Helper")
        self.assertEqual(node["id"], "other.Helper")
        self.assertEqual(candidates, [])

    def test_a_unique_simple_name_resolves(self):
        node, _candidates = resolve_one(self.model, "Controller")
        self.assertEqual(node["id"], "app.web.Controller")

    def test_an_ambiguous_name_reports_the_candidates_instead_of_guessing(self):
        node, candidates = resolve_one(self.model, "Helper")
        self.assertIsNone(node)
        self.assertEqual(sorted(n["id"] for n in candidates),["app.web.Helper", "other.Helper"])

    def test_an_unknown_name_resolves_to_nothing(self):
        node, candidates = resolve_one(self.model, "Nope")
        self.assertIsNone(node)
        self.assertEqual(candidates, [])


class TestNeighbourhood(QueryFixture):

    def test_depth_zero_is_just_the_type(self):
        self.assertEqual(neighbourhood_ids(self.model, "app.core.Session", 0),["app.core.Session"])

    def test_it_follows_relations_both_ways(self):
        # Session points at User (its field) and Controller points at Session and need both to understand it before changing it
        found = set(neighbourhood_ids(self.model, "app.core.Session", 1))
        self.assertIn("app.core.User", found)
        self.assertIn("app.web.Controller", found)
        self.assertNotIn("app.web.Helper", found)

    def test_depth_widens_the_circle(self):
        near = neighbourhood_ids(self.model, "app.core.User", 1)
        far = neighbourhood_ids(self.model, "app.core.User", 2)
        self.assertNotIn("app.web.Controller", near)
        self.assertIn("app.web.Controller", far)


class TestSlicing(QueryFixture):

    def test_a_slice_keeps_only_what_was_asked_for(self):
        sliced = sub_model(self.model, ["app.core.User"])
        self.assertEqual([n["id"] for n in sliced["nodes"]], ["app.core.User"])

    def test_a_slice_is_valid_vel_and_reparses(self):
        text = slice_vel(self.model, ["app.core.Session", "app.core.User"])
        reparsed = parse_text(text)
        self.assertEqual(sorted(n["id"] for n in reparsed["nodes"]),["app.core.Session", "app.core.User"])

    def test_a_slice_keeps_an_edge_leaving_it(self):
        # dropping it would amputate the type: you would not see that Controller depends on something at all
        sliced = sub_model(self.model, ["app.web.Controller"])
        kinds = [(e["from"], e["kind"], e["to"]) for e in sliced["edges"]]
        self.assertIn(("app.web.Controller", "depend", "app.core.Session"), kinds)

    def test_slicing_actually_costs_less(self):
        from veltro.export.vel import export_vel
        whole = export_vel(self.model)
        piece = slice_vel(self.model, ["app.core.User"])
        self.assertLess(len(piece), len(whole))


class TestEdgesOf(QueryFixture):

    def test_it_separates_the_two_directions(self):
        outgoing, incoming = edges_of(self.model, "app.core.Session")
        self.assertIn("app.core.User", [e["to"] for e in outgoing])
        self.assertIn("app.web.Controller", [e["from"] for e in incoming])


class TestNodesById(QueryFixture):

    def test_every_node_is_reachable_by_id(self):
        index = nodes_by_id(self.model)
        self.assertEqual(len(index), len(self.model["nodes"]))


class TestCommandLine(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.vel = os.path.join(self.directory, "graph.vel")
        with open(self.vel, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(GRAPH)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def run_cli(self, argv):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            code = main(argv)
        return code, buffer.getvalue()

    def test_the_bare_form_still_parses(self):
        # 'python -m veltro file.vel' predates the subcommands and must keep working
        self.assertEqual(normalise_argv([self.vel]), ["parse", self.vel])
        code, output = self.run_cli([self.vel])
        self.assertEqual(code, 0)
        self.assertIn("validation: OK", output)

    def test_a_subcommand_is_not_treated_as_a_file(self):
        self.assertEqual(normalise_argv(["find", "x.vel", "Foo"]), ["find", "x.vel", "Foo"])

    def test_find_prints_matching_ids(self):
        code, output = self.run_cli(["find", self.vel, "Controller"])
        self.assertEqual(code, 0)
        self.assertIn("app.web.Controller", output)

    def test_find_respects_the_limit(self):
        code, output = self.run_cli(["find", self.vel, "", "--limit", "2"])
        self.assertEqual(code, 0)
        self.assertIn("of 5 shown", output)

    def test_show_prints_the_type_as_vel(self):
        code, output = self.run_cli(["show", self.vel, "Controller"])
        self.assertEqual(code, 0)
        self.assertIn("class Controller", output)
        self.assertIn("session Session", output)

    def test_show_refuses_to_guess_an_ambiguous_name(self):
        code, output = self.run_cli(["show", self.vel, "Helper"])
        self.assertEqual(code, 1)
        self.assertIn("app.web.Helper", output)
        self.assertIn("other.Helper", output)

    def test_code_without_an_index_says_so_instead_of_failing_silently(self):
        code, output = self.run_cli(["show", self.vel, "Controller", "--code"])
        self.assertEqual(code, 1)
        self.assertIn("source index", output)

    def test_deps_lists_both_directions(self):
        code, output = self.run_cli(["deps", self.vel, "app.core.Session"])
        self.assertEqual(code, 0)
        self.assertIn("out (", output)
        self.assertIn("in (", output)

    def test_map_around_is_smaller_than_the_whole_graph(self):
        _code, whole = self.run_cli(["map", self.vel])
        _code, piece = self.run_cli(["map", self.vel, "--around", "app.core.User", "--depth", "0"])
        self.assertLess(len(piece), len(whole))
        self.assertIn("class User", piece)
        self.assertNotIn("class Helper", piece)


if __name__ == "__main__":
    unittest.main()
