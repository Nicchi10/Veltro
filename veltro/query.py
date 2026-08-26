"""

veltro/query.py

Queries over a type graph: the read side of Veltro.

The point is token frugality for an agent. A '.vel' of a real project is either
big enough to be worth summarising (pydantic is 5% of its own source) or too big
to read at all (Orleans is ~692k tokens), so a tool must answer a QUESTION with a
bounded payload instead of handing over the whole file:

    find    which types match this name           -> a few lines
    show    what does this one type look like     -> its '.vel' block
    deps    what does it touch, and what touches it
    map     a slice of the graph, still valid '.vel', to put in a context

Every function here is pure and works on the model (plus the optional source
index), so the CLI, the viewer and a future IDE plugin can share one
implementation rather than each inventing its own.

"""

import os

from veltro.export.vel import export_vel
from veltro.index import index_path_for, read_index, spans_of


def nodes_by_id(model: dict) -> dict:
    """
    Map every node id to its node
    """
    index = {}
    for node in model.get("nodes", []):
        index[node["id"]] = node
    return index


def load_index_beside(vel_path: str):
    """

    The source index that belongs to a '.vel', when it has been generated.

    Args:
        vel_path (str): path to the '.vel'

    Returns:
        dict or None: the index, or None when there is none on disk

    """
    path = index_path_for(vel_path)
    if not os.path.exists(path):
        return None
    return read_index(path)


def matches(node: dict, pattern: str) -> bool:
    """

    Whether a node answers to a search pattern.

    The pattern is matched case-insensitively against the simple name and the
    full id, so both 'silo' and 'Orleans.Runtime.Silo' find the same type.

    Args:
        node (dict): a model node
        pattern (str): the search text

    Returns:
        bool

    """
    if not pattern:
        return True
    needle = pattern.lower()
    return needle in node["name"].lower() or needle in node["id"].lower()


def find_types(model: dict, pattern: str, kind: str = None, module: str = None) -> list:
    """

    Every node matching a pattern, optionally narrowed by kind or module.

    Args:
        model (dict): a type-graph model
        pattern (str): text to look for in the name or the id
        kind (str): 'class' / 'interface' / 'enum', or None for any
        module (str): keep only nodes whose module starts with this, or None

    Returns:
        list[dict]: the matching nodes, in model order

    """
    found = []
    for node in model.get("nodes", []):
        if kind and node["kind"] != kind:
            continue
        if module and not node.get("module", "").startswith(module):
            continue
        if matches(node, pattern):
            found.append(node)
    return found


def resolve_one(model: dict, reference: str):
    """

    Turn a user-typed reference into a single node.

    Accepts a full id, or a simple name when it is unambiguous, because an agent
    should not have to know the module to ask about a type.

    Args:
        model (dict): a type-graph model
        reference (str): an id or a simple name

    Returns:
        (node, candidates): the node when it is unique (candidates empty), else
        (None, the competing nodes)

    """
    by_id = nodes_by_id(model)
    if reference in by_id:
        return by_id[reference], []

    candidates = []
    for node in model.get("nodes", []):
        if node["name"] == reference:
            candidates.append(node)

    if len(candidates) == 1:
        return candidates[0], []
    return None, candidates


def edges_of(model: dict, node_id: str) -> tuple:
    """

    The relations touching a node.

    Args:
        model (dict): a type-graph model
        node_id (str): the node to look at

    Returns:
        (outgoing, incoming): two lists of edges

    """
    outgoing = []
    incoming = []
    for edge in model.get("edges", []):
        if edge["from"] == node_id:
            outgoing.append(edge)
        if edge["to"] == node_id:
            incoming.append(edge)
    return outgoing, incoming


def neighbourhood_ids(model: dict, node_id: str, depth: int) -> list:
    """

    The node plus everything reachable from it within 'depth' relations,
    following edges in BOTH directions (what it uses and what uses it, which is
    what you need to understand a type before changing it).

    Args:
        model (dict): a type-graph model
        node_id (str): where to start
        depth (int): how many relations to follow

    Returns:
        list[str]: the ids, in discovery order, starting with node_id

    """
    known = {node_id}
    ordered = [node_id]
    frontier = [node_id]

    for _step in range(max(depth, 0)):
        next_frontier = []
        for current in frontier:
            outgoing, incoming = edges_of(model, current)
            for edge in outgoing:
                neighbour = edge["to"]
                if neighbour not in known:
                    known.add(neighbour)
                    ordered.append(neighbour)
                    next_frontier.append(neighbour)
            for edge in incoming:
                neighbour = edge["from"]
                if neighbour not in known:
                    known.add(neighbour)
                    ordered.append(neighbour)
                    next_frontier.append(neighbour)
        frontier = next_frontier

    return ordered


def sub_model(model: dict, wanted_ids) -> dict:
    """

    A smaller model holding only the given nodes, and the edges whose SOURCE is
    one of them.

    Keeping an edge whose target is outside the slice is deliberate: it tells
    the reader that the type extends something, even when the something is not
    part of what they asked for. Dropping it would silently amputate the type.

    Args:
        model (dict): the full model
        wanted_ids (iterable[str]): the ids to keep

    Returns:
        dict: a model matching model.schema.json

    """
    wanted = set(wanted_ids)

    nodes = []
    for node in model.get("nodes", []):
        if node["id"] in wanted:
            nodes.append(node)

    edges = []
    for edge in model.get("edges", []):
        if edge["from"] in wanted:
            edges.append(edge)

    return {"veltro": model.get("veltro", 1), "nodes": nodes, "edges": edges}


def slice_vel(model: dict, wanted_ids) -> str:
    """
    The '.vel' text of a slice: valid Veltro, small enough to put in a context
    """
    return export_vel(sub_model(model, wanted_ids))


def location_line(source_index: dict, node_id: str) -> str:
    """

    Where a type is declared, as one short string.

    Args:
        source_index (dict): a loaded index, or None
        node_id (str): the node to locate

    Returns:
        str: e.g. 'src/Silo.cs:25-692', several places joined by ', ', or ''
        when there is no index or the type is not in it

    """
    if not source_index:
        return ""

    parts = []
    for span in spans_of(source_index, node_id):
        parts.append(f"{span['file']}:{span['line']}-{span['end_line']}")
    return ", ".join(parts)
