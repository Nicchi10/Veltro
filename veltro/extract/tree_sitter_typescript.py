"""

veltro/extract/tree_sitter_typescript.py

Extractor: TypeScript / JavaScript source -> Veltro '.vel' text, using
tree-sitter's TypeScript grammar.

The Python-side twin for the TS/JS world, sharing the same tree-sitter toolchain
as the C# extractor (its declared seed). Like every extractor it works at the
PARSE level only: deterministic and best-effort, reporting what the syntax tree
states and quietly skipping what it cannot know for sure (see SKIP notes).

Two things are cleaner than the C# twin, because TypeScript spells them out:
    - extend vs impl needs no naming heuristic: 'extends' is a base class
      ('extend'), 'implements' is an interface ('impl'). No 'I'-prefix guess
    - 'abstract class' is its own grammar node, not a modifier to detect

What it captures:
    - one module per file (the dotted file path, ES-module style), OR the
      explicit 'namespace X.Y { ... }' name when types live inside one
    - class / interface / enum (incl. 'const enum'); abstract class -> 'class abstract'
    - fields and getters (-> fields), with visibility + static + nullable ('?')
    - methods and constructors, with typed parameters and return types
    - 'extends' / 'implements' clauses -> 'extend' / 'impl' edges

What it skips (v0.1, on purpose, mirroring the other extractors):
    - nested / inner type declarations (only types directly under a file/namespace)
    - type aliases ('type X = ...'), decorators, ambient 'declare' bodies
    - generic type parameters of methods (<T>) and where-like constraints
    - index/call/construct signatures, operators, destructured parameters
    - free functions and consts (Veltro is a graph of TYPES)

Visibility: TypeScript members are PUBLIC by default (unlike C#). 'private' and a
'#name' hard-private both map to '-', 'protected' to '#'. TS has no assembly
('internal') level, so '@' is never emitted.

Dependencies (tooling only):  pip install tree_sitter tree_sitter_typescript

How to run it:
    python -m veltro.extract.tree_sitter_typescript <src_dir> --out out.vel
    python -m veltro.extract.tree_sitter_typescript <src_dir>            # to stdout
"""

import argparse
import os
import re
import sys

from tree_sitter import Language, Parser
import tree_sitter_typescript as tstypescript

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.parser import parse_text

# Two grammars share this binding: 'typescript' rejects JSX but allows the '<T>expr' cast syntax, 'tsx' is the reverse. 
# So .tsx/.jsx/.js (which may carry JSX) use the tsx grammar, .ts/.mts/.cts use the typescript one.
TYPESCRIPT = Language(tstypescript.language_typescript())
TSX = Language(tstypescript.language_tsx())

# tree-sitter-typescript declaration node types -> the Veltro kind keyword. 'abstract class' is a distinct node, so it carries its modifier already.
TYPE_DECLARATIONS = {
    "class_declaration": "class",
    "abstract_class_declaration": "class abstract",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
}

# Node types that, inside a heritage clause, name a real base type. Anything else (type_arguments, punctuation) is ignored.
BASE_NODE_TYPES = {
    "identifier",
    "type_identifier",
    "generic_type",
    "member_expression",
    "nested_type_identifier",
}

# Bases that carry no domain meaning, so they never become an edge
IGNORED_BASES = {"Object"}

# Member modifiers we care about (keyword child types + accessibility text)
MODIFIER_KEYWORDS = {"static", "readonly", "abstract", "async", "get", "set", "override", "declare"}

# Veltro line-start keywords. A public member whose name is one of these would  collide with a declaration (a field 'module string' would read as a 'module'line), 
# so such a member must keep an explicit '+'. Methods are safe (the '(' tells them apart), but forcing '+' on them too is harmless.
RESERVED_NAMES = {"veltro", "module", "class", "interface", "enum", "rel"}

# A member must be a plain identifier to be a single .vel token. Computed names
# ('[Symbol.iterator]', '["foo-bar"]'), common in real code, are skipped.
VALID_MEMBER_NAME = re.compile(r"^[A-Za-z_$][\w$]*$")

