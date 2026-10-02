"""
Tests for what the CLI and the parser do with broken input (issues #13 and #14).

Three rules are pinned:

- a file that is missing, a directory given instead of a file, or a syntax error
  reads like every other failure this CLI prints: '[ERROR] - ...', exit 1, no
  traceback. Five of the six commands used to leak a raw traceback, which is the
  first mistake every user makes.
- every syntax error carries its LINE. One did not: 'find_matching_paren' raised
  a bare ValueError, so an unbalanced parenthesis escaped the CLI's handler with
  neither a line nor a file name.
- a field with no type is refused (SPEC 4.1 makes the type part of a field), but
  a default that merely LOOKS truncated is still accepted, and only '--strict'
  turns it into a failure. The distinction matters: the second-'=' check that
  seemed obvious produced 23 false positives on the shipped examples.

Run with:  python -m unittest discover tests
"""

import io
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.__main__ import main
from veltro.parser import (parse_text, suspicious_members, unbalanced_parentheses,VeltroSyntaxError)


def run_cli(arguments: list):
    """
    Run the CLI in-process, returning (exit code, stdout, stderr)
    """
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = main(arguments)
    return code, out.getvalue(), err.getvalue()


def write_vel(contents: str) -> str:
    """
    Write a throwaway '.vel' and return its path
    """
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "sample.vel")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(contents)
    return path


READ_COMMANDS = (
    ["parse", "{path}"],
    ["find", "{path}", "X"],
    ["show", "{path}", "X"],
    ["deps", "{path}", "X"],
    ["map", "{path}"],
)


class TestAMissingFile(unittest.TestCase):

    def shaped(self, template: list, path: str) -> list:
        arguments = []
        for piece in template:
            arguments.append(piece.format(path=path))
        return arguments

    def test_no_command_prints_a_traceback(self):
        for template in READ_COMMANDS:
            code, out, err = run_cli(self.shaped(template, "definitely-not-here.vel"))
            text = out + err
            self.assertEqual(code, 1, template)
            self.assertIn("[ERROR]", text, template)
            self.assertIn("definitely-not-here.vel", text, template)
            self.assertNotIn("Traceback", text, template)

    def test_a_directory_is_reported_not_crashed(self):
        directory = tempfile.mkdtemp()
        for template in READ_COMMANDS:
            code, out, err = run_cli(self.shaped(template, directory))
            self.assertEqual(code, 1, template)
            self.assertIn("[ERROR]", out + err, template)
        shutil.rmtree(directory, ignore_errors=True)

    def test_extract_still_reports_a_missing_directory(self):
        code, out, _err = run_cli(["extract", "definitely-not-here"])
        self.assertEqual(code, 1)
        self.assertIn("[ERROR]", out)


class TestASyntaxErrorIsReported(unittest.TestCase):

    def test_every_read_command_reports_it(self):
        path = write_vel("veltro 1\nmodule A\nclass Foo\nbar\n")
        for template in READ_COMMANDS:
            arguments = []
            for piece in template:
                arguments.append(piece.format(path=path))
            code, out, err = run_cli(arguments)
            self.assertEqual(code, 1, template)
            self.assertIn("[ERROR] - syntax", out + err, template)
            self.assertNotIn("Traceback", out + err, template)
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


class TestEverySyntaxErrorCarriesItsLine(unittest.TestCase):

    def test_an_unbalanced_parenthesis_is_a_veltro_error_with_a_line(self):
        with self.assertRaises(VeltroSyntaxError) as caught:
            parse_text("veltro 1\nmodule A\nclass Foo\nrun(x Int\n")
        self.assertEqual(caught.exception.line_number, 4)
        self.assertIn("unbalanced parentheses", str(caught.exception))

    def test_the_message_is_not_double_prefixed(self):
        with self.assertRaises(VeltroSyntaxError) as caught:
            parse_text("veltro 1\nmodule A\nclass Foo\nrun(x Int\n")
        self.assertEqual(str(caught.exception).count("[ERROR]"), 0)

    def test_a_field_with_no_type_is_refused_with_its_line(self):
        with self.assertRaises(VeltroSyntaxError) as caught:
            parse_text("veltro 1\nmodule A\nclass Foo\na Int\nbar\n")
        self.assertEqual(caught.exception.line_number, 5)
        self.assertIn("needs a type", str(caught.exception))

    def test_a_field_with_a_type_is_still_fine(self):
        model = parse_text("veltro 1\nmodule A\nclass Foo\nbar Baz\n")
        self.assertEqual(model["nodes"][0]["fields"][0]["type"], "Baz")


