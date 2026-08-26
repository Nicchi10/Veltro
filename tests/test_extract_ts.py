"""
Tests for the TypeScript/JavaScript -> Veltro extractor.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.tree_sitter_typescript import extract_to_vel, ts_type_to_veltro
from veltro.parser import parse_text


FIXTURE = '''\
export enum Role { System, User = 5, Assistant }

export interface ILlm {
  conversation: ConversationState;
  validate(value: string): boolean;
  readonly id: number;
}

export abstract class Base {
  abstract run(): void;
}

export class Session extends Base implements ILlm {
  token: string;
  user: User;
  expires?: number = 3;
  private _secret: string;
  #hash: string;
  tags: string[];
  static count: number = 0;
  conversation: ConversationState;
  id: number;

  constructor(token: string) { this.token = token; }
  get active(): boolean { return true; }
  set active(v: boolean) {}
  validate(value: string): boolean { return true; }
  static make(raw: Record<string, any>): Session { return new Session(""); }
  protected helper(): void {}
}

export class User {
  name: string;
}
'''


class TestTypeScriptExtractor(unittest.TestCase):

    def setUp(self):
        self.vel = extract_to_vel(FIXTURE, "app.models")
        self.model = parse_text(self.vel)
        self.nodes = {node["name"]: node for node in self.model["nodes"]}

    def test_all_types_are_extracted(self):
        self.assertEqual(
            set(self.nodes), {"Role", "ILlm", "Base", "Session", "User"})

    def test_enum_kind_and_values(self):
        self.assertEqual(self.nodes["Role"]["kind"], "enum")
        self.assertEqual(self.nodes["Role"]["values"], ["System", "User", "Assistant"])

    def test_interface_kind(self):
        self.assertEqual(self.nodes["ILlm"]["kind"], "interface")

    def test_abstract_class(self):
        node = self.nodes["Base"]
        self.assertEqual(node["kind"], "class")
        self.assertEqual(node.get("modifiers"), ["abstract"])

    def test_field_types_and_optional(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertEqual(fields["token"]["type"], "string")
        self.assertEqual(fields["user"]["type"], "User")
        self.assertEqual(fields["expires"]["type"], "number?")
        self.assertEqual(fields["tags"]["type"], "string[]")

    def test_default_is_kept(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertEqual(fields["expires"].get("default"), "3")

    def test_private_field_visibility(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertEqual(fields["_secret"]["vis"], "-")

    def test_hash_field_is_private_and_stripped(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertIn("hash", fields)        # the '#' is dropped from the name
        self.assertEqual(fields["hash"]["vis"], "-")

    def test_static_field(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertTrue(fields["count"]["static"])

    def test_getter_is_a_field_and_setter_dropped(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertIn("active", fields)
        self.assertEqual(fields["active"]["type"], "boolean")
        # the setter must not have produced a second 'active' member or a method
        method_names = [m["name"] for m in self.nodes["Session"]["methods"]]
        self.assertNotIn("active", method_names)

    def test_constructor_and_static_method(self):
        methods = {m["name"]: m for m in self.nodes["Session"]["methods"]}
        self.assertIn("Session", methods)        # constructor under the class name
        make = methods["make"]
        self.assertTrue(make["static"])
        self.assertEqual(make["args"], [{"name": "raw", "type": "Record<string,any>"}])
        self.assertEqual(make["ret"], "Session")

    def test_protected_method(self):
        methods = {m["name"]: m for m in self.nodes["Session"]["methods"]}
        self.assertEqual(methods["helper"]["vis"], "#")

    def test_extend_edge(self):
        explicit = [e for e in self.model["edges"] if not e.get("derived")]
        self.assertIn(
            {"from": "app.models.Session", "kind": "extend", "to": "app.models.Base"},
            explicit,
        )

    def test_implements_edge(self):
        explicit = [e for e in self.model["edges"] if not e.get("derived")]
        self.assertIn(
            {"from": "app.models.Session", "kind": "impl", "to": "app.models.ILlm"},
            explicit,
        )

    def test_association_derived_from_field(self):
        derived = [e for e in self.model["edges"] if e.get("derived")]
        self.assertIn(
            {"from": "app.models.Session", "kind": "assoc",
             "to": "app.models.User", "derived": True},
            derived,
        )


class TestNamespaceModule(unittest.TestCase):

    def test_namespace_overrides_file_module(self):
        source = (
            "export namespace Core.Models {\n"
            "  export class Thing { id: number; }\n"
            "}\n"
        )
        vel = extract_to_vel(source, "some.file")
        self.assertIn("module Core.Models", vel)
        self.assertNotIn("module some.file", vel)
        model = parse_text(vel)
        self.assertEqual(model["nodes"][0]["id"], "Core.Models.Thing")


class TestJavaScriptFallback(unittest.TestCase):

    def test_untyped_js_members_default_to_any(self):
        # plain JS: no annotations: class fields keep 'Any', this.x is skipped
        source = (
            "class Point {\n"
            "  x = 0;\n"
            "  constructor() { this.y = 1; }\n"
            "  move(dx, dy) {}\n"
            "}\n"
        )
        vel = extract_to_vel(source, "geo")
        model = parse_text(vel)
        node = model["nodes"][0]
        fields = {f["name"]: f for f in node["fields"]}
        self.assertEqual(fields["x"]["type"], "Any")
        self.assertNotIn("y", fields)        # in-constructor assignment, no field
        move = {m["name"]: m for m in node["methods"]}["move"]
        self.assertEqual(move["args"], [{"name": "dx", "type": "Any"}, {"name": "dy", "type": "Any"}])


class TestStructuralTypesAreSafe(unittest.TestCase):

    def test_only_a_parenthesis_forces_a_type_to_any(self):
        # the NestJS case: a constructor param typed with an inline object used to dump '(request {' into the .vel and break the parser.
        # A PARENTHESIS is what breaks a member line, because that is what tells a method from a field. Spaces and braces do not: a field's type is
        # everything between its name and the '=', so it reads back as written
        source = (
            "export class RequestReader {\n"
            "  onError: (e: Error) => void;\n"
            "  meta: { id: number; tag: string };\n"
            "  constructor(request: { headers: string[]; body: any }) {}\n"
            "  combine(a: A & B): A | B | null { return null; }\n"
            "}\n"
        )
        vel = extract_to_vel(source, "http")
        # it must round-trip through the parser without raising
        model = parse_text(vel)
        node = model["nodes"][0]
        fields = {f["name"]: f for f in node["fields"]}

        # a function type carries a parenthesis, so it cannot be written
        self.assertEqual(fields["onError"]["type"], "Any")
        # an inline object can, and is worth keeping
        self.assertEqual(fields["meta"]["type"], "{ id: number; tag: string }")

        methods = {m["name"]: m for m in node["methods"]}
        self.assertEqual(methods["RequestReader"]["args"],[{"name": "request", "type": "{ headers: string[]; body: any }"}])
        # intersections and multi-member unions survive too
        self.assertEqual(methods["combine"]["args"], [{"name": "a", "type": "A & B"}])
        self.assertEqual(methods["combine"]["ret"], "A | B | null")

    def test_computed_member_name_is_skipped(self):
        source = (
            "export class Bag {\n"
            "  size: number;\n"
            "  [Symbol.iterator]() {}\n"
            "}\n"
        )
        vel = extract_to_vel(source, "coll")
        model = parse_text(vel)
        node = model["nodes"][0]
        field_names = [f["name"] for f in node["fields"]]
        method_names = [m["name"] for m in node["methods"]]
        self.assertEqual(field_names, ["size"])
        self.assertEqual(method_names, [])        # computed-name method dropped


class TestReservedNameField(unittest.TestCase):

    def test_field_named_like_keyword_keeps_plus(self):
        source = (
            "export class Path {\n"
            "  module: string;\n"
            "  name: string;\n"
            "}\n"
        )
        vel = extract_to_vel(source, "pkg")
        self.assertIn("+ module string", vel)        # explicit '+' forced
        model = parse_text(vel)
        field_names = [f["name"] for f in model["nodes"][0]["fields"]]
        self.assertEqual(field_names, ["module", "name"])


class TestTypeTranslation(unittest.TestCase):

    def test_translations(self):
        self.assertEqual(ts_type_to_veltro("Map<string, Foo>"), "Map<string,Foo>")
        self.assertEqual(ts_type_to_veltro("Foo | null"), "Foo?")
        self.assertEqual(ts_type_to_veltro("Bar | undefined"), "Bar?")
        self.assertEqual(ts_type_to_veltro("string[]"), "string[]")
        self.assertEqual(ts_type_to_veltro("Record<string, any>"), "Record<string,any>")


if __name__ == "__main__":
    unittest.main()
