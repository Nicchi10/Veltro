"""

veltro.__main__.py

Command line entry point:  python -m veltro <file.vel>

Parses a '.vel' file, prints a short summary, validates the result against
'model.schema.json' (requires the 'jsonschema' package), and writes the
JSON model next to the source (or to the path given with --out)

"""

import argparse
import json
import os
import sys
import jsonschema

from veltro.parser import parse_file, VeltroSyntaxError
from veltro.export.vel import render_node
from veltro.index import read_span, spans_of
from veltro.query import (edges_of, find_types, load_index_beside, location_line,
                          neighbourhood_ids, resolve_one, slice_vel)


def load_schema():
    """
    Load model.schema.json from the repository root, if it is there
    """
    
    here = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(here)
    schema_path = os.path.join(repo_root, "model.schema.json")
    if not os.path.exists(schema_path):
        return None
    with open(schema_path, encoding="utf-8") as schema_file:
        return json.load(schema_file)

def find_duplicate_ids(model: dict) -> list:
    """

    Every node id that appears more than once, in first-seen order.

    A node id is the model's primary key: edges are (from, to) pairs of ids, so
    an id carried by two nodes makes a link ambiguous, and every consumer has to
    invent its own tie-break (keep the first? the last?) to survive. JSON Schema
    can require whole array items to be unique but cannot require ONE PROPERTY
    to be unique across items, so this promise has to be checked in code.

    The parser merges repeated declarations, so a model it produces is always
    clean; this guards the models that reach the schema another way (a second
    parser implementation, a PlantUML import, a hand-edited JSON).

    Args:
        model (dict): a type-graph model

    Returns:
        list[str]: the duplicated ids, empty when the model is well formed

    """
    seen = set()
    duplicates = []
    for node in model.get("nodes", []):
        node_id = node.get("id")
        if node_id in seen:
            if node_id not in duplicates:
                duplicates.append(node_id)
            continue
        seen.add(node_id)
    return duplicates

def validate_model(model: dict):
    """
    Validate the model against the schema, then against the constraints the
    schema cannot express (unique node ids)
    """

    schema = load_schema()
    if schema is None:
        raise FileNotFoundError("[ERROR] - 'model.schema.json' not found")

    try:
        jsonschema.validate(instance=model, schema=schema)
    except jsonschema.ValidationError as error:
        return f"[ERROR] - {error.message}"

    duplicates = find_duplicate_ids(model)
    if duplicates:
        shown = ", ".join(duplicates[:3])
        if len(duplicates) > 3:
            shown += f", ... (+{len(duplicates) - 3} more)"
        return f"[ERROR] - node ids must be unique, {len(duplicates)} repeated: {shown}"

    return "OK"

def summarise(model: dict):
    """
    Count and print what has been parsed
    """
    
    nodes = model["nodes"]
    edges = model["edges"]

    classes = 0
    interfaces = 0
    enums = 0
    for node in nodes:
        if node["kind"] == "class":
            classes += 1
        elif node["kind"] == "interface":
            interfaces += 1
        elif node["kind"] == "enum":
            enums += 1

    explicit_edges = 0
    derived_edges = 0
    for edge in edges:
        if edge.get("derived"):
            derived_edges += 1
        else:
            explicit_edges += 1

    print(f"[INFO] - nodes: {len(nodes)}  ({classes} classes, {interfaces} interfaces, {enums} enums)")
    print(f"[INFO] - edges: {len(edges)}  ({explicit_edges} written, {derived_edges} derived)")

# ============ COMMANDS ============

