"""

eval/plot_hero.py

Render the README "hero" chart from eval/leaderboard.csv: a cost-vs-comprehension
scatter that says, in one picture, "Veltro reads as well as the other formats
while costing ~30% fewer tokens", across every repo we evaluated.

Each point is a (format, repo) pair:
    x = token cost RELATIVE to Veltro (Veltro = 1.0x per repo, so the repos'
        very different absolute sizes collapse onto one comparable axis;
        tokens are the deterministic o200k_base counts, from the OpenAI rows)
    y = comprehension (list F1) on a capable model (Opus), where the formats
        converge - the fairest parity story

Colour encodes the format, marker shape encodes the repo. Veltro therefore forms
a vertical line at x = 1.0 (the dashed baseline), with every other format to its
right (more tokens) at a comparable height (comparable comprehension).

It renders a light AND a dark theme by default, so a README can swap them with a
<picture> + prefers-color-scheme block. Honest by construction: it draws only
what the CSV holds and never claims a comprehension WIN, only parity at a lower
token cost.

Dependency (tooling only):  pip install matplotlib

Run:
    python eval/plot_hero.py                       # both themes -> images/
    python eval/plot_hero.py --theme dark
    python eval/plot_hero.py --out images/hero.svg --theme light
"""

import argparse
import csv
import os
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The formats, in legend order. Each theme carries its own tuned palette so the
# colours stay vivid on a dark canvas as well as a light one.
FORMAT_ORDER = ["veltro", "mermaid", "plantuml", "d2"]
FORMAT_LABEL = {"veltro": "Veltro", "mermaid": "Mermaid", "plantuml": "PlantUML", "d2": "D2"}

# The repos, in legend order, each with its marker and a language-tagged label.
REPO_ORDER = ["pydantic", "spring-beans", "MediatR", "nest"]
REPO_MARKER = {"pydantic": "o", "spring-beans": "s", "MediatR": "^", "nest": "D"}
REPO_LABEL = {
    "pydantic": "pydantic (Py)",
    "spring-beans": "spring (Java)",
    "MediatR": "MediatR (C#)",
    "nest": "nest (TS)",
}

# Light and dark palettes. 'edge' rings each marker in the canvas colour so
# overlapping points stay separable; 'format' is the per-format point colour.
THEMES = {
    "light": {
        "bg": "#ffffff",
        "text": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#898781",
        "grid_alpha": 0.18,
        "spine": "#c3c2b7",
        "edge": "#ffffff",
        "repo_swatch": "#888780",
        "format": {"veltro": "#eb6834", "mermaid": "#1baf7a", "plantuml": "#2a78d6", "d2": "#4a3aa7"},
    },
    "dark": {
        "bg": "#0d1117",
        "text": "#e6edf3",
        "muted": "#9aa4b2",
        "grid": "#8b949e",
        "grid_alpha": 0.16,
        "spine": "#30363d",
        "edge": "#0d1117",
        "repo_swatch": "#9aa4b2",
        "format": {"veltro": "#ff6e40", "mermaid": "#25c08a", "plantuml": "#4a96f0", "d2": "#9b8ff0"},
    },
}

# Token cost is read from the o200k_base (OpenAI) rows; comprehension from the
# Anthropic Opus rows (a capable model). Both are the leaderboard's own columns.
TOKEN_PROVIDER = "openai"
COMP_PROVIDER = "anthropic"
COMP_MODEL = "claude-opus-4-8"


def parse_float(text):
    """
    Float of a CSV cell, or None when the cell is empty
    """
    text = (text or "").strip()
    if not text:
        return None
    return float(text)


def load_rows(csv_path):
    """
    Read every row of the leaderboard CSV into a list of dicts

    Args:
        csv_path (str): path to eval/leaderboard.csv

    Returns:
        list[dict]: the raw rows
    """
    rows = []
    with open(csv_path, encoding="utf-8") as csv_file:
        for row in csv.DictReader(csv_file):
            rows.append(row)
    return rows


