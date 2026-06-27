"""

veltro/extract/tree_sitter_csharp.py

Extractor: C# source -> Veltro '.vel' text, using tree-sitter's C# grammar.

The Python and Java extractors use each language's own parser ('ast', javac).
C# (and JS) use tree-sitter, a robust universal parser, so every Python-side
extractor shares one toolchain. Like the others it works at the PARSE level
only: it is deterministic and best-effort, reporting what the syntax tree
states and quietly skipping what it cannot know for sure (see SKIP notes).

What it captures:
    - one module per C# namespace (the dotted namespace name)
    - class / interface / enum, plus struct and record (both -> class)
    - 'abstract' / 'sealed' / 'static' class modifiers (-> 'class abstract' ...)
    - fields and auto-properties (-> fields), with visibility + static
    - methods and constructors, with typed parameters and return types
    - the base list -> 'extend' / 'impl' edges (see the I-prefix note below)

What it skips (v0, on purpose, mirroring the other extractors):
    - nested / inner type declarations (only types directly under a namespace)
    - attributes, XML doc comments, using directives
    - generic type parameters of methods (<T>) and where-constraints
    - explicit interface implementations, operators, indexers, events

Note on edges (the one place parse-level C# is uncertain): a base list like
'class C : Base, IFoo' does not say which entry is the base class and which are
interfaces without type resolution. We use the near-universal C# convention: a
base whose simple name matches I[A-Z]... is an interface ('impl'), anything else
is a base class ('extend'). An interface's bases are always 'extend'.

Dependencies (tooling only):  pip install tree_sitter tree_sitter_c_sharp

How to run it:
    python -m veltro.extract.tree_sitter_csharp <src_dir> --out out.vel
    python -m veltro.extract.tree_sitter_csharp <src_dir>            # to stdout
"""

import argparse
import os
import re
import sys

from tree_sitter import Language, Parser
import tree_sitter_c_sharp as tscsharp

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text

CSHARP = Language(tscsharp.language())

# C# tree-sitter declaration node types -> the Veltro kind they map onto.
# struct and record are class-like (they carry fields and methods), so -> class.
TYPE_DECLARATIONS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "struct_declaration": "class",
    "record_declaration": "class",
    "record_struct_declaration": "class",
    "enum_declaration": "enum",
}
NAMESPACE_DECLARATIONS = {"namespace_declaration", "file_scoped_namespace_declaration"}

# Bases that carry no domain meaning, so they never become an edge.
IGNORED_BASES = {"object", "Object", "ValueType"}

# Veltro line-start keywords. A public member whose name is one of these would collide with a declaration (a field 'module str' would read as a 'module'
# line), so such a member must keep an explicit '+'. Methods are safe (the '(' tells them apart), but forcing '+' on them too is harmless.
RESERVED_NAMES = {"veltro", "module", "class", "interface", "enum", "rel"}

# ============ TREE / NAME / TYPE HELPERS ============

def text(node) -> str:
    """
    The source text a node spans, or '' for a missing node
    """
    if node is None:
        return ""
    return node.text.decode("utf-8")

def field_text(node, field_name: str) -> str:
    """
    Text of a named child field, or '' if that field is absent
    """
    return text(node.child_by_field_name(field_name))

def named_children_of_type(node, type_name: str) -> list:
    """
    Every named child of a node with the given tree-sitter type
    """
    selected = []
    for child in node.named_children:
        if child.type == type_name:
            selected.append(child)
    return selected

def first_child_of_type(node, type_name: str):
    """
    The first named child with the given type, or None
    """
    for child in node.named_children:
        if child.type == type_name:
            return child
    return None

def csharp_type_to_veltro(type_text: str) -> str:
    """

    Translate a C# type into the Veltro type syntax.

    C# already uses '<>' for generics and a trailing '?' for nullable, exactly
    like Veltro, so the only job is to drop the spaces around '< > ,'. Arrays
    'T[]' are kept as-is.

    Args:
        type_text (str): e.g. 'Dictionary<string, object>'

    Returns:
        The Veltro type, e.g. 'Dictionary<string,object>'

    """
    collapsed = re.sub(r"\s*([<>,])\s*", r"\1", type_text)
    return collapsed.strip()

