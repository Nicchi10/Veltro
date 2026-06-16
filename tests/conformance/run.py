"""
Language-agnostic conformance harness for Veltro parsers.

A case is a .vel file in cases/ paired with an expected result:

    <name>.vel  +  <name>.expected.json   -> must parse to exactly this model
    <name>.vel  +  <name>.error.json      -> must fail; {"line", "reason_contains"}

The harness drives a parser through the stdin->stdout contract documented in
ref_adapter.py, so the SAME cases validate the Python reference today and a
TypeScript / Rust port tomorrow. Nothing here imports veltro: a non-Python
parser is tested exactly like the reference one.

    # check the reference parser
    python tests/conformance/run.py

    # check another implementation (must obey the contract)
    python tests/conformance/run.py --parser "node dist/cli.js"

    # (re)generate expected files from a trusted parser after a grammar change
    python tests/conformance/run.py --generate
"""

import argparse
import json
import os
import shlex
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CASES_DIR = os.path.join(HERE, "cases")
# Default: the reference adapter, as an argv list so no path quoting is needed
# (sidesteps Windows backslash / quote pitfalls in command splitting).
DEFAULT_PARSER = [sys.executable, os.path.join(HERE, "ref_adapter.py")]

GREEN = "\033[32m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"


def to_argv(parser_command):
    """A parser command may be a ready argv list or a string to split."""
    if isinstance(parser_command, list):
        return parser_command
    # posix=False so a Windows path's backslashes are not eaten as escapes;
    # then drop any surrounding quotes the split left attached to a token.
    tokens = shlex.split(parser_command, posix=False)
    return [token.strip('"') for token in tokens]


def run_parser(parser_command, source: str):
    """Feed source on stdin, return (exit_code, stdout_text)."""
    completed = subprocess.run(
        to_argv(parser_command),
        input=source,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.returncode, completed.stdout


def discover_cases():
    """Yield (name, vel_path, expected_path, is_error) for every case, sorted."""
    for filename in sorted(os.listdir(CASES_DIR)):
        if not filename.endswith(".vel"):
            continue
        name = filename[:-len(".vel")]
        vel_path = os.path.join(CASES_DIR, filename)
        success_path = os.path.join(CASES_DIR, name + ".expected.json")
        error_path = os.path.join(CASES_DIR, name + ".error.json")
        if os.path.exists(error_path):
            yield name, vel_path, error_path, True
        else:
            yield name, vel_path, success_path, False


def check_case(parser_command, name, vel_path, expected_path, is_error):
    """Return (passed: bool, message: str)."""
    with open(vel_path, encoding="utf-8") as handle:
        source = handle.read()

    if not os.path.exists(expected_path):
        return False, f"missing expected file: {os.path.basename(expected_path)} (run --generate)"

    exit_code, stdout = run_parser(parser_command, source)

    try:
        actual = json.loads(stdout) if stdout.strip() else None
    except json.JSONDecodeError:
        return False, f"parser did not emit valid JSON (exit {exit_code}): {stdout[:200]!r}"

    with open(expected_path, encoding="utf-8") as handle:
        expected = json.load(handle)

    if is_error:
        if exit_code == 0:
            return False, "expected a syntax error, parser succeeded"
        err = (actual or {}).get("error", {})
        if err.get("line") != expected["line"]:
            return False, f"error line: expected {expected['line']}, got {err.get('line')}"
        if expected["reason_contains"] not in (err.get("reason") or ""):
            return False, f"error reason should contain {expected['reason_contains']!r}, got {err.get('reason')!r}"
        return True, ""

    if exit_code != 0:
        return False, f"expected success, parser failed (exit {exit_code}): {actual}"
    if actual != expected:
        return False, "model mismatch (run with --generate to inspect, or diff the JSON)"
    return True, ""


def generate(parser_command):
    """Write expected files from the (trusted) parser output. Bootstrap / after grammar changes."""
    for name, vel_path, expected_path, is_error in discover_cases():
        with open(vel_path, encoding="utf-8") as handle:
            source = handle.read()
        exit_code, stdout = run_parser(parser_command, source)
        actual = json.loads(stdout)
        if is_error:
            err = actual["error"]
            payload = {"line": err["line"], "reason_contains": err["reason"]}
        else:
            payload = actual
        with open(expected_path, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        print(f"{DIM}wrote{RESET} {os.path.basename(expected_path)}")


def main(argv=None):
    argument_parser = argparse.ArgumentParser(description="Run the Veltro conformance suite")
    argument_parser.add_argument("--parser", default=DEFAULT_PARSER,
                                 help="command that reads .vel on stdin and writes the model JSON on stdout")
    argument_parser.add_argument("--generate", action="store_true",
                                 help="(re)write expected files from the parser output instead of checking")
    arguments = argument_parser.parse_args(argv)

    if arguments.generate:
        generate(arguments.parser)
        return 0

    passed = 0
    failed = 0
    for name, vel_path, expected_path, is_error in discover_cases():
        ok, message = check_case(arguments.parser, name, vel_path, expected_path, is_error)
        tag = "err" if is_error else "ok "
        if ok:
            passed += 1
            print(f"{GREEN}PASS{RESET} {DIM}[{tag}]{RESET} {name}")
        else:
            failed += 1
            print(f"{RED}FAIL{RESET} {DIM}[{tag}]{RESET} {name}  {RED}{message}{RESET}")

    print(f"\n{passed} passed, {failed} failed  ({passed + failed} cases)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
