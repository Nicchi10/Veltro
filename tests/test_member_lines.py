"""
Tests for the rule that tells a field from a method (SPEC 4).

A method is recognised by the '(' that OPENS AN ARGUMENT LIST, not by any '('.
Reading every parenthesis as a method turned real fields into malformed members
wherever a default value contained one: 72 lines across three of the shipped
examples, silently, for as long as those files had existed.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_member_line, parse_text

# The C# extractor is the [extract] extra: on a core install its one test skips
try:
    import tree_sitter
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False


class TestFieldVersusMethod(unittest.TestCase):

    def kind_of(self, line):
        member_kind, member = parse_member_line(line)
        return member_kind, member

    def test_a_plain_field(self):
        kind, member = self.kind_of("count int")
        self.assertEqual(kind, "field")
        self.assertEqual(member["type"], "int")

    def test_a_plain_method(self):
        kind, member = self.kind_of("run(ttl int) bool")
        self.assertEqual(kind, "method")
        self.assertEqual(member["ret"], "bool")

    def test_a_call_in_a_default_stays_a_field(self):
        # pydantic writes this, and it used to parse as a method called 'validators dict<str,int> = field'
        kind, member = self.kind_of("validators dict<str,int> = field(default_factory=dict)")
        self.assertEqual(kind, "field")
        self.assertEqual(member["name"], "validators")
        self.assertEqual(member["type"], "dict<str,int>")
        self.assertEqual(member["default"], "field(default_factory=dict)")

    def test_a_bracket_inside_a_string_default_stays_a_field(self):
        # Java constants in kafka and spring carry prose with brackets in it
        kind, member = self.kind_of('- $NOTE String = "see (section 2) for details"')
        self.assertEqual(kind, "field")
        self.assertEqual(member["vis"], "-")
        self.assertTrue(member["static"])
        self.assertEqual(member["default"], '"see (section 2) for details"')

    def test_a_method_with_a_default_in_its_arguments_is_still_a_method(self):
        # the '(' comes before the '=', which is what decides
        kind, member = self.kind_of("configure(retries int = 3)")
        self.assertEqual(kind, "method")

    def test_a_space_before_the_arguments_is_tolerated(self):
        kind, member = self.kind_of("Refresh (ttl int)")
        self.assertEqual(kind, "method")
        self.assertEqual(member["name"], "Refresh")

    def test_a_method_with_no_arguments(self):
        kind, _member = self.kind_of("- helper()")
        self.assertEqual(kind, "method")


class TestTypesWithSpaces(unittest.TestCase):
    """
    A space inside a type is harmless: a field's type is everything between the
    name and the '=', so it reads back as written. Python unions rely on this
    """

    def setUp(self):
        source = (
            "veltro 1\n"
            "module m\n"
            "class C\n"
            "path list<int | str>\n"
            "convert() list<str | int>\n"
            "make(a int | str, b int) Foo\n"
        )
        self.node = parse_text(source)["nodes"][0]

    def test_a_union_field_keeps_its_type(self):
        self.assertEqual(self.node["fields"][0]["type"], "list<int | str>")

    def test_a_union_return_type_survives(self):
        methods = {m["name"]: m for m in self.node["methods"]}
        self.assertEqual(methods["convert"]["ret"], "list<str | int>")

    def test_a_union_argument_survives(self):
        methods = {m["name"]: m for m in self.node["methods"]}
        self.assertEqual(methods["make"]["args"],[{"name": "a", "type": "int | str"}, {"name": "b", "type": "int"}])


class TestExtractorsRefuseUnwritableTypes(unittest.TestCase):

    @unittest.skipUnless(HAS_TREE_SITTER, "needs the [extract] extra (tree-sitter)")
    def test_csharp_named_tuple_becomes_any(self):
        # 'Task<(IConnectionMultiplexer Multiplexer,bool IsShared)>' cannot be written: the parenthesis is what tells a method from a field
        from veltro.extract.tree_sitter_csharp import safe_type
        self.assertEqual(safe_type("Task<(Foo a,bool b)>"), "Any")
        self.assertEqual(safe_type("Dictionary<string,object>"), "Dictionary<string,object>")

    def test_python_keeps_a_union_but_drops_a_parenthesis(self):
        from veltro.extract.python_ast import safe_type
        self.assertEqual(safe_type("list<int | str>"), "list<int | str>")
        self.assertEqual(safe_type("tuple<()>"), "Any")

    def test_python_drops_a_multi_line_default(self):
        from veltro.extract.python_ast import safe_default
        self.assertEqual(safe_default("field(\n  x=1)"), "")
        self.assertEqual(safe_default("field(x=1)"), "field(x=1)")


class TestTheShippedExamplesAreClean(unittest.TestCase):
    """
    A method whose NAME contains a space is impossible: it can only come from a
    line that was read as the wrong kind of member
    """

    def test_no_example_holds_a_malformed_member(self):
        import glob
        for path in sorted(glob.glob(os.path.join(REPO_ROOT, "examples", "*.vel"))):
            with open(path, encoding="utf-8") as handle:
                model = parse_text(handle.read())
            malformed = []
            for node in model["nodes"]:
                for method in node.get("methods", []):
                    if " " in method["name"]:
                        malformed.append(f"{node['id']}.{method['name']}")
            self.assertEqual(malformed, [], f"{os.path.basename(path)} holds malformed members")


if __name__ == "__main__":
    unittest.main()
