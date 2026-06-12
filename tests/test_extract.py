"""
Tests for the Python -> Veltro extractor.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.python_ast import extract_to_vel, python_type_to_veltro
from veltro.parser import parse_text


FIXTURE = '''\
from enum import Enum
from typing import Protocol, Optional, List, Dict, Any
from abc import ABC, abstractmethod


class Role(Enum):
    System = 0
    User = 1


class Validator(Protocol):
    def validate(self, value: str) -> bool: ...


class Base(ABC):
    @abstractmethod
    def run(self) -> None: ...


class Session(Base):
    token: str
    user: "User"
    expires: Optional[int] = None
    _secret: str
    tags: List[str]

    @property
    def active(self) -> bool: ...

    def refresh(self, ttl: int) -> None: ...

    @staticmethod
    def make(raw: Dict[str, Any]) -> "Session": ...


class User:
    name: str
'''


class TestPythonExtractor(unittest.TestCase):

    def setUp(self):
        self.vel = extract_to_vel(FIXTURE, "app.models")
        self.model = parse_text(self.vel)
        self.nodes = {node["name"]: node for node in self.model["nodes"]}

    def test_all_types_are_extracted(self):
        self.assertEqual(
            set(self.nodes), {"Role", "Validator", "Base", "Session", "User"})

    def test_enum_kind_and_values(self):
        self.assertEqual(self.nodes["Role"]["kind"], "enum")
        self.assertEqual(self.nodes["Role"]["values"], ["System", "User"])

    def test_protocol_becomes_interface(self):
        self.assertEqual(self.nodes["Validator"]["kind"], "interface")

    def test_abc_becomes_abstract_class(self):
        node = self.nodes["Base"]
        self.assertEqual(node["kind"], "class")
        self.assertEqual(node.get("modifiers"), ["abstract"])

    def test_field_types_and_optional(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertEqual(fields["token"]["type"], "str")
        self.assertEqual(fields["user"]["type"], "User")
        self.assertEqual(fields["expires"]["type"], "int?")
        self.assertEqual(fields["tags"]["type"], "List<str>")

    def test_private_attribute_visibility(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertEqual(fields["_secret"]["vis"], "-")

    def test_property_is_a_field(self):
        fields = {f["name"]: f for f in self.nodes["Session"]["fields"]}
        self.assertIn("active", fields)
        self.assertEqual(fields["active"]["type"], "bool")

    def test_self_is_dropped_and_static_is_marked(self):
        methods = {m["name"]: m for m in self.nodes["Session"]["methods"]}
        # instance method: self dropped, one arg left
        self.assertEqual(methods["refresh"]["args"], [{"name": "ttl", "type": "int"}])
        # staticmethod: marked static, generic comma not split, brackets translated
        make = methods["make"]
        self.assertTrue(make["static"])
        self.assertEqual(make["args"], [{"name": "raw", "type": "Dict<str,Any>"}])

    def test_inheritance_edge(self):
        explicit = [e for e in self.model["edges"] if not e.get("derived")]
        self.assertIn(
            {"from": "app.models.Session", "kind": "extend", "to": "app.models.Base"},
            explicit,
        )

    def test_association_derived_from_field(self):
        derived = [e for e in self.model["edges"] if e.get("derived")]
        self.assertIn(
            {"from": "app.models.Session", "kind": "assoc",
             "to": "app.models.User", "derived": True},
            derived,
        )


class TestTypeTranslation(unittest.TestCase):

    def test_translations(self):
        self.assertEqual(python_type_to_veltro("List[Message]"), "List<Message>")
        self.assertEqual(python_type_to_veltro("Optional[int]"), "int?")
        self.assertEqual(python_type_to_veltro("str | None"), "str?")
        self.assertEqual(python_type_to_veltro("Dict[str, Any]"), "Dict<str,Any>")
        self.assertEqual(python_type_to_veltro("Optional[List[int]]"), "List<int>?")


if __name__ == "__main__":
    unittest.main()
