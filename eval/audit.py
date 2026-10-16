"""

eval/audit.py

STEP 2 of eval/DESIGN.md: before anyone is charged for an API call, answer the
oracle's questions from the '.vel' ITSELF and see where it disagrees with the
source.

Two numbers come out, and they are different questions:

    THE CEILING. For each family, what could a perfect reader of the '.vel'
    possibly answer? If the format does not carry the fact, no model reading it
    can score, and a later low number says nothing about comprehension. Knowing
    the ceiling first is what stops a paid run from being read as a reading-
    comprehension result when it is a format-coverage result.

    THE DISAGREEMENTS. Where the '.vel' and the source say different things.
    eval/DESIGN.md calls these extractor bugs and says they are fixed before
    anything is published - but only after each one has been looked at, because
    some disagreements are a deliberate modelling choice rather than a mistake,
    and those belong in the SCORING RULE instead (see ACCEPTED_OMISSIONS).

It also reports how much the question set itself changes under rules R1 and R2,
which is the first piece of evidence that the design document was needed.

Nothing here calls an API.

Run:
    python eval/audit.py venv/Lib/site-packages/jsonschema
    python eval/audit.py ./pydantic/pydantic --limit 25 --show 5

"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval import oracle
from eval.generate import build_questions as build_old_questions
from veltro.extract.python_ast import extract_project
from veltro.parser import parse_text

# Bases that every subject may leave out of an 'inherits' answer without being wrong. 
# They are type-system scaffolding rather than domain parents, and three of the six subjects 
# promote them to a KIND instead of a relation: Veltro writes 'class A(Protocol)' as 'interface A' and 'class A(ABC)' as 'class abstract A'
# The oracle still reports them, because it reports what the source says. 
# This set belongs to the SCORER, and it applies to every subject equally which is the only thing that keeps it from being a favour to Veltro.
ACCEPTED_OMISSIONS = frozenset({
    "object", "Generic", "Protocol", "ABC", "ABCMeta",
    "Enum", "IntEnum", "StrEnum", "Flag", "IntFlag",
})


# ============ ANSWERING FROM THE MODEL ============

def nodes_by_name(model: dict) -> dict:
    """

    Map a simple type name to its node, for the names that are unique.

    Args:
        model (dict): a parsed model

    Returns:
        dict: name -> node

    """
    seen = {}
    duplicated = set()
    for node in model["nodes"]:
        if node["name"] in seen:
            duplicated.add(node["name"])
        seen[node["name"]] = node
    for name in duplicated:
        del seen[name]
    return seen


def name_of_id(model: dict) -> dict:
    """

    Map a node id to its simple name. An edge may point at a bare name the
    model does not declare, which stays as it is.

    Args:
        model (dict): a parsed model

    Returns:
        dict: id -> simple name

    """
    names = {}
    for node in model["nodes"]:
        names[node["id"]] = node["name"]
    return names


def written_inheritance(model: dict) -> dict:
    """

    The inheritance written in the '.vel': child name -> parent names.

    Derived associations are not inheritance and are left out.

    Args:
        model (dict): a parsed model

    Returns:
        dict: name -> sorted list of parent names

    """
    names = name_of_id(model)
    parents = {}
    for edge in model["edges"]:
        if edge["kind"] not in ("extend", "impl"):
            continue
        if edge.get("derived"):
            continue
        child = names.get(edge["from"], edge["from"])
        parent = names.get(edge["to"], edge["to"])
        parents.setdefault(child, set()).add(parent)

    answer = {}
    for child in parents:
        answer[child] = sorted(parents[child])
    return answer


def answer_inherits(model: dict, name: str) -> list:
    """
    What the '.vel' says a type inherits from
    """
    return written_inheritance(model).get(name, [])


def answer_implementors(model: dict, name: str) -> list:
    """
    What the '.vel' says extends or implements a type
    """
    inheritance = written_inheritance(model)
    children = []
    for child in sorted(inheritance):
        if name in inheritance[child]:
            children.append(child)
    return children


def answer_defined_in(model: dict, name: str) -> str:
    """

    Where the '.vel' says a type lives.

    The '.vel' carries a MODULE, never a file: the file lives in the sidecar
    index, which is not part of what a model is shown. So the answer is the
    dotted module, and comparing it to the oracle's path is the scorer's job
    (see same_location).

    Args:
        model (dict): a parsed model
        name (str): a type name

    Returns:
        str: the module, or "" when the type is not in the model

    """
    node = nodes_by_name(model).get(name)
    if node is None:
        return ""
    return node["module"]


def answer_members(model: dict, name: str) -> int:
    """

    How many public methods the '.vel' declares for a type.

    Args:
        model (dict): a parsed model
        name (str): a type name

    Returns:
        int: the count, or -1 when the type is not in the model

    """
    node = nodes_by_name(model).get(name)
    if node is None:
        return -1
    total = 0
    for method in node.get("methods", []):
        if method["vis"] == "+":
            total += 1
    return total


def veltro_type_to_python(type_string: str) -> str:
    """

    A rendered Veltro type written back as a Python annotation, so that the
    ONE collection rule in the oracle decides both sides.

    'List<str>' -> 'List[str]', 'int?' -> 'int', 'Mapping | bool' unchanged.

    Having a second rule here was a real bug, not a hypothetical one: the first
    version read only the head of the type, so 'Mapping | bool' came back as not
    a collection and the audit reported an extractor bug that did not exist. The
    '.vel' carried the union perfectly well; the reader could not read it.

    Args:
        type_string (str): a type as the '.vel' writes it

    Returns:
        str: the same type in Python annotation syntax

    """
    text = type_string.strip().replace("<", "[").replace(">", "]")
    # a trailing '?' is Veltro's Optional, and Optional alone isn't a collection
    while text.endswith("?"):
        text = text[:-1].strip()
    return text


def answer_field_types(model: dict, name: str) -> list:
    """

    Which fields the '.vel' shows holding a collection.

    Args:
        model (dict): a parsed model
        name (str): a type name

    Returns:
        list[str]: sorted field names

    """
    node = nodes_by_name(model).get(name)
    if node is None:
        return []
    found = []
    for field in node.get("fields", []):
        if field["vis"] != "+":
            continue
        if oracle.is_collection(veltro_type_to_python(field["type"])):
            found.append(field["name"])
    return sorted(found)


ANSWERERS = {
    "inherits": answer_inherits,
    "implementors": answer_implementors,
    "defined_in": answer_defined_in,
    "members": answer_members,
    "field_types": answer_field_types,
}


# ============ COMPARING AN ANSWER TO THE TRUTH ============

def module_of_path(path: str) -> str:
    """

    The dotted module a source path denotes.

    'pydantic/main.py' -> 'pydantic.main', 'pydantic/__init__.py' ->
    'pydantic'. The Python extractor roots its index so that a file and a
    module read as the same thing, which is what makes this comparison legal
    rather than generous.

    Args:
        path (str): a POSIX-style relative path

    Returns:
        str: the dotted module

    """
    text = path
    if text.endswith(".py"):
        text = text[:-3]
    if text.endswith("/__init__"):
        text = text[:-len("/__init__")]
    return text.replace("/", ".")


def same_location(truth: str, given: str) -> bool:
    """

    Whether two location answers name the same place, one as a path and one as
    a module.

    Args:
        truth (str): the oracle's answer, a path
        given (str): the subject's answer

    Returns:
        bool

    """
    if not given:
        return False
    if truth == given:
        return True
    expected = module_of_path(truth)
    # the extractor's module path may be rooted above the oracle's, so a suffix match is the honest comparison ('main' vs 'pydantic.main')
    return expected == given or expected.endswith("." + given) or given.endswith("." + expected)


def compare_lists(truth: list, given: list, accepted_omissions=frozenset()) -> bool:
    """

    Whether a list answer is right, allowing declared omissions.

    Args:
        truth (list): the oracle's answer
        given (list): the subject's answer
        accepted_omissions (frozenset): names a subject may leave out

    Returns:
        bool

    """
    expected = set(item for item in truth if item not in accepted_omissions)
    return set(given) == expected


def judge(question: dict, given) -> str:
    """

    Compare one answer from the model to the oracle's truth.

    Args:
        question (dict): an oracle question
        given: what the model says

    Returns:
        str: 'agree' or 'disagree'

    """
    family = question["type"]
    truth = question["answer"]

    if family == "defined_in":
        return "agree" if same_location(truth, given) else "disagree"
    if family == "members":
        return "agree" if truth == given else "disagree"
    if family == "inherits":
        return "agree" if compare_lists(truth, given, ACCEPTED_OMISSIONS) else "disagree"
    return "agree" if compare_lists(truth, given) else "disagree"


# ============ THE AUDIT ============

def audit(model: dict, questions: list) -> dict:
    """

    Answer every question from the model and record the outcome.

    Args:
        model (dict): a parsed model
        questions (list): the oracle's questions

    Returns:
        dict: family -> {'agree', 'disagree', 'absent', 'cases'}

    """
    outcome = {}
    for question in questions:
        family = question["type"]
        record = outcome.setdefault(family, {"agree": 0, "disagree": 0, "absent": 0, "cases": []})

        if "veltro" not in question["expressible_in"]:
            # the format does not carry this at all: absent, never wrong
            record["absent"] += 1
            continue

        given = ANSWERERS[family](model, question["subject"])
        verdict = judge(question, given)
        record[verdict] += 1
        if verdict == "disagree":
            record["cases"].append({
                "subject": question["subject"],
                "source": question["answer"],
                "vel": given,
            })
    return outcome


def ceiling(record: dict) -> str:
    """

    The share of a family a perfect reader of the '.vel' could answer.

    Args:
        record (dict): one family's outcome

    Returns:
        str: e.g. '8/10' or 'not expressible'

    """
    asked = record["agree"] + record["disagree"] + record["absent"]
    if record["absent"] == asked:
        return "not expressible"
    return f"{record['agree']}/{asked}"


def compare_question_sets(model: dict, new_questions: list, limit: int) -> dict:
    """

    How much the question set changes under R1 and R2.

    Args:
        model (dict): a parsed model
        new_questions (list): the oracle's set
        limit (int): the per-family limit both sets were built with

    Returns:
        dict: 'old' and 'new' family counts, and 'about_functions'

    """
    old_questions = build_old_questions(model, limit)

    old_counts = {}
    for question in old_questions:
        old_counts[question["type"]] = old_counts.get(question["type"], 0) + 1

    new_counts = oracle.summarise(new_questions)

    about_functions = 0
    for question in new_questions:
        if question["type"] in ("function_params", "callers"):
            about_functions += 1

    return {"old": old_counts, "new": new_counts, "about_functions": about_functions}


# ============ CLI ============

def main(argv=None):
    examples = (
        "examples:\n"
        "  python eval/audit.py venv/Lib/site-packages/jsonschema\n"
        "  python eval/audit.py ./pydantic/pydantic --limit 25 --show 5\n"
    )
    parser = argparse.ArgumentParser(
        description="Answer the oracle's questions from the '.vel' itself: the ceiling, and where the two disagree (eval/DESIGN.md step 2)",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repository", help="path to the Python package or repository")
    parser.add_argument("--limit", type=int, default=10, help="max questions per family (default: 10)")
    parser.add_argument("--show", type=int, default=3, help="how many disagreements to print per family (default: 3)")
    oracle.add_walk_arguments(parser)
    arguments = parser.parse_args(argv)

    report = oracle.new_report()
    table, calls = oracle.build_symbol_table(arguments.repository, arguments.include_tests, arguments.exclude, report)
    questions = oracle.build_questions(table, calls, arguments.limit)
    if not questions:
        print("[ERROR] - no questions could be built: nothing uniquely named was found")
        return 1

    vel_text, _stats, _index = extract_project(arguments.repository, arguments.include_tests, arguments.exclude)
    model = parse_text(vel_text)

    print(f"[INFO] - source: {table['files']} files, {len(table['classes'])} class names, {len(table['functions'])} function names")
    print(f"[INFO] - the .vel: {len(model['nodes'])} types, {len(model['edges'])} edges")
    print()

    outcome = audit(model, questions)
    disagreements = 0
    for family in sorted(outcome):
        record = outcome[family]
        disagreements += record["disagree"]
        print(f"[INFO] - {family:18} ceiling {ceiling(record):16} disagreements {record['disagree']}")
        for case in record["cases"][:arguments.show]:
            print(f"[DIFF] -     {case['subject']}")
            print(f"[DIFF] -         source: {case['source']}")
            print(f"[DIFF] -         .vel:   {case['vel']}")
        if len(record["cases"]) > arguments.show:
            print(f"[DIFF] -     and {len(record['cases']) - arguments.show} more")

    print()
    change = compare_question_sets(model, questions, arguments.limit)
    print(f"[INFO] - question set, old design: {sum(change['old'].values())} questions in {len(change['old'])} families")
    print(f"[INFO] - question set, this design: {len(questions)} questions in {len(change['new'])} families")
    print(f"[INFO] - of those, {change['about_functions']} ask about things Veltro does not model at all")
    print(f"[INFO] -     old families: {', '.join(sorted(change['old']))}")
    print(f"[INFO] -     new families: {', '.join(sorted(change['new']))}")

    if disagreements:
        print()
        print(f"[ERROR] - {disagreements} answers disagree with the source: look at each one before publishing a number")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
