"""
Tests for which files an extractor is allowed to read.

This is the rule that decides whether Veltro is usable on a real project at
all. Before it existed, pointing the Python extractor at this repository's root
produced 25,735 types, 99.6% of them from the virtualenv: one module out of
6,020 was the project.

The opposite failure is worse and quieter, so it is pinned hardest here: a
pruning list that eats real source returns a SMALLER graph and nothing says so.
'packages' is the trap - NuGet downloads live there, and so do the sources of
nest and angular - which is why build directories are per-language.

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

from veltro.extract.walk import (DEPENDENCY_DIRS, describe, iter_source_files,
                                 looks_like_a_test, matches_any, new_report)


def build_tree(layout: dict) -> str:
    """

    Write a throwaway source tree.

    Args:
        layout (dict): relative path -> file contents

    Returns:
        str: the root directory, which the caller must remove

    """
    root = tempfile.mkdtemp()
    for relative, contents in layout.items():
        path = os.path.join(root, relative.replace("/", os.sep))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
    return root


TREE = {
    "src/app.py": "class App: pass\n",
    "src/models/user.py": "class User: pass\n",
    "tests/test_app.py": "class AppTest: pass\n",
    "src/test_helpers.py": "class Helper: pass\n",
    "venv/Lib/site-packages/dep/thing.py": "class Dependency: pass\n",
    "__pycache__/app.cpython-310.pyc": "",
    "docs/conf.py": "class Config: pass\n",
    "build/generated.py": "class Generated: pass\n",
}


class TestWhatIsRead(unittest.TestCase):

    def setUp(self):
        self.root = build_tree(TREE)
        self.report = new_report()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def found(self, **options) -> set:
        names = set()
        for path in iter_source_files(self.root, (".py",), report=self.report, **options):
            names.add(os.path.relpath(path, self.root).replace(os.sep, "/"))
        return names

    def test_a_virtualenv_is_never_read(self):
        self.assertNotIn("venv/Lib/site-packages/dep/thing.py", self.found())

    def test_build_output_is_not_read(self):
        self.assertNotIn("build/generated.py", self.found())

    def test_the_real_source_is_read(self):
        found = self.found()
        self.assertIn("src/app.py", found)
        self.assertIn("src/models/user.py", found)

    def test_an_ordinary_directory_is_not_pruned(self):
        # 'docs' is not a dependency, not build output and not a test
        self.assertIn("docs/conf.py", self.found())

    def test_tests_are_skipped_by_default(self):
        found = self.found()
        self.assertNotIn("tests/test_app.py", found)
        self.assertNotIn("src/test_helpers.py", found)

    def test_tests_can_be_asked_for(self):
        found = self.found(keep_tests=True)
        self.assertIn("tests/test_app.py", found)
        self.assertIn("src/test_helpers.py", found)

    def test_an_exclude_glob_prunes_a_directory(self):
        self.assertNotIn("docs/conf.py", self.found(exclude=["docs"]))

    def test_an_exclude_glob_skips_a_file(self):
        found = self.found(exclude=["src/models/*"])
        self.assertNotIn("src/models/user.py", found)
        self.assertIn("src/app.py", found)

    def test_the_report_counts_what_happened(self):
        self.found()
        self.assertEqual(self.report["files"], 3)        # app, user, docs/conf
        self.assertIn("venv", self.report["pruned"])
        self.assertIn("files read", describe(self.report))
        self.assertIn("pruned", describe(self.report))


class TestBuildDirectoriesArePerLanguage(unittest.TestCase):
    """
    The dangerous direction: pruning a directory that holds real source.
    """

    def setUp(self):
        self.root = build_tree({
            "packages/core/service.ts": "export class CoreService {}\n",
            "packages/Newtonsoft.Json/lib.cs": "public class Vendored {}\n",
            "src/App.cs": "public class App {}\n",
            "obj/Debug/Generated.cs": "public class Generated {}\n",
            "dist/bundle.ts": "export class Bundled {}\n",
        })

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def found(self, extensions) -> set:
        names = set()
        for path in iter_source_files(self.root, extensions):
            names.add(os.path.relpath(path, self.root).replace(os.sep, "/"))
        return names

    def test_typescript_keeps_a_monorepo_packages_directory(self):
        # nest and angular both keep their sources there: pruning it globally would return an empty graph and say nothing
        self.assertIn("packages/core/service.ts", self.found((".ts",)))

    def test_csharp_prunes_its_own_packages_directory(self):
        self.assertNotIn("packages/Newtonsoft.Json/lib.cs", self.found((".cs",)))

    def test_csharp_prunes_obj_but_typescript_does_not_care(self):
        self.assertNotIn("obj/Debug/Generated.cs", self.found((".cs",)))
        self.assertIn("src/App.cs", self.found((".cs",)))

    def test_typescript_prunes_its_own_bundle_output(self):
        self.assertNotIn("dist/bundle.ts", self.found((".ts",)))

    def test_packages_is_not_in_the_shared_list(self):
        self.assertNotIn("packages", DEPENDENCY_DIRS)


class TestHelpers(unittest.TestCase):

    def test_test_file_conventions_per_language(self):
        for name in ("test_app.py", "app_test.py", "service.spec.ts", "service.test.js", "AppTests.cs"):
            self.assertTrue(looks_like_a_test(name), name)

    def test_ordinary_names_are_not_tests(self):
        for name in ("app.py", "latest.py", "contest.ts", "Manifest.cs"):
            self.assertFalse(looks_like_a_test(name), name)

    def test_a_glob_matches_with_either_separator(self):
        self.assertTrue(matches_any(os.path.join("docs", "conf.py"), ["docs/*"]))

    def test_an_empty_pattern_list_matches_nothing(self):
        self.assertFalse(matches_any("src/app.py", []))


if __name__ == "__main__":
    unittest.main()
