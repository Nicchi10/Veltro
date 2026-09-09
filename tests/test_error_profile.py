"""
Tests for the eval error profile.

This tool exists to publish a NEGATIVE result: the answers saved in
eval/results/ contain almost no reversed relations, so the direction hypothesis
for the exact-match gap is dead. A negative result from a detector nobody
tested is worth nothing - "reversed: 0" reads the same whether the models never
reversed a relation or the classifier cannot recognise one.

So what is pinned here is that each kind of error is actually RECOGNISED, on
answers built to contain exactly one of them.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.error_profile import classify_answer, reachable

# Base <|-- Middle <|-- Leaf, and Middle holds a Helper
TABLES = {
    "parents": {"middle": {"base"}, "leaf": {"middle"}},
    "children": {"base": {"middle"}, "middle": {"leaf"}},
    "out": {"middle": {"base", "helper"}, "base": {"marker"}},
    "in": {"base": {"middle"}, "helper": {"middle"}, "marker": {"base"}},
}

IMPLEMENTORS = {
    "id": "q1",
    "type": "implementors",
    "subject": "Base",
    "answer": ["Middle"],
}

DEPENDS_ON = {
    "id": "q2",
    "type": "depends_on",
    "subject": "Middle",
    "answer": ["Base", "Helper"],
}


class TestReachable(unittest.TestCase):

    def test_it_follows_the_chain(self):
        self.assertEqual(reachable("base", TABLES["children"]), {"middle", "leaf"})

    def test_the_start_is_not_in_its_own_closure(self):
        self.assertNotIn("base", reachable("base", TABLES["children"]))

    def test_a_name_with_no_edges_reaches_nothing(self):
        self.assertEqual(reachable("nobody", TABLES["children"]), set())


class TestImplementorsErrors(unittest.TestCase):

    def test_a_right_answer_produces_nothing(self):
        tally = classify_answer(IMPLEMENTORS, ["Middle"], TABLES)
        self.assertEqual(sum(tally.values()), 0)

    def test_the_subject_itself_is_recognised(self):
        tally = classify_answer(IMPLEMENTORS, ["Base", "Middle"], TABLES)
        self.assertEqual(tally["the subject itself"], 1)

    def test_a_reversed_answer_is_recognised(self):
        # asked for what extends Middle, answered with what Middle extends
        question = dict(IMPLEMENTORS, subject="Middle", answer=["Leaf"])
        tally = classify_answer(question, ["Base"], TABLES)
        self.assertEqual(tally["reversed"], 1)
        self.assertEqual(tally["missed"], 1)

    def test_a_grandchild_is_transitive_not_unrelated(self):
        tally = classify_answer(IMPLEMENTORS, ["Middle", "Leaf"], TABLES)
        self.assertEqual(tally["transitive"], 1)
        self.assertEqual(tally["unrelated"], 0)

    def test_a_name_from_nowhere_is_unrelated(self):
        tally = classify_answer(IMPLEMENTORS, ["Middle", "Stranger"], TABLES)
        self.assertEqual(tally["unrelated"], 1)

    def test_a_missing_name_is_counted(self):
        tally = classify_answer(IMPLEMENTORS, [], TABLES)
        self.assertEqual(tally["missed"], 1)


class TestDependsOnErrors(unittest.TestCase):

    def test_a_right_answer_produces_nothing(self):
        tally = classify_answer(DEPENDS_ON, ["Base", "Helper"], TABLES)
        self.assertEqual(sum(tally.values()), 0)

    def test_answering_with_the_dependents_is_reversed(self):
        # asked what Helper points at, answered with what points at Helper
        question = dict(DEPENDS_ON, subject="Helper", answer=["Nothing"])
        tally = classify_answer(question, ["Middle"], TABLES)
        self.assertEqual(tally["reversed"], 1)

    def test_a_second_hop_is_transitive(self):
        tally = classify_answer(DEPENDS_ON, ["Base", "Helper", "Marker"], TABLES)
        self.assertEqual(tally["transitive"], 1)


if __name__ == "__main__":
    unittest.main()