def token_count(rows, project, fmt):
    """

    The o200k_base token count for one (project, format), from an OpenAI row.

    When several OpenAI models ran the same subject the count is identical (same
    tokenizer), so the row with the most runs is picked for stability.

    Args:
        rows (list[dict])
        project (str)
        fmt (str)

    Returns:
        int or None
    """
    chosen = None
    for row in rows:
        if row["project"] != project or row["format"] != fmt:
            continue
        if row.get("provider", "openai") != TOKEN_PROVIDER:
            continue
        if chosen is None or int(row["runs"]) > int(chosen["runs"]):
            chosen = row
    if chosen is None:
        return None
    return int(chosen["tokens"])


def comprehension_f1(rows, project, fmt):
    """
    The list-F1 mean for one (project, format) on the comprehension model (Opus)

    Args:
        rows (list[dict])
        project (str)
        fmt (str)

    Returns:
        float or None
    """
    for row in rows:
        if row["project"] != project or row["format"] != fmt:
            continue
        if row.get("provider") != COMP_PROVIDER or row["model"] != COMP_MODEL:
            continue
        return parse_float(row["listf1_mean"])
    return None


def collect_points(rows):
    """

    Build the plottable points, normalising tokens to Veltro = 1.0 per repo.

    A repo is included only if its Veltro token count exists (the normalisation
    reference); a format inside a repo is included only if it has both a token
    count and an F1.

    Args:
        rows (list[dict])

    Returns:
        dict: project -> { format -> (relative_tokens, f1) }
    """
    points = {}
    for project in REPO_ORDER:
        veltro_tokens = token_count(rows, project, "veltro")
        if veltro_tokens is None:
            continue
        per_format = {}
        for fmt in FORMAT_ORDER:
            tokens = token_count(rows, project, fmt)
            f1 = comprehension_f1(rows, project, fmt)
            if tokens is None or f1 is None:
                continue
            per_format[fmt] = (tokens / veltro_tokens, f1)
        if per_format:
            points[project] = per_format
    return points


def saving_summary(points):
    """
    The mean token overhead of the non-Veltro formats, as a "-NN%" headline
    (how much Veltro saves on average vs the other formats)

    Args:
        points (dict): from collect_points

    Returns:
        str: e.g. "-26%"
    """
    ratios = []
    for per_format in points.values():
        for fmt, (relative_tokens, _f1) in per_format.items():
            if fmt != "veltro":
                ratios.append(relative_tokens)
    if not ratios:
        return "-"
    average = sum(ratios) / len(ratios)
    return f"-{round((1 - 1 / average) * 100)}%"


def build_figure(points, title, theme):
    """

    Draw the scatter for one theme and return the matplotlib Figure.

    Legends sit OUTSIDE the plot area (to the right) so they never cover a point.

    Args:
        points (dict): from collect_points
        title (str): the chart title
        theme (dict): one entry of THEMES

    Returns:
        matplotlib.figure.Figure
    """
    figure, axes = plt.subplots(figsize=(8.6, 5.0))
    figure.patch.set_facecolor(theme["bg"])
    axes.set_facecolor(theme["bg"])

    for project, per_format in points.items():
        marker = REPO_MARKER[project]
        for fmt, (relative_tokens, f1) in per_format.items():
            axes.scatter(
                relative_tokens,
                f1,
                marker=marker,
                s=130,
                color=theme["format"][fmt],
                edgecolors=theme["edge"],
                linewidths=1.0,
                zorder=3,
            )

    # The Veltro baseline: every Veltro point sits on x = 1.0.
    axes.axvline(1.0, color=theme["format"]["veltro"], linestyle="--", linewidth=1.4, alpha=0.5, zorder=1)

    axes.set_xlabel("token cost relative to Veltro  (lower = cheaper)", fontsize=11, color=theme["muted"])
    axes.set_ylabel("comprehension - list F1 (Opus)", fontsize=11, color=theme["muted"])
    axes.set_xlim(0.9, 1.7)
    axes.set_ylim(0.55, 1.0)

    def format_times(value, _position):
        """
        Tick formatter: render an x value as a multiplier like '1.2x'
        """
        return f"{value:.1f}x"

    axes.xaxis.set_major_formatter(plt.FuncFormatter(format_times))
    axes.grid(True, color=theme["grid"], alpha=theme["grid_alpha"], linewidth=0.8)
    axes.tick_params(colors=theme["muted"])
    for spine_name in ("top", "right"):
        axes.spines[spine_name].set_visible(False)
    for spine_name in ("left", "bottom"):
        axes.spines[spine_name].set_color(theme["spine"])

    if title:
        axes.set_title(title, fontsize=13, color=theme["text"], pad=12)

    format_handles = []
    for fmt in FORMAT_ORDER:
        if any(fmt in per_format for per_format in points.values()):
            handle = Line2D([0], [0], marker="o", linestyle="", markersize=9,
                            markerfacecolor=theme["format"][fmt], markeredgecolor=theme["edge"],
                            label=FORMAT_LABEL[fmt])
            format_handles.append(handle)
    repo_handles = []
    for project in REPO_ORDER:
        if project in points:
            handle = Line2D([0], [0], marker=REPO_MARKER[project], linestyle="", markersize=9,
                            markerfacecolor=theme["repo_swatch"], markeredgecolor=theme["edge"],
                            label=REPO_LABEL[project])
            repo_handles.append(handle)

    # Reserve room on the right, then anchor both legends just outside the axes.
    figure.subplots_adjust(right=0.74)
    legend_formats = axes.legend(handles=format_handles, title="format", loc="upper left",
                                 bbox_to_anchor=(1.03, 1.0), fontsize=10, frameon=False,
                                 labelcolor=theme["text"])
    legend_formats.get_title().set_color(theme["text"])
    axes.add_artist(legend_formats)
    legend_repos = axes.legend(handles=repo_handles, title="repo", loc="upper left",
                               bbox_to_anchor=(1.03, 0.5), fontsize=10, frameon=False,
                               labelcolor=theme["text"])
    legend_repos.get_title().set_color(theme["text"])

    return figure


