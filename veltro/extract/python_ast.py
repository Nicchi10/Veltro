"""

veltro/extract/python_ast.py

Extractor: Python source -> Veltro '.vel' text, using the standard library 'ast'.

It walks the class/interface/enum declarations of a package and emits the
equivalent '.vel'. It is deterministic and best-effort: it captures what the
syntax tree states (types, annotated members, visibility, inheritance) and
quietly skips what it cannot know for sure (see SKIP notes below).

What it captures:
    - one module per .py file (dotted import path)
    - classes, Enum subclasses (-> enum), Protocol subclasses (-> interface)
    - ABC subclasses / classes with @abstractmethod (-> class abstract)
    - annotated class attributes (-> fields), @property (-> field)
    - methods (skipping self/cls), @staticmethod / @classmethod (-> '$')
    - base classes (-> 'extend' edges; associations are derived by the parser)

What it skips (v0, documented on purpose):
    - un-annotated 'self.x = ...' assignments (no type to record)
    - dunder methods except __init__
    - *args / **kwargs, method-argument defaults
    - nested classes
    - the extend/impl distinction: every base becomes 'extend'

How to run it:

    1. As a module, writing the result to a file (recommended):
        python -m veltro.extract.python_ast <package_dir> --out out.vel

    2. As a module, printing the result to stdout:
        python -m veltro.extract.python_ast <package_dir>

    3. As a plain script (same arguments):
        python veltro/extract/python_ast.py <package_dir> --out out.vel

    4. On a third-party project (download/clone it first, then point at its
       source folder -- there is no auto-detection):
        python -m veltro.extract.python_ast ./pydantic/pydantic --out build/pydantic.vel

    5. Programmatically, from Python:
        from veltro.extract import extract_project, extract_to_vel
        vel_text, stats = extract_project("path/to/package")   # a whole package
        vel_text = extract_to_vel(source_string, "my.module")  # a single source
"""

import ast
import os
import re
import argparse

from veltro.parser import parse_text


# Base classes that map a class onto a different Veltro kind.
ENUM_BASES = {"Enum", "IntEnum", "Flag", "IntFlag", "StrEnum"}
INTERFACE_BASES = {"Protocol"}
ABSTRACT_BASES = {"ABC"}

# Bases that carry no domain meaning, so they never become an edge.
IGNORED_BASES = ENUM_BASES | INTERFACE_BASES | ABSTRACT_BASES | {"object", "Generic"}

# ============ NAME / TYPE HELPERS ============

