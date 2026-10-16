"""
Tests for eval/oracle.py: the ground truth read from the source.

The oracle exists so that a comparison against another tool is scored against
the CODE and not against Veltro's opinion of the code (eval/DESIGN.md, rule R1).
Two things are therefore pinned harder than the rest:

- the oracle must not learn anything from Veltro. A test reads its imports and
  fails if it ever reaches for the parser or an extractor. Nothing else would
  catch that: borrowing Veltro's answer would make every test here pass and the
  experiment meaningless.
- the semantic decisions in the module docstring are facts only because they are
  written down. Each one has a test, so a later "improvement" that quietly
  redefines what a public method is has to argue with a failing test first.

Run with:  python -m unittest discover tests
"""

import ast
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.oracle import (MODULE_SCOPE, SUBJECTS_BY_FAMILY, annotated_fields,
                         base_names, build_questions, build_symbol_table,
                         collection_field_names, first_argument, head_of,
                         is_collection, is_property, main, parameter_names,
                         public_first, public_method_names, summarise,
                         unique_names, unwrap_annotation)

ORACLE_PATH = os.path.join(REPO_ROOT, "eval", "oracle.py")


def parse_class(source: str):
    """
    The first class in a snippet
    """
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef):
            return node
    raise AssertionError("the snippet declares no class")


def parse_function(source: str):
    """
    The first function in a snippet
    """
    for node in ast.parse(source).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return node
    raise AssertionError("the snippet declares no function")


def build_tree(files: dict) -> str:
    """
    A throwaway repository, {relative path: content}
    """
    root = tempfile.mkdtemp()
    for relative in files:
        path = os.path.join(root, relative.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(files[relative])
    return root


class TestTheOracleStaysIndependent(unittest.TestCase):

    def test_it_never_imports_the_parser_or_an_extractor(self):
        # R1: truth comes from the source. Borrowing Veltro's answer would make every other test here pass while the experiment measured nothing
        with open(ORACLE_PATH, encoding="utf-8") as oracle_file:
            tree = ast.parse(oracle_file.read())

        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)

        from_veltro = [name for name in imported if name == "veltro" or name.startswith("veltro.")]
        # the file walk is the one allowed exception: every subject must see the same files, or the experiment measures the walk instead of the formats
        self.assertEqual(from_veltro, ["veltro.extract.walk"], from_veltro)


class TestAnnotations(unittest.TestCase):

    def test_the_head_is_what_it_is_not_what_it_holds(self):
        self.assertEqual(head_of("typing.List[int]"), "List")
        self.assertEqual(head_of("int"), "int")

    def test_a_transparent_wrapper_comes_off(self):
        self.assertEqual(unwrap_annotation("Optional[List[int]]"), "List[int]")
        self.assertEqual(unwrap_annotation("ClassVar[int]"), "int")

    def test_annotated_keeps_only_its_first_argument(self):
        self.assertEqual(unwrap_annotation("Annotated[List[int], Field(gt=0)]"), "List[int]")

    def test_a_top_level_comma_splits_but_a_nested_one_does_not(self):
        self.assertEqual(first_argument("Dict[str, int], Field(gt=0)"), "Dict[str, int]")

    def test_optional_of_a_scalar_is_not_a_collection(self):
        # the trap this function exists for: 'Optional[int]' has a '[' and holds nothing
        self.assertFalse(is_collection("Optional[int]"))

    def test_optional_of_a_collection_is_one(self):
        self.assertTrue(is_collection("Optional[List[int]]"))

    def test_a_bare_builtin_container_counts(self):
        self.assertTrue(is_collection("list"))
        self.assertTrue(is_collection("dict"))

    def test_a_scalar_is_not_a_collection(self):
        self.assertFalse(is_collection("int"))
        self.assertFalse(is_collection("str"))
        self.assertFalse(is_collection(""))

    def test_a_union_is_a_collection_when_a_branch_is(self):
        self.assertTrue(is_collection("Union[List[int], None]"))
        self.assertFalse(is_collection("Union[int, str]"))

    def test_the_pep_604_union_is_read_too(self):
        self.assertTrue(is_collection("list[int] | None"))
        self.assertFalse(is_collection("int | None"))


