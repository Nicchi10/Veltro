"""

eval/error_profile.py

Ask WHAT KIND of mistake each format makes, not just how many.

The leaderboard says a format trails; it never says where. That gap was
explained in the docs for a long time by a mechanism nobody had measured
(Veltro's 'rel' block being "less local"), and the explanation turned out to be
untestable against the shipped subjects, which put relations at 87-90% of the
file in every format.

This reads the answers ALREADY SAVED under 'eval/results/' and costs nothing.
It prints two tables:

- exact accuracy per QUESTION TYPE, which says whether a gap is about relations
  at all, and
- for the two relation question types, what the wrong answers are made of:
  names that are the subject itself, names that sit on the WRONG SIDE of the
  relation (the reversal hypothesis), names that are real but further away than
  asked (transitive), names with no connection, and names simply missed.

Run:
    python eval/error_profile.py
    python eval/error_profile.py --project nest --model openai-gpt-4.1-mini

"""

import argparse
import collections
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.score import as_name_set, score_question
from veltro.parser import parse_file

RESULTS_DIR = os.path.join(REPO_ROOT, "eval", "results")
SUBJECTS_DIR = os.path.join(REPO_ROOT, "eval", "subjects")

FORMATS = ("veltro", "mermaid", "plantuml", "d2")

QUESTION_TYPES = ("implementors", "depends_on", "module_of", "public_method_count", "collection_fields")

# The two that ask about relations, i.e. the ones the 'rel' block explanation was about
RELATION_TYPES = ("implementors", "depends_on")

INHERITANCE_KINDS = ("extend", "impl")

DEFAULT_MODEL = "openai-gpt-4.1-mini"

DEFAULT_PROJECTS = ("spring-beans", "nest", "pydantic", "MediatR")


def subject_path(project: str, suffix: str) -> str:
    """
    Where one of a project's eval subject files lives
    """
    return os.path.join(SUBJECTS_DIR, project, project + suffix)


def read_questions(project: str) -> list:
    """
    The ground-truth questions generated for a project
    """
    with open(subject_path(project, ".questions.json"), encoding="utf-8") as questions_file:
        return json.load(questions_file)["questions"]


def read_answers(project: str, fmt: str, model_tag: str):
    """

    The saved answers for one (project, format, model), or None when that run
    was never made.

    Args:
        project (str): the eval subject
        fmt (str): veltro / mermaid / plantuml / d2
        model_tag (str): the '<provider>-<model>' part of the file name

    Returns:
        list[dict] | None: one answers dict per run

    """
    path = os.path.join(RESULTS_DIR, f"{project}.{fmt}.{model_tag}.json")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as result_file:
        result = json.load(result_file)

    runs = []
    for run in result["runs"]:
        runs.append(run["answers"])
    return runs


def build_relations(project: str) -> dict:
    """

    The relation tables needed to tell one kind of wrong name from another,
    read from the SAME '.vel' the ground truth was generated from.

    Everything is keyed by lowercased simple name, because that is how the
    scorer compares answers.

    Args:
        project (str): the eval subject

    Returns:
        dict: 'parents', 'children', 'out' and 'in', each name -> set of names

    """
    model = parse_file(subject_path(project, ".vel"))

    names = {}
    for node in model["nodes"]:
        names[node["id"]] = node["name"].lower()

    tables = {
        "parents": collections.defaultdict(set),
        "children": collections.defaultdict(set),
        "out": collections.defaultdict(set),
        "in": collections.defaultdict(set),
    }
    for edge in model["edges"]:
        source = names.get(edge["from"], edge["from"].rsplit(".", 1)[-1].lower())
        target = names.get(edge["to"], edge["to"].rsplit(".", 1)[-1].lower())
        tables["out"][source].add(target)
        tables["in"][target].add(source)
        if edge["kind"] in INHERITANCE_KINDS:
            tables["parents"][source].add(target)
            tables["children"][target].add(source)
    return tables


def reachable(start: str, table: dict) -> set:
    """

    Everything reachable from a name by following one table, excluding the
    start itself.

    Args:
        start (str): the name to walk from
        table (dict): name -> set of names

    Returns:
        set[str]: the transitive closure

    """
    seen = set()
    pending = [start]
    while pending:
        current = pending.pop()
        for following in table.get(current, ()):
            if following not in seen and following != start:
                seen.add(following)
                pending.append(following)
    return seen


def classify_answer(question: dict, given, tables: dict) -> collections.Counter:
    """

    Break one wrong relation answer into the kinds of name it got wrong.

    'reversed' is the interesting one: for 'implementors' it means the answer
    named a SUPERtype of the subject when subtypes were asked for; for
    'depends_on' it means naming something that depends on the subject rather
    than something the subject depends on. A format whose direction the model
    systematically inverts would show up here and nowhere else.

    Args:
        question (dict): the ground-truth question
        given: the answer as the model returned it
        tables (dict): from build_relations

    Returns:
        collections.Counter: counts by kind of error

    """
    truth = as_name_set(question["answer"])
    answered = as_name_set(given)
    subject = question["subject"].lower()

    if question["type"] == "implementors":
        wrong_side = reachable(subject, tables["parents"])
        further = reachable(subject, tables["children"]) - truth
    else:
        wrong_side = set(tables["in"].get(subject, set()))
        further = reachable(subject, tables["out"]) - truth

    tally = collections.Counter()
    for name in answered - truth:
        if name == subject:
            tally["the subject itself"] += 1
        elif name in wrong_side:
            tally["reversed"] += 1
        elif name in further:
            tally["transitive"] += 1
        else:
            tally["unrelated"] += 1

    tally["missed"] += len(truth - answered)
    return tally


