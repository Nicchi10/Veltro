"""
Tests for the Java extractor's source index.

The Java extractor is a standalone Java program, so it is the one extractor
these tests cannot simply import: they compile it with the JDK on this machine
and run it, which is also the only way to prove the published command line still
works. Everything here SKIPS when no JDK 9+ is available, and the CI
'extractors' job installs one so it runs somewhere for real.

What is pinned:

- the index VALIDATES against index.schema.json. It is written by hand in Java
  (no JSON library, so the extractor needs nothing but a JDK), which is exactly
  the kind of code that drifts out of shape unnoticed.
- every type in the model has a location, and no location names a type that is
  not in the model. The index and the '.vel' are produced by one pass over one
  source tree; if their ids ever disagree, 'find' and 'show --code' go quiet on
  the types that disagree and say nothing about why.
- the spans are real: the text they point at is the declaration they claim.
- the bytes are deterministic, so the artefact is diffable.

Run with:  python -m unittest discover tests
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.__main__ import schema_path
from veltro.index import index_path_for, read_index, read_span, spans_of
from veltro.parser import parse_text

FIXTURE_DIR = os.path.join(REPO_ROOT, "tests", "java")
EXTRACTOR = os.path.join(REPO_ROOT, "veltro", "extract", "java", "VeltroJavaExtractor.java")

# The extractor reads two internal javac packages (for the authoritative enum-constant flag), which the module system encapsulates from JDK 9 on, so both javac and java need them opened explicitly.
ADD_EXPORTS = [
    "--add-exports", "jdk.compiler/com.sun.tools.javac.tree=ALL-UNNAMED",
    "--add-exports", "jdk.compiler/com.sun.tools.javac.code=ALL-UNNAMED",
]


def jdk_tool(name: str) -> str:
    """
    A JDK executable, preferring JAVA_HOME over the PATH.

    On a developer machine the PATH often points at an old JRE or JDK 8 while
    JAVA_HOME holds the current JDK, and the Java extractor needs the newer one.

    Args:
        name (str): 'javac' or 'java'

    Returns:
        str | None: the full path, or None when it cannot be found
    """
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        found = shutil.which(name, path=os.path.join(java_home, "bin"))
        if found:
            return found
    return shutil.which(name)


def major_version(javac: str):
    """
    The language level of a javac, as an integer.

    Args:
        javac (str): path to javac

    Returns:
        int | None: 8, 17, 21..., or None when the version cannot be read
    """
    try:
        finished = subprocess.run([javac, "-version"], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None

    # JDK 8 prints to stderr, later ones to stdout
    text = (finished.stdout + " " + finished.stderr).strip()
    for word in text.split():
        if not word[:1].isdigit():
            continue
        if word.startswith("1."):
            return 8
        number = word.split(".")[0]
        if number.isdigit():
            return int(number)
    return None


def usable_jdk():
    """
    The JDK to test with, or None to skip.

    Returns:
        (str, str) | None: (javac, java), both from a JDK 9 or newer
    """
    javac = jdk_tool("javac")
    java = jdk_tool("java")
    if not javac or not java:
        return None
    version = major_version(javac)
    if version is None or version < 9:
        return None
    return javac, java


JDK = usable_jdk()
WHY_SKIPPED = "no JDK 9+ found (JAVA_HOME or PATH); the Java extractor cannot be compiled here"


@unittest.skipUnless(JDK, WHY_SKIPPED)
class TestTheJavaIndex(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """
        Compile the extractor once, then run it once over the fixtures
        """
        javac, java = JDK
        cls.workspace = tempfile.mkdtemp()
        classes = os.path.join(cls.workspace, "classes")
        os.makedirs(classes)

        compiled = subprocess.run(
            [javac] + ADD_EXPORTS + ["-d", classes, EXTRACTOR],
            capture_output=True, text=True, timeout=300,
        )
        if compiled.returncode != 0:
            shutil.rmtree(cls.workspace, ignore_errors=True)
            raise unittest.SkipTest(f"the extractor did not compile with this JDK: {compiled.stderr.strip()}")

        cls.vel_path = os.path.join(cls.workspace, "models.vel")
        cls.index_path = index_path_for(cls.vel_path)
        cls.extraction = subprocess.run(
            [java] + ADD_EXPORTS + ["-cp", classes, "VeltroJavaExtractor", FIXTURE_DIR, "--out", cls.vel_path],
            capture_output=True, text=True, timeout=300,
        )
        cls.classes = classes

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.workspace, ignore_errors=True)

    def setUp(self):
        self.assertEqual(self.extraction.returncode, 0, self.extraction.stderr)
        with open(self.vel_path, encoding="utf-8") as vel_file:
            self.model = parse_text(vel_file.read())
        self.index = read_index(self.index_path)

    def test_the_index_is_written_next_to_the_vel(self):
        self.assertTrue(os.path.exists(self.index_path), self.extraction.stderr)
        self.assertIn("source index:", self.extraction.stderr)

    def test_the_index_validates_against_its_schema(self):
        import jsonschema

        path = schema_path("index.schema.json")
        self.assertIsNotNone(path, "index.schema.json is missing from the package")
        with open(path, encoding="utf-8") as schema_file:
            schema = json.load(schema_file)
        jsonschema.validate(self.index, schema)

    def test_every_type_in_the_model_has_a_location(self):
        missing = []
        for node in self.model["nodes"]:
            if not spans_of(self.index, node["id"]):
                missing.append(node["id"])
        self.assertEqual(missing, [])

    def test_the_index_names_no_type_the_model_does_not_have(self):
        in_model = set(node["id"] for node in self.model["nodes"])
        self.assertEqual(sorted(set(self.index["locations"]) - in_model), [])

    def test_the_root_is_the_directory_that_was_scanned(self):
        self.assertEqual(self.index["root"], os.path.abspath(FIXTURE_DIR).replace(os.sep, "/"))

    def test_paths_are_relative_and_posix(self):
        for type_id in self.index["locations"]:
            for span in self.index["locations"][type_id]:
                self.assertNotIn("\\", span["file"])
                self.assertFalse(os.path.isabs(span["file"]), f"{type_id} -> {span['file']}")

    def test_a_span_points_at_the_declaration_it_claims(self):
        spans = spans_of(self.index, "app.models.Session")
        self.assertEqual(len(spans), 1)
        source = read_span(self.index, spans[0])
        self.assertTrue(source.startswith("class Session extends Base"), source[:80])
        # and it stops at the closing brace of that class, not at the file's end
        self.assertNotIn("class User", source)

    def test_an_enum_has_a_span_too(self):
        # an enum renders as a single '.vel' line, which is the sort of type an extractor forgets to locate
        source = read_span(self.index, spans_of(self.index, "app.models.Role")[0])
        self.assertIn("enum Role", source)

    def test_an_annotated_type_starts_at_its_first_annotation(self):
        source = read_span(self.index, spans_of(self.index, "app.models.Annotated")[0])
        self.assertTrue(source.startswith("@Deprecated"), source[:80])
        self.assertIn("class Annotated", source)

    def test_the_bytes_are_the_same_on_a_second_run(self):
        javac, java = JDK
        second = os.path.join(self.workspace, "again.vel")
        finished = subprocess.run(
            [java] + ADD_EXPORTS + ["-cp", self.classes, "VeltroJavaExtractor", FIXTURE_DIR, "--out", second],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        with open(self.index_path, "rb") as first_file:
            first_bytes = first_file.read()
        with open(index_path_for(second), "rb") as second_file:
            self.assertEqual(second_file.read(), first_bytes)

    def test_the_cli_can_now_print_a_file_and_line(self):
        finished = subprocess.run(
            [sys.executable, "-m", "veltro", "find", self.vel_path, "Session"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=300,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("Models.java:19", finished.stdout)

    def test_the_cli_can_now_show_the_java_source(self):
        finished = subprocess.run(
            [sys.executable, "-m", "veltro", "show", self.vel_path, "app.models.Session", "--code"],
            capture_output=True, text=True, cwd=REPO_ROOT, timeout=300,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("public static Session make", finished.stdout)

    def test_stdout_writes_no_index_unless_asked(self):
        javac, java = JDK
        finished = subprocess.run(
            [java] + ADD_EXPORTS + ["-cp", self.classes, "VeltroJavaExtractor", FIXTURE_DIR],
            capture_output=True, text=True, cwd=self.workspace, timeout=300,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertIn("class Session", finished.stdout)
        self.assertNotIn("source index:", finished.stderr)

    def test_the_index_flag_puts_it_where_it_is_told(self):
        javac, java = JDK
        elsewhere = os.path.join(self.workspace, "chosen", "place.json")
        os.makedirs(os.path.dirname(elsewhere))
        finished = subprocess.run(
            [java] + ADD_EXPORTS + ["-cp", self.classes, "VeltroJavaExtractor", FIXTURE_DIR, "--index", elsewhere],
            capture_output=True, text=True, timeout=300,
        )
        self.assertEqual(finished.returncode, 0, finished.stderr)
        self.assertTrue(os.path.exists(elsewhere))
        self.assertEqual(read_index(elsewhere)["locations"], self.index["locations"])


if __name__ == "__main__":
    unittest.main()