class TestDeclarations(unittest.TestCase):

    def test_object_is_not_an_inherited_base(self):
        self.assertEqual(base_names(parse_class("class A(object):\n    pass\n")), [])

    def test_a_subscripted_base_is_reduced_to_its_head(self):
        self.assertEqual(base_names(parse_class("class A(Generic[T]):\n    pass\n")), ["Generic"])

    def test_a_qualified_base_keeps_its_simple_name(self):
        self.assertEqual(base_names(parse_class("class A(pydantic.BaseModel):\n    pass\n")), ["BaseModel"])

    def test_a_dunder_is_not_a_public_method(self):
        # whether '__init__' is "public" has no agreed answer, so it is excluded rather than argued about (see the oracle's docstring)
        source = "class A:\n    def __init__(self):\n        pass\n    def run(self):\n        pass\n"
        self.assertEqual(public_method_names(parse_class(source)), ["run"])

    def test_an_underscore_method_is_not_public(self):
        source = "class A:\n    def _helper(self):\n        pass\n    def run(self):\n        pass\n"
        self.assertEqual(public_method_names(parse_class(source)), ["run"])

    def test_static_and_class_methods_are_methods(self):
        source = ("class A:\n"
                  "    @staticmethod\n    def make():\n        pass\n"
                  "    @classmethod\n    def build(cls):\n        pass\n")
        self.assertEqual(public_method_names(parse_class(source)), ["build", "make"])

    def test_a_property_is_a_field_not_a_method(self):
        source = "class A:\n    @property\n    def tags(self) -> list:\n        return []\n"
        self.assertEqual(public_method_names(parse_class(source)), [])
        self.assertEqual(annotated_fields(parse_class(source)), [("tags", "list")])

    def test_a_setter_is_not_counted_as_a_method_either(self):
        source = ("class A:\n"
                  "    @property\n    def tag(self) -> str:\n        return ''\n"
                  "    @tag.setter\n    def tag(self, value):\n        pass\n")
        self.assertEqual(public_method_names(parse_class(source)), [])

    def test_a_cached_property_is_a_field(self):
        source = "class A:\n    @cached_property\n    def rows(self) -> list:\n        return []\n"
        self.assertTrue(is_property(parse_class(source).body[0]))

    def test_only_annotated_attributes_are_fields(self):
        source = "class A:\n    typed: int = 1\n    untyped = 2\n"
        self.assertEqual(annotated_fields(parse_class(source)), [("typed", "int")])

    def test_collection_fields_skip_the_private_ones(self):
        source = "class A:\n    tags: list\n    _cache: dict\n    name: str\n"
        self.assertEqual(collection_field_names(parse_class(source)), ["tags"])

    def test_parameters_keep_their_order_and_their_stars(self):
        source = "def f(a, /, b, *extra, c, **rest):\n    pass\n"
        self.assertEqual(parameter_names(parse_function(source)), ["a", "b", "*extra", "c", "**rest"])


