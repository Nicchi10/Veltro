"""

veltro/parser.py

Parser: Veltro '.vel' source  ->  type-graph model (dict).

The output dict matches 'model.schema.json': a graph of 'nodes' (the types) and
'edges' (the relations between them).

Design notes (kept deliberately simple and explicit):

Indentation is insignificant: strips every line and decides what it is by
looking at its first token ('module' / 'class' / 'interface' / 'enum' /
'rel'), or its first character ('- # @' for a non-public member, '>' for a
doc line). Any other line inside a type is a public member.

"""

import re
from typing import Any, Tuple

# The visibility markers a member line can start with
VISIBILITY_MARKERS = ("+", "-", "#", "@")

# Modifiers that may appear before a type name, e.g. 'class abstract Foo'
TYPE_MODIFIERS = ("abstract", "sealed", "static")

# The relation kinds allowed in a 'rel' block (and in derived edges)
RELATION_KINDS = ("extend", "impl", "depend", "assoc", "aggregate", "compose")

class VeltroSyntaxError(Exception):
    """
    
    Raised when a .vel line cannot be understood

    Args:
        line_number (int): the row number where error has occured
        line_text (str): the content of indicted row
        reason (str): why the analysis failed
    """
    
    def __init__(self, line_number, line_text, reason):
        self.line_number = line_number
        self.line_text = line_text
        self.reason = reason
        message = f"line {line_number}: {reason} -> {line_text}"
        super().__init__(message)

# ============ TEXT HELPERS ============

def split_top_level(text: str, separator: str) -> list[str]:
    """
    
    Splits text on separator, but ignore separators inside <...>.
    
    Args:
        text (str)
        separator (str): comma or other
        
    Returns:
        Parts, e.g: List<Int,String>, Int -> a = List<Int,String>, b = Int

    
    """
    
    parts = []
    current = ""
    depth = 0
    for char in text:
        if char == "<":
            depth += 1
            current += char
        elif char == ">":
            depth -= 1
            current += char
        elif char == separator and depth == 0: # cuts
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return parts