def themed_path(out_path, theme_name):
    """
    Insert a '-dark' suffix before the extension for the dark theme; leave the
    light theme on the base name

    Args:
        out_path (str): the base output path (e.g. images/hero.svg)
        theme_name (str): 'light' or 'dark'

    Returns:
        str
    """
    if theme_name == "light":
        return out_path
    root, extension = os.path.splitext(out_path)
    return f"{root}-{theme_name}{extension}"


def write_outputs(figure, out_path, theme):
    """

    Save the figure as the requested file plus a sibling .png (GitHub does not
    always render SVG in a README).

    Args:
        figure (matplotlib.figure.Figure)
        out_path (str): the output path for this theme (typically an .svg)
        theme (dict): the theme, for the saved background colour

    Returns:
        list[str]: the paths written
    """
    directory = os.path.dirname(out_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    written = [out_path]
    figure.savefig(out_path, bbox_inches="tight", facecolor=theme["bg"])

    root, extension = os.path.splitext(out_path)
    if extension.lower() != ".png":
        png_path = root + ".png"
        figure.savefig(png_path, dpi=150, bbox_inches="tight", facecolor=theme["bg"])
        written.append(png_path)
    return written


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render the README hero chart from the leaderboard")
    parser.add_argument("--csv", default=os.path.join("eval", "leaderboard.csv"))
    parser.add_argument("--out", default=os.path.join("images", "comprehension_vs_tokens.svg"))
    parser.add_argument("--title", default="Same comprehension, fewer tokens")
    parser.add_argument("--theme", choices=["light", "dark", "both"], default="both")
    arguments = parser.parse_args(argv)

    rows = load_rows(arguments.csv)
    points = collect_points(rows)
    if not points:
        print(f"[ERROR] - no plottable (token + Opus F1) data in {arguments.csv}", file=sys.stderr)
        return 1

    title = arguments.title
    if title:
        title = f"{title}  ({saving_summary(points)} tokens, {len(points)} repos)"

    if arguments.theme == "both":
        theme_names = ["light", "dark"]
    else:
        theme_names = [arguments.theme]

    repo_names = ", ".join(points)
    print(f"[INFO] - repos plotted: {len(points)} ({repo_names})")
    print(f"[INFO] - mean token saving vs other formats: {saving_summary(points)}")

    for theme_name in theme_names:
        theme = THEMES[theme_name]
        figure = build_figure(points, title, theme)
        out_path = themed_path(arguments.out, theme_name)
        for path in write_outputs(figure, out_path, theme):
            print(f"[INFO] - wrote {path}  ({theme_name})")
        plt.close(figure)

    return 0


if __name__ == "__main__":
    sys.exit(main())
