"""

eval/generate.py

STEP 1 of the LLM comprehension eval.

From a Python package (or an existing .vel file) it produces, under --out-dir:

    <name>.vel / <name>.mmd / <name>.puml   the three "subjects" (same model)
    <name>.questions.json                   structural questions + ground-truth answers

The ground truth is computed directly from the type-graph model, so every
answer is a fact and the later scoring step is automatic.

Run:
    python eval/generate.py examples/pydantic.vel
    python eval/generate.py path/to/package --out-dir eval/subjects --limit 10
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.python_ast import extract_project
from veltro.parser import parse_text
from veltro.export.plantuml import export_plantuml
from veltro.export.mermaid import export_mermaid
from veltro.export.d2 import export_d2


def load_model(source: str):
    """

    Get the (name, vel_text, model) for a source that is either a package
    directory (extracted) or an existing .vel file (parsed)

    """
    if os.path.isdir(source):
        vel_text, _stats = extract_project(source)
        name = os.path.basename(os.path.normpath(source))
    else:
        with open(source, encoding="utf-8") as vel_file:
            vel_text = vel_file.read()
        name = os.path.splitext(os.path.basename(source))[0]

    model = parse_text(vel_text)
    return name, vel_text, model


def name_index(model: dict) -> dict:
    """
    Map node id -> simple name (edges store ids, questions use names)
    """
    index = {}
    for node in model["nodes"]:
        index[node["id"]] = node["name"]
    return index


def node_id(node: dict) -> str:
    """
    Sort key: a node's id. A named function so we avoid a lambda
    """
    return node["id"]


def append_question(questions: list, qtype: str, subject: str, prompt: str, answer) -> None:
    """

    Append one question to the list, numbering it from the current length.

    Args:
        questions (list): the list being built (modified in place)
        qtype (str): the question family
        subject (str): the type the question is about
        prompt (str): the natural-language question
        answer: the ground-truth answer (a fact from the model)

    """
    number = len(questions) + 1
    question = {
        "id": f"q{number}",
        "type": qtype,
        "subject": subject,
        "prompt": prompt,
        "answer": answer,
    }
    questions.append(question)


def build_questions(model: dict, limit: int) -> list:
    """

    Build structural questions whose answers come from the graph itself.

    Args:
        model (dict): a type-graph model
        limit (int): max questions per question-type (keeps the set bounded)

    Returns:
        list[dict]: each {id, type, subject, prompt, answer}

    """
    nodes = model["nodes"]
    edges = model["edges"]
    id_to_name = name_index(model)

    questions = []

    # 1. Who extends / implements a given type?
    implementors = {}
    for edge in edges:
        if edge["kind"] in ("impl", "extend"):
            target = id_to_name.get(edge["to"], edge["to"])
            child = id_to_name.get(edge["from"], edge["from"])
            implementors.setdefault(target, set()).add(child)

    for target in sorted(implementors)[:limit]:
        prompt = (
            f"List every type that extends or implements '{target}'. "
            f"Answer with type names only."
        )
        append_question(questions, "implementors", target, prompt, sorted(implementors[target]))

    # 2. What does a type reference or inherit (its outgoing relations)?
    outgoing = {}
    for edge in edges:
        source = id_to_name.get(edge["from"], edge["from"])
        destination = id_to_name.get(edge["to"], edge["to"])
        outgoing.setdefault(source, set()).add(destination)

    for source in sorted(outgoing)[:limit]:
        prompt = ( f"List every type that '{source}' references or inherits (its outgoing relations)")
        append_question(questions, "depends_on", source, prompt, sorted(outgoing[source]))

    # 3. Which module is a type defined in?
    for node in sorted(nodes, key=node_id)[:limit]:
        prompt = f"Which module is the type '{node['name']}' defined in?"
        append_question(questions, "module_of", node["name"], prompt, node["module"])

    # Only classes and interfaces carry members
    typed_nodes = []
    for node in nodes:
        if node["kind"] in ("class", "interface"):
            typed_nodes.append(node)

    # 4. How many public methods does a type declare?
    for node in sorted(typed_nodes, key=node_id)[:limit]:
        public_method_count = 0
        for method in node.get("methods", []):
            if method["vis"] == "+":
                public_method_count += 1
        prompt = f"How many public methods does '{node['name']}' declare?"
        append_question(questions, "public_method_count", node["name"], prompt, public_method_count)

    # 5. Which fields of a type have a generic / collection type?
    for node in sorted(typed_nodes, key=node_id)[:limit]:
        generic_fields = []
        for field in node.get("fields", []):
            if "<" in field["type"]:
                generic_fields.append(field["name"])
        prompt = (f"Which fields of '{node['name']}' have a generic or collection type (e.g. a List, Dict, Optional, ...)? Answer with field names only")
        append_question(questions, "collection_fields", node["name"], prompt, sorted(generic_fields))

    return questions


def write_subjects(name: str, vel_text: str, model: dict, out_dir: str) -> None:
    """
    Render the three subjects into out_dir
    """
    os.makedirs(out_dir, exist_ok=True)

    artefacts = {
        ".vel": vel_text,
        ".puml": export_plantuml(model),
        ".mmd": export_mermaid(model),
        ".d2": export_d2(model),
    }
    for extension, text in artefacts.items():
        path = os.path.join(out_dir, name + extension)
        with open(path, "w", encoding="utf-8", newline="\n") as out_file:
            out_file.write(text)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate eval subjects and ground-truth questions")
    parser.add_argument("source", help="a package directory or a .vel file")
    parser.add_argument("--out-dir", default="eval/subjects")
    parser.add_argument("--limit", type=int, default=10, help="max questions per type (default 10)")
    arguments = parser.parse_args(argv)

    name, vel_text, model = load_model(arguments.source)
    questions = build_questions(model, arguments.limit)
    write_subjects(name, vel_text, model, arguments.out_dir)

    payload = {
        "project": name,
        "types": len(model["nodes"]),
        "questions": questions,
    }

    questions_path = os.path.join(arguments.out_dir, name + ".questions.json")
    with open(questions_path, "w", encoding="utf-8", newline="\n") as out_file:
        json.dump(payload, out_file, indent=2, ensure_ascii=False)
        out_file.write("\n")

    count_by_type = {}
    for question in questions:
        qtype = question["type"]
        count_by_type[qtype] = count_by_type.get(qtype, 0) + 1

    subjects_path = os.path.join(arguments.out_dir, name)
    print(f"project:   {name}  ({len(model['nodes'])} types)")
    print(f"subjects:  {subjects_path}.{{vel,puml,mmd}}")
    print(f"questions: {len(questions)} -> {questions_path}")
    for qtype in sorted(count_by_type):
        print(f"  {qtype:22} {count_by_type[qtype]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
