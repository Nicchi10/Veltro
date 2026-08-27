"""

bench/slice_formats.py

The benchmark slice in every format, assembled so it cannot drift.

The 7-format ranking is the most quoted table in the README, and it used to
tokenise whatever text happened to sit in 'bench/formats/'. Those files were
maintained by hand, and some had fallen behind the exporters: 'slice.mmd' and
'slice.d2' were missing the field defaults the model carries ('True', '12',
'19') and the 'namespace' grouping Mermaid now emits, which made both look
SHORTER than the exporters would actually render them. The drift ran in the
competitors' favour, so nothing about the conclusion was being flattered, but
nothing was guaranteeing it either.

So the formats are gathered in two ways, and neither can go stale silently:

    - PlantUML / Mermaid / D2 are RENDERED from the model at run time, by the
      same exporters the rest of the project uses. There is no file to drift
    - Graphviz DOT / yUML / Nomnoml have no exporter and stay hand-written,
      because authoring a competitor's rendering ourselves is how a benchmark
      quietly becomes unfair. Instead every fact of the model -- type names,
      member names, enum values, field defaults -- must appear in them, so a
      hand-written file cannot silently omit content and look cheaper for it

Everything derives from 'bench/formats/slice.vel', which is the one source.

"""

import os

from veltro.export.d2 import export_d2
from veltro.export.mermaid import export_mermaid
from veltro.export.plantuml import export_plantuml
from veltro.parser import parse_file

HERE = os.path.dirname(os.path.abspath(__file__))
FORMATS_DIR = os.path.join(HERE, "formats")
SLICE_VEL = os.path.join(FORMATS_DIR, "slice.vel")

# Formats Veltro can render: produced from the model, never read from disk.
GENERATED = (
    ("PlantUML", export_plantuml),
    ("Mermaid", export_mermaid),
    ("D2", export_d2),
)

# Formats with no exporter: hand-written, and checked against the model.
HAND_WRITTEN = (
    ("Graphviz DOT", "dot"),
    ("yUML", "yuml"),
    ("Nomnoml", "nomnoml"),
)


def model_vocabulary(model: dict) -> list:
    """

    Every fact a rendering of this model has to mention.

    A format may spell them differently, but it cannot leave them out: a file
    missing a type, a member or a default is describing less architecture than
    the others and would win the token count for the wrong reason.

    Args:
        model (dict): the parsed slice

    Returns:
        list[str]: the names, enum values and defaults to look for

    """
    vocabulary = []
    for node in model["nodes"]:
        vocabulary.append(node["name"])
        vocabulary.extend(node.get("values", []))
        for field in node.get("fields", []):
            vocabulary.append(field["name"])
            if "default" in field:
                vocabulary.append(field["default"])
        for method in node.get("methods", []):
            vocabulary.append(method["name"])
    return vocabulary


def missing_from(text: str, vocabulary: list) -> list:
    """
    The vocabulary entries a rendering does not mention, in first-seen order
    and without repeats
    """
    missing = []
    for entry in vocabulary:
        if entry not in text and entry not in missing:
            missing.append(entry)
    return missing


def load_formats():
    """

    Every format of the slice, plus whatever failed its parity check.

    Returns:
        (texts, problems):
            texts (dict): format label -> its text, Veltro included
            problems (dict): format label -> the facts it is missing, empty when
                every hand-written file carries the whole model

    """
    with open(SLICE_VEL, encoding="utf-8") as slice_file:
        veltro_text = slice_file.read()

    model = parse_file(SLICE_VEL)
    vocabulary = model_vocabulary(model)

    texts = {"Veltro": veltro_text}
    for label, exporter in GENERATED:
        texts[label] = exporter(model)

    problems = {}
    for label, extension in HAND_WRITTEN:
        path = os.path.join(FORMATS_DIR, "slice." + extension)
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        texts[label] = text
        missing = missing_from(text, vocabulary)
        if missing:
            problems[label] = missing

    return texts, problems


def report_problems(problems: dict) -> None:
    """
    Print what a hand-written rendering is missing, so the ranking below it is
    read knowing the file describes less than the others
    """
    for label in problems:
        missing = problems[label]
        shown = ", ".join(missing[:6])
        if len(missing) > 6:
            shown += f", ... (+{len(missing) - 6} more)"
        print(f"[ERROR] - {label} does not mention {len(missing)} facts of the model: {shown}")