def simple_name(type_text: str) -> str:
    """
    The last identifier of a (possibly qualified, generic) type:
    'System.Collections.Generic.List<int>' -> 'List'
    """
    name = type_text.strip()
    # Cut off generic args, array brackets, and a primary-constructor base call
    # ('Base(args)' -> 'Base'), then the namespace qualifier.
    for cut in ("<", "[", "("):
        index = name.find(cut)
        if index >= 0:
            name = name[:index]
    dot = name.rfind(".")
    if dot >= 0:
        name = name[dot + 1:]
    return name.strip()

# ============ VISIBILITY / MEMBER HELPERS ============

def modifiers_of(node) -> set:
    """
    The set of modifier keywords on a declaration (public, static, abstract, ...)
    """
    names = set()
    for child in node.children:
        if child.type == "modifier":
            names.add(text(child))
    return names

def visibility_marker(modifiers: set, inside_interface: bool) -> str:
    """

    The Veltro visibility marker from C# access modifiers.

    Interface members are implicitly public. A C# type member with no modifier
    defaults to private, and 'internal' (assembly-private) maps onto Veltro's
    package marker '@'.

    Args:
        modifiers (set)
        inside_interface (bool)

    Returns:
        "" (public), "-" (private), "#" (protected) or "@" (package/internal)

    """
    if inside_interface:
        return ""
    if "public" in modifiers:
        return ""
    if "protected" in modifiers:
        return "#"
    if "internal" in modifiers:
        return "@"
    # 'private' explicit, or no modifier at all (C#'s default for members)
    return "-"

def member_prefix(name: str, marker: str, is_static: bool) -> str:
    """
    Build the start of a member line: visibility marker (if any) + '$' if static
    + the name. A public member whose name collides with a Veltro keyword keeps
    an explicit '+'.
    """
    core = ("$" if is_static else "") + name
    if marker == "":
        if name in RESERVED_NAMES:
            return "+ " + core
        return core
    return marker + " " + core

def safe_default(value_text: str) -> str:
    """

    Keep a field initializer only when it is a short, single-line value.

    Anything multi-line (e.g. 'new Foo { ... }') would inject newlines into the
    line-oriented .vel and corrupt it (the same lesson the Java extractor
    learned on Spring), so it is dropped. A default is informative, not
    load-bearing.

    Args:
        value_text (str)

    Returns:
        The value, or "" when it is unsafe to keep

    """
    value_text = value_text.strip()
    if not value_text or "\n" in value_text or "{" in value_text:
        return ""
    return value_text

# ============ MEMBER EXTRACTION ============

def initializer_text(declarator) -> str:
    """
    The text after '=' in a variable_declarator, or '' if there is none
    """
    named = declarator.named_children
    if len(named) >= 2:
        return text(named[-1])
    return ""

def extract_field_declaration(node, inside_interface: bool) -> list:
    """

    Turn a C# field declaration into Veltro field lines.

    A single declaration may introduce several variables ('int a, b = 0;'), so
    this returns one line per declared name.

    Args:
        node: a field_declaration node
        inside_interface (bool)

    Returns:
        list[str]: e.g. ['- _cache Dictionary<string,object>', 'count int = 0']

    """
    modifiers = modifiers_of(node)
    marker = visibility_marker(modifiers, inside_interface)
    is_static = "static" in modifiers or "const" in modifiers

    declaration = first_child_of_type(node, "variable_declaration")
    if declaration is None:
        return []

    type_string = csharp_type_to_veltro(field_text(declaration, "type"))

    lines = []
    for declarator in named_children_of_type(declaration, "variable_declarator"):
        name = field_text(declarator, "name")
        line = member_prefix(name, marker, is_static) + " " + type_string
        default = safe_default(initializer_text(declarator))
        if default:
            line += " = " + default
        lines.append(line)
    return lines

def extract_property(node, inside_interface: bool) -> str:
    """
    Turn an auto-property into a field line (its conceptual role), e.g.
    'public string Name { get; set; }' -> 'Name string'
    """
    modifiers = modifiers_of(node)
    marker = visibility_marker(modifiers, inside_interface)
    is_static = "static" in modifiers

    name = field_text(node, "name")
    type_string = csharp_type_to_veltro(field_text(node, "type"))
    return member_prefix(name, marker, is_static) + " " + type_string

