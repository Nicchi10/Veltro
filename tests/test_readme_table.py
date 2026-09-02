"""
Tests for the README token-table check.

A check that cannot FAIL is worse than no check: it is a green light nobody
looks behind. So what is pinned here is that a drifted row is actually caught,
not just that the current README passes.

Importing the checker pulls in bench/scale_bench.py, which counts tokens, so
this module needs the [bench] extra and skips without it.

Run with:  python -m unittest discover tests
"""

import os
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

try:
    from bench import check_readme_table
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

NEEDS_TIKTOKEN = unittest.skipUnless(HAS_TIKTOKEN, "needs the [bench] extra (tiktoken)")

TABLE = """\
Some prose above the table.

| project | language | types | Veltro | Mermaid | PlantUML |
|---------|----------|-------|--------|---------|----------|
| [MediatR](https://github.com/jbogard/MediatR) | C# | 216 | 9,875 | +24% | +32% |
| [Rich](https://github.com/Textualize/rich) | Python | 173 | 12,795 | +20% | +33% |

Some prose below it.
"""


def readme_holding(text: str) -> str:
    """

    Write a throwaway README and give back its path.

    Args:
        text (str): the file content

    Returns:
        str: the path, in a directory the caller is expected to leave behind

    """
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "README.md")
    with open(path, "w", encoding="utf-8", newline="\n") as readme_file:
        readme_file.write(text)
    return path


@NEEDS_TIKTOKEN
class TestReadingTheTable(unittest.TestCase):

    def setUp(self):
        self.rows = check_readme_table.read_rows(readme_holding(TABLE))

    def test_only_the_table_rows_are_read(self):
        self.assertEqual(len(self.rows), 2)

    def test_the_project_is_the_link_text(self):
        self.assertEqual(self.rows[0]["project"], "MediatR")

    def test_numbers_lose_their_separators_and_signs(self):
        row = self.rows[0]
        self.assertEqual(row["types"], 216)
        self.assertEqual(row["veltro"], 9875)
        self.assertEqual(row["mermaid"], 24)
        self.assertEqual(row["plantuml"], 32)

    def test_a_missing_table_is_an_error_not_an_empty_pass(self):
        path = readme_holding("no table here at all\n")
        with self.assertRaises(LookupError):
            check_readme_table.read_rows(path)


@NEEDS_TIKTOKEN
class TestDriftIsCaught(unittest.TestCase):

    def setUp(self):
        self.row = {"types": 216, "veltro": 9875, "mermaid": 24, "plantuml": 32}

    def test_a_row_that_matches_reports_nothing(self):
        self.assertEqual(check_readme_table.differences(self.row, dict(self.row)), [])

    def test_one_token_of_drift_is_reported(self):
        measured = dict(self.row, veltro=9876)
        found = check_readme_table.differences(self.row, measured)
        self.assertEqual(len(found), 1)
        self.assertIn("9876", found[0])

    def test_every_wrong_number_is_reported_not_just_the_first(self):
        measured = {"types": 217, "veltro": 9876, "mermaid": 25, "plantuml": 33}
        self.assertEqual(len(check_readme_table.differences(self.row, measured)), 4)


@NEEDS_TIKTOKEN
class TestEveryRowHasASource(unittest.TestCase):
    """
    A row added to the README without a '.vel' to recompute it would otherwise
    be checked by nobody, quietly.
    """

    def test_the_real_table_is_fully_accounted_for(self):
        rows = check_readme_table.read_rows(check_readme_table.README)
        for row in rows:
            self.assertIn(row["project"], check_readme_table.SOURCES, f"{row['project']} is in the README table but not in SOURCES")


if __name__ == "__main__":
    unittest.main()
