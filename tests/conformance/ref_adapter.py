"""
Reference conformance adapter for the Python parser.

This is the canonical implementation of the conformance contract every
Veltro parser (Python today, TypeScript / Rust tomorrow) must satisfy:

stdin   <- the .vel source text (UTF-8)
stdout  <- on success: the model JSON (see model.schema.json), exit 0
            on a syntax error: {"error": {"line": <int>, "reason": <str>}}, exit 1

The harness (run.py) speaks only this contract, so it can drive a parser
written in any language as long as that language ships an executable obeying
the three rules above. Point the harness at another implementation with:

    python tests/conformance/run.py --parser "node dist/cli.js"
    python tests/conformance/run.py --parser "target/release/veltro-parse"

Run this adapter directly:

    python tests/conformance/ref_adapter.py < some.vel
"""

import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text, VeltroSyntaxError


def main() -> int:
    source = sys.stdin.read()
    try:
        model = parse_text(source)
    except VeltroSyntaxError as error:
        payload = {"error": {"line": error.line_number, "reason": error.reason}}
        json.dump(payload, sys.stdout, ensure_ascii=False)
        sys.stdout.write("\n")
        return 1

    json.dump(model, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