def accuracy_by_type(questions: list, runs: list) -> dict:
    """

    Exact accuracy per question type, averaged over every run.

    Args:
        questions (list): the ground truth
        runs (list): one answers dict per run

    Returns:
        dict: question type -> accuracy, plus 'ALL'

    """
    hits = collections.Counter()
    totals = collections.Counter()
    for answers in runs:
        for question in questions:
            if question["id"] not in answers:
                continue
            is_exact, _tp, _given, _truth = score_question(question, answers[question["id"]])
            totals[question["type"]] += 1
            if is_exact:
                hits[question["type"]] += 1

    accuracy = {}
    for question_type in QUESTION_TYPES:
        if totals[question_type]:
            accuracy[question_type] = hits[question_type] / totals[question_type]
    if sum(totals.values()):
        accuracy["ALL"] = sum(hits.values()) / sum(totals.values())
    return accuracy


def report_gap(questions: list, rows: dict):
    """

    Split the distance between Veltro and the best other format into the
    question types that produce it.

    Every question type carries the same weight in the overall score, so a
    per-type difference divided by the number of types is exactly what that
    type contributes to the gap. A NEGATIVE contribution is a type where Veltro
    is ahead, and printing those matters: a gap quoted as one number can hide
    that the format wins half the questions it is supposedly losing.

    Args:
        questions (list): the ground truth
        rows (dict): format -> list of answers dicts

    """
    accuracies = {}
    for fmt in rows:
        accuracies[fmt] = accuracy_by_type(questions, rows[fmt])

    rival = None
    for fmt in rows:
        if fmt == "veltro":
            continue
        if rival is None or accuracies[fmt].get("ALL", 0) > accuracies[rival].get("ALL", 0):
            rival = fmt

    mine = accuracies["veltro"]
    theirs = accuracies[rival]
    gap = mine.get("ALL", 0) - theirs.get("ALL", 0)

    print()
    print(f"  where the gap against the best other format comes from (veltro {mine.get('ALL', 0):.2f} vs {rival} {theirs.get('ALL', 0):.2f}, {gap:+.2f})")
    shared = []
    for question_type in QUESTION_TYPES:
        if question_type in mine and question_type in theirs:
            shared.append(question_type)
    for question_type in shared:
        contribution = (mine[question_type] - theirs[question_type]) / len(shared)
        if contribution < 0:
            share = f"{abs(contribution) / abs(gap) * 100:.0f}% of it" if gap < 0 else "against the gap"
        else:
            share = "in Veltro's favour"
        print(f"    {question_type:22} {mine[question_type]:.2f} vs {theirs[question_type]:.2f}   {contribution:+.3f}   {share}")


def report_project(project: str, model_tag: str) -> bool:
    """

    Print both tables for one project.

    Args:
        project (str): the eval subject
        model_tag (str): the '<provider>-<model>' part of the file name

    Returns:
        bool: False when no result file exists for this project

    """
    questions = read_questions(project)
    tables = build_relations(project)

    rows = {}
    for fmt in FORMATS:
        runs = read_answers(project, fmt, model_tag)
        if runs is not None:
            rows[fmt] = runs

    if not rows:
        return False

    print("=" * 96)
    print(f"{project}  ({model_tag})")

    print()
    print("  exact accuracy per question type")
    header = f"    {'format':10}"
    for question_type in QUESTION_TYPES:
        header += f"{question_type[:17]:>19}"
    print(header + f"{'ALL':>8}")
    for fmt in rows:
        accuracy = accuracy_by_type(questions, rows[fmt])
        line = f"    {fmt:10}"
        for question_type in QUESTION_TYPES:
            if question_type in accuracy:
                line += f"{accuracy[question_type]:>19.2f}"
            else:
                line += f"{'-':>19}"
        line += f"{accuracy.get('ALL', 0):>8.2f}"
        print(line)

    if "veltro" in rows and len(rows) > 1:
        report_gap(questions, rows)

    print()
    print("  what the wrong relation answers are made of (implementors + depends_on)")
    kinds = ("the subject itself", "reversed", "transitive", "unrelated", "missed")
    header = f"    {'format':10}"
    for kind in kinds:
        header += f"{kind:>20}"
    print(header)
    for fmt in rows:
        tally = collections.Counter()
        for answers in rows[fmt]:
            for question in questions:
                if question["type"] not in RELATION_TYPES or question["id"] not in answers:
                    continue
                tally.update(classify_answer(question, answers[question["id"]], tables))
        line = f"    {fmt:10}"
        for kind in kinds:
            line += f"{tally[kind]:>20}"
        print(line)
    print()
    return True


def main(argv=None):
    parser = argparse.ArgumentParser(description="What kind of error each format makes, from the saved answers")
    parser.add_argument("--project", help="just this subject (default: all four)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"the provider-model tag in the result file name (default: {DEFAULT_MODEL})")
    arguments = parser.parse_args(argv)

    if arguments.project:
        projects = [arguments.project]
    else:
        projects = list(DEFAULT_PROJECTS)

    reported = 0
    for project in projects:
        if report_project(project, arguments.model):
            reported += 1
        else:
            print(f"[SKIP]   - {project}: no results for '{arguments.model}'")

    if not reported:
        print("[ERROR] - nothing to report, check --model against the file names in eval/results/")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