def command_parse(arguments) -> int:
    """
    Parse a '.vel', report it, validate it, and write the JSON model
    """
    try:
        model = parse_file(arguments.source, derive_associations=not arguments.no_derive)
    except VeltroSyntaxError as error:
        print(f"[ERROR] - syntax: {error}")
        return 1

    summarise(model)
    validation = validate_model(model)
    print(f"[INFO] - validation: {validation}")

    if arguments.out:
        output_path = arguments.out
    else:
        base, _ = os.path.splitext(arguments.source)
        output_path = base + ".model.json"

    with open(output_path, "w", encoding="utf-8", newline="\n") as output_file:
        json.dump(model, output_file, indent=2, ensure_ascii=False)
        output_file.write("\n")

    print(f"[INFO] - written: {output_path}")

    # A model that breaks the contract must not pass quietly: the file is still written (it is what you need to debug), but the exit code says it failed
    if validation != "OK":
        return 1
    return 0


def load_for_query(source: str):
    """

    Read a '.vel' and the source index sitting next to it, for a read-only
    command.

    Args:
        source (str): path to the '.vel'

    Returns:
        (model, source_index): the index is None when it has not been generated

    """
    model = parse_file(source)
    return model, load_index_beside(source)


def command_find(arguments) -> int:
    """
    List the types whose name or id matches a pattern
    """
    model, source_index = load_for_query(arguments.source)
    found = find_types(model, arguments.pattern, arguments.kind, arguments.module)

    shown = found[:arguments.limit]
    for node in shown:
        where = location_line(source_index, node["id"])
        line = f"{node['id']}  {node['kind']}"
        if where:
            line += "  " + where
        print(line)

    if not found:
        print(f"[INFO] - nothing matches '{arguments.pattern}'")
    elif len(found) > len(shown):
        print(f"[INFO] - {len(shown)} of {len(found)} shown, raise --limit for more")
    return 0


def report_ambiguous(reference: str, candidates: list) -> int:
    """
    Tell the caller which types a bare name could have meant
    """
    if not candidates:
        print(f"[ERROR] - no type called '{reference}'")
        return 1
    print(f"[ERROR] - '{reference}' is declared in {len(candidates)} modules, say which:")
    for node in candidates:
        print("  " + node["id"])
    return 1


def command_show(arguments) -> int:
    """
    Print one type as '.vel', with where it lives and optionally its source
    """
    model, source_index = load_for_query(arguments.source)
    node, candidates = resolve_one(model, arguments.type)
    if node is None:
        return report_ambiguous(arguments.type, candidates)

    print("module " + node["module"])
    for line in render_node(node):
        print(line)

    outgoing, incoming = edges_of(model, node["id"])
    written = []
    for edge in outgoing:
        if not edge.get("derived"):
            written.append(f"{edge['kind']} {edge['to']}")
    if written:
        print("rel " + ", ".join(written))

    # With --code each block prints its own header, so the summary line would only repeat it.
    if not arguments.code:
        where = location_line(source_index, node["id"])
        if where:
            print("# " + where)
        elif source_index is None:
            print("# no source index: run the extractor to create one")

    if arguments.code:
        if source_index is None:
            print("[ERROR] - --code needs a source index next to the .vel")
            return 1
        spans = spans_of(source_index, node["id"])
        if not spans:
            print(f"[ERROR] - the index does not know where '{node['id']}' is")
            return 1
        for span in spans:
            print()
            print(f"# {span['file']}:{span['line']}-{span['end_line']}")
            print(read_span(source_index, span, arguments.root).rstrip())
    return 0


def command_deps(arguments) -> int:
    """
    List what a type touches and what touches it
    """
    model, _source_index = load_for_query(arguments.source)
    node, candidates = resolve_one(model, arguments.type)
    if node is None:
        return report_ambiguous(arguments.type, candidates)

    outgoing, incoming = edges_of(model, node["id"])

    if arguments.direction in ("out", "both"):
        print(f"out ({len(outgoing)}):")
        for edge in outgoing[:arguments.limit]:
            derived = "  (derived)" if edge.get("derived") else ""
            print(f"  {edge['kind']:10} {edge['to']}{derived}")

    if arguments.direction in ("in", "both"):
        print(f"in ({len(incoming)}):")
        for edge in incoming[:arguments.limit]:
            derived = "  (derived)" if edge.get("derived") else ""
            print(f"  {edge['kind']:10} {edge['from']}{derived}")
    return 0


