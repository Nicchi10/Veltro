"""

bench/scale_bench.py

End-to-end token benchmark on a real Python project.

Pipeline:  project source  --extract-->  .vel  --parse-->  model  --export-->  PlantUML + Mermaid

All three artefacts come from the *same* model, so the comparison is fair:
identical types, members and relations. We then count tokens with tiktoken.

Run:
    python bench/scale_bench.py <package_dir> [--out-dir build]
    python bench/scale_bench.py "C:/.../rich/rich"
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Token benchmark of Veltro vs PlantUML vs Mermaid on a real project")
    parser.add_argument("package", help="path to the Python package directory")
    parser.add_argument("--out-dir", default="build", help="where to write the three artefacts (default: build)")
    arguments = parser.parse_args(argv)

    # 1. Extract -> .vel, 2. parse -> model, 3. export the other two formats
    vel_text, stats = extract_project(arguments.package)
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
    base = os.path.basename(os.path.normpath(arguments.package))
    extensions = {"Veltro": ".vel", "PlantUML": ".puml", "Mermaid": ".mmd"}
    for label, text in artefacts.items():
        path = os.path.join(arguments.out_dir, base + extensions[label])
        with open(path, "w", encoding="utf-8", newline="\n") as out_file:
            out_file.write(text)

    seen_types = stats["class"] + stats["interface"] + stats["enum"]
    print(f"project: {base}")
    print(f"modules: {stats['modules']}  types: {seen_types}  ({stats['class']} classes, {stats['interface']} interfaces, {stats['enum']} enums)")

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
