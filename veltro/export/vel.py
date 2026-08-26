"""

veltro/export/vel.py

Exporter: type-graph model -> Veltro ('.vel') text.

The other exporters translate the model into a foreign notation. This one writes
it back into its own, which is what SPEC design law 4 asks for: one canonical
serialization per model, so a round trip is lossless and diffs stay clean.

Its practical job is slicing. A '.vel' of a large project does not fit in an
LLM's context (Orleans is ~692k tokens), so a tool has to hand over a
NEIGHBOURHOOD instead of the whole file: pick the nodes and edges that matter,
and render them as a smaller, still-valid '.vel'.

Canonical form, as the SPEC defines it: no indentation, public implicit,
associations left to be derived rather than written.
"""

# Line-start keywords: a public member whose NAME is one of these must keep an
# explicit '+', or the line would read as a declaration (SPEC 4).
RESERVED_NAMES = {"veltro", "module", "class", "interface", "enum", "rel"}


def member_prefix(member: dict) -> str:
    """

    The start of a member line: the visibility marker, then '$' when static,
    then the name.

    Public is implicit and carries no marker, which is where most of the token
    saving comes from.

    Args:
        member (dict): a field or a method

    Returns:
        str: e.g. 'name', '- _cache', '# helper', '$Make', '+ module'

    """
    core = ("$" if member.get("static") else "") + member["name"]

    visibility = member.get("vis", "+")
    if visibility == "+":
        if member["name"] in RESERVED_NAMES:
            return "+ " + core
        return core
    return visibility + " " + core


def render_field(field: dict) -> str:
    """
    One field line: '[vis] name Type [= default]'
    """
    line = member_prefix(field) + " " + field["type"]
    if "default" in field:
        line += " = " + field["default"]
    return line


def render_arguments(arguments: list) -> str:
    """
    Method arguments as 'name Type', or type-only when the name is unknown
    (which is what a UML import gives)
    """
    parts = []
    for argument in arguments:
        if "name" in argument:
            parts.append(argument["name"] + " " + argument["type"])
        else:
            parts.append(argument["type"])
    return ", ".join(parts)


def render_method(method: dict) -> str:
    """
    One method line: '[vis] name(args) [ret]', no return type meaning void
    """
    line = member_prefix(method) + "(" + render_arguments(method.get("args", [])) + ")"
    if method.get("ret"):
        line += " " + method["ret"]
    return line


def render_node(node: dict) -> list:
    """

    Render one type: its declaration line followed by its members.

    Args:
        node (dict): a model node

    Returns:
        list[str]: the '.vel' lines for that type

    """
    lines = []
    for doc_line in node.get("doc", "").split("\n"):
        if doc_line:
            lines.append("> " + doc_line)

    if node["kind"] == "enum":
        lines.append("enum " + node["name"] + " = " + ", ".join(node.get("values", [])))
        return lines

    declaration = node["kind"]
    for modifier in node.get("modifiers", []):
        declaration += " " + modifier
    lines.append(declaration + " " + node["name"])

    for field in node.get("fields", []):
        lines.append(render_field(field))
    for method in node.get("methods", []):
        lines.append(render_method(method))
    return lines


def reference_for(node_id: str, id_to_name: dict, ambiguous: set) -> str:
    """

    How to write a node id in the 'rel' block: the simple name when it is
    unique, the qualified id otherwise (SPEC 6).

    An id the model does not know (a type outside the project, like
    'IDisposable') is written back exactly as it came in.

    Args:
        node_id (str): the edge endpoint
        id_to_name (dict): known id -> simple name
        ambiguous (set): the simple names carried by more than one node

    Returns:
        str: the reference to write

    """
    name = id_to_name.get(node_id)
    if name is None:
        return node_id
    if name in ambiguous:
        return node_id
    return name


def ambiguous_names(nodes: list) -> set:
    """
    The simple names carried by more than one node, which therefore cannot
    identify a type on their own
    """
    counts = {}
    for node in nodes:
        counts[node["name"]] = counts.get(node["name"], 0) + 1

    repeated = set()
    for name, count in counts.items():
        if count > 1:
            repeated.add(name)
    return repeated


def export_vel(model: dict) -> str:
    """

    Render a model as '.vel' text, in canonical form.

    Nodes keep the model's order and are grouped under their module. Only
    WRITTEN edges are emitted: associations are derived from field types by the
    parser, so writing them would both cost tokens and duplicate a fact the
    file already carries (SPEC design law 2).

    Args:
        model (dict): a graph matching model.schema.json

    Returns:
        str: the '.vel' document

    """
    nodes = model.get("nodes", [])

    id_to_name = {}
    for node in nodes:
        id_to_name[node["id"]] = node["name"]
    ambiguous = ambiguous_names(nodes)

    lines = ["veltro " + str(model.get("veltro", 1)), ""]

    modules = []
    nodes_by_module = {}
    for node in nodes:
        module_path = node.get("module", "")
        if module_path not in nodes_by_module:
            nodes_by_module[module_path] = []
            modules.append(module_path)
        nodes_by_module[module_path].append(node)

    for module_path in modules:
        lines.append("module " + module_path)
        for node in nodes_by_module[module_path]:
            lines.extend(render_node(node))
        lines.append("")

    written_edges = []
    for edge in model.get("edges", []):
        if not edge.get("derived"):
            written_edges.append(edge)

    if written_edges:
        lines.append("rel")
        for edge in written_edges:
            source = reference_for(edge["from"], id_to_name, ambiguous)
            target = reference_for(edge["to"], id_to_name, ambiguous)
            lines.append(source + " " + edge["kind"] + " " + target)
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
