"""

bench/check_readme_table.py

Recompute every row of the README token table and fail when one has drifted.

The table is the most quoted claim in the project, and it is the kind of number
that goes stale in silence: it moves whenever the parser or an extractor
changes, and nothing in the repository used to notice. A local script caught a
Kafka row that had been wrong for months, so the check belongs in the repository
and in CI, not in someone's shell history.

Rows are recomputed exactly the way the README says to reproduce them, by
calling into 'bench/scale_bench.py' rather than re-implementing the count: the
document and the check must not be able to disagree about what a token is.

Seven of the eight rows are recomputed from the '.vel' committed under
'examples/'. The Rich row cannot be: no 'examples/rich.vel' is committed, so
reproducing it needs a checkout of Rich itself. It is reported as unchecked,
which is the honest state, and is not counted as a pass.

Run:
    python bench/check_readme_table.py
    python bench/check_readme_table.py --only Orleans     # one row, it is the slow one

"""

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from bench.scale_bench import count_kinds, count_tokens, load_vel
from veltro.export.mermaid import export_mermaid
from veltro.export.plantuml import export_plantuml
from veltro.parser import parse_text

README = os.path.join(REPO_ROOT, "README.md")

# The README quotes o200k_base, which is what scale_bench prints second
ENCODER = "o200k_base"

TABLE_HEADER = "| project | language | types | Veltro | Mermaid | PlantUML |"

# The link text of the first cell -> the committed '.vel' that reproduces the row.
# None means the row exists but nothing in the repository can recompute it.
SOURCES = {
    "Rich": None,
    "Pydantic": "examples/pydantic.vel",
    "Spring": "examples/spring-beans.vel",
    "Kafka": "examples/kafka-clients.vel",
    "MediatR": "examples/MediatR.vel",
    "Orleans": "examples/Orleans.vel",
    "NestJS": "examples/nest.vel",
    "Angular": "examples/angular.vel",
}


def read_rows(readme_path: str) -> list:
    """

    The rows of the token table, as they are written in the README.

    Args:
        readme_path (str): path to README.md

    Returns:
        list[dict]: one dict per row, with the project name and the four numbers

    Raises:
        LookupError: when the table is not where it is expected

    """
    with open(readme_path, encoding="utf-8") as readme_file:
        lines = readme_file.read().splitlines()

    start = None
    for position, line in enumerate(lines):
        if line.strip() == TABLE_HEADER:
            start = position
            break
    if start is None:
        raise LookupError(f"the token table is gone from {readme_path}: no header '{TABLE_HEADER}'")

    rows = []
    # +2 skips the header and the '|---|' separator under it
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        cells = []
        for cell in line.strip().strip("|").split("|"):
            cells.append(cell.strip())
        rows.append({
            "project": link_text(cells[0]),
            "cell": cells[0],
            "types": as_number(cells[2]),
            "veltro": as_number(cells[3]),
            "mermaid": as_number(cells[4]),
            "plantuml": as_number(cells[5]),
        })
    return rows


def link_text(cell: str) -> str:
    """

    The label of the markdown link a cell opens with ('[Rich](url) (x)' -> 'Rich')

    Args:
        cell (str): the first cell of a row

    Returns:
        str: the link text, or the whole cell when there is no link

    """
    match = re.match(r"\[([^\]]+)\]", cell)
    if match:
        return match.group(1)
    return cell


def as_number(cell: str) -> int:
    """
    The integer inside a cell, ignoring thousands separators and a '+...%' shape
    """
    digits = cell.replace(",", "").replace("+", "").replace("%", "").strip()
    return int(digits)


def percentage_over(tokens: int, veltro_tokens: int) -> int:
    """
    How much dearer a format is than Veltro, rounded the way scale_bench prints it
    """
    return int(round((tokens / veltro_tokens - 1) * 100))


def measure(vel_path: str) -> dict:
    """

    Recompute one row from a '.vel': the three formats come from ONE model, so
    the comparison stays the apples-to-apples one the README claims.

    Args:
        vel_path (str): path to the committed '.vel'

    Returns:
        dict: the same four numbers a README row carries

    """
    _name, vel_text = load_vel(vel_path)
    model = parse_text(vel_text)

    classes, interfaces, enums, _modules = count_kinds(model)
    veltro_tokens = count_tokens(vel_text, ENCODER)

    return {
        "types": classes + interfaces + enums,
        "veltro": veltro_tokens,
        "mermaid": percentage_over(count_tokens(export_mermaid(model), ENCODER), veltro_tokens),
        "plantuml": percentage_over(count_tokens(export_plantuml(model), ENCODER), veltro_tokens),
    }


def differences(row: dict, measured: dict) -> list:
    """

    Every number of a row that the recomputation disagrees with.

    Args:
        row (dict): what the README says
        measured (dict): what the code produces now

    Returns:
        list[str]: one readable line per mismatch, empty when the row holds

    """
    labels = {
        "types": "types",
        "veltro": "Veltro tokens",
        "mermaid": "Mermaid %",
        "plantuml": "PlantUML %",
    }
    found = []
    for key in ("types", "veltro", "mermaid", "plantuml"):
        if row[key] != measured[key]:
            found.append(f"{labels[key]}: README says {row[key]}, measured {measured[key]}")
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check that every README token row is reproducible")
    parser.add_argument("--only", help="check just this project (the link text, e.g. Orleans)")
    arguments = parser.parse_args(argv)

    rows = read_rows(README)

    if arguments.only:
        known = []
        for row in rows:
            known.append(row["project"])
        if arguments.only not in known:
            # otherwise a typo checks nothing and reports success
            print(f"[ERROR] - no row called '{arguments.only}', the table has: {', '.join(known)}")
            return 1

    checked = 0
    unchecked = []
    failed = []

    for row in rows:
        project = row["project"]
        if arguments.only and project != arguments.only:
            continue

        if project not in SOURCES:
            failed.append(project)
            print(f"[FAIL]   - {project}: a new row with no source to reproduce it, add one to SOURCES")
            continue

        relative = SOURCES[project]
        if relative is None:
            unchecked.append(project)
            print(f"[SKIP]   - {project}: no '.vel' committed, reproducing it needs a checkout of the project")
            continue

        measured = measure(os.path.join(REPO_ROOT, relative))
        mismatches = differences(row, measured)
        if mismatches:
            failed.append(project)
            print(f"[FAIL]   - {project} ({relative})")
            for mismatch in mismatches:
                print(f"           {mismatch}")
        else:
            checked += 1
            print(f"[OK]     - {project}: {measured['types']} types, {measured['veltro']} tokens, Mermaid +{measured['mermaid']}%, PlantUML +{measured['plantuml']}%")

    print(f"[INFO] - {checked} reproduced, {len(failed)} wrong, {len(unchecked)} not checkable ({len(rows)} rows in the table)")

    if failed:
        print("[ERROR] - the README no longer matches the code that produces it")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
