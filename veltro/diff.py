"""

veltro/diff.py

Two models, compared: what a '.vel' says against what the code says now.

A stale '.vel' is worse than no '.vel'. It validates, it queries, it slices, and
it answers questions about an architecture that no longer exists - which is the
one failure mode a documentation format cannot afford, because nothing about the
file looks wrong.

Comparison is by node ID, which is the model's primary key, and ORDER NEVER
MATTERS: two extractions of the same code may meet the files in a different
order, so a diff that reported that would cry drift on every run. Members are
compared as sets, the same definition of equality the conformance harness uses
for two parser implementations.

Pure functions over two models, so the CLI, a pre-commit hook and the viewer can
all ask the same question.

"""

import json
from typing import Any

# Order-insensitive: everything here is sorted before being compared
MEMBER_KEYS = ("fields", "methods", "values")


def member_key(member) -> str:
    """

    A stable string for one member, so a list of them can be sorted.

    Args:
        member: a field, method or enum value

    Returns:
        str: a deterministic key

    """
    return json.dumps(member, sort_keys=True, ensure_ascii=False)


def canonical_node(node: dict[str, Any]) -> str:
    """

    One node reduced to the facts it states, independent of ordering.

    Args:
        node (dict[str, Any]): a model node

    Returns:
        str: a deterministic string, equal for two nodes that say the same thing

    """
    reduced = {}
    for key in sorted(node):
        if key in MEMBER_KEYS:
            members = []
            for member in node[key]:
                members.append(member)
            reduced[key] = sorted(members, key=member_key)
        else:
            reduced[key] = node[key]
    return json.dumps(reduced, sort_keys=True, ensure_ascii=False)


def nodes_by_id(model: dict[str, Any]) -> dict:
    """
    The model's nodes keyed by id
    """
    found = {}
    for node in model.get("nodes", []):
        found[node["id"]] = node
    return found


def edge_keys(model: dict[str, Any]) -> set:
    """

    Every WRITTEN relation as a (from, kind, to) triple.

    Derived edges are left out on purpose: they are a function of the members, so
    a change in them is already reported as a changed node, and counting both
    would report one edit twice.

    Args:
        model (dict[str, Any]): a model

    Returns:
        set[tuple]: the written edges

    """
    keys = set()
    for edge in model.get("edges", []):
        if not edge.get("derived"):
            keys.add((edge["from"], edge["kind"], edge["to"]))
    return keys


def compare_models(documented: dict[str, Any], current: dict[str, Any]) -> dict:
    """

    What changed between the '.vel' on disk and a fresh extraction.

    'documented' is what the file claims, 'current' is what the code says now,
    so 'added' means "in the code, missing from the file".

    Args:
        documented (dict[str, Any]): the model parsed from the '.vel'
        current (dict[str, Any]): the model from re-extracting the source

    Returns:
        dict: 'added', 'removed' and 'changed' lists of node ids (sorted),
            'edges_added' and 'edges_removed' sets, and 'in_sync'

    """
    documented_nodes = nodes_by_id(documented)
    current_nodes = nodes_by_id(current)

    documented_ids = set(documented_nodes)
    current_ids = set(current_nodes)

    changed = []
    for node_id in sorted(documented_ids & current_ids):
        if canonical_node(documented_nodes[node_id]) != canonical_node(current_nodes[node_id]):
            changed.append(node_id)

    documented_edges = edge_keys(documented)
    current_edges = edge_keys(current)

    result = {
        "added": sorted(current_ids - documented_ids),
        "removed": sorted(documented_ids - current_ids),
        "changed": changed,
        "edges_added": sorted(current_edges - documented_edges),
        "edges_removed": sorted(documented_edges - current_edges),
    }
    result["in_sync"] = not any(result[key] for key in ("added", "removed", "changed", "edges_added", "edges_removed"))
    return result


def describe(comparison: dict, limit: int = 5) -> list:
    """

    The comparison as lines a person can read, worst first.

    Args:
        comparison (dict): from compare_models
        limit (int): how many ids to name per category

    Returns:
        list[str]: the report, empty when the two models agree

    """
    if comparison["in_sync"]:
        return []

    lines = []
    labels = (
        ("removed", "in the .vel but gone from the code"),
        ("added", "in the code but missing from the .vel"),
        ("changed", "declared differently now"),
    )
    for key, meaning in labels:
        ids = comparison[key]
        if not ids:
            continue
        lines.append(f"{len(ids)} types {meaning}:")
        for node_id in ids[:limit]:
            lines.append(f"    {node_id}")
        if len(ids) > limit:
            lines.append(f"    ... and {len(ids) - limit} more")

    for key, meaning in (("edges_removed", "relations gone"), ("edges_added", "relations new")):
        edges = comparison[key]
        if not edges:
            continue
        lines.append(f"{len(edges)} written {meaning}:")
        for edge in edges[:limit]:
            lines.append(f"    {edge[0]} {edge[1]} {edge[2]}")
        if len(edges) > limit:
            lines.append(f"    ... and {len(edges) - limit} more")

    return lines
