"""

eval/run.py

STEP 2 of the LLM comprehension eval (this is the only step that calls an LLM).

For a project, it loads the three subjects produced by generate.py and the
questions, then asks the SAME questions to the model once per format. The model
sees only the diagram as context and must answer from it. Raw answers and token
usage are saved under eval/results/ so step 3 (score.py) can score them offline
and a run can be re-scored without re-querying.

Provider: Anthropic. Model: claude-opus-4-8 by default (override with --model).
The API key is read from the ANTHROPIC_API_KEY environment variable; it is never
read from a file or hardcoded.

Run:
    set ANTHROPIC_API_KEY=...           (Windows)  / export on Unix
    python eval/run.py pydantic
    python eval/run.py pydantic --model claude-opus-4-8 --formats veltro,mermaid,plantuml
"""

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_MODEL = "claude-opus-4-8"

# Each format: the subject file extension and a short legend given to the model
# PlantUML and Mermaid are widely known; Veltro is not, so it gets a real legend
# to keep the comparison fair (the model is not penalised for an unknown syntax)
FORMATS = {
    "veltro": {
        "extension": ".vel",
        "legend": (
            "The diagram is written in Veltro, a compact architecture notation. "
            "Rules: 'module X.Y' groups the types under it; 'class', 'interface' "
            "and 'enum' declare types; a member line with no marker is public, "
            "while '-' is private, '#' protected, '@' package, and a leading '$' "
            "means static; a member with '(' is a method, otherwise a field "
            "written as 'name Type'; generics use angle brackets; the 'rel' block "
            "lists relations as '<from> <kind> <to>' (kind = extend or impl)."
        ),
    },
    "mermaid": {
        "extension": ".mmd",
        "legend": "The diagram is written in Mermaid classDiagram notation.",
    },
    "plantuml": {
        "extension": ".puml",
        "legend": "The diagram is written in PlantUML.",
    },
}


def load_subject(subjects_dir: str, project: str, extension: str) -> str:
    """
    Read one rendered subject file (e.g. pydantic.vel)
    """
    path = os.path.join(subjects_dir, project + extension)
    with open(path, encoding="utf-8") as subject_file:
        return subject_file.read()


def load_questions(subjects_dir: str, project: str) -> list:
    """
    Read the questions produced by generate.py
    """
    path = os.path.join(subjects_dir, project + ".questions.json")
    with open(path, encoding="utf-8") as questions_file:
        payload = json.load(questions_file)
    return payload["questions"]


def build_prompt(legend: str, diagram: str, questions: list) -> tuple:
    """

    Build the (system, user) prompt pair for one format.

    Args:
        legend (str): a short description of the notation
        diagram (str): the rendered architecture in that notation
        questions (list): the questions to ask

    Returns:
        (system_text, user_text)

    """
    system_text = (
        "You answer questions about a software architecture diagram "
        "Use ONLY the information present in the diagram, do not guess from "
        "prior knowledge of the library. Answer every question"
        "Reply with a single JSON object mapping each question id to its answer"
        "For a list answer use a JSON array of type names (strings)"
        "For a count use an integer. For a single value use a string"
        "Output only the JSON object, with no surrounding prose or code fences"
    )

    lines = []
    lines.append(legend)
    lines.append("")
    lines.append("=== DIAGRAM ===")
    lines.append(diagram)
    lines.append("=== QUESTIONS ===")
    for question in questions:
        lines.append(f"{question['id']}: {question['prompt']}")
    user_text = "\n".join(lines)

    return system_text, user_text


def extract_json(text: str) -> dict:
    """

    Parse the model's reply into a dict, tolerating a json code fence.

    Returns an empty dict if nothing parseable is found.

    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the first fence line and any trailing fence
        newline_index = cleaned.find("\n")
        if newline_index != -1:
            cleaned = cleaned[newline_index + 1:]
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {}


def ask_model(client, model: str, system_text: str, user_text: str) -> tuple:
    """

    Send one request and return (raw_text, input_tokens, output_tokens)

    """
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        system=system_text,
        messages=[{"role": "user", "content": user_text}],
    )

    raw_text = ""
    for block in response.content:
        if block.type == "text":
            raw_text += block.text

    return raw_text, response.usage.input_tokens, response.usage.output_tokens


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ask an LLM the eval questions, once per format")
    parser.add_argument("project", help="project name (matches eval/subjects/<project>.*)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--formats", default="veltro,mermaid,plantuml",help="comma-separated subset of: veltro,mermaid,plantuml")
    parser.add_argument("--subjects-dir", default="eval/subjects")
    parser.add_argument("--out-dir", default="eval/results")
    arguments = parser.parse_args(argv)

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("[ERROR] - set ANTHROPIC_API_KEY in the environment first", file=sys.stderr)
        return 1

    try:
        import anthropic
    except ImportError:
        print("[ERROR] - the 'anthropic' package is required: pip install anthropic",
              file=sys.stderr)
        return 1

    client = anthropic.Anthropic()

    questions = load_questions(arguments.subjects_dir, arguments.project)
    os.makedirs(arguments.out_dir, exist_ok=True)

    chosen_formats = []
    for name in arguments.formats.split(","):
        name = name.strip()
        if name:
            chosen_formats.append(name)

    for format_name in chosen_formats:
        if format_name not in FORMATS:
            print(f"[WARN] - unknown format '{format_name}', skipping")
            continue

        info = FORMATS[format_name]
        diagram = load_subject(arguments.subjects_dir, arguments.project, info["extension"])
        system_text, user_text = build_prompt(info["legend"], diagram, questions)

        raw_text, input_tokens, output_tokens = ask_model(client, arguments.model, system_text, user_text)
        answers = extract_json(raw_text)

        result = {
            "project": arguments.project,
            "format": format_name,
            "model": arguments.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "answers": answers,
            "raw_text": raw_text,
        }

        out_path = os.path.join(
            arguments.out_dir,
            f"{arguments.project}.{format_name}.{arguments.model}.json")
        with open(out_path, "w", encoding="utf-8", newline="\n") as out_file:
            json.dump(result, out_file, indent=2, ensure_ascii=False)
            out_file.write("\n")

        parsed_count = len(answers)
        print(f"[INFO] - {format_name:9} input={input_tokens:6} output={output_tokens:5} answers={parsed_count} -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