class TestStrictMode(unittest.TestCase):

    def test_a_truncated_default_is_accepted_by_default(self):
        model = parse_text("veltro 1\nmodule A\nclass Foo\nbar Baz = (\n")
        self.assertEqual(model["nodes"][0]["fields"][0]["default"], "(")

    def test_but_it_is_reported_as_suspicious(self):
        model = parse_text("veltro 1\nmodule A\nclass Foo\nbar Baz = (\n")
        problems = suspicious_members(model)
        self.assertEqual(len(problems), 1)
        self.assertIn("unbalanced parentheses", problems[0])

    def test_the_legitimate_call_default_is_never_flagged(self):
        # the case the whole field-versus-method rule exists to protect
        model = parse_text("veltro 1\nmodule A\nclass Foo\ncache dict = field(default_factory=dict)\n")
        self.assertEqual(suspicious_members(model), [])

    def test_a_second_equals_is_not_flagged(self):
        # 23 false positives on the shipped examples said so: strings, lambdas, and a constant whose value is '=' itself
        for default in ("1 = 2", "_ => Task.CompletedTask", "'='", '"key=value"'):
            model = parse_text(f"veltro 1\nmodule A\nclass Foo\nbar Baz = {default}\n")
            self.assertEqual(suspicious_members(model), [], default)

    def test_strict_turns_it_into_a_failure(self):
        path = write_vel("veltro 1\nmodule A\nclass Foo\nbar Baz = (\n")
        output = os.path.join(os.path.dirname(path), "out.json")

        code, out, _err = run_cli(["parse", path, "--out", output])
        self.assertEqual(code, 0)
        self.assertIn("[WARN]", out)

        code, out, _err = run_cli(["parse", path, "--out", output, "--strict"])
        self.assertEqual(code, 1)
        self.assertIn("[ERROR]", out)
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)

    def test_strict_is_silent_on_a_clean_file(self):
        path = write_vel("veltro 1\nmodule A\nclass Foo\nbar Baz = 0\n")
        output = os.path.join(os.path.dirname(path), "out.json")
        code, out, _err = run_cli(["parse", path, "--out", output, "--strict"])
        self.assertEqual(code, 0)
        self.assertNotIn("[ERROR]", out)
        self.assertNotIn("[WARN]", out)
        shutil.rmtree(os.path.dirname(path), ignore_errors=True)


class TestTheParenthesisHelper(unittest.TestCase):

    def test_balanced_text(self):
        for text in ("field(x)", "f(g(h()))", "no parens at all", "'('+')'"):
            self.assertFalse(unbalanced_parentheses(text), text)

    def test_unbalanced_text(self):
        for text in ("(", "field(x", "f(g(h())", ")("):
            self.assertTrue(unbalanced_parentheses(text), text)


class TestTheShippedFilesStayClean(unittest.TestCase):
    """
    The false-positive guard: --strict must say nothing about anything this
    repository ships, or it is a check nobody will be able to leave on.
    """

    def test_no_example_is_flagged(self):
        import glob
        from veltro.parser import parse_file

        patterns = ["examples/*.vel", "eval/subjects/*/*.vel", "conformance/cases/*.vel", "bench/formats/*.vel"]
        paths = []
        for pattern in patterns:
            paths.extend(glob.glob(os.path.join(REPO_ROOT, pattern)))
        self.assertTrue(paths, "no .vel files found to check")

        for path in paths:
            # a conformance case with a '.rejected' marker is MEANT not to parse
            if os.path.exists(path[:-len(".vel")] + ".rejected"):
                continue
            problems = suspicious_members(parse_file(path))
            self.assertEqual(problems, [], f"{os.path.basename(path)}: {problems[:2]}")


if __name__ == "__main__":
    unittest.main()