def find_matching_paren(text: str, open_index: int) -> int:
    """
    
    Simple brackets matching
    
    Args:
        text (str)
        open_index (int): index of the opening '('

    Returns:
        index (int) -> if brackets ok,
        error -> otherwise
        
    Raise:
        ValueError: No matching

    """
    
    depth = 0
    for index in range(open_index, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError(f"[ERROR] - unbalanced parentheses in {text}")

def extract_type_names(type_string: str) -> list[str]:
    """
    
    Used to derive association edges from the types of fields.
    
    Args:
        type_string (str)
    
    Returns:
        Every identifier mentioned in a type string, e.g: "Dictionary<String,Object>" -> ["Dictionary", "String", "Object"]
    
    """
    
    return re.findall(r"[A-Za-z_][A-Za-z0-9_]*", type_string)

def normalize_type(type_string: str) -> str:
    """

    Canonicalises a type string so spacing never changes its identity.

    The canonical form has no spaces around generic brackets or commas, so a
    sloppy 'Dictionary<String, Object>' and a clean 'Dictionary<String,Object>'
    end up as the same model value, the parser stays tolerant of messy input
    while the model stays deterministic.

    Args:
        type_string (str)

    Returns:
        The type with spaces around '< > ,' removed, e.g:
        'List< Message >' -> 'List<Message>'

    """

    collapsed = re.sub(r"\s*([<>,])\s*", r"\1", type_string)
    return collapsed.strip()

# ============ MEMBER PARSING ============

def parse_field(visibility: str, body: str, is_static: bool) -> dict[str, Any]:
    """
    
    Parses a field body like 'TokenBudget Int? = 0' (without the '+')
    
    Args:
        visibility (str): 'None, +, -, @, #'
        body (str): row field line
        is_static (bool)
        
    Returns:
        A row's dict fields review, 
        e.g: {"vis": "+", "name": "TokenBudget", "type": "Int?", "default" : 0}
    
    """
    
    default_value = None
    if "=" in body:
        before_equals, after_equals = body.split("=", 1) # [(<name> <type>), <value>]
        body = before_equals.strip()
        default_value = after_equals.strip()

    
    pieces = body.split(None, 1) # [<name>, <type>]
    name = pieces[0]
    type_string = ""
    if len(pieces) > 1:
        type_string = normalize_type(pieces[1])

    field = {"vis": visibility, "name": name, "type": type_string}
    if default_value is not None:
        field["default"] = default_value
    if is_static:
        field["static"] = True
    return field

def parse_arguments(arguments_string: str) -> list[dict[str, Any]]:
    """
    
    Parses the inside of a method's parentheses into a list of arg dicts
    
    Args:
        arguments_string (str)
        
    Returns:
        List of arg dicts, e.g:
        [{opt "name", "type", opt "default"} , {...}]
    
    """
    
    arguments = []
    if not arguments_string.strip():
        return arguments

    for raw_argument in split_top_level(arguments_string, ","):
        argument_text = raw_argument.strip()

        # An argument may carry a default, e.g: "IEnumerable<String> = null"
        default_value = None
        if "=" in argument_text:
            argument_text, default_value = argument_text.split("=", 1)
            argument_text = argument_text.strip()
            default_value = default_value.strip()

        # Collapse generic spacing first, so "Dictionary<String, Object>" stays a
        # single token and is not mistaken for a "name Type" pair
        argument_text = normalize_type(argument_text)

        # Same shape as a field: "name Type" (named) or just "Type" (unnamed,
        # common when the source was imported from UML)
        pieces = argument_text.split(None, 1)
        if len(pieces) == 2:
            argument = {"name": pieces[0], "type": pieces[1]}
        else:
            argument = {"type": pieces[0]}

        if default_value is not None:
            argument["default"] = default_value
        arguments.append(argument)

    return arguments

def parse_method(visibility: str, body: str, is_static: bool) -> dict[str, Any]:
    """
    
    Parses a method body like 'ExecuteAsync(x Int) Task<Foo>'

    Args:
        visibility (str): 'None, +, -, @, #'
        body (str): row field line
        is_static (bool)

    Returns:
        A row's dict fields review,
        e.g: {"vis": "+", "name": "ExecuteAsync", "args": [{"name": "x", "type": "Int"}], "ret": "Task<Foo>", "static": y/n}
    
    """
    
    open_index = body.index("(")
    close_index = find_matching_paren(body, open_index)

    name = body[:open_index].strip()
    arguments_string = body[open_index + 1:close_index]
    return_type = normalize_type(body[close_index + 1:])

    method = {"vis": visibility, "name": name}

    arguments = parse_arguments(arguments_string)
    if arguments:
        method["args"] = arguments
    if return_type != "":
        method["ret"] = return_type
    if is_static:
        method["static"] = True

    return method

def parse_member_line(line: str) -> Tuple[str, dict[str, Any]]:
    """
    Parses a whole member line. Returns ("field"|"method", member_dict).

    Visibility is optional: a leading '+ - # @' sets it explicitly, otherwise the
    member is public, 
    so 'Conversation ConversationState' and
    '+ Conversation ConversationState' mean the same thing, the canonical form
    omits the '+'
    
    Args:
        line (str)
        
    Returns: 
        Parsed 'method' or 'field' dictionary
    
    """
    
    if line[0] in VISIBILITY_MARKERS:
        visibility = line[0]
        body = line[1:].strip()
    else:
        visibility = "+"  # public is implicit
        body = line.strip()

    # A leading '$' marks the member as static, e.g: '$Success() Foo'
    is_static = False
    if body.startswith("$"):
        is_static = True
        body = body[1:].strip()

    # Fields and methods are told apart by the presence of '('
    if "(" in body:
        return "method", parse_method(visibility, body, is_static)
    else:
        return "field", parse_field(visibility, body, is_static)

# ============ DECLARATION PARSING ============

def qualify(module_path: str, name: str) -> str:
    """
    Builds a node id from its module and its name
    """
    if module_path:
        return module_path + "." + name
    return name

def parse_enum_declaration(line: str, module_path: str, doc_lines: list[str]) -> dict[str, Any]:
    """
    Parses 'enum Name = A, B, C' into a node

    Args:
        line (str)
        module_path (str)
        doc_lines (list[str])

    Returns:
        The enum node,
        e.g: {"id": "Core.Name", "kind": "enum", "name": "Name", "module": "Core", "values": ["A", "B"], "doc": "..."}
    """
    left_part, right_part = line.split("=", 1)

    # left_part -> "enum Name"
    name = left_part.split()[1]
    values = []
    for raw_value in right_part.split(","):
        values.append(raw_value.strip())

    node = {
        "id": qualify(module_path, name),
        "kind": "enum",
        "name": name,
        "module": module_path,
        "values": values,
    }
    if doc_lines:
        node["doc"] = "\n".join(doc_lines)
    return node

def parse_type_declaration(line: str, module_path: str, doc_lines: list[str]) -> dict[str, Any]:
    """
    Parses a 'class ...' or 'interface ...' declaration into a node

    Args:
        line (str)
        module_path (str)
        doc_lines (list[str])

    Returns:
        The class/interface node,
        e.g: {"id": "Core.Name", "kind": "class", "name": "Name", "module": "Core", "fields": [], "methods": [], "modifiers": ["abstract"], "doc": "..."}

    """
    tokens = line.split()
    kind = tokens[0]  # "class" or "interface"

    # Everything after the keyword is either a modifier or the name
    modifiers = []
    name = None
    for token in tokens[1:]:
        if token in TYPE_MODIFIERS:
            modifiers.append(token)
        else:
            name = token
            break

    node = {
        "id": qualify(module_path, name),
        "kind": kind,
        "name": name,
        "module": module_path,
        "fields": [],
        "methods": [],
    }
    if modifiers:
        node["modifiers"] = modifiers
    if doc_lines:
        node["doc"] = "\n".join(doc_lines)
    return node

# ============ EDGE RESOLUTION & ASSOCIATION DERIVATION ============

def build_name_index(nodes: list[dict[str,Any]]) -> dict[str, str]:
    """
    Maps both simple names and ids to ids, so edges can be resolved.

    A 'rel' row usually uses the simple name ('LlmInvocation'), turns that
    into the full id ('Core.Models.LlmInvocation'), if a simple name is not
    unique we keep the id->id mapping only, and ambiguous simple names are left
    untouched (the author should qualify them).
    
    Args:
        nodes (list[dict[str,Any]]): mapped declarations
    
    Returns:
        Mapped index, e.g:
        {
            "Core.Models.LlmInvocation": "Core.Models.LlmInvocaton"
            "Utils.LlmInvocation": "Utils.LlmInvocation"
            ...
            "Logger": "App.Logger" # unique
        }
    """
    
    name_counts = {}
    for node in nodes:
        name_counts[node["name"]] = name_counts.get(node["name"], 0) + 1

    index = {}
    for node in nodes:
        index[node["id"]] = node["id"]
        if name_counts[node["name"]] == 1:
            index[node["name"]] = node["id"]
    return index

def resolve_edges(raw_edges: list[dict[str, str]], name_index: dict[str, str]) -> list[dict[str, str]]:
    """
    Turns the simple names in rel rows into full node ids
    
    Args:
        raw_edges (dict[str, str]): from kind to
        name_index (dict[str, str]): mapped index
        
    Returns:
        List with all mapped kinds
    
    """
    resolved = []
    for edge in raw_edges:
        from_id = name_index.get(edge["from"], edge["from"])
        to_id = name_index.get(edge["to"], edge["to"])
        resolved.append({"from": from_id, "kind": edge["kind"], "to": to_id})
    return resolved

def derive_association_edges(nodes: list[dict[str, Any]], explicit_edges: list[dict[str, str]], name_index: dict[str, str]) -> list[dict[str, Any]]:
    """
    Create association edges from the types of fields.

    A field '+ user User' already says "this type points at User".
    Rather than forcing the author to also write that in the 'rel' block, derives it here
    and mark it 'derived: True'. If the author already declared a relation between the same pair, skips it.

    Args:
        nodes (list[dict[str, Any]]): the parsed type nodes
        explicit_edges (list[dict[str, str]]): edges already written in 'rel'
        name_index (dict[str, str]): maps names to node ids

    Returns:
        list[dict[str, Any]]: the derived association edges (marked 'derived')
    """
    # Remember which (from, to) pairs already have an explicit edge
    explicit_pairs = set()
    for edge in explicit_edges:
        explicit_pairs.add((edge["from"], edge["to"]))

    derived_edges = []
    seen_pairs = set()

    for node in nodes:
        from_id = node["id"]
        for field in node.get("fields", []):
            for referenced_name in extract_type_names(field["type"]):
                target_id = name_index.get(referenced_name)

                # Skip names that are not types we know (primitives, generics, containers like List, external types, ...)
                if target_id is None:
                    continue
                # Skip self references
                if target_id == from_id:
                    continue

                pair = (from_id, target_id)
                if pair in explicit_pairs:
                    continue
                if pair in seen_pairs:
                    continue

                seen_pairs.add(pair)
                derived_edges.append({
                    "from": from_id,
                    "kind": "assoc",
                    "to": target_id,
                    "derived": True,
                })

    return derived_edges


# ============ MAIN PARSING LOOP ============

def parse_text(text: str, derive_associations=True) -> dict[str, Any]:
    """
   Analyzes the Veltro source code and transforms it into a graph model.

    The process occurs in three main phases:
    1. Sequential parsing: Reads the text line by line, identifying modules,
    classes, interfaces, enums, and their members (fields/methods), it also handles the 'rel' block for explicit relationships
    2. Name resolution: Creates an index (name_index) to map short names
    (e.g., 'User') to full identifiers (e.g., 'Core.Models.User') and resolves explicit relationships
    3. Automatic derivation (optional): If enabled, analyzes the types of the
    fields to discover implicit relationships (e.g., associations) not explicitly declared in the 'rel' block

    Args:
        text (str): The '.vel' file content to analyze
        derive_associations (bool): If True, automaticaly adds the relationships derived to fields kind

    Returns:
        dict[str, Any]: The resulting model containing 'veltro' (version), 'nodes' (list of classes/interfaces) and 'edges' (relationships)
    """
    
    model = {"veltro": 1, "nodes": [], "edges": []}

    current_module = None
    current_node = None
    pending_doc_lines = []
    raw_edges = []
    in_relation_block = False

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        # Blank lines carry no meaning
        if not line:
            continue

        # The version pragma, e.g. "veltro 1"
        if line.startswith("veltro "):
            model["veltro"] = int(line.split()[1])
            continue

        # A documentation line attaches to the next declaration
        if line.startswith(">"):
            pending_doc_lines.append(line[1:].strip())
            continue

        # The start of the relation block.
        if line == "rel":
            in_relation_block = True
            current_node = None
            continue

        first_token = line.split()[0]

        if first_token == "module":
            in_relation_block = False
            current_module = line.split(None, 1)[1].strip()
            current_node = None
            pending_doc_lines = []  # docs never attach to a module
            continue

        if first_token == "enum":
            in_relation_block = False
            node = parse_enum_declaration(line, current_module, pending_doc_lines)
            model["nodes"].append(node)
            current_node = node
            pending_doc_lines = []
            continue

        if first_token in ("class", "interface"):
            in_relation_block = False
            node = parse_type_declaration(line, current_module, pending_doc_lines)
            model["nodes"].append(node)
            current_node = node
            pending_doc_lines = []
            continue

        # Inside a type, any other line is a member (field or method)
        if current_node is not None and not in_relation_block:
            member_kind, member = parse_member_line(line)
            if member_kind == "field":
                current_node["fields"].append(member)
            else:
                current_node["methods"].append(member)
            continue

        # Inside the relation block, anything else is an edge row
        if in_relation_block:
            parts = line.split()
            if len(parts) != 3:
                raise VeltroSyntaxError(line_number, line, "a relation must be '<from> <kind> <to>'")
            from_name, kind, to_name = parts
            if kind not in RELATION_KINDS:
                raise VeltroSyntaxError(line_number, line, f"unknown relation kind: {kind}")
            raw_edges.append({"from": from_name, "kind": kind, "to": to_name})
            continue

        # If gets here did not recognises the line
        raise VeltroSyntaxError(line_number, line, "unrecognised line")

    # Now that every node exists, resolve the edges by name
    name_index = build_name_index(model["nodes"])
    explicit_edges = resolve_edges(raw_edges, name_index)
    model["edges"].extend(explicit_edges)

    if derive_associations:
        derived = derive_association_edges(model["nodes"], explicit_edges, name_index)
        model["edges"].extend(derived)

    return model

def parse_file(path, derive_associations=True):
    """
    Reads a '.vel' file from disk and parse it
    
    Args:
        path (Path): to '.vel' file
        derive_associations (bool): parser command input
    """
    with open(path, encoding="utf-8") as source_file:
        text = source_file.read()
    return parse_text(text, derive_associations)
