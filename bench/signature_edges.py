"""

bench/signature_edges.py

What deriving edges from method signatures adds to each shipped example.

Issue #11 asked the question to settle before the derivation could ever become
the default: is a constructor-injected codebase's graph "closer to a list"
without it? If the edge count jumped by an order of magnitude, the answer would
be yes. This parses each example twice - as the parser does by default, and with
'derive_signatures=True' - and reports the difference, plus how many types have
no edge at all either way, which is the direct measure of an "empty" graph.

Run:
    python bench/signature_edges.py
    python bench/signature_edges.py examples/nest.vel

"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_file

DEFAULT_EXAMPLES = (
    "examples/pydantic.vel",
    "examples/spring-beans.vel",
    "examples/kafka-clients.vel",
    "examples/MediatR.vel",
    "examples/nest.vel",
    "examples/angular.vel",
    "examples/Orleans.vel",
)


def isolated_types(model: dict) -> int:
    """

    How many types take part in no edge at all, in either direction.

    Edges may point outside the model (an unresolved name such as an external
    base class), so only endpoints that are nodes of this model count.

    Args:
        model (dict): a parsed model

    Returns:
        int: the number of nodes no edge touches

    """
    node_ids = set()
    for node in model["nodes"]:
        node_ids.add(node["id"])

    touched = set()
    for edge in model["edges"]:
        if edge["from"] in node_ids:
            touched.add(edge["from"])
        if edge["to"] in node_ids:
            touched.add(edge["to"])
    return len(node_ids - touched)


def measure(path: str) -> dict:
    """

    The graph of one example, without and with signature-derived edges.

    Args:
        path (str): a '.vel'

    Returns:
        dict: type count, edge counts both ways, isolated types both ways

    """
    plain = parse_file(path)
    derived = parse_file(path, derive_signatures=True)
    return {
        "types": len(plain["nodes"]),
        "edges": len(plain["edges"]),
        "added": len(derived["edges"]) - len(plain["edges"]),
        "isolated_before": isolated_types(plain),
        "isolated_after": isolated_types(derived),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Edges added by deriving dependencies from method signatures")
    parser.add_argument("sources", nargs="*", help="the .vel files (default: every shipped example)")
    arguments = parser.parse_args(argv)

    sources = arguments.sources or list(DEFAULT_EXAMPLES)

    print(f"{'example':16} {'types':>6} {'edges':>7} {'+signatures':>12} {'ratio':>6} {'isolated types':>16}")
    for source in sources:
        path = os.path.join(REPO_ROOT, source)
        if not os.path.exists(path):
            print(f"[SKIP]   - {source}: not found")
            continue
        found = measure(path)
        name = os.path.splitext(os.path.basename(source))[0]
        ratio = found["added"] / found["edges"] if found["edges"] else 0
        isolated = f"{found['isolated_before']} -> {found['isolated_after']}"
        print(f"{name:16} {found['types']:>6,} {found['edges']:>7,} {found['added']:>+12,} {ratio:>5.1f}x {isolated:>16}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
