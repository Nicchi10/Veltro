"""
Tests for eval/score.py scoring, especially the leaf-name normalisation that
makes a fully-qualified answer match a simple ground-truth name.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.score import as_name_set, score_question


class TestLeafNormalisation(unittest.TestCase):

    def test_qualified_matches_simple(self):
        # The D2 case: model answers qualified, ground truth is simple
        self.assertEqual(as_name_set(["pydantic.types.Base64Encoder"]),as_name_set(["Base64Encoder"]))

    def test_simple_names_unchanged(self):
        # No-op for the other formats (already simple names)
        self.assertEqual(as_name_set(["HttpUrl", "FtpUrl"]), {"httpurl", "ftpurl"})

    def test_string_answer_is_split(self):
        self.assertEqual(as_name_set("A, B"), {"a", "b"})


class TestScoreQuestion(unittest.TestCase):

    def test_implementors_exact_with_qualified_answer(self):
        question = {
            "type": "implementors",
            "answer": ["Base64Encoder", "Base64UrlEncoder"],
        }
        given = ["pydantic.types.Base64Encoder", "pydantic.types.Base64UrlEncoder"]
        is_exact, _tp, _pred, _truth = score_question(question, given)
        self.assertTrue(is_exact)

    def test_module_of_is_not_leaf_stripped(self):
        # module_of is scalar: the full dotted module must be compared as-is, NOT reduced to its leaf
        question = {"type": "module_of", "answer": "pydantic.types"}
        right, _, _, _ = score_question(question, "pydantic.types")
        wrong, _, _, _ = score_question(question, "types")
        self.assertTrue(right)
        self.assertFalse(wrong)

    def test_count_coercion(self):
        question = {"type": "public_method_count", "answer": 3}
        is_exact, _, _, _ = score_question(question, "3")
        self.assertTrue(is_exact)


if __name__ == "__main__":
    unittest.main()
