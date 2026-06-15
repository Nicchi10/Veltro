"""
Tests for eval/generate.py (STEP 1): the ground-truth question builder.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text
from eval.generate import build_questions


SOURCE = """\
veltro 1
module M
interface Shape
area() float
class Circle
radius float
center Point
tags List<str>
draw() None
- _hidden() None
class Point
x int

rel
Circle extend Shape
"""


class TestBuildQuestions(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(SOURCE)
        self.questions = build_questions(self.model, limit=10)

    def find(self, qtype, subject):
        for question in self.questions:
            if question["type"] == qtype and question["subject"] == subject:
                return question
        return None

    def test_implementors_ground_truth(self):
        question = self.find("implementors", "Shape")
        self.assertIsNotNone(question)
        self.assertEqual(question["answer"], ["Circle"])

    def test_module_of_ground_truth(self):
        question = self.find("module_of", "Circle")
        self.assertEqual(question["answer"], "M")

    def test_public_method_count_excludes_private(self):
        # Circle has draw() (public) and _hidden() (private) -> 1 public
        question = self.find("public_method_count", "Circle")
        self.assertEqual(question["answer"], 1)

    def test_collection_fields_detects_generic(self):
        question = self.find("collection_fields", "Circle")
        self.assertEqual(question["answer"], ["tags"])

    def test_depends_on_includes_inheritance_and_derived(self):
        question = self.find("depends_on", "Circle")
        # extends Shape (written) + references Point (derived from 'center')
        self.assertEqual(question["answer"], ["Point", "Shape"])

    def test_every_question_has_an_answer(self):
        for question in self.questions:
            self.assertIn("answer", question)
            self.assertTrue(question["prompt"])


if __name__ == "__main__":
    unittest.main()
