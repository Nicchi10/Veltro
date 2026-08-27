"""
Tests for the benchmark slice.

The 7-format ranking is the most quoted table in the README and the easiest one
to attack, so what it measures has to be guaranteed rather than maintained by
hand: every format must describe the SAME architecture, or a file that quietly
says less would win the token count for the wrong reason.

Run with:  python -m unittest discover tests
"""

import os
import sys
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bench.slice_formats import (FORMATS_DIR, GENERATED, SLICE_VEL, load_formats,
                                 missing_from, model_vocabulary)
from veltro.parser import parse_file


class TestSliceFormats(unittest.TestCase):

    def setUp(self):
        self.texts, self.problems = load_formats()
        self.model = parse_file(SLICE_VEL)

    def test_every_format_describes_the_whole_model(self):
        # the parity check is the point: no rendering may omit a type, a member, an enum value or a default and still be ranked against the others
        self.assertEqual(self.problems, {})

    def test_the_seven_formats_are_all_present(self):
        self.assertEqual(sorted(self.texts), sorted(
            ["D2", "Graphviz DOT", "Mermaid", "Nomnoml", "PlantUML", "Veltro", "yUML"]))

    def test_the_renderable_formats_are_not_read_from_disk(self):
        # a file that does not exist cannot drift: PlantUML, Mermaid and D2 are produced by the exporters every time the benchmark runs
        for label, _exporter in GENERATED:
            for extension in ("puml", "mmd", "d2"):
                path = os.path.join(FORMATS_DIR, "slice." + extension)
                self.assertFalse(os.path.exists(path),
                                 f"{path} is back on disk and can fall behind the exporter")

    def test_a_rendering_that_drops_a_default_is_caught(self):
        # exactly what had gone wrong: slice.mmd and slice.d2 had lost the three field defaults the model carries, which made both look shorter
        vocabulary = model_vocabulary(self.model)
        defaults = []
        for node in self.model["nodes"]:
            for field in node.get("fields", []):
                if "default" in field:
                    defaults.append(field["default"])
        self.assertTrue(defaults, "the slice should carry defaults for this to test anything")

        crippled = self.texts["Nomnoml"]
        for default in defaults:
            crippled = crippled.replace("= " + default, "")
        self.assertNotEqual(missing_from(crippled, vocabulary), [])

    def test_veltro_is_still_the_densest(self):
        import tiktoken
        encoder = tiktoken.get_encoding("o200k_base")
        counts = {}
        for label in self.texts:
            counts[label] = len(encoder.encode(self.texts[label]))
        cheapest = min(counts, key=counts.get)
        self.assertEqual(cheapest, "Veltro", f"ranking changed: {sorted(counts.items(), key=lambda r: r[1])}")


if __name__ == "__main__":
    unittest.main()
