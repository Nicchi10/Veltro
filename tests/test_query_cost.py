"""
Tests for the query-cost check.

The same four numbers are quoted in README.md and in CLI.md, which is two
chances to go stale, so a check reads both and compares them against a live run
of the CLI. What is pinned here is that the check can FAIL: a drift detector
that silently parses nothing reports success forever.

Importing the checker pulls in tiktoken, so this module needs the [bench] extra
and skips without it.

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
    from bench import query_cost
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False

NEEDS_TIKTOKEN = unittest.skipUnless(HAS_TIKTOKEN, "needs the [bench] extra (tiktoken)")

TABLE = """\
Prose above.

| command | tokens | share of the file |
|---------|--------|-------------------|
| `map --module Orleans.Runtime` | 86,718 | 12.60% |
| `show Silo` | 945 | **0.14%** |

Prose below.
"""

MEASURED = {"map --module Orleans.Runtime": 86718, "show Silo": 945}


def document_holding(text: str) -> str:
    """

    Write a throwaway markdown file and give back the directory holding it.

    Args:
        text (str): the file content

    Returns:
        str: the directory, which the caller is expected to leave behind

    """
    directory = tempfile.mkdtemp()
    for name in query_cost.DOCUMENTS:
        with open(os.path.join(directory, name), "w", encoding="utf-8", newline="\n") as document:
            document.write(text)
    return directory


@NEEDS_TIKTOKEN
class TestReadingTheTable(unittest.TestCase):

    def test_the_rows_are_read_with_their_numbers(self):
        directory = document_holding(TABLE)
        rows = query_cost.documented_rows(os.path.join(directory, "CLI.md"))
        self.assertEqual(rows, MEASURED)

    def test_backticks_and_bold_do_not_confuse_it(self):
        directory = document_holding(TABLE)
        rows = query_cost.documented_rows(os.path.join(directory, "CLI.md"))
        self.assertNotIn("`show Silo`", rows)
        self.assertIn("show Silo", rows)

    def test_a_document_with_no_table_reads_as_empty(self):
        directory = document_holding("nothing here\n")
        self.assertEqual(query_cost.documented_rows(os.path.join(directory, "CLI.md")), {})


@NEEDS_TIKTOKEN
class TestTheCheckCanFail(unittest.TestCase):

    def setUp(self):
        self.original_root = query_cost.REPO_ROOT

    def tearDown(self):
        query_cost.REPO_ROOT = self.original_root

    def check_against(self, text: str) -> int:
        query_cost.REPO_ROOT = document_holding(text)
        return query_cost.check_documents(MEASURED)

    def test_matching_documents_report_nothing_wrong(self):
        self.assertEqual(self.check_against(TABLE), 0)

    def test_one_token_of_drift_is_caught(self):
        drifted = TABLE.replace("| 945 |", "| 946 |")
        self.assertGreater(self.check_against(drifted), 0)

    def test_a_deleted_table_is_caught(self):
        self.assertGreater(self.check_against("the table is gone\n"), 0)

    def test_a_dropped_row_is_caught(self):
        without = TABLE.replace("| `show Silo` | 945 | **0.14%** |\n", "")
        self.assertGreater(self.check_against(without), 0)


@NEEDS_TIKTOKEN
class TestTheRealDocuments(unittest.TestCase):

    def test_both_documents_still_carry_the_table(self):
        # not the numbers, those need a live run, which CI does, only that the table the check reads has not been renamed or reformatted away
        for name in query_cost.DOCUMENTS:
            rows = query_cost.documented_rows(os.path.join(REPO_ROOT, name))
            self.assertTrue(rows, f"{name} no longer holds a query-cost table the check can read")


if __name__ == "__main__":
    unittest.main()
