"""

bench/scale_bench.py

End-to-end token benchmark on a real project.

Pipeline:  project source  --extract-->  .vel  --parse-->  model  --export-->  PlantUML + Mermaid

All three artefacts come from the *same* model, so the comparison is fair:
identical types, members and relations. We then count tokens with tiktoken.

The input is either a Python package directory (extracted here with the Python
AST extractor) or an already-extracted '.vel' file (e.g. produced by the Java or
C# extractor), so the same command reproduces every row of the README table.

Run:
    python bench/scale_bench.py <package_dir>      # extract a Python package
    python bench/scale_bench.py examples/spring-beans.vel   # a pre-extracted .vel
"""

import argparse
import os
import sys

import tiktoken

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.python_ast import extract_project
from veltro.parser import parse_text
from veltro.export.plantuml import export_plantuml
from veltro.export.mermaid import export_mermaid

ENCODERS = ["cl100k_base", "o200k_base"]


def count_tokens(text: str, encoder_name: str) -> int:
    encoder = tiktoken.get_encoding(encoder_name)
    return len(encoder.encode(text))


def load_vel(source: str):
    """

    Get the (name, vel_text) for a source that is either a Python package
    directory (extracted here) or an existing '.vel' file (read as-is).

    Args:
        source (str): a package directory or a path ending in '.vel'

    Returns:
        (name, vel_text)

    """
    if os.path.isdir(source):
        vel_text, _stats = extract_project(source)
        name = os.path.basename(os.path.normpath(source))
    else:
        with open(source, encoding="utf-8") as vel_file:
            vel_text = vel_file.read()
        name = os.path.splitext(os.path.basename(source))[0]
    return name, vel_text


def count_kinds(model: dict) -> tuple:
    """
    Count classes / interfaces / enums and distinct modules in a parsed model
    """
    classes = interfaces = enums = 0
    modules = set()
    for node in model["nodes"]:
        modules.add(node["module"])
        if node["kind"] == "class":
            classes += 1
        elif node["kind"] == "interface":
            interfaces += 1
        elif node["kind"] == "enum":
            enums += 1
    return classes, interfaces, enums, len(modules)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Token benchmark of Veltro vs PlantUML vs Mermaid on a real project")
    parser.add_argument("source", help="a Python package directory or a .vel file")
    parser.add_argument("--out-dir", default="build", help="where to write the three artefacts (default: build)")
    arguments = parser.parse_args(argv)

    # 1. Load -> .vel (extract a package, or read a pre-extracted .vel),
    # 2. parse -> model, 3. export the other two formats from that same model
    name, vel_text = load_vel(arguments.source)
    model = parse_text(vel_text)
    plantuml_text = export_plantuml(model)
    mermaid_text = export_mermaid(model)

    artefacts = {
        "Veltro": vel_text,
        "PlantUML": plantuml_text,
        "Mermaid": mermaid_text,
    }

    # Write them out so they can be inspected
    os.makedirs(arguments.out_dir, exist_ok=True)
    extensions = {"Veltro": ".vel", "PlantUML": ".puml", "Mermaid": ".mmd"}
    for label, text in artefacts.items():
        path = os.path.join(arguments.out_dir, name + extensions[label])
        with open(path, "w", encoding="utf-8", newline="\n") as out_file:
            out_file.write(text)

    classes, interfaces, enums, module_count = count_kinds(model)
    seen_types = classes + interfaces + enums
    print(f"project: {name}")
    print(f"modules: {module_count}  types: {seen_types}  ({classes} classes, {interfaces} interfaces, {enums} enums)")

    for encoder_name in ENCODERS:
        veltro_tokens = count_tokens(vel_text, encoder_name)
        print(f"\n=== tokenizer: {encoder_name} ===")
        print(f"{'format':10} {'tokens':>8} {'vs Veltro':>10}")
        for label in ("Veltro", "PlantUML", "Mermaid"):
            tokens = count_tokens(artefacts[label], encoder_name)
            if label == "Veltro":
                delta = "--"
            else:
                delta = f"+{(tokens / veltro_tokens - 1) * 100:.0f}%"
            print(f"{label:10} {tokens:8} {delta:>10}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
