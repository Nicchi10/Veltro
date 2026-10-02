"""

conformance/adapter_python.py

Reference adapter for the Veltro parser conformance contract.

The contract (see conformance/README.md): a conforming parser reads '.vel' text
on stdin and writes the model JSON on stdout. This adapter implements that over
'veltro.parser', so it is the executable definition of "parsed correctly" that
any second parser (TypeScript, Rust, ...) is measured against.

Run (normally the harness invokes it for you):
    python conformance/adapter_python.py < some.vel
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text, VeltroSyntaxError


def main():
    """
    Read '.vel' from stdin, write the model JSON to stdout
    """
    text = sys.stdin.read()
    try:
        model = parse_text(text)
    except VeltroSyntaxError as error:
        # Exiting non-zero IS the contract for a parse error (see README.md), so
        # the reference adapter has to demonstrate it properly: a readable line
        # on stderr, nothing on stdout, and no traceback.
        print(f"[ERROR] - syntax: {error}", file=sys.stderr)
        return 1
    json.dump(model, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