# Source extensions, longest first so '.d.ts' is matched before '.ts'
SOURCE_EXTENSIONS = (".d.ts", ".tsx", ".ts", ".mts", ".cts", ".jsx", ".js", ".mjs", ".cjs")
TSX_EXTENSIONS = (".tsx", ".jsx", ".js", ".mjs", ".cjs")

# Directories that hold vendored code, build output or tests, never the architecture under study. Pruned during the walk.
SKIP_DIRS = {"node_modules", "dist", "build", "out", ".git", "test", "tests", "__tests__", "__mocks__", "e2e"}

# Test files mirror production types and would pollute the graph with fixtures (the NestJS lesson: integration/sample apps drowned the real framework).
TEST_FILE_SUFFIXES = (".spec.ts", ".spec.tsx", ".spec.js", ".spec.jsx", ".test.ts", ".test.tsx", ".test.js", ".test.jsx")

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

def first_child_of_type(node, type_name: str):
    """
    The first named child with the given type, or None
    """
    for child in node.named_children:
        if child.type == type_name:
            return child
    return None

def ts_type_to_veltro(type_text: str) -> str:
    """

    Translate a TypeScript type into the Veltro type syntax.

    TypeScript already uses '<>' for generics, '[]' for arrays and a member '?'
    for optionals, so the main jobs are: collapse spaces around '< > ,', and
    fold a two-member 'X | null' / 'X | undefined' union into the Veltro
    nullable 'X?' (the common optional shape).

    Args:
        type_text (str): e.g. 'Map<string, Foo>' or 'Foo | null'

    Returns:
        The Veltro type, e.g. 'Map<string,Foo>' or 'Foo?'

    """
    stripped = type_text.strip()

    # 'X | null' / 'X | undefined' (a two-member optional) -> 'X?'. Skip when the union sits inside a generic (a '<' is present), where splitting is unsafe
    if "|" in stripped and "<" not in stripped:
        members = [part.strip() for part in stripped.split("|")]
        non_null = [part for part in members if part not in ("null", "undefined")]
        if len(members) == 2 and len(non_null) == 1:
            return ts_type_to_veltro(non_null[0]) + "?"

    collapsed = re.sub(r"\s*([<>,])\s*", r"\1", stripped)
    return collapsed.strip()

def annotation_type(node, field_name: str) -> str:
    """

    Read a 'type_annotation' field (e.g. ': Map<string, Foo>') and return the
    Veltro type. The annotation node wraps a leading ':' plus the real type, so
    the type is its last named child.

    Args:
        node: the declaration owning the annotation
        field_name (str): 'type' (fields) or 'return_type' (methods)

    Returns:
        The Veltro type, or '' when the annotation is absent (untyped JS)

    """
    annotation = node.child_by_field_name(field_name)
    if annotation is None or annotation.named_child_count == 0:
        return ""
    return safe_type(ts_type_to_veltro(text(annotation.named_children[-1])))

def safe_type(type_string: str) -> str:
    """

    Reduce a type to a single Veltro token, or 'Any' when it cannot be.

    The .vel line format splits fields and arguments on spaces, so a type must
    be ONE token: identifiers, generics ('Map<string,Foo>') and arrays ('Foo[]')
    qualify. TypeScript's structural types do not: an inline object
    ('{ a: number }'), a function type ('(x: number) => void'), an intersection
    ('A & B') or a multi-member union all carry spaces, parens or braces that
    would corrupt the line (the real case that bit us: a NestJS constructor
    parameter typed with an inline object dumped '(request {' into the file).
    Such types collapse to 'Any' rather than break the format.

    Args:
        type_string (str): an already space-collapsed candidate type

    Returns:
        The type if it is a single safe token, else 'Any'

    """
    if not type_string:
        return "Any"
    if any(char in type_string for char in " (){}\n\t"):
        return "Any"
    return type_string

