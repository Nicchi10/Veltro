"""

veltro/index.py

The sidecar source index: where each type of the model is declared.

A '.vel' is a map without coordinates. It says that 'Orleans.Runtime.Silo'
exists, what it carries and what it relates to, but not where to find it, and
the module cannot be turned back into a path in general (a C# namespace has no
relation to the directory tree, and a TypeScript module path is ambiguous when a
file name itself contains dots). So going from the map to the code needs an
explicit index.

It is kept OUT of the '.vel' on purpose. The '.vel' is what enters an LLM's
context and must stay frugal; a 'file:line' on every type would cost tokens on
every single read for information only a tool ever uses. Here it costs nothing.

The index is a build artefact: it is derived from the source, it is specific to
one checkout, and it goes stale at the first edit (line numbers move). Regenerate
it, do not commit it -- an index pointing at the wrong line is worse than none.

Shape (see index.schema.json):

    {
      "veltro": 1,
      "root": "C:/src/orleans",
      "locations": {
        "Orleans.Runtime.Silo": [
          {"file": "src/Orleans.Runtime/Silo/Silo.cs", "line": 61, "end_line": 402}
        ]
      }
    }

A type maps to a LIST of spans because one type can legitimately be declared in
several files (C# 'partial class', TypeScript interface merging), which the
parser merges into a single node.

"""

import json
import os

INDEX_VERSION = 1

# The suffix that replaces '.vel', so an index always travels next to the file it describes ('build/out.vel' -> 'build/out.index.json')
INDEX_SUFFIX = ".index.json"


def posix_path(path: str) -> str:
    """
    A path with forward slashes, so an index written on Windows reads the same
    everywhere

    Args:
        path (str)

    Returns:
        str: the path with '\\' turned into '/'
    """
    return path.replace(os.sep, "/").replace("\\", "/")


def new_index(root: str) -> dict:
    """

    An empty index for a scan rooted at 'root'.

    Args:
        root (str): the directory every recorded file will be relative to

    Returns:
        dict: an index with no locations yet

    """
    return {
        "veltro": INDEX_VERSION,
        "root": posix_path(os.path.abspath(root)),
        "locations": {},
    }


def add_location(index: dict, type_id: str, absolute_path: str, line: int, end_line: int) -> None:
    """

    Record one place a type is declared.

    Called once per DECLARATION, not once per type: a partial class adds a span
    to the same id for every file it is spread over, in the order the extractor
    met them.

    Args:
        index (dict): the index being built (modified in place)
        type_id (str): the model node id, e.g. 'Orleans.Runtime.Silo'
        absolute_path (str): the file the declaration was read from
        line (int): 1-based line the declaration starts on
        end_line (int): 1-based line the declaration ends on

    """
    relative = os.path.relpath(os.path.abspath(absolute_path), index["root"])
    span = {
        "file": posix_path(relative),
        "line": line,
        "end_line": end_line,
    }
    index["locations"].setdefault(type_id, []).append(span)


def index_path_for(vel_path: str) -> str:
    """

    Where the index of a '.vel' belongs: next to it, same stem.

    Args:
        vel_path (str): e.g. 'build/orleans.vel'

    Returns:
        str: e.g. 'build/orleans.index.json'

    """
    root, extension = os.path.splitext(vel_path)
    if extension:
        return root + INDEX_SUFFIX
    return vel_path + INDEX_SUFFIX


def write_index(index: dict, path: str) -> None:
    """

    Write the index as JSON, with its ids sorted so two runs over the same
    source produce the same bytes (a diffable, deterministic artefact).

    Args:
        index (dict): the index to write
        path (str): where to write it

    """
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)

    ordered = {
        "veltro": index["veltro"],
        "root": index["root"],
        "locations": {},
    }
    for type_id in sorted(index["locations"]):
        ordered["locations"][type_id] = index["locations"][type_id]

    with open(path, "w", encoding="utf-8", newline="\n") as index_file:
        json.dump(ordered, index_file, indent=2, ensure_ascii=False)
        index_file.write("\n")


def read_index(path: str) -> dict:
    """

    Read an index from disk.

    Args:
        path (str): the '.index.json' to read

    Returns:
        dict: the index

    """
    with open(path, encoding="utf-8") as index_file:
        return json.load(index_file)


def spans_of(index: dict, type_id: str) -> list:
    """

    Every place a type is declared, empty when the index does not know it.

    Args:
        index (dict): a loaded index
        type_id (str): the model node id

    Returns:
        list[dict]: the spans, each {'file', 'line', 'end_line'}

    """
    return index.get("locations", {}).get(type_id, [])


def resolve_file(index: dict, span: dict, root: str = None) -> str:
    """

    The absolute path of a span, letting the caller override the recorded root
    when the project has been moved or is being read from another checkout.

    Args:
        index (dict): a loaded index
        span (dict): one span of that index
        root (str): a replacement for the index's own root, or None

    Returns:
        str: the absolute path of the file the span points into

    """
    base = root if root else index.get("root", "")
    return os.path.normpath(os.path.join(base, span["file"]))


def read_span(index: dict, span: dict, root: str = None) -> str:
    """

    The source text a span covers, declaration line included.

    Args:
        index (dict): a loaded index
        span (dict): one span of that index
        root (str): a replacement for the index's own root, or None

    Returns:
        str: the lines of the declaration, or "" when the file cannot be read

    """
    path = resolve_file(index, span, root)
    try:
        with open(path, encoding="utf-8", errors="replace") as source_file:
            lines = source_file.readlines()
    except OSError:
        return ""

    first = max(span["line"] - 1, 0)
    last = min(span["end_line"], len(lines))
    return "".join(lines[first:last])
