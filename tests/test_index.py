"""
Tests for the sidecar source index: where each type of the model is declared.

The index is what turns the '.vel' from a map into a map WITH coordinates, and
it is kept out of the '.vel' so a 'file:line' never costs a token to read.

Run with:  python -m unittest discover tests
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.index import (add_location, index_path_for, new_index, posix_path,read_index, read_span, resolve_file, spans_of,write_index)
from veltro.extract.python_ast import extract_project
from veltro.parser import parse_text


class TestIndexPath(unittest.TestCase):

    def test_index_sits_next_to_the_vel(self):
        self.assertEqual(index_path_for("build/out.vel"), "build/out.index.json")

    def test_a_path_without_extension_still_gets_one(self):
        self.assertEqual(index_path_for("out"), "out.index.json")


class TestPosixPath(unittest.TestCase):

    def test_backslashes_become_slashes(self):
        # an index written on Windows must read the same everywhere
        self.assertEqual(posix_path("src\\models\\user.ts"), "src/models/user.ts")


class TestIndexBuilding(unittest.TestCase):

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.index = new_index(self.directory)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_paths_are_recorded_relative_to_the_root(self):
        add_location(self.index, "a.Foo", os.path.join(self.directory, "src", "a.py"), 3, 9)
        self.assertEqual(spans_of(self.index, "a.Foo"),[{"file": "src/a.py", "line": 3, "end_line": 9}])

    def test_a_type_declared_twice_keeps_both_places(self):
        # a C# 'partial class' is one node in the model and two places on disk
        add_location(self.index, "Demo.Silo", os.path.join(self.directory, "a.cs"), 2, 5)
        add_location(self.index, "Demo.Silo", os.path.join(self.directory, "b.cs"), 2, 6)
        spans = spans_of(self.index, "Demo.Silo")
        self.assertEqual([span["file"] for span in spans], ["a.cs", "b.cs"])

    def test_an_unknown_type_has_no_spans(self):
        self.assertEqual(spans_of(self.index, "nope.Missing"), [])

    def test_round_trip_through_disk_is_deterministic(self):
        add_location(self.index, "b.Second", os.path.join(self.directory, "b.py"), 1, 2)
        add_location(self.index, "a.First", os.path.join(self.directory, "a.py"), 1, 2)

        first_path = os.path.join(self.directory, "one.index.json")
        second_path = os.path.join(self.directory, "two.index.json")
        write_index(self.index, first_path)
        write_index(read_index(first_path), second_path)

        with open(first_path, encoding="utf-8") as handle:
            first = handle.read()
        with open(second_path, encoding="utf-8") as handle:
            second = handle.read()
        self.assertEqual(first, second)

        # ids are sorted, so the file is diffable rather than walk-order dependent
        written = json.loads(first)
        self.assertEqual(list(written["locations"]), ["a.First", "b.Second"])


class TestReadingTheSourceBack(unittest.TestCase):
    """
    The whole point of the index: going from a model id back to its code
    """

    def setUp(self):
        self.directory = tempfile.mkdtemp()
        self.package = os.path.join(self.directory, "pkg")
        os.makedirs(self.package)
        with open(os.path.join(self.package, "models.py"), "w", encoding="utf-8") as handle:
            handle.write(
                "CONSTANT = 1\n"
                "\n"
                "\n"
                "class User:\n"
                "    name: str\n"
                "    age: int\n"
                "\n"
                "\n"
                "class Session:\n"
                "    user: User\n"
            )
        self.vel, _stats, self.index = extract_project(self.package)

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_every_model_node_is_locatable(self):
        model = parse_text(self.vel)
        for node in model["nodes"]:
            self.assertTrue(spans_of(self.index, node["id"]), f"no location recorded for {node['id']}")

    def test_the_span_points_at_the_declaration(self):
        span = spans_of(self.index, "pkg.models.User")[0]
        self.assertEqual(span["file"], "pkg/models.py")
        self.assertEqual(span["line"], 4)

    def test_reading_a_span_returns_the_whole_type(self):
        span = spans_of(self.index, "pkg.models.User")[0]
        source = read_span(self.index, span)
        self.assertIn("class User:", source)
        self.assertIn("age: int", source)
        # and it stops there: the next type is not swept in
        self.assertNotIn("class Session", source)

    def test_resolve_file_can_be_rerooted(self):
        # the same index used against another checkout of the same code
        span = spans_of(self.index, "pkg.models.User")[0]
        moved = resolve_file(self.index, span, root="/elsewhere")
        self.assertEqual(posix_path(moved), "/elsewhere/pkg/models.py")


if __name__ == "__main__":
    unittest.main()