def simple_name(type_text: str) -> str:
    """
    The last identifier of a (possibly qualified, generic) type:
    'React.Component<Props>' -> 'Component'
    """
    name = type_text.strip()
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
    The set of modifier tokens on a member: keyword child types (static,
    readonly, abstract, get, set, ...) plus any accessibility modifier text
    (public / private / protected).
    """
    names = set()
    for child in node.children:
        if child.type == "accessibility_modifier":
            names.add(text(child))
        elif child.type in MODIFIER_KEYWORDS:
            names.add(child.type)
    return names

def visibility_marker(modifiers: set, raw_name: str, inside_interface: bool) -> str:
    """

    The Veltro visibility marker from TypeScript access modifiers.

    Interface members are implicitly public. A TypeScript class member with no
    modifier is also public (unlike C#'s private default). A '#name' is a
    hard-private field, equivalent to the 'private' modifier.

    Args:
        modifiers (set)
        raw_name (str): the member name as written (may start with '#')
        inside_interface (bool)

    Returns:
        "" (public), "-" (private) or "#" (protected)

    """
    if inside_interface:
        return ""
    if raw_name.startswith("#") or "private" in modifiers:
        return "-"
    if "protected" in modifiers:
        return "#"
    return ""

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

def clean_name(raw_name: str):
    """
    Split a member name into (display_name, is_hard_private), stripping the
    leading '#' of a hard-private field.
    """
    if raw_name.startswith("#"):
        return raw_name[1:], True
    return raw_name, False

def has_optional_marker(node) -> bool:
    """
    True when a field or parameter carries the optional '?' token
    """
    for child in node.children:
        if child.type == "?":
            return True
    return False

def safe_default(value_text: str) -> str:
    """

    Keep a field initializer only when it is a short, single-line value.

    Anything multi-line, or carrying parens/braces, would break the
    line-oriented .vel: '(' makes the parser read the field line as a method and
    '{' starts an object initializer (the same lesson the Java and C# extractors
    learned). A default is informative, not load-bearing, so unsafe values are
    dropped.

    Args:
        value_text (str)

    Returns:
        The value, or "" when it is unsafe to keep

    """
    value_text = value_text.strip()
    if not value_text or "\n" in value_text:
        return ""
    if any(char in value_text for char in "(){}"):
        return ""
    return value_text

# ============ MEMBER EXTRACTION ============

def extract_field(node, inside_interface: bool) -> str:
    """

    Turn a class field ('public_field_definition') or an interface property
    ('property_signature') into a Veltro field line.

    Args:
        node: the field/property node
        inside_interface (bool)

    Returns:
        The field line, e.g. '- _cache Map<string,Foo>' or 'count number = 0',
        or "" when it has no usable name

    """
    modifiers = modifiers_of(node)
    is_static = "static" in modifiers

    raw_name = field_text(node, "name")
    if not raw_name:
        return ""
    name, _is_hash = clean_name(raw_name)
    if not VALID_MEMBER_NAME.match(name):
        return ""
    marker = visibility_marker(modifiers, raw_name, inside_interface)

    type_string = annotation_type(node, "type") or "Any"
    if has_optional_marker(node) and not type_string.endswith("?"):
        type_string += "?"

    line = member_prefix(name, marker, is_static) + " " + type_string

    value = node.child_by_field_name("value")
    if value is not None:
        default = safe_default(text(value))
        if default:
            line += " = " + default
    return line

def extract_getter(node, inside_interface: bool) -> str:
    """
    Turn a getter ('get active(): boolean') into a field line, its conceptual
    role, mirroring the way the other extractors treat properties.
    """
    modifiers = modifiers_of(node)
    is_static = "static" in modifiers

    raw_name = field_text(node, "name")
    name, _is_hash = clean_name(raw_name)
    if not VALID_MEMBER_NAME.match(name):
        return ""
    marker = visibility_marker(modifiers, raw_name, inside_interface)

    type_string = annotation_type(node, "return_type") or "Any"
    return member_prefix(name, marker, is_static) + " " + type_string

def method_arguments(node) -> list:
    """

    Collect a method's parameters as Veltro 'name Type' tokens.

    Skips the synthetic 'this' parameter and any destructured parameter (whose
    pattern is not a plain identifier, so it has no single name to record). An
    optional parameter's type gains a trailing '?'. An un-annotated parameter
    (plain JS) gets type 'Any', keeping the right arity.

    Args:
        node: a method/constructor node

    Returns:
        list[str]: e.g. ['value string', 'count number?']

    """
    parameters = node.child_by_field_name("parameters")
    tokens = []
    if parameters is None:
        return tokens
    for parameter in parameters.named_children:
        if parameter.type not in ("required_parameter", "optional_parameter"):
            continue
        pattern = parameter.child_by_field_name("pattern")
        if pattern is None or pattern.type != "identifier":
            continue
        name = text(pattern)
        if name == "this":
            continue
        type_string = annotation_type(parameter, "type") or "Any"
        if parameter.type == "optional_parameter" and not type_string.endswith("?"):
            type_string += "?"
        tokens.append(name + " " + type_string)
    return tokens

def extract_method(node, class_name: str, inside_interface: bool) -> str:
    """

    Turn a method, constructor or interface method signature into a Veltro
    method line. A constructor is emitted under the class's own name and, like a
    void method, carries no return type.

    Args:
        node: a method_definition or method_signature node
        class_name (str)
        inside_interface (bool)

    Returns:
        e.g. 'refresh(ttl number)' or '$make(raw Record<string,any>) Session'

    """
    modifiers = modifiers_of(node)
    is_static = "static" in modifiers

    raw_name = field_text(node, "name")
    is_constructor = raw_name == "constructor"
    if is_constructor:
        name = class_name
    else:
        name, _is_hash = clean_name(raw_name)
        if not VALID_MEMBER_NAME.match(name):
            return ""

    marker = visibility_marker(modifiers, raw_name, inside_interface)
    arguments = method_arguments(node)
    line = member_prefix(name, marker, is_static) + "(" + ", ".join(arguments) + ")"

    if not is_constructor:
        return_type = annotation_type(node, "return_type")
        if return_type and return_type != "void":
            line += " " + return_type
    return line

# ============ TYPE (CLASS / INTERFACE / ENUM) EXTRACTION ============

def extract_enum(node, name: str) -> list:
    """
    Emit the single 'enum Name = A, B, C' line (values only, not their numbers)
    """
    values = []
    body = node.child_by_field_name("body")
    if body is not None:
        for member in body.named_children:
            if member.type == "enum_assignment":
                values.append(field_text(member, "name"))
            elif member.type == "property_identifier":
                values.append(text(member))
    return ["enum " + name + " = " + ", ".join(values)]

def clause_bases(clause) -> list:
    """
    The simple names of the base types in a heritage clause (extends/implements),
    keeping only clean identifiers so a relation row can never be malformed.
    """
    names = []
    for child in clause.named_children:
        if child.type not in BASE_NODE_TYPES:
            continue
        base_name = simple_name(text(child))
        if not re.match(r"^[A-Za-z_]\w*$", base_name):
            continue
        if base_name in IGNORED_BASES:
            continue
        names.append(base_name)
    return names

def collect_edges(node, name: str, edges: list) -> None:
    """

    Record a type's inheritance edges. Unlike C#, TypeScript states the kind:
    a class's 'extends' is a base class ('extend'), its 'implements' is an
    interface ('impl'), an interface's 'extends' is always 'extend'.

    Args:
        node: the type declaration
        name (str): the declaring type's name
        edges (list): the running list of (from, kind, to) to append to

    """
    heritage = first_child_of_type(node, "class_heritage")
    if heritage is not None:
        for clause in heritage.named_children:
            if clause.type == "extends_clause":
                for base in clause_bases(clause):
                    edges.append((name, "extend", base))
            elif clause.type == "implements_clause":
                for base in clause_bases(clause):
                    edges.append((name, "impl", base))

    interface_extends = first_child_of_type(node, "extends_type_clause")
    if interface_extends is not None:
        for base in clause_bases(interface_extends):
            edges.append((name, "extend", base))

def extract_type(node, edges: list) -> list:
    """

    Turn one type declaration into its Veltro lines, appending its inheritance
    edges to the shared list.

    Args:
        node: a type declaration node
        edges (list)

    Returns:
        list[str]: the declaration line plus its member lines, or [] for an
        anonymous declaration (e.g. 'export default class { ... }')

    """
    kind = TYPE_DECLARATIONS[node.type]
    name = field_text(node, "name")
    if not name:
        return []

    collect_edges(node, name, edges)

    if kind == "enum":
        return extract_enum(node, name)

    inside_interface = kind == "interface"
    lines = [kind + " " + name]

    body = node.child_by_field_name("body")
    if body is not None:
        for member in body.named_children:
            if member.type in ("public_field_definition", "property_signature"):
                field_line = extract_field(member, inside_interface)
                if field_line:
                    lines.append(field_line)
            elif member.type == "method_definition":
                modifiers = modifiers_of(member)
                if "set" in modifiers:
                    # a setter would duplicate the getter's field, skip it
                    continue
                if "get" in modifiers:
                    member_line = extract_getter(member, inside_interface)
                else:
                    member_line = extract_method(member, name, inside_interface)
                if member_line:
                    lines.append(member_line)
            elif member.type == "method_signature":
                member_line = extract_method(member, name, inside_interface)
                if member_line:
                    lines.append(member_line)
    return lines

# ============ PROJECT WALK & RENDERING ============

def namespace_name(node) -> str:
    """
    The dotted name of a 'namespace X.Y { ... }' (internal_module) node, with the
    quotes of a string module name ('module "foo"') stripped.
    """
    name = field_text(node, "name")
    return name.strip().strip('"').strip("'")

def collect(node, namespace, file_module: str, modules: dict, edges: list, stats: dict) -> None:
    """

    Recursively walk the tree: unwrap 'export' statements, descend into
    namespaces (tracking the dotted name), extract top-level types, and never
    recurse into a type, so nested types are skipped like the other extractors.

    A type's module is its enclosing namespace when it has one, else the file
    module (TS/JS are file-as-module by default).

    Args:
        node: the current tree-sitter node
        namespace: the enclosing namespace's dotted name, or None
        file_module (str): the module derived from the file path
        modules (dict): module path -> accumulated type lines (modified in place)
        edges (list): the running inheritance edges (modified in place)
        stats (dict): counts per kind (modified in place)

    """
    for child in node.children:
        if child.type == "export_statement":
            collect(child, namespace, file_module, modules, edges, stats)
        elif child.type == "internal_module":
            name = namespace_name(child)
            inner = (namespace + "." + name) if namespace else name
            body = child.child_by_field_name("body")
            collect(body if body is not None else child, inner, file_module, modules, edges, stats)
        elif child.type in TYPE_DECLARATIONS:
            lines = extract_type(child, edges)
            if not lines:
                continue
            kind = TYPE_DECLARATIONS[child.type]
            base_kind = "class" if kind.startswith("class") else kind
            stats[base_kind] = stats.get(base_kind, 0) + 1
            module_path = (namespace if namespace else file_module) or "global"
            # TypeScript merges repeated 'interface' declarations into one type, so the self-audit counts distinct ids, not declarations (the parser folds the declarations into a single node).
            stats.setdefault("ids", set()).add(module_path + "." + field_text(child, "name"))
            modules.setdefault(module_path, []).extend(lines)
        else:
            collect(child, namespace, file_module, modules, edges, stats)

def render_vel(modules: dict, edges: list) -> str:
    """
    Assemble the final '.vel' text from the per-module lines and the edges
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

def grammar_for(path: str) -> Language:
    """
    The grammar to use for a file: the tsx grammar for .tsx/.jsx/.js (which may
    carry JSX), the typescript grammar otherwise.
    """
    if path.endswith(TSX_EXTENSIONS):
        return TSX
    return TYPESCRIPT

def module_for(absolute_path: str, base: str) -> str:
    """

    The dotted module path for a file, relative to the scan root's parent
    (mirroring the Python extractor). The extension is dropped and an 'index'
    file collapses onto its directory, the ES-module convention.

    Args:
        absolute_path (str): the file's absolute path
        base (str): the directory the relative path is measured from

    Returns:
        e.g. 'src.models.user' for '<base>/src/models/user.ts'

    """
    relative = os.path.relpath(absolute_path, base)
    for extension in SOURCE_EXTENSIONS:
        if relative.endswith(extension):
            relative = relative[:-len(extension)]
            break
    dotted = relative.replace(os.sep, ".")
    if dotted.endswith(".index"):
        dotted = dotted[:-len(".index")]
    return dotted

def iter_source_files(directory: str):
    """
    Yield every TS/JS source file path under a directory, recursively, pruning
    vendored / build / test directories and *.spec / *.test files so the graph
    is the production architecture, not fixtures (see SKIP_DIRS, TEST_FILE_SUFFIXES)
    """
    for current_root, dirs, files in os.walk(directory):
        dirs[:] = [name for name in dirs if name not in SKIP_DIRS]
        for file_name in sorted(files):
            if file_name.endswith(TEST_FILE_SUFFIXES):
                continue
            if file_name.endswith(SOURCE_EXTENSIONS):
                yield os.path.join(current_root, file_name)

def extract_project(directory: str):
    """

    Extract a whole TS/JS source tree into '.vel' text.

    Args:
        directory (str): path to the source folder to scan

    Returns:
        (vel_text, stats):
            vel_text (str): the complete '.vel' document
            stats (dict): counts of each kind (class / interface / enum)

    """
    modules = {}
    edges = []
    stats = {"class": 0, "interface": 0, "enum": 0}

    base = os.path.dirname(os.path.abspath(directory))
    for path in iter_source_files(directory):
        with open(path, "rb") as source_file:
            source = source_file.read()
        parser = Parser(grammar_for(path))
        tree = parser.parse(source)
        file_module = module_for(path, base)
        collect(tree.root_node, None, file_module, modules, edges, stats)

    return render_vel(modules, edges), stats

def extract_to_vel(source_text: str, module_path: str, jsx: bool = False) -> str:
    """
    Convenience for tests: extract a single TS/JS source string into '.vel' text,
    under the given module path. Set jsx=True to parse .tsx/.jsx content.
    """
    parser = Parser(TSX if jsx else TYPESCRIPT)
    tree = parser.parse(source_text.encode("utf-8"))
    modules = {}
    edges = []
    stats = {"class": 0, "interface": 0, "enum": 0}
    collect(tree.root_node, None, module_path, modules, edges, stats)
    return render_vel(modules, edges)

# ============ CLI ============

def main(argv=None):
    parser = argparse.ArgumentParser(description="Extract Veltro '.vel' from a TypeScript/JavaScript source tree")
    parser.add_argument("source", help="path to the TS/JS source directory")
    parser.add_argument("--out", help="where to write the .vel (default: stdout)")
    arguments = parser.parse_args(argv)

    vel_text, stats = extract_project(arguments.source)
    seen_types = stats["class"] + stats["interface"] + stats["enum"]
    unique_types = len(stats.get("ids", ()))

    # Self-audit: re-parse the produced .vel and check nothing was lost
    # Yardstick is the number of DISTINCT types: TypeScript can declare one type twice (interface merging), and the parser merges those into a single node.
    model = parse_text(vel_text)
    in_model = len(model["nodes"])
    audit = "MATCH" if in_model == unique_types else "MISMATCH"

    print(f"[INFO] - types seen: {seen_types} ({stats['class']} classes, {stats['interface']} interfaces, {stats['enum']} enums)")
    if seen_types != unique_types:
        print(f"[INFO] - unique types: {unique_types}  (merged duplicate declarations: {seen_types - unique_types})")
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
