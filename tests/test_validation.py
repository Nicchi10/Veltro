"""
Tests for the model-level constraints the JSON schema cannot express.

The central one is that a node id identifies exactly one type: edges are pairs
of ids, so a repeated id makes every link to it ambiguous and forces each
consumer to invent its own tie-break.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.__main__ import find_duplicate_ids, validate_model
from veltro.parser import parse_text


def model_with_ids(ids):
    """
    A minimal, schema-valid model carrying the given node ids
    """
    nodes = []
    for node_id in ids:
        nodes.append({
            "id": node_id,
            "kind": "class",
            "name": node_id.rsplit(".", 1)[-1],
            "module": node_id.rsplit(".", 1)[0],
            "fields": [],
            "methods": [],
        })
    return {"veltro": 1, "nodes": nodes, "edges": []}


class TestFindDuplicateIds(unittest.TestCase):

    def test_clean_model_has_none(self):
        model = model_with_ids(["M.A", "M.B", "N.A"])
        self.assertEqual(find_duplicate_ids(model), [])

    def test_repeated_id_is_reported_once(self):
        model = model_with_ids(["M.A", "M.B", "M.A", "M.A"])
        self.assertEqual(find_duplicate_ids(model), ["M.A"])

    def test_several_duplicates_keep_first_seen_order(self):
        model = model_with_ids(["M.B", "M.A", "M.B", "M.A"])
        self.assertEqual(find_duplicate_ids(model), ["M.B", "M.A"])


class TestValidationRejectsDuplicates(unittest.TestCase):

    def test_clean_model_validates(self):
        self.assertEqual(validate_model(model_with_ids(["M.A", "M.B"])), "OK")

    def test_duplicate_id_fails_validation(self):
        result = validate_model(model_with_ids(["M.A", "M.A"]))
        self.assertNotEqual(result, "OK")
        self.assertIn("unique", result)
        self.assertIn("M.A", result)

    def test_schema_errors_still_reported(self):
        broken = {"veltro": 1, "nodes": [{"id": "M.A"}], "edges": []}
        self.assertNotEqual(validate_model(broken), "OK")


class TestParserOutputAlwaysValidates(unittest.TestCase):

    def test_repeated_declarations_still_produce_a_valid_model(self):
        # the parser merges them, so what reaches the schema is already clean
        source = (
            "veltro 1\n"
            "module M\n"
            "class Silo\n"
            "a int\n"
            "class Silo\n"
            "b int\n"
        )
        model = parse_text(source)
        self.assertEqual(find_duplicate_ids(model), [])
        self.assertEqual(validate_model(model), "OK")


if __name__ == "__main__":
    unittest.main()