def method_arguments(node) -> list:
    """
    Collect a method's parameters as Veltro 'name Type' tokens
    """
    parameters = node.child_by_field_name("parameters")
    tokens = []
    if parameters is None:
        return tokens
    for parameter in named_children_of_type(parameters, "parameter"):
        name = field_text(parameter, "name")
        type_string = csharp_type_to_veltro(field_text(parameter, "type"))
        tokens.append(name + " " + type_string)
    return tokens

def extract_method(node, class_name: str, inside_interface: bool) -> str:
    """

    Turn a method or constructor into a Veltro method line. A constructor is
    emitted under the class's own name and, like a void method, carries no
    return type.

    Args:
        node: a method_declaration or constructor_declaration node
        class_name (str)
        inside_interface (bool)

    Returns:
        e.g. 'Refresh(ttl int)' or '$Make(raw Dictionary<string,object>) Session'

    """
    modifiers = modifiers_of(node)
    marker = visibility_marker(modifiers, inside_interface)
    is_static = "static" in modifiers

    is_constructor = node.type == "constructor_declaration"
    if is_constructor:
        name = class_name
    else:
        name = field_text(node, "name")

    arguments = method_arguments(node)
    line = member_prefix(name, marker, is_static) + "(" + ", ".join(arguments) + ")"

    if not is_constructor:
        return_type = csharp_type_to_veltro(field_text(node, "type"))
        if return_type and return_type != "void":
            line += " " + return_type
    return line

# ============ TYPE (CLASS / INTERFACE / ENUM) EXTRACTION ============

def classify_kind(node) -> str:
    """
    The Veltro kind keyword for a type: 'enum', 'interface', 'class', or
    'class abstract' / 'class sealed' / 'class static'
    """
    kind = TYPE_DECLARATIONS[node.type]
    if kind == "class":
        modifiers = modifiers_of(node)
        for modifier in ("abstract", "sealed", "static"):
            if modifier in modifiers:
                return "class " + modifier
    return kind

def extract_enum(node) -> list:
    """
    Emit the single 'enum Name = A, B, C' line
    """
    name = field_text(node, "name")
    values = []
    body = node.child_by_field_name("body")
    if body is not None:
        for member in named_children_of_type(body, "enum_member_declaration"):
            values.append(field_text(member, "name"))
    return ["enum " + name + " = " + ", ".join(values)]

def collect_edges(node, kind: str, edges: list) -> None:
    """

    Record the inheritance edges of a type from its base list.

    For an interface every base is an 'extend' edge. For a class/struct/record
    cannot resolve class-vs-interface at parse level, so applies the C#
    naming convention: a base named I[A-Z]... is an interface ('impl'),
    everything else is a base class ('extend').

    Args:
        node: the type declaration
        kind (str): the Veltro kind keyword
        edges (list): the running list of (from, kind, to) to append to

    """
    child_name = field_text(node, "name")
    base_list = node.child_by_field_name("bases")
    if base_list is None:
        base_list = first_child_of_type(node, "base_list")
    if base_list is None:
        return

    is_interface = kind == "interface"
    for base in base_list.named_children:
        base_name = simple_name(text(base))
        # A base list can also carry non-type nodes (e.g. the 'argument_list' of
        # a 'Base(args)' primary-constructor base). Keep only clean identifiers,
        # so a relation row can never become malformed.
        if not re.match(r"^[A-Za-z_]\w*$", base_name):
            continue
        if base_name in IGNORED_BASES:
            continue
        if is_interface:
            edge_kind = "extend"
        elif re.match(r"^I[A-Z]", base_name):
            edge_kind = "impl"
        else:
            edge_kind = "extend"
        edges.append((child_name, edge_kind, base_name))

def extract_type(node, edges: list) -> list:
    """

    Turn one type declaration into its Veltro lines, appending its inheritance
    edges to the shared list.

    Args:
        node: a type declaration node
        edges (list)

    Returns:
        list[str]: the declaration line plus its member lines

    """
    kind = classify_kind(node)
    collect_edges(node, kind, edges)

    if kind == "enum":
        return extract_enum(node)

    inside_interface = kind == "interface"
    class_name = field_text(node, "name")

    lines = [kind + " " + class_name]

    body = node.child_by_field_name("body")
    if body is not None:
        for member in body.named_children:
            if member.type == "field_declaration":
                lines.extend(extract_field_declaration(member, inside_interface))
            elif member.type == "property_declaration":
                lines.append(extract_property(member, inside_interface))
            elif member.type in ("method_declaration", "constructor_declaration"):
                lines.append(extract_method(member, class_name, inside_interface))
    return lines