def node_name(node) -> str:
    """

    Best-effort name of an expression used as a base class or decorator.

    Handles 'Name' (Foo), 'Attribute' (enum.Enum -> Enum) and 'Subscript'
    (Protocol[T] -> Protocol).

    Args:
        node: an ast expression

    Returns:
        The simple name, or "" if it cannot be determined

    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript):
        return node_name(node.value)
    if isinstance(node, ast.Call):
        return node_name(node.func)
    return ""

def python_type_to_veltro(raw_type: str) -> str:
    """

    Translate a Python type expression into the Veltro type syntax.

    Python writes generics with '[]' and optionals with 'Optional[X]' or
    'X | None'; Veltro uses '<>' and a trailing '?'. Translating keeps the
    model uniform and lets the parser protect commas inside generics.

    Args:
        raw_type (str): e.g. ast.unparse(annotation)

    Returns:
        The Veltro type, e.g:
        'List[Message]'        -> 'List<Message>'
        'Optional[int]'        -> 'int?'
        'Dict[str, Any]'       -> 'Dict<str,Any>'
        'str | None'           -> 'str?'

    """
    # Drop the quotes of forward references ("User", List["User"], ...).
    text = raw_type.strip().replace('"', "").replace("'", "")

    # Optional[X] -> X?
    if text.startswith("Optional[") and text.endswith("]"):
        inner = text[len("Optional["):-1]
        return python_type_to_veltro(inner) + "?"

    # "X | None" / "None | X" (a two-member optional) -> X?
    if "|" in text:
        members = [part.strip() for part in text.split("|")]
        non_none = [part for part in members if part != "None"]
        if len(members) == 2 and len(non_none) == 1:
            return python_type_to_veltro(non_none[0]) + "?"

    # Generic brackets, then collapse spacing around '< > ,'.
    text = text.replace("[", "<").replace("]", ">")
    text = re.sub(r"\s*([<>,])\s*", r"\1", text)
    return text

def annotation_to_type(annotation) -> str:
    """
    Translate an annotation node into a Veltro type, or 'Any' if missing
    """
    if annotation is None:
        return "Any"
    return python_type_to_veltro(ast.unparse(annotation))

def is_dunder(name: str) -> bool:
    """
    True for names like __init__ or __repr__
    """
    return name.startswith("__") and name.endswith("__")

def member_prefix(name: str, is_static: bool) -> str:
    """

    Build the start of a member line: visibility marker (if any) + '$' if static
    + the name.

    A leading underscore means private ('-'); public has no marker.

    Args:
        name (str)
        is_static (bool)

    Returns:
        e.g: 'Conversation', '- _cache', '$Success', '- $helper'

    """
    core = ("$" if is_static else "") + name
    if name.startswith("_"):
        return "- " + core
    return core

def decorator_names(func_node) -> set:
    """
    The set of decorator names on a function/class
    """
    names = set()
    for decorator in func_node.decorator_list:
        names.add(node_name(decorator))
    return names

# ============ MEMBER EXTRACTION ============

def extract_field(ann_assign) -> str:
    """

    Turn an annotated class attribute into a Veltro field line.

    Args:
        ann_assign (ast.AnnAssign): e.g. 'TurnIndex: int = 0'

    Returns:
        The field line, e.g. 'TurnIndex int = 0', or "" if it must be skipped

    """
    target = ann_assign.target
    if not isinstance(target, ast.Name):
        return ""
    name = target.id
    if is_dunder(name):
        return ""

    type_string = annotation_to_type(ann_assign.annotation)

    # ClassVar[T] is a static (class-level) field of type T
    is_static = False
    if type_string.startswith("ClassVar<") and type_string.endswith(">"):
        is_static = True
        type_string = type_string[len("ClassVar<"):-1]

    line = member_prefix(name, is_static) + " " + type_string
    if ann_assign.value is not None:
        line += " = " + ast.unparse(ann_assign.value)
    return line

def extract_property(func_node) -> str:
    """
    Turn an @property method into a field line (its conceptual role)
    """
    name = func_node.name
    type_string = annotation_to_type(func_node.returns)
    return member_prefix(name, False) + " " + type_string

def method_arguments(func_node, is_staticmethod: bool) -> list:
    """

    Collect a method's arguments as Veltro 'name Type' tokens.

    Skips the implicit 'self'/'cls' (unless it is a @staticmethod) and drops
    *args / **kwargs. An un-annotated argument gets the type 'Any' so the model
    keeps the right arity.

    Args:
        func_node (ast.FunctionDef | ast.AsyncFunctionDef)
        is_staticmethod (bool)

    Returns:
        list[str]: e.g. ['invocation ILlmInvocation', 'retries Any']

    """
    positional = func_node.args.args
    skip_first = (
        not is_staticmethod
        and len(positional) > 0
        and positional[0].arg in ("self", "cls")
    )

    selected = []
    if skip_first:
        selected.extend(positional[1:])
    else:
        selected.extend(positional)
    selected.extend(func_node.args.kwonlyargs)

    tokens = []
    for argument in selected:
        argument_type = annotation_to_type(argument.annotation)
        tokens.append(argument.arg + " " + argument_type)
    return tokens

def extract_method(func_node) -> str:
    """

    Turn a method definition into a Veltro method line.

    Args:
        func_node (ast.FunctionDef | ast.AsyncFunctionDef)

    Returns:
        The method line, e.g. 'ExecuteAsync(invocation ILlmInvocation) Task<Foo>'

    """
    decorators = decorator_names(func_node)
    is_staticmethod = "staticmethod" in decorators
    is_static = is_staticmethod or "classmethod" in decorators

    arguments = method_arguments(func_node, is_staticmethod)
    line = member_prefix(func_node.name, is_static) + "(" + ", ".join(arguments) + ")"

    return_type = annotation_to_type(func_node.returns) if func_node.returns else ""
    if return_type:
        line += " " + return_type
    return line

# ============ CLASS / MODULE EXTRACTION ============

def classify(base_names: set, has_abstractmethod: bool) -> str:
    """
    Decide the Veltro kind of a class from its bases
    """
    if base_names & ENUM_BASES:
        return "enum"
    if base_names & INTERFACE_BASES:
        return "interface"
    if (base_names & ABSTRACT_BASES) or has_abstractmethod:
        return "class abstract"
    return "class"

def extract_enum(class_node) -> list:
    """
    Emit the single 'enum Name = A, B, C' line
    """
    values = []
    for item in class_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            values.append(item.target.id)
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    values.append(target.id)
    return ["enum " + class_node.name + " = " + ", ".join(values)]

def extract_class(class_node):
    """

    Turn a class definition into Veltro lines plus its inheritance edges.

    Args:
        class_node (ast.ClassDef)

    Returns:
        (lines, edges):
            lines (list[str]): the declaration and its members
            edges (list[tuple]): (child_name, 'extend', base_name)

    """
    base_names = set()
    raw_bases = []
    for base in class_node.bases:
        name = node_name(base)
        if name:
            base_names.add(name)
            raw_bases.append(name)

    # Does any method carry @abstractmethod?
    has_abstractmethod = False
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if "abstractmethod" in decorator_names(item):
                has_abstractmethod = True

    kind = classify(base_names, has_abstractmethod)

    # Inheritance edges (associations are derived later by the parser)
    edges = []
    for base in raw_bases:
        if base not in IGNORED_BASES:
            edges.append((class_node.name, "extend", base))

    if kind == "enum":
        return extract_enum(class_node), edges

    header = kind + " " + class_node.name
    lines = [header]

    for item in class_node.body:
        if isinstance(item, ast.AnnAssign):
            field_line = extract_field(item)
            if field_line:
                lines.append(field_line)
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            name = item.name
            if is_dunder(name) and name != "__init__":
                continue
            if "property" in decorator_names(item):
                lines.append(extract_property(item))
            else:
                lines.append(extract_method(item))

    return lines, edges

def extract_module(source: str, module_path: str):
    """

    Extract every top-level type from one Python source string.

    Args:
        source (str): the file content
        module_path (str): the dotted module path, e.g. 'veltro.parser'

    Returns:
        (type_lines, edges, stats):
            type_lines (list[str]): all declaration lines for this module
            edges (list[tuple]): inheritance edges found here
            stats (dict): counts per kind

    """
    tree = ast.parse(source)

    type_lines = []
    edges = []
    stats = {"class": 0, "interface": 0, "enum": 0}

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        lines, class_edges = extract_class(node)
        type_lines.extend(lines)
        edges.extend(class_edges)

        header = lines[0]
        if header.startswith("enum "):
            stats["enum"] += 1
        elif header.startswith("interface "):
            stats["interface"] += 1
        else:
            stats["class"] += 1

    return type_lines, edges, stats

# ============ PROJECT WALK ============

def iter_python_files(package_dir: str):
    """
    Yield (absolute_path, dotted_module) for every .py file under package_dir
    """
    base = os.path.dirname(os.path.abspath(package_dir))
    for current_root, _dirs, files in os.walk(package_dir):
        for file_name in sorted(files):
            if not file_name.endswith(".py"):
                continue
            absolute_path = os.path.join(current_root, file_name)
            relative = os.path.relpath(absolute_path, base)
            without_ext = relative[:-len(".py")]
            dotted = without_ext.replace(os.sep, ".")
            if dotted.endswith(".__init__"):
                dotted = dotted[:-len(".__init__")]
            yield absolute_path, dotted

def render_vel(modules: list, all_edges: list) -> str:
    """

    Assemble the final '.vel' text from per-module lines and the global edges.

    Args:
        modules (list[tuple[str, list[str]]]): (module_path, type_lines)
        all_edges (list[tuple]): (from, kind, to)

    Returns:
        str: the complete '.vel' document

    """
    lines = ["veltro 1", ""]

    for module_path, type_lines in modules:
        if not type_lines:
            continue
        lines.append("module " + module_path)
        lines.extend(type_lines)
        lines.append("")

    if all_edges:
        lines.append("rel")
        for from_name, kind, to_name in all_edges:
            lines.append(from_name + " " + kind + " " + to_name)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

def extract_project(package_dir: str):
    """

    Extract a whole package directory into '.vel' text.

    Args:
        package_dir (str): path to the package to scan

    Returns:
        (vel_text, stats):
            vel_text (str): the complete '.vel' document
            stats (dict): counts of modules and of each kind

    """
    modules = []
    all_edges = []
    stats = {"modules": 0, "class": 0, "interface": 0, "enum": 0}

    for absolute_path, module_path in iter_python_files(package_dir):
        with open(absolute_path, encoding="utf-8") as source_file:
            source = source_file.read()

        type_lines, edges, module_stats = extract_module(source, module_path)
        if not type_lines:
            continue

        modules.append((module_path, type_lines))
        all_edges.extend(edges)
        stats["modules"] += 1
        for kind in ("class", "interface", "enum"):
            stats[kind] += module_stats[kind]

    return render_vel(modules, all_edges), stats

def extract_to_vel(source: str, module_path: str) -> str:
    """
    Convenience for tests: extract a single source string into '.vel' text
    """
    type_lines, edges, _stats = extract_module(source, module_path)
    return render_vel([(module_path, type_lines)], edges)

# ============ CLI ============

def main(argv=None):

    examples = (
        "examples:\n"
        "  python -m veltro.extract.python_ast veltro --out build/veltro.vel\n"
        "  python -m veltro.extract.python_ast ./pydantic/pydantic --out build/pydantic.vel\n"
        "  python -m veltro.extract.python_ast veltro            # print to stdout\n"
    )
    parser = argparse.ArgumentParser(
        description="Extract Veltro '.vel' from a Python package",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("package", help="path to the Python package directory")
    parser.add_argument("--out", help="where to write the .vel (default: stdout)")
    arguments = parser.parse_args(argv)

    vel_text, stats = extract_project(arguments.package)

    seen_types = stats["class"] + stats["interface"] + stats["enum"]

    # Self-audit: re-parse the produced .vel and check nothing was lost
    model = parse_text(vel_text)
    in_model = len(model["nodes"])
    audit = "MATCH" if in_model == seen_types else "MISMATCH"

    print(f"[INFO] - modules: {stats['modules']}")
    print(f"[INFO] - types seen in AST: {seen_types} ({stats['class']} classes, {stats['interface']} interfaces,{stats['enum']} enums)")
    print(f"[INFO] - types in parsed model: {in_model}  -> {audit}")
    print(f"[INFO] - edges: {len(model['edges'])}")

    if arguments.out:
        with open(arguments.out, "w", encoding="utf-8", newline="\n") as out_file:
            out_file.write(vel_text)
        print(f"[INFO] - written: {arguments.out}")
    else:
        print()
        print(vel_text)

    return 0 if audit == "MATCH" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