class TestTheSymbolTable(unittest.TestCase):

    def setUp(self):
        self.root = build_tree({
            "pkg/models.py": (
                "class Base:\n"
                "    def run(self):\n        pass\n"
                "\n\n"
                "class Session(Base):\n"
                "    tags: list\n"
                "    name: str\n"
                "    def refresh(self):\n        pass\n"
                "    def _hidden(self):\n        pass\n"
                "\n\n"
                "class Outer:\n"
                "    class Inner:\n        pass\n"
            ),
            "pkg/util.py": (
                "def normalise(path, encoding):\n"
                "    return path\n"
                "\n\n"
                "def load(path):\n"
                "    return normalise(path, 'utf-8')\n"
            ),
        })
        self.table, self.calls = build_symbol_table(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_top_level_declarations_are_recorded(self):
        self.assertEqual(sorted(self.table["classes"]), ["Base", "Outer", "Session"])
        self.assertEqual(sorted(self.table["functions"]), ["load", "normalise"])

    def test_a_nested_class_is_counted_but_not_recorded(self):
        self.assertEqual(self.table["nested_classes"], 1)
        self.assertNotIn("Inner", self.table["classes"])

    def test_a_file_is_recorded_with_posix_separators(self):
        self.assertEqual(self.table["classes"]["Session"][0]["file"], "pkg/models.py")

    def test_a_call_is_attributed_to_the_function_it_sits_in(self):
        self.assertEqual(self.calls["normalise"], {"load"})

    def test_a_decorator_is_not_a_call_made_by_what_it_decorates(self):
        # found on jsonschema: '_checks_drafts' came back "called by" the twenty functions it decorates, which is a false fact in the ground truth
        root = build_tree({
            "a.py": (
                "def checks(name):\n"
                "    return name\n"
                "\n\n"
                "@checks('date')\n"
                "def is_date(value):\n"
                "    return True\n"
            ),
        })
        try:
            _table, calls = build_symbol_table(root)
            self.assertNotIn("is_date", calls.get("checks", set()))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_file_level_call_site_is_not_a_function(self):
        root = build_tree({"a.py": "def make():\n    return 1\n\n\nVALUE = make()\n"})
        try:
            _table, calls = build_symbol_table(root)
            self.assertEqual(calls["make"], {MODULE_SCOPE})
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_an_unparsable_file_is_skipped_not_crashed(self):
        root = build_tree({"pkg/broken.py": "class :::\n", "pkg/ok.py": "class A:\n    pass\n"})
        try:
            table, _calls = build_symbol_table(root)
            self.assertEqual(sorted(table["classes"]), ["A"])
            self.assertEqual(table["files"], 1)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestUniqueness(unittest.TestCase):

    def test_a_name_declared_twice_is_never_asked_about(self):
        root = build_tree({
            "a.py": "class Ping:\n    pass\n",
            "b.py": "class Ping:\n    pass\n",
            "c.py": "class Once:\n    pass\n",
        })
        try:
            table, _calls = build_symbol_table(root)
            self.assertEqual(unique_names(table)["classes"], ["Once"])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_public_names_are_sampled_before_private_ones(self):
        # '_' sorts before every letter, so taking the first N alphabetically put every function question on a private helper
        # which would have read as the summarising formats answering badly
        self.assertEqual(public_first(["_hidden", "_other", "run", "save"]),
                         ["run", "save", "_hidden", "_other"])

    def test_a_name_that_is_both_a_class_and_a_function_is_dropped(self):
        root = build_tree({
            "a.py": "class Thing:\n    pass\n",
            "b.py": "def Thing():\n    pass\n",
        })
        try:
            table, _calls = build_symbol_table(root)
            unique = unique_names(table)
            self.assertEqual(unique["classes"], [])
            self.assertEqual(unique["functions"], [])
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestTheQuestions(unittest.TestCase):

    def setUp(self):
        self.root = build_tree({
            "pkg/models.py": (
                "class Base:\n"
                "    def run(self):\n        pass\n"
                "\n\n"
                "class Session(Base):\n"
                "    tags: list\n"
                "    name: str\n"
                "    def refresh(self):\n        pass\n"
                "    def __init__(self):\n        pass\n"
            ),
            "pkg/util.py": (
                "def normalise(path, encoding):\n"
                "    return path\n"
                "\n\n"
                "def load(path):\n"
                "    return normalise(path, 'utf-8')\n"
            ),
        })
        table, calls = build_symbol_table(self.root)
        self.questions = build_questions(table, calls, limit=10)
        self.by_subject = {}
        for question in self.questions:
            self.by_subject.setdefault(question["type"], {})[question["subject"]] = question

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def answer(self, family: str, subject: str):
        return self.by_subject[family][subject]["answer"]

    def test_inheritance_is_read_from_the_source(self):
        self.assertEqual(self.answer("inherits", "Session"), ["Base"])

    def test_implementors_are_found_across_the_repository(self):
        self.assertEqual(self.answer("implementors", "Base"), ["Session"])

    def test_the_file_is_the_one_that_declares_it(self):
        self.assertEqual(self.answer("defined_in", "Session"), "pkg/models.py")

    def test_the_method_count_excludes_the_constructor(self):
        self.assertEqual(self.answer("members", "Session"), 1)

    def test_collection_fields_are_named(self):
        self.assertEqual(self.answer("field_types", "Session"), ["tags"])

    def test_functions_are_asked_about_too(self):
        # rule R2: a tool that models only types scores zero here instead of never being asked, which is the point of the family
        self.assertEqual(self.answer("function_params", "normalise"), ["path", "encoding"])

    def test_callers_are_asked_about(self):
        self.assertEqual(self.answer("callers", "normalise"), ["load"])

    def test_a_function_only_called_at_file_level_is_not_asked_about(self):
        root = build_tree({"a.py": "def make():\n    return 1\n\n\nVALUE = make()\n"})
        try:
            table, calls = build_symbol_table(root)
            questions = build_questions(table, calls, limit=10)
            self.assertNotIn("callers", summarise(questions))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_every_question_declares_which_subjects_can_answer_it(self):
        for question in self.questions:
            self.assertIn(question["type"], SUBJECTS_BY_FAMILY)
            self.assertEqual(question["expressible_in"], list(SUBJECTS_BY_FAMILY[question["type"]]))

    def test_veltro_is_not_among_the_subjects_for_the_blind_spot_families(self):
        # if this ever flips, either Veltro grew function nodes or someone made the comparison easier on it
        self.assertNotIn("veltro", SUBJECTS_BY_FAMILY["function_params"])
        self.assertNotIn("veltro", SUBJECTS_BY_FAMILY["callers"])

    def test_a_class_with_no_methods_is_not_asked_how_many_it_has(self):
        # the answer would be 0, which a subject can get right by reading nothing
        root = build_tree({"a.py": "class Bare:\n    name: str\n"})
        try:
            table, calls = build_symbol_table(root)
            questions = build_questions(table, calls, limit=10)
            self.assertNotIn("members", summarise(questions))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_class_with_no_annotated_fields_is_not_asked_about_field_types(self):
        root = build_tree({"a.py": "class Bare:\n    def run(self):\n        pass\n"})
        try:
            table, calls = build_symbol_table(root)
            questions = build_questions(table, calls, limit=10)
            self.assertNotIn("field_types", summarise(questions))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_a_class_whose_methods_are_all_dunders_still_counts(self):
        # answering 0 here means reading the class and judging its members, so it discriminates and is kept
        root = build_tree({"a.py": "class Tree:\n    def __init__(self):\n        pass\n"})
        try:
            table, calls = build_symbol_table(root)
            questions = build_questions(table, calls, limit=10)
            members = [question for question in questions if question["type"] == "members"]
            self.assertEqual([question["answer"] for question in members], [0])
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_ids_are_unique_and_dense(self):
        ids = [question["id"] for question in self.questions]
        self.assertEqual(ids, list(range(1, len(ids) + 1)))

    def test_the_limit_is_per_family(self):
        root = build_tree({"big.py": "".join(f"def f{number}(a):\n    pass\n" for number in range(30))})
        try:
            table, calls = build_symbol_table(root)
            questions = build_questions(table, calls, limit=4)
            self.assertEqual(summarise(questions)["function_params"], 4)
        finally:
            shutil.rmtree(root, ignore_errors=True)


class TestTheCommandLine(unittest.TestCase):

    def setUp(self):
        self.root = build_tree({"pkg/models.py": "class Base:\n    pass\n\n\nclass A(Base):\n    tags: list\n"})
        self.out = os.path.join(self.root, "questions.json")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_cli(self, arguments: list) -> int:
        """
        Run the oracle's CLI with its report captured
        """
        with redirect_stdout(io.StringIO()):
            return main(arguments)

    def test_it_writes_a_question_file(self):
        self.assertEqual(self.run_cli([self.root, "--out", self.out]), 0)
        with open(self.out, encoding="utf-8") as handle:
            questions = json.load(handle)
        self.assertTrue(questions)
        for question in questions:
            self.assertIn("answer", question)

    def test_a_repository_with_nothing_to_ask_about_is_an_error_not_an_empty_file(self):
        empty = build_tree({"pkg/nothing.py": "VALUE = 1\n"})
        try:
            self.assertEqual(self.run_cli([empty]), 1)
        finally:
            shutil.rmtree(empty, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
