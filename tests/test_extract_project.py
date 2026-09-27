"""
Tests for 'veltro extract': a whole repository into one '.vel' and one index.

This is the first command someone new runs, so what is pinned here is mostly
about honesty rather than parsing:

- a language that is present but cannot be read is REPORTED. "there is C# here
  and I could not read it" is a different statement from "there is no C# here",
  and only one of them is true when the [extract] extra is missing.
- Veltro models TYPES, so a repository built out of free functions produces an
  almost empty '.vel'. Saying so is the tool's job, not the user's to infer.
- one repository gives ONE index, with every path relative to the same root.
  Two extractions rooted differently would otherwise record spans that resolve
  to nothing.

Run with:  python -m unittest discover tests
"""

import os
import shutil
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.project import (build_notes, detect_languages, extract_repository,
                                    language_by_name, strip_version_pragma)
from veltro.index import merge_index, new_index
from veltro.parser import parse_text

try:
    import tree_sitter
    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False


def build_tree(layout: dict) -> str:
    """
    Write a throwaway repository and give back its root
    """
    root = tempfile.mkdtemp()
    for relative, contents in layout.items():
        path = os.path.join(root, relative.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
    return root


MIXED = {
    "src/app.py": "class App:\n    name: str\n",
    "web/service.ts": "export class WebService { id: number; }\n",
    "legacy/Thing.cs": "public class Thing {}\n",
    "server/Main.java": "public class Main {}\n",
    "node_modules/dep/vendor.ts": "export class Vendored {}\n",
}


class TestDetection(unittest.TestCase):

    def setUp(self):
        self.root = build_tree(MIXED)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_every_language_present_is_found(self):
        found = detect_languages(self.root)
        self.assertEqual(set(found), {"python", "typescript", "csharp", "java"})

    def test_vendored_code_does_not_count_as_a_language(self):
        # the only other TypeScript file is under node_modules
        self.assertEqual(detect_languages(self.root)["typescript"], 1)

    def test_an_absent_language_is_not_reported(self):
        root = build_tree({"src/app.py": "class App: pass\n"})
        self.assertEqual(set(detect_languages(root)), {"python"})
        shutil.rmtree(root, ignore_errors=True)

    def test_an_unknown_language_name_has_no_entry(self):
        self.assertIsNone(language_by_name("cobol"))


class TestOneDocument(unittest.TestCase):

    def setUp(self):
        self.root = build_tree(MIXED)
        self.result = extract_repository(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_the_result_is_one_valid_vel(self):
        model = parse_text(self.result["vel"])
        self.assertTrue(model["nodes"])

    def test_only_one_version_pragma_survives(self):
        pragmas = 0
        for line in self.result["vel"].splitlines():
            if line.strip().startswith("veltro "):
                pragmas += 1
        self.assertEqual(pragmas, 1)

    def test_python_is_always_read_because_it_needs_no_extra(self):
        self.assertIn("python", self.result["per_language"])

    def test_every_type_is_locatable_from_one_root(self):
        index = self.result["index"]
        model = parse_text(self.result["vel"])
        for node in model["nodes"]:
            spans = index["locations"].get(node["id"])
            self.assertTrue(spans, f"no location recorded for {node['id']}")
            for span in spans:
                path = os.path.join(index["root"], span["file"])
                self.assertTrue(os.path.exists(path), f"{span['file']} does not resolve under the index root")

    @unittest.skipUnless(HAS_TREE_SITTER, "needs the [extract] extra (tree-sitter)")
    def test_several_languages_land_in_the_same_document(self):
        names = set()
        for node in parse_text(self.result["vel"])["nodes"]:
            names.add(node["name"])
        self.assertIn("App", names)
        self.assertIn("WebService", names)
        self.assertIn("Thing", names)


class TestWhatTheUserIsTold(unittest.TestCase):

    def test_java_is_reported_rather_than_ignored(self):
        root = build_tree({"src/app.py": "class App:\n    a: int\n", "server/Main.java": "public class Main {}\n"})
        result = extract_repository(root)
        self.assertIn("java", result["skipped"])
        self.assertTrue(any("java" in note for note in result["notes"]))
        shutil.rmtree(root, ignore_errors=True)

    def test_a_missing_extra_is_named_with_the_command_to_fix_it(self):
        # simulated rather than uninstalled: the note must carry the pip line
        result = {
            "files": 10,
            "per_language": {"python": {"files": 10, "types": 10}},
            "skipped": {"typescript": "needs the [extract] extra: pip install 'veltro[extract]'"},
        }
        notes = build_notes(result, {"typescript": 3, "python": 10})
        self.assertEqual(len(notes), 1)
        self.assertIn("pip install", notes[0])
        self.assertIn("3 typescript files", notes[0])

    def test_a_repository_with_no_types_is_told_so(self):
        root = build_tree({"src/tools.py": "def helper():\n    return 1\n"})
        result = extract_repository(root)
        self.assertTrue(any("no types at all" in note for note in result["notes"]))
        shutil.rmtree(root, ignore_errors=True)

    def test_a_function_heavy_repository_is_warned_about(self):
        layout = {}
        for number in range(10):
            layout[f"src/mod{number}.py"] = "def work():\n    return 1\n"
        layout["src/only.py"] = "class Only:\n    a: int\n"
        root = build_tree(layout)
        result = extract_repository(root)
        self.assertTrue(any("models TYPES" in note for note in result["notes"]))
        shutil.rmtree(root, ignore_errors=True)

    def test_a_type_heavy_repository_is_left_alone(self):
        layout = {}
        for number in range(5):
            layout[f"src/mod{number}.py"] = f"class Thing{number}:\n    a: int\n\n\nclass Other{number}:\n    b: int\n"
        root = build_tree(layout)
        result = extract_repository(root)
        self.assertEqual(result["notes"], [])
        shutil.rmtree(root, ignore_errors=True)


class TestJoiningDocuments(unittest.TestCase):

    def test_the_pragma_is_dropped_only_once(self):
        joined = strip_version_pragma("veltro 1\n\nmodule a\nclass A\n")
        self.assertFalse(joined.startswith("veltro"))
        self.assertIn("class A", joined)

    def test_a_document_without_a_pragma_is_unchanged(self):
        self.assertEqual(strip_version_pragma("module a\nclass A\n"), "module a\nclass A")


class TestMergingIndexes(unittest.TestCase):

    def test_spans_are_rebased_onto_the_target_root(self):
        root = build_tree({"web/service.ts": "export class S {}\n"})
        target = new_index(root)
        other = new_index(os.path.join(root, "web"))
        other["locations"]["web.service.S"] = [{"file": "service.ts", "line": 1, "end_line": 1}]

        merge_index(target, other)
        span = target["locations"]["web.service.S"][0]
        self.assertEqual(span["file"], "web/service.ts")
        self.assertTrue(os.path.exists(os.path.join(target["root"], span["file"])))
        shutil.rmtree(root, ignore_errors=True)

    def test_merging_keeps_what_the_target_already_had(self):
        target = new_index("/repo")
        target["locations"]["a.A"] = [{"file": "a.py", "line": 1, "end_line": 2}]
        other = new_index("/repo")
        other["locations"]["b.B"] = [{"file": "b.py", "line": 3, "end_line": 4}]
        merge_index(target, other)
        self.assertEqual(set(target["locations"]), {"a.A", "b.B"})


if __name__ == "__main__":
    unittest.main()
