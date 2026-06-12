"""
Tests for the Veltro parser.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

# Make the repository root importable when running the file directly
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text


SAMPLE = """\
veltro 1

module Core.Enums
enum MessageRole = System, User, Assistant, Tool

module Core.Models
> The master object.
class LlmInvocation
Conversation ConversationState
TurnIndex Int = 0
Validate() IValidationResult
class ConversationState
+ Messages List<Message>
class ValidationResult
- _isValid Boolean
$Success() ValidationResult
$Failure(errors: IEnumerable<String>) ValidationResult
Merge(a: Dictionary<String,Object>, b: Int) Boolean

rel
LlmInvocation impl ILlmInvocation
"""


class TestParser(unittest.TestCase):

    def setUp(self):
        self.model = parse_text(SAMPLE)
        self.nodes = {node["id"]: node for node in self.model["nodes"]}

    def test_node_count_and_kinds(self):
        self.assertEqual(len(self.model["nodes"]), 4)
        self.assertEqual(self.nodes["Core.Enums.MessageRole"]["kind"], "enum")
        self.assertEqual(
            self.nodes["Core.Models.LlmInvocation"]["kind"], "class")

    def test_enum_values(self):
        enum_node = self.nodes["Core.Enums.MessageRole"]
        self.assertEqual(
            enum_node["values"], ["System", "User", "Assistant", "Tool"])

    def test_doc_line_attaches_to_next_type(self):
        node = self.nodes["Core.Models.LlmInvocation"]
        self.assertEqual(node["doc"], "The master object.")

    def test_field_default(self):
        node = self.nodes["Core.Models.LlmInvocation"]
        turn_index = node["fields"][1]
        self.assertEqual(turn_index["name"], "TurnIndex")
        self.assertEqual(turn_index["type"], "Int")
        self.assertEqual(turn_index["default"], "0")

    def test_public_is_implicit(self):
        # A member with no marker is public
        node = self.nodes["Core.Models.LlmInvocation"]
        self.assertEqual(node["fields"][0]["name"], "Conversation")
        self.assertEqual(node["fields"][0]["vis"], "+")

    def test_explicit_plus_still_accepted(self):
        # Writing the '+' explicitly is tolerated and means the same thing
        node = self.nodes["Core.Models.ConversationState"]
        self.assertEqual(node["fields"][0]["name"], "Messages")
        self.assertEqual(node["fields"][0]["vis"], "+")

    def test_private_marker(self):
        node = self.nodes["Core.Models.ValidationResult"]
        self.assertEqual(node["fields"][0]["name"], "_isValid")
        self.assertEqual(node["fields"][0]["vis"], "-")

    def test_method_no_args_with_return(self):
        node = self.nodes["Core.Models.LlmInvocation"]
        validate = node["methods"][0]
        self.assertEqual(validate["name"], "Validate")
        self.assertEqual(validate["ret"], "IValidationResult")
        self.assertNotIn("args", validate)

    def test_static_method(self):
        node = self.nodes["Core.Models.ValidationResult"]
        success = node["methods"][0]
        self.assertEqual(success["name"], "Success")
        self.assertTrue(success["static"])

    def test_generic_argument_is_not_split_on_inner_comma(self):
        node = self.nodes["Core.Models.ValidationResult"]
        merge = node["methods"][2]
        self.assertEqual(len(merge["args"]), 2)
        self.assertEqual(merge["args"][0]["name"], "a")
        self.assertEqual(merge["args"][0]["type"], "Dictionary<String,Object>")
        self.assertEqual(merge["args"][1]["type"], "Int")

    def test_explicit_edge_is_present(self):
        explicit = [edge for edge in self.model["edges"] if not edge.get("derived")]
        self.assertIn({"from": "Core.Models.LlmInvocation", "kind": "impl", "to": "ILlmInvocation"},explicit,)

    def test_association_is_derived_from_field_type(self):
        derived = [edge for edge in self.model["edges"] if edge.get("derived")]
        # LlmInvocation has a field of type ConversationState -> derived assoc
        self.assertIn({"from": "Core.Models.LlmInvocation", "kind": "assoc", "to": "Core.Models.ConversationState", "derived": True}, derived,)


class TestRefinements(unittest.TestCase):
    """
    Edge cases raised in review
    """

    def test_type_spacing_is_normalized(self):
        # Sloppy spaces around commas/brackets must not change the model
        model = parse_text(
            "module M\n"
            "class C\n"
            "Metadata Dictionary<String, Object>\n"
            "Merge(a: List< Int >, b: Int) Dictionary<String, Object>\n"
        )
        node = model["nodes"][0]
        self.assertEqual(node["fields"][0]["type"], "Dictionary<String,Object>")
        merge = node["methods"][0]
        self.assertEqual(merge["args"][0]["type"], "List<Int>")
        self.assertEqual(merge["ret"], "Dictionary<String,Object>")

    def test_doc_attaches_to_following_declaration(self):
        # A '>' between two types documents the next one, never the previous
        model = parse_text(
            "module M\n"
            "class Foo\n"
            "> describes Bar\n"
            "class Bar\n"
            "Id String\n"
        )
        nodes = {node["name"]: node for node in model["nodes"]}
        self.assertNotIn("doc", nodes["Foo"])
        self.assertEqual(nodes["Bar"]["doc"], "describes Bar")


if __name__ == "__main__":
    unittest.main()
