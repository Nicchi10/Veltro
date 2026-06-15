"""

veltro/export/d2.py

Exporter: type-graph model -> D2 ('.d2') declaration text.

Same contract as the PlantUML and Mermaid exporters: it renders the same model
so the comparison is fair. Each type is declared by its full dotted id
(e.g. 'pydantic.types.Foo'), D2 reads the dots as nested containers, so the
module is part of the diagram (the answer to "which module is X in?"). 

Only written relations become arrows, associations stay encoded in the field types.
"""


# Veltro visibility -> D2 visibility. D2 has no package marker, map '@'/'~' to '#'
VISIBILITY = {"+": "+", "-": "-", "#": "#", "~": "#", "@": "#"}

# Veltro relation kind -> a function (from_id, to_id) -> a D2 connection line
RELATION_LINES = {
    "extend": lambda a, b: f"{a} -> {b}: extends",
    "impl": lambda a, b: f"{a} -> {b}: implements",
    "depend": lambda a, b: f"{a} -> {b}: depends",
    "assoc": lambda a, b: f"{a} -> {b}",
    "aggregate": lambda a, b: f"{a} -> {b}: aggregates",
    "compose": lambda a, b: f"{a} -> {b}: composes",
}


def visibility(symbol: str) -> str:
    return VISIBILITY.get(symbol, "+")


def render_field(field: dict) -> str:
    return f"  {visibility(field['vis'])}{field['name']}: {field['type']}"


def render_arguments(arguments: list) -> str:
    parts = []
    for argument in arguments:
        if "name" in argument:
            parts.append(argument["name"] + ": " + argument["type"])
        else:
            parts.append(argument["type"])
    return ", ".join(parts)


def render_method(method: dict) -> str:
    arguments = render_arguments(method.get("args", []))
    line = f"  {visibility(method['vis'])}{method['name']}({arguments})"
    if method.get("ret"):
        line += ": " + method["ret"]
    return line


def render_node(node: dict) -> list:
    """
    Render one type as a D2 'shape: class' block keyed by its full id
    """
    lines = [f"{node['id']}: {{", "  shape: class"]

    if node["kind"] == "enum":
        for value in node.get("values", []):
            lines.append("  " + value)
        lines.append("}")
        return lines

    for field in node.get("fields", []):
        lines.append(render_field(field))
    for method in node.get("methods", []):
        lines.append(render_method(method))
    lines.append("}")
    return lines


def export_d2(model: dict) -> str:
    """

    Render the whole model as a D2 document.

    Args:
        model (dict): a graph matching model.schema.json

    Returns:
        str: the '.d2' text

    """
    lines = []
    for node in model["nodes"]:
        lines.extend(render_node(node))

    for edge in model["edges"]:
        if edge.get("derived"):
            continue  # associations live in the field types, like in the .vel
        make_line = RELATION_LINES.get(edge["kind"])
        if make_line is None:
            continue
        lines.append(make_line(edge["from"], edge["to"]))

    return "\n".join(lines) + "\n"
