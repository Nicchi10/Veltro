"""

veltro/extract/project.py

A whole repository -> one '.vel' and one source index.

Until this existed, getting started meant knowing which extractor matched which
language, running one module invocation per language with a different syntax
each time, and being left with several '.vel' files and several indexes that
nothing could join. That is not a tool someone new can pick up.

So: detect what the repository is written in, run the extractors that apply,
and hand back ONE document. Languages are detected by counting the source files
that survive the pruning policy in walk.py, which means a repository whose only
Python is a build script does not get reported as a Python project.

Two honesty rules live here, because this is the first thing a newcomer runs:

- an extractor that needs an extra which is not installed is REPORTED, never
  skipped in silence: "there is C# here and I could not read it" is a different
  statement from "there is no C# here".
- Veltro models TYPES. On a repository built out of free functions the '.vel'
  is nearly empty, and that is a property of the format, not a failure the user
  should have to infer from a small file.

"""

import os

from veltro.extract.walk import iter_source_files, new_report
from veltro.index import merge_index, new_index

# TypeScript and JavaScript share a toolchain, an extractor and a file walk
TYPESCRIPT_EXTENSIONS = (".d.ts", ".tsx", ".ts", ".mts", ".cts", ".jsx", ".js", ".mjs", ".cjs")

# Detection order is report order. 'extra' is the pip extra that supplies the extractor's dependency, None when the standard library is enough.
LANGUAGES = (
    {"name": "python", "extensions": (".py",), "module": "veltro.extract.python_ast", "extra": None},
    {"name": "typescript", "extensions": TYPESCRIPT_EXTENSIONS, "module": "veltro.extract.tree_sitter_typescript", "extra": "extract"},
    {"name": "csharp", "extensions": (".cs",), "module": "veltro.extract.tree_sitter_csharp", "extra": "extract"},
    # The Java extractor is a standalone Java program, so it cannot be called
    # from here. Detected anyway: saying nothing would read as "no Java".
    {"name": "java", "extensions": (".java",), "module": None, "extra": None},
)

# Fewer than one type per three source files, and the repository is probably not organised around types at all. 
# The number is a judgement call, chosen so that it fires on Veltro's own repository 8 types across 35 files, a tool built
# out of functions and stays quiet on the extracted examples, where pydantic
# alone carries 360 types. It exists to say something true and unwelcome early, so err towards saying it.
SPARSE_TYPES_PER_FILE = 1.0 / 3.0


def language_by_name(name: str):
    """

    One entry of LANGUAGES, or None when the name is not one we know.

    Args:
        name (str): e.g. 'python'

    Returns:
        dict | None: the language entry

    """
    for language in LANGUAGES:
        if language["name"] == name:
            return language
    return None


def detect_languages(root: str, keep_tests: bool = False, exclude=()) -> dict:
    """

    How many source files of each language the repository holds.

    Counted AFTER pruning, so a vendored 'node_modules' does not make a Python
    project look like a TypeScript one.

    Args:
        root (str): the repository to scan
        keep_tests (bool): count test files too
        exclude (iterable[str]): extra glob patterns to skip

    Returns:
        dict: language name -> file count, only for languages actually present

    """
    found = {}
    for language in LANGUAGES:
        count = 0
        for _path in iter_source_files(root, language["extensions"], keep_tests, exclude):
            count += 1
        if count:
            found[language["name"]] = count
    return found


def load_extractor(language: dict):
    """

    Import a language's extractor, or say why it cannot be used.

    Args:
        language (dict): an entry of LANGUAGES

    Returns:
        (callable | None, str | None): its extract_project, or a reason

    """
    if language["module"] is None:
        return None, "the Java extractor is a standalone Java program, see veltro/extract/java/"

    try:
        module = __import__(language["module"], fromlist=["extract_project"])
    except ImportError:
        return None, f"needs the [{language['extra']}] extra: pip install 'veltro[{language['extra']}]'"
    return module.extract_project, None


def strip_version_pragma(vel_text: str) -> str:
    """

    Drop a leading 'veltro N' line, so several documents can be joined into one.

    Args:
        vel_text (str): a '.vel' document

    Returns:
        str: the same text without its version pragma

    """
    lines = vel_text.splitlines()
    kept = []
    dropped = False
    for line in lines:
        if not dropped and line.strip().startswith("veltro "):
            dropped = True
            continue
        kept.append(line)
    return "\n".join(kept).lstrip("\n")


def extract_repository(root: str, languages=None, keep_tests: bool = False, exclude=()) -> dict:
    """

    Extract every language present into one '.vel' and one index.

    Args:
        root (str): the repository to scan
        languages (list[str] | None): only these, or None for everything found
        keep_tests (bool): read tests too
        exclude (iterable[str]): extra glob patterns to skip

    Returns:
        dict: 'vel' (the joined document), 'index', 'per_language' (name ->
            counts), 'files' (total read), 'skipped' (name -> reason) and
            'notes' (things the user must be told)

    """
    detected = detect_languages(root, keep_tests, exclude)
    wanted = languages if languages else list(detected)

    result = {
        "vel": "",
        "index": new_index(root),
        "per_language": {},
        "files": 0,
        "skipped": {},
        "notes": [],
        "detected": detected,
    }

    documents = []
    for name in wanted:
        language = language_by_name(name)
        if language is None:
            result["skipped"][name] = "not a language Veltro knows"
            continue
        if name not in detected:
            result["skipped"][name] = "no source files found"
            continue

        extract_project, reason = load_extractor(language)
        if extract_project is None:
            result["skipped"][name] = reason
            continue

        report = new_report()
        vel_text, stats, source_index = extract_project(root, keep_tests, list(exclude), report)
        types = stats["class"] + stats["interface"] + stats["enum"]

        result["per_language"][name] = {"files": report["files"], "types": types}
        result["files"] += report["files"]
        merge_index(result["index"], source_index)
        if vel_text.strip():
            documents.append(strip_version_pragma(vel_text))

    result["vel"] = "veltro 1\n\n" + "\n".join(documents) if documents else "veltro 1\n"
    result["notes"] = build_notes(result, detected)
    return result


def build_notes(result: dict, detected: dict) -> list:
    """

    What the user has to be told, in plain words.

    Args:
        result (dict): the extraction so far
        detected (dict): language -> file count

    Returns:
        list[str]: the notes, empty when there is nothing to say

    """
    notes = []

    total_types = 0
    for name in result["per_language"]:
        total_types += result["per_language"][name]["types"]

    for name in sorted(result["skipped"]):
        if name in detected:
            notes.append(f"{detected[name]} {name} files were found but not read: {result['skipped'][name]}")

    if result["files"] and total_types == 0:
        notes.append("no types at all: Veltro models classes, interfaces and enums, and this repository appears to have none")
    elif result["files"] and total_types < result["files"] * SPARSE_TYPES_PER_FILE:
        notes.append(f"only {total_types} types in {result['files']} files: Veltro models TYPES, so a repository built out of free functions gives it little to describe")

    return notes
