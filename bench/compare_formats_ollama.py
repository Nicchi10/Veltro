"""
Exhaustive token benchmark across architecture-description formats.

The same slice as bench/compare_formats.py, measured with a Hugging Face
tokenizer (e.g. Llama 3) instead of tiktoken, to check the ranking is not an
artefact of one tokenizer's vocabulary.

The formats come from bench/slice_formats.py, so this script reads the same
assembled slice: PlantUML, Mermaid and D2 rendered from the model at run time,
the three Veltro cannot render hand-written but checked against it.

Run:  python bench/compare_formats_ollama.py
"""

import os
import sys

from transformers import AutoTokenizer

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bench.slice_formats import load_formats, report_problems

MODELS = ["meta-llama/Meta-Llama-3-8B"]


def token_count(row):
    """
    Sort key: the token count of a (label, tokens) row
    """
    return row[1]


def rank(texts: dict, model_id: str) -> None:
    """

    Print the ranking for one Hugging Face tokenizer, cheapest first.

    Args:
        texts (dict): format label -> its text
        model_id (str): the model whose tokenizer to load

    """
    print(f"\nLoading tokenizer: {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id)

    rows = []
    for label in texts:
        rows.append((label, len(tokenizer.encode(texts[label]))))
    rows.sort(key=token_count)

    base = dict(rows).get("Veltro")

    print(f"\n=== tokenizer: {model_id} ===")
    print(f"{'rank':>4} {'format':14} {'tokens':>7} {'vs Veltro':>10}")
    for position, (label, tokens) in enumerate(rows, 1):
        if label == "Veltro":
            delta = ""
            marker = "  <--"
        else:
            delta = f"{(tokens / base - 1) * 100:+.0f}%"
            marker = ""
        print(f"{position:>4} {label:14} {tokens:7} {delta:>10}{marker}")


def main():
    texts, problems = load_formats()

    if problems:
        report_problems(problems)

    for model_id in MODELS:
        rank(texts, model_id)

    # A hand-written rendering that omits part of the model would win on tokens for the wrong reason, so the ranking above must not pass as trustworthy
    if problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
