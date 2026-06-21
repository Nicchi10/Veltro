"""

eval/report.py

Turn eval/leaderboard.csv (the editable, version-controlled dataset) into a
Markdown leaderboard in eval/REPORT.md.

The CSV is the source of truth, hand-editable, git-diffable. This script is
just a view over it: token cost, exact% (mean +/- std) and listF1, pivoted as
format (rows) x system (columns), where a "system" is model+provider (e.g.
OpenAI-API and Anthropic-API runs are visibly distinct).

The token-cost table uses a single tokenizer (o200k_base) so it draws on the
OpenAI rows only, other providers API token counts use a different tokenizer
and are not directly comparable.

Run:
    python eval/report.py            # project pydantic -> eval/REPORT.md
"""

import argparse
import csv
import sys

FORMAT_ORDER = ["veltro", "mermaid", "plantuml", "d2"]
PROVIDER_DISPLAY = {"openai": "openai", "anthropic": "anthropic"}
TOKEN_COMPARABLE_PROVIDERS = ("openai",)


def parse_float(text: str):
    """
    Float of a CSV cell, or None when the cell is empty
    """
    text = (text or "").strip()
    if not text:
        return None
    return float(text)


def load_rows(csv_path: str, project: str) -> list:
    """
    Read the leaderboard rows for one project
    """
    rows = []
    with open(csv_path, encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            if row["project"] == project:
                rows.append(row)
    return rows


def system_of(row: dict) -> tuple:
    """
    A column key: (model, provider)
    """
    return (row["model"], row.get("provider", "openai"))


def system_label(system: tuple) -> str:
    model, provider = system
    return f"{model} ({PROVIDER_DISPLAY.get(provider, provider)})"


def systems_in_order(rows: list) -> list:
    """
    Distinct (model, provider) columns, in first-appearance order
    """
    systems = []
    for row in rows:
        key = system_of(row)
        if key not in systems:
            systems.append(key)
    return systems


def formats_present(rows: list) -> list:
    """
    The formats that appear, in FORMAT_ORDER
    """
    seen = set()
    for row in rows:
        seen.add(row["format"])
    ordered = []
    for name in FORMAT_ORDER:
        if name in seen:
            ordered.append(name)
    return ordered


def index_rows(rows: list) -> dict:
    """
    Map (format, (model, provider)) -> row
    """
    index = {}
    for row in rows:
        index[(row["format"], system_of(row))] = row
    return index


def is_contaminated(row: dict) -> bool:
    return "contaminated" in (row.get("notes") or "")


def exact_cell(row: dict) -> str:
    if row is None:
        return "-"
    mean = parse_float(row["exact_mean"])
    if mean is None:
        return "-"
    std = parse_float(row["exact_std"])
    flag = "*" if is_contaminated(row) else ""
    if std is not None:
        return f"{round(mean * 100)}+/-{round(std * 100)}%{flag}"
    return f"{round(mean * 100)}%{flag}"


def f1_cell(row: dict) -> str:
    if row is None:
        return "-"
    mean = parse_float(row["listf1_mean"])
    if mean is None:
        return "-"
    std = parse_float(row["listf1_std"])
    flag = "*" if is_contaminated(row) else ""
    if std is not None:
        return f"{mean:.2f}+/-{std:.2f}{flag}"
    return f"{mean:.2f}{flag}"


def tokens_per_format(rows: list, formats: list) -> dict:
    """
    One token figure per format, from a token-comparable provider only
    (a single tokenizer, o200k_base, so only the OpenAI rows qualify, other
    providers' API token counts use a different tokenizer). Picks the row with
    the most runs
    """
    best = {}
    for fmt in formats:
        chosen = None
        for row in rows:
            if row["format"] != fmt:
                continue
            if row.get("provider", "openai") not in TOKEN_COMPARABLE_PROVIDERS:
                continue
            if chosen is None or int(row["runs"]) > int(chosen["runs"]):
                chosen = row
        if chosen is not None:
            best[fmt] = int(chosen["tokens"])
    return best


def pivot_table(title: str, rows: list, formats: list, systems: list, cell_func) -> list:
    """
    Build a Markdown pivot: rows = formats, columns = models
    """
    
    index = index_rows(rows)
    labels = []
    for system in systems:
        labels.append(system_label(system))

    lines = [f"### {title}", ""]
    lines.append("| format | " + " | ".join(labels) + " |")
    lines.append("|" + "---|" * (len(systems) + 1))
    for fmt in formats:
        cells = []
        for system in systems:
            cells.append(cell_func(index.get((fmt, system))))
        lines.append(f"| {fmt} | " + " | ".join(cells) + " |")
    lines.append("")
    return lines


def build_report(project: str, rows: list) -> str:
    systems = systems_in_order(rows)
    formats = formats_present(rows)
    tokens = tokens_per_format(rows, formats)

    lines = []
    lines.append(f"# Veltro eval leaderboard - {project}")
    lines.append("")
    lines.append("Generated from `eval/leaderboard.csv` by `eval/report.py`. "
                 "Columns are model (provider): all runs are via paid API "
                 "(OpenAI / Anthropic). Compare formats within a column.")
    lines.append("")
    lines.append("**Read it honestly:** token cost is deterministic and solid, "
                 "comprehension accuracy is model-dependent and the formats land "
                 "in overlapping bands, no robust comprehension winner. The "
                 "durable result is fewer tokens at comparable comprehension.")
    lines.append("")

    lines.append("### Token cost (o200k_base, per format, API runs only)")
    lines.append("")
    lines.append("| format | tokens | vs Veltro |")
    lines.append("|---|---|---|")
    veltro_tokens = tokens.get("veltro")
    for fmt in formats:
        count = tokens.get(fmt)
        if count is None:
            continue
        if veltro_tokens and fmt != "veltro":
            delta = f"+{round((count / veltro_tokens - 1) * 100)}%"
        else:
            delta = "-"
        lines.append(f"| {fmt} | {count} | {delta} |")
    lines.append("")

    lines.extend(pivot_table("Exact accuracy (mean +/- std)", rows, formats, systems, exact_cell))
    lines.extend(pivot_table("List-question F1 (mean +/- std)", rows, formats, systems, f1_cell))

    lines.append("Legend: `-` = combination not tested (not a zero). `*` = contaminated run (pre-fix or weak model), indicative only. Cells without `+/-` are single runs (n=1, no variance).")
    lines.append("")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render the eval leaderboard to Markdown")
    parser.add_argument("--project", default="pydantic")
    parser.add_argument("--csv", default="eval/leaderboard.csv")
    parser.add_argument("--out", default="eval/REPORT.md")
    arguments = parser.parse_args(argv)

    rows = load_rows(arguments.csv, arguments.project)
    if not rows:
        print(f"[ERROR] - no rows for project '{arguments.project}' in {arguments.csv}",
              file=sys.stderr)
        return 1

    report = build_report(arguments.project, rows)
    with open(arguments.out, "w", encoding="utf-8", newline="\n") as out_file:
        out_file.write(report)
        if not report.endswith("\n"):
            out_file.write("\n")

    print(f"[INFO] - wrote {arguments.out} ({len(rows)} rows, project {arguments.project})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
