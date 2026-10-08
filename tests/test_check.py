"""
Tests for drift detection: is the '.vel' still true?

A stale '.vel' is the one failure a documentation format cannot afford, because
nothing about the file looks wrong - it validates, it queries, it slices, and it
answers questions about an architecture that no longer exists.

Two properties matter more than the diff itself:

- a freshly extracted '.vel' must report IN SYNC. A checker that cries drift on
  an untouched repository is one nobody leaves switched on, and the usual cause
  is ordering: two extractions may meet the files in a different order.
- when a language is present but unreadable, the answer is "I cannot judge",
  not "every type of that language was deleted". Those look identical to a
  diff and only one of them is true.

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

from veltro.__main__ import main
from veltro.diff import canonical_node, compare_models, describe, edge_keys
from veltro.parser import parse_text

BEFORE = """\
veltro 1

module app
class Session
user User
token str
class User
name str

rel
Session depend User
"""


def run_cli(arguments: list):
    out = io.StringIO()
    with redirect_stdout(out):
        code = main(arguments)
    return code, out.getvalue()


def build_repository(contents: str) -> str:
    """
    A throwaway Python repository with one module
    """
    root = tempfile.mkdtemp()
    os.makedirs(os.path.join(root, "src"))
    with open(os.path.join(root, "src", "app.py"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)
    return root


class TestComparingModels(unittest.TestCase):

    def test_a_model_against_itself_is_in_sync(self):
        model = parse_text(BEFORE)
        comparison = compare_models(model, model)
        self.assertTrue(comparison["in_sync"])
        self.assertEqual(describe(comparison), [])

    def test_member_order_is_not_a_change(self):
        swapped = BEFORE.replace("user User\ntoken str", "token str\nuser User")
        comparison = compare_models(parse_text(BEFORE), parse_text(swapped))
        self.assertTrue(comparison["in_sync"], describe(comparison))

    def test_declaration_order_is_not_a_change(self):
        reordered = """\
veltro 1

module app
class User
name str
class Session
user User
token str

rel
Session depend User
"""
        comparison = compare_models(parse_text(BEFORE), parse_text(reordered))
        self.assertTrue(comparison["in_sync"], describe(comparison))

    def test_a_deleted_type_is_removed(self):
        after = BEFORE.replace("class User\nname str\n", "").replace("Session depend User\n", "")
        comparison = compare_models(parse_text(BEFORE), parse_text(after))
        self.assertEqual(comparison["removed"], ["app.User"])
        self.assertEqual(comparison["added"], [])

    def test_a_new_type_is_added(self):
        after = BEFORE.replace("class User\n", "class Audit\nat str\nclass User\n")
        comparison = compare_models(parse_text(BEFORE), parse_text(after))
        self.assertEqual(comparison["added"], ["app.Audit"])

    def test_a_new_member_makes_the_type_changed(self):
        after = BEFORE.replace("token str", "token str\nexpires int")
        comparison = compare_models(parse_text(BEFORE), parse_text(after))
        self.assertEqual(comparison["changed"], ["app.Session"])
        self.assertEqual(comparison["removed"], [])

    def test_a_changed_type_is_named_in_the_report(self):
        after = BEFORE.replace("token str", "token bytes")
        lines = describe(compare_models(parse_text(BEFORE), parse_text(after)))
        self.assertTrue(any("app.Session" in line for line in lines))

    def test_a_dropped_relation_is_reported(self):
        after = BEFORE.replace("Session depend User\n", "")
        comparison = compare_models(parse_text(BEFORE), parse_text(after))
        self.assertEqual(comparison["edges_removed"], [("app.Session", "depend", "app.User")])

    def test_derived_edges_are_not_counted_as_relations(self):
        # 'user User' derives an association; it is already reported as the node's own change, and counting it twice would double every edit
        model = parse_text(BEFORE)
        for edge in edge_keys(model):
            self.assertEqual(edge[1], "depend")

    def test_the_report_truncates_long_lists(self):
        before = "veltro 1\n\nmodule app\n"
        after = before
        for number in range(12):
            before += f"class Gone{number}\na int\n"
        lines = describe(compare_models(parse_text(before), parse_text(after)), limit=3)
        self.assertTrue(any("and 9 more" in line for line in lines))


class TestCanonicalNode(unittest.TestCase):

    def test_two_nodes_with_reordered_members_are_equal(self):
        first = parse_text("veltro 1\nmodule a\nclass A\nx int\ny str\n")["nodes"][0]
        second = parse_text("veltro 1\nmodule a\nclass A\ny str\nx int\n")["nodes"][0]
        self.assertEqual(canonical_node(first), canonical_node(second))

    def test_a_different_type_is_not_equal(self):
        first = parse_text("veltro 1\nmodule a\nclass A\nx int\n")["nodes"][0]
        second = parse_text("veltro 1\nmodule a\nclass A\nx str\n")["nodes"][0]
        self.assertNotEqual(canonical_node(first), canonical_node(second))


class TestTheCommand(unittest.TestCase):

    def setUp(self):
        self.root = build_repository("class Session:\n    user: User\n    token: str\n\n\nclass User:\n    name: str\n")
        self.vel = os.path.join(self.root, "map.vel")
        code, _out = run_cli(["extract", self.root, "--out", self.vel])
        self.assertEqual(code, 0)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_a_fresh_extraction_is_in_sync(self):
        code, out = run_cli(["check", self.vel, self.root])
        self.assertEqual(code, 0, out)
        self.assertIn("in sync", out)

    def test_an_edited_repository_drifts(self):
        with open(os.path.join(self.root, "src", "app.py"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("class Session:\n    user: User\n    token: str\n    expires: int\n\n\nclass User:\n    name: str\n")
        code, out = run_cli(["check", self.vel, self.root])
        self.assertEqual(code, 1)
        self.assertIn("[DRIFT]", out)
        self.assertIn("declared differently", out)

    def test_a_deleted_file_drifts(self):
        os.remove(os.path.join(self.root, "src", "app.py"))
        code, out = run_cli(["check", self.vel, self.root])
        self.assertEqual(code, 1)
        self.assertIn("gone from the code", out)

    def test_a_missing_vel_is_reported_not_crashed(self):
        code, out = run_cli(["check", os.path.join(self.root, "nope.vel"), self.root])
        self.assertEqual(code, 1)
        self.assertIn("[ERROR]", out)

    def test_a_repository_that_is_not_a_directory_is_reported(self):
        code, out = run_cli(["check", self.vel, os.path.join(self.root, "nope")])
        self.assertEqual(code, 1)
        self.assertIn("[ERROR] - not a directory", out)

    def test_an_unreadable_language_refuses_to_judge(self):
        with open(os.path.join(self.root, "src", "Main.java"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("public class Main {}\n")
        code, out = run_cli(["check", self.vel, self.root])
        self.assertEqual(code, 1)
        self.assertIn("cannot judge drift", out)
        self.assertNotIn("[DRIFT]", out)
        # and it names the way out
        self.assertIn("--lang python", out)

    def test_naming_the_languages_judges_the_rest(self):
        with open(os.path.join(self.root, "src", "Main.java"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write("public class Main {}\n")
        code, out = run_cli(["check", self.vel, self.root, "--lang", "python"])
        self.assertEqual(code, 0, out)
        self.assertIn("in sync", out)


if __name__ == "__main__":
    unittest.main()
