"""
Exhaustive token benchmark across architecture-description formats.

The same representative slice of the architecture in each format, measured with
real LLM tokenizers (tiktoken) and ranked against Veltro.

Everything derives from 'bench/formats/slice.vel': PlantUML, Mermaid and D2 are
rendered from its model at run time, and the three formats Veltro cannot render
are hand-written but checked against that model, so no file can quietly fall
behind and look cheaper for describing less. See bench/slice_formats.py.

Run:  python bench/compare_formats.py
"""

import os
import sys

import tiktoken

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bench.slice_formats import load_formats, report_problems

ENCODERS = ["cl100k_base", "o200k_base"]


def rank(texts: dict, encoder_name: str) -> None:
    """

    Print the ranking for one tokenizer, cheapest first.

    Args:
        texts (dict): format label -> its text
        encoder_name (str): a tiktoken encoding name

    """
    encoder = tiktoken.get_encoding(encoder_name)

    rows = []
    for label in texts:
        rows.append((label, len(encoder.encode(texts[label]))))
    rows.sort(key=token_count)

    base = dict(rows).get("Veltro")

    print(f"\n=== tokenizer: {encoder_name} ===")
    print(f"{'rank':>4} {'format':14} {'tokens':>7} {'vs Veltro':>10}")
    for position, (label, tokens) in enumerate(rows, 1):
        if label == "Veltro":
            delta = ""
            marker = "  <--"
        else:
            delta = f"{(tokens / base - 1) * 100:+.0f}%"
            marker = ""
        print(f"{position:>4} {label:14} {tokens:7} {delta:>10}{marker}")


def token_count(row):
    """
    Sort key: the token count of a (label, tokens) row
    """
    return row[1]


def main():
    texts, problems = load_formats()

    if problems:
        report_problems(problems)

    for encoder_name in ENCODERS:
        rank(texts, encoder_name)

    # A hand-written rendering that omits part of the model would win on tokens for the wrong reason, so the ranking above must not pass as trustworthy
    if problems:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