# ============ PROJECT WALK & RENDERING ============

def namespace_name(node, parent_namespace: str) -> str:
    """
    The dotted namespace path for a namespace node, nested under its parent
    """
    name = field_text(node, "name")
    if parent_namespace:
        return parent_namespace + "." + name
    return name

def collect(node, namespace: str, modules: dict, edges: list, stats: dict) -> None:
    """

    Recursively walk the tree: descend into namespaces (tracking the dotted
    name), extract top-level types, and never recurse into a type, so nested
    types are skipped like the other extractors.

    Args:
        node: the current tree-sitter node
        namespace (str): the namespace enclosing this node
        modules (dict): namespace -> accumulated type lines (modified in place)
        edges (list): the running inheritance edges (modified in place)
        stats (dict): counts per kind (modified in place)

    """
    if node.type in NAMESPACE_DECLARATIONS:
        inner = namespace_name(node, namespace)
        body = node.child_by_field_name("body")
        children = body.children if body is not None else node.children
        for child in children:
            collect(child, inner, modules, edges, stats)
        return

    if node.type in TYPE_DECLARATIONS:
        kind = TYPE_DECLARATIONS[node.type]
        stats[kind] = stats.get(kind, 0) + 1
        module_lines = modules.setdefault(namespace or "global", [])
        module_lines.extend(extract_type(node, edges))
        return

    for child in node.children:
        collect(child, namespace, modules, edges, stats)

def render_vel(modules: dict, edges: list) -> str:
    """
    Assemble the final '.vel' text from the per-namespace lines and the edges
    """
    lines = ["veltro 1", ""]

    for module_path, type_lines in modules.items():
        if not type_lines:
            continue
        lines.append("module " + module_path)
        lines.extend(type_lines)
        lines.append("")

    if edges:
        lines.append("rel")
        for from_name, kind, to_name in edges:
            lines.append(from_name + " " + kind + " " + to_name)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"

def iter_csharp_files(directory: str):
    """
    Yield every .cs file path under a directory, recursively
    """
    for current_root, _dirs, files in os.walk(directory):
        for file_name in sorted(files):
            if file_name.endswith(".cs"):
                yield os.path.join(current_root, file_name)

def extract_project(directory: str):
    """

    Extract a whole C# source tree into '.vel' text.

    Args:
        directory (str): path to the source folder to scan

    Returns:
        (vel_text, stats):
            vel_text (str): the complete '.vel' document
            stats (dict): counts of each kind (class / interface / enum)

    """
    parser = Parser(CSHARP)
    modules = {}
    edges = []
    stats = {"class": 0, "interface": 0, "enum": 0}

    for path in iter_csharp_files(directory):
        with open(path, "rb") as source_file:
            source = source_file.read()
        tree = parser.parse(source)
        collect(tree.root_node, "", modules, edges, stats)

    return render_vel(modules, edges), stats

def extract_to_vel(source_text: str) -> str:
    """
    Convenience for tests: extract a single C# source string into '.vel' text
    """
    parser = Parser(CSHARP)
    tree = parser.parse(source_text.encode("utf-8"))
    modules = {}
    edges = []
    stats = {"class": 0, "interface": 0, "enum": 0}
    collect(tree.root_node, "", modules, edges, stats)
    return render_vel(modules, edges)

# ============ CLI ============

def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract Veltro '.vel' from a C# source tree")
    parser.add_argument("source", help="path to the C# source directory")
    parser.add_argument("--out", help="where to write the .vel (default: stdout)")
    arguments = parser.parse_args(argv)

    vel_text, stats = extract_project(arguments.source)
    seen_types = stats["class"] + stats["interface"] + stats["enum"]

    # Self-audit: re-parse the produced .vel and check nothing was lost
    model = parse_text(vel_text)
    in_model = len(model["nodes"])
    audit = "MATCH" if in_model == seen_types else "MISMATCH"

    print(f"[INFO] - types seen: {seen_types} ({stats['class']} classes, {stats['interface']} interfaces, {stats['enum']} enums)")
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
    sys.exit(main())
