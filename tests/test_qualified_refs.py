"""
Tests for SPEC 6: a reference in the 'rel' block is the simple name when that
name is unique, and the module-qualified id otherwise.

Writing the bare name for a type declared in several modules leaves the row
unresolvable, so the relation is silently lost -- and two such rows are
textually identical, so one of them is dropped as a duplicate on top of that.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.python_ast import extract_project
from veltro.extract.tree_sitter_csharp import extract_to_vel as csharp_to_vel
from veltro.extract.tree_sitter_typescript import extract_to_vel as typescript_to_vel
from veltro.parser import parse_text


CSHARP_HOMONYMS = """\
namespace App.Alpha {
    public class Base {}
    public class Ping : Base {}
    public class Solo : Base {}
}
namespace App.Beta {
    public class Ping : Base {}
}
"""

TYPESCRIPT_HOMONYMS = """\
export namespace App.Alpha {
  export class Base {}
  export class Ping extends Base {}
  export class Solo extends Base {}
}
export namespace App.Beta {
  export class Ping extends Base {}
}
"""


class QualifiedReferenceChecks:
    """
    The assertions shared by every extractor: an ambiguous source is qualified,
    a unique one is not, and both homonyms keep their own relation
    """

    def assert_ambiguous_source_is_qualified(self, vel_text):
        self.assertIn("App.Alpha.Ping extend Base", vel_text)
        self.assertIn("App.Beta.Ping extend Base", vel_text)

    def assert_unique_source_stays_simple(self, vel_text):
        # token frugality: only the ambiguous minority pays for the qualifier
        self.assertIn("Solo extend Base", vel_text)
        self.assertNotIn("App.Alpha.Solo extend Base", vel_text)

    def assert_both_relations_resolve(self, vel_text):
        model = parse_text(vel_text)
        ids = {node["id"] for node in model["nodes"]}
        written = []
        for edge in model["edges"]:
            if not edge.get("derived"):
                written.append((edge["from"], edge["kind"], edge["to"]))
        self.assertIn(("App.Alpha.Ping", "extend", "App.Alpha.Base"), written)
        self.assertIn(("App.Beta.Ping", "extend", "App.Alpha.Base"), written)
        for from_id, _kind, to_id in written:
            self.assertIn(from_id, ids)
            self.assertIn(to_id, ids)


class TestCSharpQualifiesAmbiguousSource(unittest.TestCase, QualifiedReferenceChecks):

    def setUp(self):
        self.vel = csharp_to_vel(CSHARP_HOMONYMS)

    def test_ambiguous_source_is_qualified(self):
        self.assert_ambiguous_source_is_qualified(self.vel)

    def test_unique_source_stays_simple(self):
        self.assert_unique_source_stays_simple(self.vel)

    def test_both_relations_resolve(self):
        self.assert_both_relations_resolve(self.vel)


class TestTypeScriptQualifiesAmbiguousSource(unittest.TestCase, QualifiedReferenceChecks):

    def setUp(self):
        self.vel = typescript_to_vel(TYPESCRIPT_HOMONYMS, "ignored.module")

    def test_ambiguous_source_is_qualified(self):
        self.assert_ambiguous_source_is_qualified(self.vel)

    def test_unique_source_stays_simple(self):
        self.assert_unique_source_stays_simple(self.vel)

    def test_both_relations_resolve(self):
        self.assert_both_relations_resolve(self.vel)


class TestPythonQualifiesAmbiguousSource(unittest.TestCase):

    def setUp(self):
        import tempfile
        self.directory = tempfile.mkdtemp()
        package = os.path.join(self.directory, "pkg")
        os.makedirs(package)
        with open(os.path.join(package, "base.py"), "w", encoding="utf-8") as handle:
            handle.write("class Base:\n    pass\n")
        with open(os.path.join(package, "alpha.py"), "w", encoding="utf-8") as handle:
            handle.write("from .base import Base\n\n\nclass Ping(Base):\n    pass\n" "\n\nclass Solo(Base):\n    pass\n")
        with open(os.path.join(package, "beta.py"), "w", encoding="utf-8") as handle:
            handle.write("from .base import Base\n\n\nclass Ping(Base):\n    pass\n")
        self.vel, _stats = extract_project(package)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_ambiguous_source_is_qualified(self):
        self.assertIn("pkg.alpha.Ping extend Base", self.vel)
        self.assertIn("pkg.beta.Ping extend Base", self.vel)

    def test_unique_source_stays_simple(self):
        self.assertIn("Solo extend Base", self.vel)
        self.assertNotIn("pkg.alpha.Solo extend Base", self.vel)

    def test_both_relations_resolve(self):
        model = parse_text(self.vel)
        ids = {node["id"] for node in model["nodes"]}
        written = []
        for edge in model["edges"]:
            if not edge.get("derived"):
                written.append((edge["from"], edge["kind"], edge["to"]))
        self.assertIn(("pkg.alpha.Ping", "extend", "pkg.base.Base"), written)
        self.assertIn(("pkg.beta.Ping", "extend", "pkg.base.Base"), written)
        for from_id, _kind, to_id in written:
            self.assertIn(from_id, ids)
            self.assertIn(to_id, ids)


if __name__ == "__main__":
    unittest.main()
