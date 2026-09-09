"""

bench/query_cost.py

What a QUESTION costs, against reading the whole graph.

The token benchmark next door answers "is the format cheap?". This answers the
question that matters once a project is real: Orleans is ~688k tokens, so it
does not fit a context at any compression ratio, and the only useful number is
what a bounded answer costs instead. These are the figures quoted in CLI.md.

Every case runs the actual CLI in a subprocess, so what is counted is exactly
what a caller would receive on stdout, not an internal shortcut.

Run:
    python bench/query_cost.py
    python bench/query_cost.py examples/pydantic.vel --around BaseModel

"""

import argparse
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import tiktoken

# The README and CLI.md quote o200k_base, the same encoder the format benchmark uses
ENCODER = "o200k_base"

DEFAULT_SOURCE = os.path.join("examples", "Orleans.vel")
DEFAULT_TYPE = "Silo"
DEFAULT_MODULE = "Orleans.Runtime"


def count_tokens(text: str) -> int:
    """
    Tokens in a piece of text, with the encoder the published numbers use
    """
    encoder = tiktoken.get_encoding(ENCODER)
    return len(encoder.encode(text))


def run_cli(arguments: list) -> str:
    """

    Run the CLI and give back what it printed.

    Args:
        arguments (list[str]): the command line after 'python -m veltro'

    Returns:
        str: stdout

    Raises:
        RuntimeError: when the command failed, because a cheap answer that is
            also an error message would flatter the table

    """
    completed = subprocess.run(
        [sys.executable, "-m", "veltro"] + arguments,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"'{' '.join(arguments)}' exited {completed.returncode}: {completed.stderr.strip() or completed.stdout.strip()}")
    return completed.stdout


def build_cases(source: str, type_name: str, module: str) -> list:
    """

    The commands to measure, cheapest last.

    Args:
        source (str): the '.vel' to query
        type_name (str): the type for the type-scoped commands
        module (str): the module prefix for the module slice

    Returns:
        list[tuple]: (label, CLI arguments)

    """
    return [
        (f"map --module {module}", ["map", source, "--module", module]),
        (f"map --around {type_name} --depth 1", ["map", source, "--around", type_name, "--depth", "1"]),
        (f"show {type_name}", ["show", source, type_name]),
        (f"deps {type_name}", ["deps", source, type_name]),
    ]


# The same table is quoted in two places, which is two chances to go stale
DOCUMENTS = ("README.md", "CLI.md")

TABLE_HEADER = "| command | tokens | share of the file |"


def documented_rows(path: str) -> dict:
    """

    The query-cost table as a document states it.

    Args:
        path (str): a markdown file that may quote the table

    Returns:
        dict: command label -> token count, empty when the file has no table

    """
    with open(path, encoding="utf-8") as document:
        lines = document.read().splitlines()

    start = None
    for position, line in enumerate(lines):
        if line.strip() == TABLE_HEADER:
            start = position
            break
    if start is None:
        return {}

    rows = {}
    # +2 skips the header and the '|---|' separator under it
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = line.strip().strip("|").split("|")
        label = cells[0].strip().strip("`")
        rows[label] = int(re.sub(r"[^0-9]", "", cells[1]))
    return rows


def check_documents(measured: dict) -> int:
    """

    Compare every documented copy of the table against what was just measured.

    Args:
        measured (dict): command label -> token count

    Returns:
        int: how many rows disagree

    """
    wrong = 0
    for name in DOCUMENTS:
        path = os.path.join(REPO_ROOT, name)
        rows = documented_rows(path)
        if not rows:
            print(f"[FAIL]   - {name}: the query-cost table is gone")
            wrong += 1
            continue

        # counted per document: one bad file must not hide that the other is fine
        here = 0
        for label in measured:
            if label not in rows:
                print(f"[FAIL]   - {name}: no row for '{label}'")
                here += 1
            elif rows[label] != measured[label]:
                print(f"[FAIL]   - {name}: '{label}' says {rows[label]:,}, measured {measured[label]:,}")
                here += 1
        if not here:
            print(f"[OK]     - {name}: all {len(measured)} rows reproduce")
        wrong += here
    return wrong


def main(argv=None):
    parser = argparse.ArgumentParser(description="What a bounded answer costs against reading the whole .vel")
    parser.add_argument("source", nargs="?", default=DEFAULT_SOURCE, help=f"the .vel to query (default: {DEFAULT_SOURCE})")
    parser.add_argument("--around", default=DEFAULT_TYPE, help=f"the type to ask about (default: {DEFAULT_TYPE})")
    parser.add_argument("--module", default=DEFAULT_MODULE, help=f"the module prefix to slice (default: {DEFAULT_MODULE})")
    parser.add_argument("--check", action="store_true", help="fail when README.md or CLI.md no longer quote these numbers")
    arguments = parser.parse_args(argv)

    path = os.path.join(REPO_ROOT, arguments.source)
    if not os.path.exists(path):
        print(f"[ERROR] - no such file: {arguments.source}")
        return 1

    with open(path, encoding="utf-8") as source_file:
        whole = count_tokens(source_file.read())

    print(f"[INFO] - {arguments.source}: {whole:,} tokens read whole")
    print()
    print(f"{'command':40} {'tokens':>10} {'share':>9}")

    measured = {}
    for label, cli_arguments in build_cases(arguments.source, arguments.around, arguments.module):
        try:
            output = run_cli(cli_arguments)
        except RuntimeError as error:
            print(f"{label:40} {'-':>10} {'-':>9}   {error}")
            continue
        tokens = count_tokens(output)
        measured[label] = tokens
        print(f"{label:40} {tokens:>10,} {tokens / whole * 100:>8.2f}%")

    if not arguments.check:
        return 0

    # The documented table is the default one, so checking a different query would compare rows that were never published
    defaults = (arguments.source == DEFAULT_SOURCE.replace(os.sep, "/") or arguments.source == DEFAULT_SOURCE)
    if not defaults or arguments.around != DEFAULT_TYPE or arguments.module != DEFAULT_MODULE:
        print("[ERROR] - --check only makes sense on the default query, which is the one the docs quote")
        return 1

    print()
    if check_documents(measured):
        print("[ERROR] - the docs no longer match what the CLI costs")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
