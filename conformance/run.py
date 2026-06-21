"""

conformance/run.py

Conformance harness: drive any Veltro parser through the contract and measure
it against the golden cases.

The parser-under-test is a COMMAND that reads '.vel' on stdin and writes the
model JSON on stdout (the contract). The harness feeds it each case in
'conformance/cases/<rule>.vel' and compares the JSON it prints against the
frozen 'conformance/cases/<rule>.expected.json'.

Run:
    python conformance/run.py                      # test the reference adapter
    python conformance/run.py -- node dist/cli.js  # test another implementation
    python conformance/run.py --update             # (re)write the golden outputs

Equality (the whole point -- see README.md): two models are equivalent when
they have the same version and the same SET of nodes (each with the same set of
fields and methods) and the same SET of edges. Ordering is NEVER significant, so
a parser that iterates a hash map in a different order still conforms.

"""

import argparse
import json
import os
import subprocess
import sys

CASES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cases")


def default_command():
    """
    The reference adapter command, used when the caller gives no '-- command'
    """
    adapter = os.path.join(os.path.dirname(os.path.abspath(__file__)), "adapter_python.py")
    return [sys.executable, adapter]


def sort_key(item) -> str:
    """
    A stable string key for any JSON value, so lists can be order-normalised
    """
    return json.dumps(item, sort_keys=True, ensure_ascii=False)


def canonicalize(model: dict) -> dict:
    """

    Reduce a model to its order-independent essence: the set of facts.

    Nodes, edges, and each node's fields and methods are sorted by a stable key,
    so two parsers that emit the same facts in a different order compare equal.
    This function IS the definition of model equality for the contract.

    Args:
        model (dict): a parsed model

    Returns:
        dict: the canonical form, safe to compare with '=='

    """
    canonical_nodes = []
    for node in model.get("nodes", []):
        canonical_node = dict(node)
        if "fields" in canonical_node:
            canonical_node["fields"] = sorted(canonical_node["fields"], key=sort_key)
        if "methods" in canonical_node:
            canonical_node["methods"] = sorted(canonical_node["methods"], key=sort_key)
        canonical_nodes.append(canonical_node)

    return {
        "veltro": model.get("veltro"),
        "nodes": sorted(canonical_nodes, key=sort_key),
        "edges": sorted(model.get("edges", []), key=sort_key),
    }


def run_adapter(command: list, vel_text: str) -> dict:
    """

    Feed one '.vel' to the parser-under-test and return the model it prints

    Args:
        command (list): the adapter command (reads stdin, writes stdout)
        vel_text (str): the case input

    Returns:
        dict: the parsed model JSON

    """
    completed = subprocess.run(
        command,
        input=vel_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"adapter failed ({completed.returncode}): {completed.stderr.strip()}")
    return json.loads(completed.stdout)


def find_cases() -> list:
    """
    Every case stem under cases/ that has a '.vel' input, sorted by name
    """
    stems = []
    for file_name in sorted(os.listdir(CASES_DIR)):
        if file_name.endswith(".vel"):
            stems.append(file_name[:-len(".vel")])
    return stems


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run the Veltro parser conformance suite")
    parser.add_argument("--update", action="store_true", help="write the adapter's output as the golden files (bless)")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="the parser-under-test, after '--' (default: the reference adapter)")
    arguments = parser.parse_args(argv)

    command = arguments.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        command = default_command()

    stems = find_cases()
    if not stems:
        print(f"[ERROR] - no cases found in {CASES_DIR}", file=sys.stderr)
        return 1

    passed = 0
    failed = 0
    for stem in stems:
        vel_path = os.path.join(CASES_DIR, stem + ".vel")
        expected_path = os.path.join(CASES_DIR, stem + ".expected.json")

        with open(vel_path, encoding="utf-8") as vel_file:
            vel_text = vel_file.read()

        actual = run_adapter(command, vel_text)

        if arguments.update:
            with open(expected_path, "w", encoding="utf-8", newline="\n") as expected_file:
                json.dump(actual, expected_file, indent=2, ensure_ascii=False)
                expected_file.write("\n")
            print(f"[UPDATE] - {stem}")
            continue

        with open(expected_path, encoding="utf-8") as expected_file:
            expected = json.load(expected_file)

        if canonicalize(actual) == canonicalize(expected):
            passed += 1
            print(f"[PASS]   - {stem}")
        else:
            failed += 1
            print(f"[FAIL]   - {stem}")
            print(" expected: " + sort_key(canonicalize(expected)))
            print(" actual:   " + sort_key(canonicalize(actual)))

    if arguments.update:
        print(f"[INFO] - blessed {len(stems)} cases")
        return 0

    print(f"[INFO] - {passed} passed, {failed} failed, {len(stems)} total")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
