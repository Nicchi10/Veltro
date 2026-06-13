"""

veltro/export/plantuml.py

Exporter: type-graph model -> PlantUML ('.puml') text.

Renders the same model the parser produced, so a token benchmark across
Veltro / PlantUML / Mermaid compares identical content. Only *written* relations
(extend / impl / depend ...) become arrows; associations stay encoded in the
field types, exactly as they do in the '.vel' source.
"""


# Veltro visibility -> PlantUML visibility ('@' package becomes '~')
VISIBILITY = {"+": "+", "-": "-", "#": "#", "~": "~", "@": "~"}

# Veltro relation kind -> a function (from_name, to_name) -> PlantUML line.
# PlantUML draws generalization/realization as "parent <arrow> child".
RELATION_LINES = {
    "extend": lambda a, b: f"{b} <|-- {a}",
    "impl": lambda a, b: f"{b} <|.. {a}",
    "depend": lambda a, b: f"{a} ..> {b}",
    "assoc": lambda a, b: f"{a} --> {b}",
    "aggregate": lambda a, b: f"{b} o-- {a}",
    "compose": lambda a, b: f"{b} *-- {a}",
}


def visibility(symbol: str) -> str:
    return VISIBILITY.get(symbol, "+")


def render_field(field: dict) -> str:
    static = "{static} " if field.get("static") else ""
    line = f"    {visibility(field['vis'])} {static}{field['name']} : {field['type']}"
    if "default" in field:
        line += " = " + field["default"]
    return line


def render_arguments(arguments: list) -> str:
    parts = []
    for argument in arguments:
        if "name" in argument:
            parts.append(argument["name"] + ": " + argument["type"])
        else:
            parts.append(argument["type"])
    return ", ".join(parts)


def render_method(method: dict) -> str:
    static = "{static} " if method.get("static") else ""
    arguments = render_arguments(method.get("args", []))
    line = f"    {visibility(method['vis'])} {static}{method['name']}({arguments})"
    if method.get("ret"):
        line += " : " + method["ret"]
    return line


def render_node(node: dict) -> list:
    """Render one type into PlantUML lines (indented one level for the package)."""
    if node["kind"] == "enum":
        lines = [f"  enum {node['name']} {{"]
        for value in node.get("values", []):
            lines.append("    " + value)
        lines.append("  }")
        return lines

    if node["kind"] == "interface":
        header = f"  interface {node['name']} {{"
    elif "abstract" in node.get("modifiers", []):
        header = f"  abstract class {node['name']} {{"
    else:
        header = f"  class {node['name']} {{"

    lines = [header]
    for field in node.get("fields", []):
        lines.append(render_field(field))
    for method in node.get("methods", []):
        lines.append(render_method(method))
    lines.append("  }")
    return lines


def export_plantuml(model: dict) -> str:
    """

    Render the whole model as a PlantUML document.

    Args:
        model (dict): a graph matching model.schema.json

    Returns:
        str: the '.puml' text

    """
    id_to_name = {}
    modules = {}
    for node in model["nodes"]:
        id_to_name[node["id"]] = node["name"]
        modules.setdefault(node["module"], []).append(node)

    lines = ["@startuml"]
    for module_path in sorted(modules):
        lines.append(f"package {module_path} {{")
        for node in modules[module_path]:
            lines.extend(render_node(node))
        lines.append("}")

    for edge in model["edges"]:
        if edge.get("derived"):
            continue  # associations live in the field types, like in the .vel
        make_line = RELATION_LINES.get(edge["kind"])
        if make_line is None:
            continue
        from_name = id_to_name.get(edge["from"], edge["from"])
        to_name = id_to_name.get(edge["to"], edge["to"])
        lines.append(make_line(from_name, to_name))

    lines.append("@enduml")
    return "\n".join(lines) + "\n"
