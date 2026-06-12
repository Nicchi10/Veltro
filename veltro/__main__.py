"""

veltro.__main__.py

Command line entry point:  python -m veltro <file.vel>

Parses a '.vel' file, prints a short summary, validates the result against
'model.schema.json' when the 'jsonschema' package is available, and writes the
JSON model next to the source (or to the path given with --out)

"""

import argparse
import json
import os
import sys
import jsonschema

from veltro.parser import parse_file, VeltroSyntaxError


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

def validate_model(model):
    """
    Validate the model against the schema
    """

    schema = load_schema()
    if schema is None:
        raise FileNotFoundError("[ERROR] - 'model.schema.json' not found'")

    try:
        jsonschema.validate(instance=model, schema=schema)
    except jsonschema.ValidationError as error:
        return f"[ERROR] - {error.message}"
    return "OK"

def summarise(model):
    """
    Counting the prints of what has been analyzed
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

def main(argv=None):
    
    parser = argparse.ArgumentParser(description="Parse a Veltro .vel file")
    parser.add_argument("source", help="path to the .vel file")
    parser.add_argument("--out", help="where to write the JSON model")
    parser.add_argument("--no-derive", action="store_true", help="do not derive association edges from field types")
    arguments = parser.parse_args(argv)

    try:
        model = parse_file(arguments.source, derive_associations=not arguments.no_derive)
    except VeltroSyntaxError as error:
        print(f"[ERROR] - syntax: {error}")
        return 1

    summarise(model)
    print(f"[INFO] - validation: {validate_model(model)}")

    if arguments.out:
        output_path = arguments.out
    else:
        base, _ = os.path.splitext(arguments.source)
        output_path = base + ".model.json"

    with open(output_path, "w", encoding="utf-8", newline="\n") as output_file:
        json.dump(model, output_file, indent=2, ensure_ascii=False)
        output_file.write("\n")
        
    print(f"[INFO] - written: {output_path}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
