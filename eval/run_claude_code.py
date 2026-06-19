"""

eval/run_claude_code.py

STEP 2, Claude edition. Same job as run.py, but the answers come from a local
Claude Code session (`claude -p`) instead of a paid API — so it runs on the
Claude Code subscription, not per-token API billing.

Isolation (critical): the model must answer from the prompt ALONE. We pass
`--tools ""` so the session has no file/bash tools and therefore cannot read the
repo or the ground truth (eval/subjects/*.questions.json). The diagram is piped
on stdin (too large for an argv); the short notation legend goes in the system
prompt. The Veltro legend in run.py.FORMATS is the "minimal context" the model
needs for a notation it has never seen.

Caveats (write these down when reporting):
- This is the Claude Code HARNESS, not the raw API: every call carries Claude
  Code's own (cached) system prompt, so token counts are NOT comparable to API
  runs and `total_cost_usd` is informational (subscription, not billed per token).
- Comparing formats WITHIN a Claude model is valid; comparing a Claude-Code
  model's absolute accuracy to an OpenAI-API model is cross-harness — mark it.

Run (one model per invocation, like run.py; repeat for haiku/sonnet/opus):
    python eval/run_claude_code.py pydantic --model sonnet
    python eval/run_claude_code.py pydantic --model opus --repeat 5
"""

import argparse
import json
import os
import shutil
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from eval.run import FORMATS, load_subject, load_questions, build_prompt, extract_json

PROVIDER = "claudecode"


def call_claude_code(model: str, effort: str, system_text: str, user_text: str) -> tuple:
    """

    Ask a local Claude Code session one question set and return
    (raw_text, input_tokens, output_tokens, cost_usd).

    Tools are disabled (`--tools ""`) so the model cannot read any file; the
    diagram is sent on stdin so it is never an argv (no length limit, no shell
    quoting of the big text).

    """
    executable = shutil.which("claude")
    if executable is None:
        raise RuntimeError("the 'claude' CLI was not found on PATH")

    command = [
        executable,
        "-p",
        "--output-format", "json",
        "--model", model,
        "--effort", effort,
        "--append-system-prompt", system_text,
        "--tools", "",  # last: disable every tool (no repo / ground-truth access)
    ]

    completed = subprocess.run(
        command,
        input=user_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(f"claude -p failed ({completed.returncode}): {completed.stderr.strip()}")

    payload = json.loads(completed.stdout)
    raw_text = payload.get("result", "")
    usage = payload.get("usage", {})
    return (
        raw_text,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        payload.get("total_cost_usd"),
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Ask the eval questions to a local Claude Code session (no API cost)")
    parser.add_argument("project", help="project name (matches eval/subjects/<project>.*)")
    parser.add_argument("--model", default="sonnet", help="claude alias: haiku, sonnet, opus")
    parser.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    parser.add_argument("--formats", default="veltro,mermaid,plantuml,d2",
                        help="comma-separated subset of: veltro,mermaid,plantuml,d2")
    parser.add_argument("--subjects-dir", default="eval/subjects")
    parser.add_argument("--out-dir", default="eval/results")
    parser.add_argument("--repeat", type=int, default=1,
                        help="how many times to query each format (for mean +/- std)")
    arguments = parser.parse_args(argv)

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

        format_info = FORMATS[format_name]
        diagram = load_subject(arguments.subjects_dir, arguments.project,
                               format_info["extension"])
        system_text, user_text = build_prompt(format_info["legend"], diagram, questions)

        runs = []
        for run_index in range(arguments.repeat):
            raw_text, input_tokens, output_tokens, cost = call_claude_code(
                arguments.model, arguments.effort, system_text, user_text)
            runs.append({
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
                "answers": extract_json(raw_text),
                "raw_text": raw_text,
            })

        result = {
            "project": arguments.project,
            "provider": PROVIDER,
            "format": format_name,
            "model": arguments.model,
            "effort": arguments.effort,
            "runs": runs,
        }

        # Model in the filename so haiku/sonnet/opus do not overwrite each other.
        out_path = os.path.join(
            arguments.out_dir,
            f"{arguments.project}.{format_name}.{PROVIDER}-{arguments.model}.json")
        with open(out_path, "w", encoding="utf-8", newline="\n") as out_file:
            json.dump(result, out_file, indent=2, ensure_ascii=False)
            out_file.write("\n")

        answers_per_run = []
        for run in runs:
            answers_per_run.append(len(run["answers"]))
        print(f"[INFO] - claudecode/{arguments.model} (effort={arguments.effort}) "
              f"{format_name:9} runs={len(runs)} answers/run={answers_per_run} -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