def command_map(arguments) -> int:
    """
    Print a slice of the graph as '.vel', ready to drop into a context
    """
    model, _source_index = load_for_query(arguments.source)

    if arguments.around:
        node, candidates = resolve_one(model, arguments.around)
        if node is None:
            return report_ambiguous(arguments.around, candidates)
        wanted = neighbourhood_ids(model, node["id"], arguments.depth)
    elif arguments.module:
        wanted = []
        for node in find_types(model, "", None, arguments.module):
            wanted.append(node["id"])
    else:
        wanted = []
        for node in model["nodes"]:
            wanted.append(node["id"])

    print(slice_vel(model, wanted), end="")
    return 0


# ============ CLI ============

# The bare form 'python -m veltro file.vel' predates the subcommands and is what
# the docs and everyone's muscle memory use, so it keeps working as 'parse'.
COMMANDS = ("parse", "find", "show", "deps", "map")


def normalise_argv(argv: list) -> list:
    """

    Insert the implicit 'parse' when the first argument is a file rather than a
    command.

    Args:
        argv (list[str]): the arguments as given

    Returns:
        list[str]: the arguments with a command in front

    """
    if argv and not argv[0].startswith("-") and argv[0] not in COMMANDS:
        return ["parse"] + argv
    return argv


def build_parser():
    """
    The argument parser for every subcommand
    """
    parser = argparse.ArgumentParser(prog="veltro", description="Read and query a Veltro type graph")
    subparsers = parser.add_subparsers(dest="command", required=True)

    parse_command = subparsers.add_parser("parse", help="parse a .vel, validate it, write the JSON model")
    parse_command.add_argument("source", help="path to the .vel file")
    parse_command.add_argument("--out", help="where to write the JSON model")
    parse_command.add_argument("--no-derive", action="store_true", help="do not derive association edges from field types")
    parse_command.set_defaults(run=command_parse)

    find_command = subparsers.add_parser("find", help="list the types matching a name")
    find_command.add_argument("source", help="path to the .vel file")
    find_command.add_argument("pattern", nargs="?", default="", help="text to look for in the name or the id")
    find_command.add_argument("--kind", choices=["class", "interface", "enum"], help="keep only this kind")
    find_command.add_argument("--module", help="keep only modules starting with this")
    find_command.add_argument("--limit", type=int, default=20, help="how many to print (default 20)")
    find_command.set_defaults(run=command_find)

    show_command = subparsers.add_parser("show", help="print one type, and optionally its source")
    show_command.add_argument("source", help="path to the .vel file")
    show_command.add_argument("type", help="a node id, or a simple name when unambiguous")
    show_command.add_argument("--code", action="store_true", help="also print the source, using the index")
    show_command.add_argument("--root", help="read the source from here instead of the index's root")
    show_command.set_defaults(run=command_show)

    deps_command = subparsers.add_parser("deps", help="what a type touches, and what touches it")
    deps_command.add_argument("source", help="path to the .vel file")
    deps_command.add_argument("type", help="a node id, or a simple name when unambiguous")
    deps_command.add_argument("--direction", choices=["in", "out", "both"], default="both")
    deps_command.add_argument("--limit", type=int, default=30, help="how many per direction (default 30)")
    deps_command.set_defaults(run=command_deps)

    map_command = subparsers.add_parser("map", help="print a slice of the graph as .vel")
    map_command.add_argument("source", help="path to the .vel file")
    map_command.add_argument("--module", help="only the types of this module (prefix match)")
    map_command.add_argument("--around", help="only the neighbourhood of this type")
    map_command.add_argument("--depth", type=int, default=1, help="how many relations to follow from --around (default 1)")
    map_command.set_defaults(run=command_map)

    return parser


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]

    parser = build_parser()
    arguments = parser.parse_args(normalise_argv(list(argv)))
    return arguments.run(arguments)

if __name__ == "__main__":
    sys.exit(main())
