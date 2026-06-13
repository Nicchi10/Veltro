"""

veltro/export/mermaid.py

Exporter: type-graph model -> Mermaid ('.mmd') classDiagram text.

Same contract as the PlantUML exporter: it renders the same model so the token
benchmark is fair. Mermaid writes generics with '~' instead of '<>' and marks
static members with a trailing '$'.
"""


# Veltro visibility -> Mermaid visibility ('@' package becomes '~')
VISIBILITY = {"+": "+", "-": "-", "#": "#", "~": "~", "@": "~"}

# Veltro relation kind -> a function (from_name, to_name) -> Mermaid line
RELATION_LINES = {
    "extend": lambda a, b: f"  {b} <|-- {a}",
    "impl": lambda a, b: f"  {b} <|.. {a}",
    "depend": lambda a, b: f"  {a} ..> {b}",
    "assoc": lambda a, b: f"  {a} --> {b}",
    "aggregate": lambda a, b: f"  {b} o-- {a}",
    "compose": lambda a, b: f"  {b} *-- {a}",
}


def visibility(symbol: str) -> str:
    return VISIBILITY.get(symbol, "+")


def mermaid_type(type_string: str) -> str:
    """Mermaid spells generics with '~' instead of angle brackets."""
    return type_string.replace("<", "~").replace(">", "~")


def render_field(field: dict) -> str:
    static = "$" if field.get("static") else ""
    return f"    {visibility(field['vis'])}{mermaid_type(field['type'])} {field['name']}{static}"


def render_arguments(arguments: list) -> str:
    parts = []
    for argument in arguments:
        if "name" in argument:
            parts.append(mermaid_type(argument["type"]) + " " + argument["name"])
        else:
            parts.append(mermaid_type(argument["type"]))
    return ", ".join(parts)


def render_method(method: dict) -> str:
    static = "$" if method.get("static") else ""
    arguments = render_arguments(method.get("args", []))
    line = f"    {visibility(method['vis'])}{method['name']}({arguments})"
    if method.get("ret"):
        line += " " + mermaid_type(method["ret"])
    return line + static


def render_node(node: dict) -> list:
    """Render one type into Mermaid lines."""
    lines = [f"  class {node['name']} {{"]

    if node["kind"] == "enum":
        lines.append("    <<enumeration>>")
        for value in node.get("values", []):
            lines.append("    " + value)
        lines.append("  }")
        return lines

    if node["kind"] == "interface":
        lines.append("    <<interface>>")
    elif "abstract" in node.get("modifiers", []):
        lines.append("    <<abstract>>")

    for field in node.get("fields", []):
        lines.append(render_field(field))
    for method in node.get("methods", []):
        lines.append(render_method(method))
    lines.append("  }")
    return lines


def export_mermaid(model: dict) -> str:
    """

    Render the whole model as a Mermaid classDiagram.

    Args:
        model (dict): a graph matching model.schema.json

    Returns:
        str: the '.mmd' text

    """
    id_to_name = {}
    for node in model["nodes"]:
        id_to_name[node["id"]] = node["name"]

    lines = ["classDiagram"]
    for node in model["nodes"]:
        lines.extend(render_node(node))

    for edge in model["edges"]:
        if edge.get("derived"):
            continue
        make_line = RELATION_LINES.get(edge["kind"])
        if make_line is None:
            continue
        from_name = id_to_name.get(edge["from"], edge["from"])
        to_name = id_to_name.get(edge["to"], edge["to"])
        lines.append(make_line(from_name, to_name))

    return "\n".join(lines) + "\n"
