"""
Tests for the token budget on a slice.

A real project's graph does not fit in a context, so the useful question is not
"what is the whole architecture" but "what fits in N tokens". The rule pinned
here: the result is a PREFIX of the order it is given, so with a breadth-first
order the budget is spent on the nearest types and the furthest ones are what
gets dropped.

The counter is injected, so these tests measure with a fake one and need no
tokenizer: the budget logic is exact arithmetic, independent of who counts.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text
from veltro.query import budgeted_ids, neighbourhood_ids, slice_vel

# A chain, so breadth-first order from Centre is unambiguous:
# Far <- Near <- Centre -> Other
CHAIN = """\
veltro 1

module app
class Centre
near Near
other Other
class Near
far Far
class Far
class Other
"""


def counting_lines(text: str) -> int:
    """
    A stand-in for a tokenizer: one 'token' per non-empty line
    """
    total = 0
    for line in text.splitlines():
        if line.strip():
            total += 1
    return total


class TestTheBudgetIsRespected(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(CHAIN)
        self.ordered = neighbourhood_ids(self.model, "app.Centre", 5)

    def fits(self, budget: int) -> int:
        kept = budgeted_ids(self.model, self.ordered, budget, counting_lines)
        return counting_lines(slice_vel(self.model, kept))

    def test_the_whole_graph_is_kept_when_it_fits(self):
        kept = budgeted_ids(self.model, self.ordered, 10_000, counting_lines)
        self.assertEqual(kept, self.ordered)

    def test_the_result_never_exceeds_the_budget(self):
        for budget in range(1, 20):
            self.assertLessEqual(self.fits(budget), budget, f"budget {budget} was overspent")

    def test_it_takes_as_much_as_fits(self):
        # one more type would have to break the budget, or the slice is too small
        for budget in range(1, 20):
            kept = budgeted_ids(self.model, self.ordered, budget, counting_lines)
            if len(kept) == len(self.ordered):
                continue
            one_more = self.ordered[:len(kept) + 1]
            self.assertGreater(counting_lines(slice_vel(self.model, one_more)), budget)


class TestWhatGetsDropped(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(CHAIN)
        self.ordered = neighbourhood_ids(self.model, "app.Centre", 5)

    def test_the_subject_comes_first(self):
        self.assertEqual(self.ordered[0], "app.Centre")

    def test_the_result_is_a_prefix_of_the_order_given(self):
        kept = budgeted_ids(self.model, self.ordered, 6, counting_lines)
        self.assertEqual(kept, self.ordered[:len(kept)])

    def test_the_furthest_type_is_the_first_to_go(self):
        # 'Far' is two relations away, so it must not survive a budget that already drops something
        kept = budgeted_ids(self.model, self.ordered, 6, counting_lines)
        self.assertLess(len(kept), len(self.ordered))
        self.assertNotIn("app.Far", kept)


class TestEdges(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(CHAIN)

    def test_a_budget_too_small_for_one_type_keeps_nothing(self):
        ordered = neighbourhood_ids(self.model, "app.Centre", 5)
        self.assertEqual(budgeted_ids(self.model, ordered, 1, counting_lines), [])

    def test_a_zero_or_negative_budget_keeps_nothing(self):
        ordered = neighbourhood_ids(self.model, "app.Centre", 5)
        self.assertEqual(budgeted_ids(self.model, ordered, 0, counting_lines), [])
        self.assertEqual(budgeted_ids(self.model, ordered, -5, counting_lines), [])

    def test_no_candidates_keeps_nothing(self):
        self.assertEqual(budgeted_ids(self.model, [], 100, counting_lines), [])


class TestTheSliceStaysValid(unittest.TestCase):
    """
    A budgeted slice is still Veltro: it has to be, or it cannot be handed to a
    model or back to the parser.
    """

    def test_a_truncated_slice_parses_back(self):
        model = parse_text(CHAIN)
        ordered = neighbourhood_ids(model, "app.Centre", 5)
        kept = budgeted_ids(model, ordered, 6, counting_lines)
        text = slice_vel(model, kept)
        reparsed = parse_text(text)
        self.assertEqual(len(reparsed["nodes"]), len(kept))


try:
    import tiktoken
    HAS_TIKTOKEN = True
except ImportError:
    HAS_TIKTOKEN = False


@unittest.skipUnless(HAS_TIKTOKEN, "needs the [tokenizer] extra (tiktoken)")
class TestTheCommandLine(unittest.TestCase):
    """
    End to end, with the real tokenizer: what the CLI prints must actually fit.
    """

    def setUp(self):
        self.source = os.path.join(REPO_ROOT, "examples", "pydantic.vel")
        self.encoder = tiktoken.get_encoding("o200k_base")

    def run_map(self, arguments: list):
        from contextlib import redirect_stdout, redirect_stderr
        import io
        from veltro.__main__ import main

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(arguments)
        return code, out.getvalue(), err.getvalue()

    def test_the_printed_slice_fits_the_budget(self):
        budget = 800
        code, text, _err = self.run_map(["map", self.source, "--around", "BaseModel", "--budget", str(budget)])
        self.assertEqual(code, 1)        # 'BaseModel' is ambiguous in pydantic

        code, text, report = self.run_map(["map", self.source, "--around", "pydantic.main.BaseModel", "--budget", str(budget)])
        self.assertEqual(code, 0)
        self.assertLessEqual(len(self.encoder.encode(text)), budget)
        self.assertIn("of 800 tokens", report)

    def test_the_report_goes_to_stderr_so_stdout_stays_vel(self):
        _code, text, report = self.run_map(["map", self.source, "--around", "pydantic.types.Base64Encoder", "--budget", "900"])
        self.assertNotIn("[INFO]", text)
        self.assertIn("[INFO]", report)
        parse_text(text)        # raises if stdout is not valid Veltro

    def test_a_budget_that_fits_nothing_fails_loudly(self):
        code, text, _report = self.run_map(["map", self.source, "--around", "pydantic.main.BaseModel", "--budget", "1"])
        self.assertEqual(code, 1)
        self.assertEqual(text.strip(), "")

    def test_a_negative_budget_is_refused(self):
        code, _text, _report = self.run_map(["map", self.source, "--around", "pydantic.main.BaseModel", "--budget", "-10"])
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
