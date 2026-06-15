"""

eval/score.py

STEP 3 of the LLM comprehension eval (offline, no LLM).

Joins the raw answers saved by run.py with the ground truth from generate.py and
reports, per format: how many questions were answered exactly right, a per-type
breakdown, a partial-credit F1 over the list questions, and the input-token cost.

The headline question it answers: does Veltro keep accuracy at least as high as
Mermaid / PlantUML while spending fewer tokens?

Run:
    python eval/score.py pydantic
"""

import argparse
import glob
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

# Question types whose answer is a set of names (order does not matter).
LIST_TYPES = ("implementors", "depends_on", "collection_fields")


def as_name_set(value) -> set:
    """

    Normalise a list-style answer into a lowercased set of names.

    Accepts a JSON list, a comma-joined string, or a single value, so that a
    model that replies with a string instead of an array is still scored fairly.

    """
    items = []
    if isinstance(value, list):
        items = value
    elif isinstance(value, str):
        items = value.split(",")
    elif value is not None:
        items = [value]

    names = set()
    for item in items:
        text = str(item).strip().lower()
        if text:
            names.add(text)
    return names


def normalise_scalar(value) -> str:
    """
    Lowercase, stripped string form of a scalar answer
    """
    return str(value).strip().lower()


def as_count(value):
    """
    Coerce an answer into an int, or None if it cannot be read as a number
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if text.isdigit():
        return int(text)
    return None


def score_question(question: dict, given) -> tuple:
    """

    Score one answer against the ground truth.

    Returns (is_exact, true_positives, predicted_count, truth_count). The last
    three are only meaningful for list questions (used for F1); for scalar and
    count questions they mirror is_exact so the caller can ignore them.

    """
    qtype = question["type"]
    truth = question["answer"]

    if qtype in LIST_TYPES:
        truth_set = as_name_set(truth)
        given_set = as_name_set(given)
        true_positives = len(truth_set & given_set)
        is_exact = truth_set == given_set
        return is_exact, true_positives, len(given_set), len(truth_set)

    if qtype == "public_method_count":
        is_exact = as_count(given) == as_count(truth)
        return is_exact, int(is_exact), 1, 1

    # module_of and any other scalar question
    is_exact = normalise_scalar(given) == normalise_scalar(truth)
    return is_exact, int(is_exact), 1, 1


def score_result(questions: list, answers: dict) -> dict:
    """

    Score one format's answers against all questions.

    Returns a dict with the overall exact accuracy, per-type accuracy, and the
    precision/recall/F1 over the list questions.

    """
    total = len(questions)
    exact_correct = 0

    per_type_total = {}
    per_type_correct = {}

    list_true_positives = 0
    list_predicted = 0
    list_truth = 0

    for question in questions:
        qtype = question["type"]
        given = answers.get(question["id"])

        is_exact, true_positives, predicted, truth_count = score_question(question, given)

        per_type_total[qtype] = per_type_total.get(qtype, 0) + 1
        if is_exact:
            exact_correct += 1
            per_type_correct[qtype] = per_type_correct.get(qtype, 0) + 1
        else:
            per_type_correct.setdefault(qtype, 0)

        if qtype in LIST_TYPES:
            list_true_positives += true_positives
            list_predicted += predicted
            list_truth += truth_count

    precision = list_true_positives / list_predicted if list_predicted else 0.0
    recall = list_true_positives / list_truth if list_truth else 0.0
    if precision + recall > 0:
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0

    per_type_accuracy = {}
    for qtype in per_type_total:
        per_type_accuracy[qtype] = per_type_correct[qtype] / per_type_total[qtype]

    return {
        "total": total,
        "exact_correct": exact_correct,
        "exact_accuracy": exact_correct / total if total else 0.0,
        "per_type_accuracy": per_type_accuracy,
        "list_f1": f1,
    }


def load_questions(subjects_dir: str, project: str) -> list:
    path = os.path.join(subjects_dir, project + ".questions.json")
    with open(path, encoding="utf-8") as questions_file:
        return json.load(questions_file)["questions"]


def mean(values: list) -> float:
    """
    Arithmetic mean, or 0.0 for an empty list
    """
    if not values:
        return 0.0
    return sum(values) / len(values)


def stdev(values: list) -> float:
    """
    Sample standard deviation (n-1), or 0.0 when there are fewer than 2 values
    """
    count = len(values)
    if count < 2:
        return 0.0
    average = mean(values)
    total = 0.0
    for value in values:
        total += (value - average) ** 2
    return (total / (count - 1)) ** 0.5


def runs_of(result: dict) -> list:
    """

    Return the list of runs in a result file.

    Supports both the new shape ({"runs": [...]}) and the old single-run shape
    ({"answers": ..., "input_tokens": ...}), so older result files still score.

    """
    if "runs" in result:
        return result["runs"]
    return [{
        "answers": result.get("answers", {}),
        "input_tokens": result.get("input_tokens", 0),
    }]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Score eval answers against ground truth")
    parser.add_argument("project")
    parser.add_argument("--subjects-dir", default="eval/subjects")
    parser.add_argument("--results-dir", default="eval/results")
    arguments = parser.parse_args(argv)

    questions = load_questions(arguments.subjects_dir, arguments.project)

    result_paths = sorted(glob.glob(
        os.path.join(arguments.results_dir, arguments.project + ".*.json")))
    if not result_paths:
        print(f"[ERROR] - no result files for '{arguments.project}' in {arguments.results_dir}", file=sys.stderr)
        return 1

    rows = []
    question_types = []
    for question in questions:
        if question["type"] not in question_types:
            question_types.append(question["type"])

    for path in result_paths:
        with open(path, encoding="utf-8") as result_file:
            result = json.load(result_file)

        runs = runs_of(result)

        exact_values = []
        f1_values = []
        token_values = []
        per_type_values = {}

        for run in runs:
            scored = score_result(questions, run.get("answers", {}))
            exact_values.append(scored["exact_accuracy"])
            f1_values.append(scored["list_f1"])
            token_values.append(run.get("input_tokens", 0))
            for qtype, accuracy in scored["per_type_accuracy"].items():
                per_type_values.setdefault(qtype, []).append(accuracy)

        per_type_mean = {}
        for qtype, values in per_type_values.items():
            per_type_mean[qtype] = mean(values)

        rows.append({
            "format": result["format"],
            "provider": result.get("provider", "?"),
            "model": result.get("model", "?"),
            "runs": len(runs),
            "tokens": int(mean(token_values)),
            "exact_mean": mean(exact_values),
            "exact_std": stdev(exact_values),
            "f1_mean": mean(f1_values),
            "f1_std": stdev(f1_values),
            "per_type_mean": per_type_mean,
        })

    # Sort by accuracy desc, then tokens asc (best + cheapest first)
    rows.sort(key=sort_key)

    provider = rows[0]["provider"]
    model = rows[0]["model"]
    run_count = rows[0]["runs"]
    print(f"project: {arguments.project}   provider: {provider}   model: {model}   runs: {run_count}")
    print(f"ground-truth questions: {len(questions)}\n")

    print(f"{'format':10} {'tokens':>7} {'exact%':>10} {'listF1':>12}")
    for row in rows:
        exact = f"{100 * row['exact_mean']:.0f}+/-{100 * row['exact_std']:.0f}%"
        f1 = f"{row['f1_mean']:.2f}+/-{row['f1_std']:.2f}"
        print(f"{row['format']:10} {row['tokens']:7} {exact:>10} {f1:>12}")

    print("\nper-type exact accuracy (mean):")
    type_header = f"{'format':10}"
    for qtype in question_types:
        type_header += f" {qtype:>20}"
    print(type_header)
    for row in rows:
        line = f"{row['format']:10}"
        for qtype in question_types:
            accuracy = row["per_type_mean"].get(qtype, 0.0)
            line += f" {100 * accuracy:19.0f}%"
        print(line)

    return 0


def sort_key(row: dict):
    """
    Best first: higher mean accuracy, then fewer tokens
    """
    return (-row["exact_mean"], row["tokens"])


if __name__ == "__main__":
    sys.exit(main())
