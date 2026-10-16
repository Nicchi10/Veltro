"""

eval/oracle.py

The source of truth for the comparison in eval/DESIGN.md, rule R1: the correct
answer to a question is a fact about the SOURCE CODE, never the output of one of
the tools under test.

Everything here reads the real repository with Python's own 'ast'. It imports
nothing from veltro except the file walk, and that exception is deliberate: if
the oracle and the subject builders disagreed about WHICH FILES are part of the
project, the experiment would be measuring the walk instead of the formats. What
the oracle refuses to borrow is any INTERPRETATION of the code.

Why this file has to exist: the current eval generates both the questions and
their answers from the Veltro model, which is fair while every subject is a
rendering of that one model, and stops being fair the moment a subject comes
from another tool with its own ontology. Then "truth from the model" means
"truth is Veltro's answer" and every disagreement scores as the competitor's
error. See eval/DESIGN.md section 1.

THE SEMANTIC DECISIONS, stated because they are the whole value of this file.
A question is only a fact if its rule is written down; otherwise the scorer is
quietly arbitrating a convention dispute.

    - 'object' is not an inherited base. Every class has it, so naming it
      carries no information and no tool writes it.
    - A base written with subscripts is reduced to its head: 'Generic[T]' is
      'Generic', because the question asks what a class inherits FROM.
    - A method is a 'def' or 'async def' in the class body whose name does NOT
      start with an underscore. Dunders are therefore excluded, including
      '__init__'. They are language protocol rather than API surface, and
      counting them would turn the family into a referendum on a naming
      convention: whether '__init__' is "a public method" has no agreed answer,
      and a question with no agreed answer cannot be ground truth.
    - An '@property' is a FIELD, not a method. It is declared with 'def' and
      read as an attribute, and the question families split members by the role
      they play for a caller.
    - A field's type is unwrapped through the annotations that decorate rather
      than contain: Optional, ClassVar, Final, Annotated. So
      'Optional[List[int]]' IS a collection and 'Optional[int]' is NOT - which
      is the trap in detecting a collection by looking for a '[': 'Optional[int]'
      has one and holds nothing.
    - Only TOP-LEVEL classes and functions are asked about. Nested classes are
      counted and reported, never asked, because measuring a second blind spot
      would mix it with the two this experiment declares in advance.
    - 'callers' is syntactic and is a LOWER BOUND: 'ast' sees a call by name, it
      does not resolve imports, aliases or re-exports. Stated here rather than
      discovered later, because a lower bound is still a fact as long as every
      subject is scored against the same one.
    - A name that is not unique in the repository is never asked about. The
      question would have several right answers and the record holds one.

Run:
    python eval/oracle.py veltro                      # report what it found
    python eval/oracle.py ./pydantic/pydantic --out eval/subjects/pydantic/questions.json

"""

import argparse
import ast
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from veltro.extract.walk import add_walk_arguments, describe, iter_source_files, new_report

# Container types, by the head of the annotation. A name is enough: the question asks which fields hold a collection, and no subject under test carries more
# than the written annotation anyway
COLLECTION_HEADS = frozenset({
    "list", "List",
    "dict", "Dict",
    "set", "Set",
    "frozenset", "FrozenSet",
    "tuple", "Tuple",
    "deque", "Deque",
    "Sequence", "MutableSequence",
    "Iterable", "Iterator", "Generator",
    "Mapping", "MutableMapping",
    "Collection", "AbstractSet",
    "DefaultDict", "OrderedDict", "Counter", "ChainMap",
})

# Annotations that decorate a type rather than contain one, so the type inside
# is what the question is about
TRANSPARENT_HEADS = ("Optional", "ClassVar", "Final", "Annotated", "InitVar")

# What a call made at file level, outside any declaration, is recorded against.
# Kept out of the 'callers' answers: that family asks which FUNCTIONS call a function, and a ground truth that also demanded 'validators.py' would be
# asking for something the prompt never asked for
MODULE_SCOPE = "<module>"

# Which subjects can express an answer AT ALL (eval/DESIGN.md section 4). 
# A subject that cannot is scored 'absent', never 'wrong': lacking a feature and giving a wrong answer are different facts and collapsing them hides which
# one happened
SUBJECTS_BY_FAMILY = {
    "inherits": ("veltro", "source", "repomap", "ctags", "outline", "graphify"),
    "implementors": ("veltro", "source", "repomap", "ctags", "outline", "graphify"),
    "defined_in": ("veltro", "source", "repomap", "ctags", "outline", "graphify"),
    "members": ("veltro", "source", "outline", "graphify"),
    "field_types": ("veltro", "source"),
    "function_params": ("source", "outline", "ctags", "graphify"),
    "callers": ("source", "graphify"),
}


# ============ READING ONE ANNOTATION ============

def annotation_text(annotation) -> str:
    """

    The annotation as it is written in the source.

    Args:
        annotation (ast.AST | None): an annotation node

    Returns:
        str: the unparsed text, or "" when there is no annotation

    """
    if annotation is None:
        return ""
    return ast.unparse(annotation)


def head_of(text: str) -> str:
    """

    The head of an annotation: what it is, before what it holds.

    Args:
        text (str): e.g. 'typing.List[int]'

    Returns:
        str: e.g. 'List'

    """
    bracket = text.find("[")
    if bracket >= 0:
        text = text[:bracket]
    dot = text.rfind(".")
    if dot >= 0:
        text = text[dot + 1:]
    return text.strip()


def inside_of(text: str) -> str:
    """

    What a subscripted annotation holds.

    Args:
        text (str): e.g. 'Optional[List[int]]'

    Returns:
        str: e.g. 'List[int]', or "" when it holds nothing

    """
    open_bracket = text.find("[")
    close_bracket = text.rfind("]")
    if open_bracket < 0 or close_bracket < open_bracket:
        return ""
    return text[open_bracket + 1:close_bracket].strip()


def unwrap_annotation(text: str) -> str:
    """

    Strip the annotations that decorate rather than contain, so the question is
    asked about the type a caller actually sees.

    'Optional[List[int]]' -> 'List[int]', 'ClassVar[int]' -> 'int'.
    An 'Optional[A, B]' cannot happen, but 'Annotated[int, Field(gt=0)]' can, and
    only its first argument is the type.

    Args:
        text (str): the written annotation

    Returns:
        str: the annotation with every transparent wrapper removed

    """
    current = text.strip()
    while True:
        head = head_of(current)
        if head not in TRANSPARENT_HEADS:
            return current
        inside = inside_of(current)
        if not inside:
            return current
        # 'Annotated[T, metadata]': the type is the first argument. Splitting on the top-level comma only, so 'Dict[str, int]' survives intact
        current = first_argument(inside)


def first_argument(text: str) -> str:
    """

    The first top-level comma-separated part of a subscript.

    Args:
        text (str): e.g. 'Dict[str, int], Field(gt=0)'

    Returns:
        str: e.g. 'Dict[str, int]'

    """
    depth = 0
    for position, character in enumerate(text):
        if character in "[(":
            depth += 1
        elif character in "])":
            depth -= 1
        elif character == "," and depth == 0:
            return text[:position].strip()
    return text.strip()


def is_collection(text: str) -> bool:
    """

    Whether an annotation holds a collection.

    A bare 'list' counts; so does 'List[str]'. 'Optional[int]' does not, which
    is why the wrappers come off first: detecting a '[' alone would call it one.

    Args:
        text (str): the written annotation

    Returns:
        bool

    """
    if not text:
        return False
    unwrapped = unwrap_annotation(text)
    if head_of(unwrapped) == "Union":
        for part in split_arguments(inside_of(unwrapped)):
            if part.strip() not in ("None", "NoneType") and is_collection(part):
                return True
        return False
    if "|" in unwrapped:
        for part in unwrapped.split("|"):
            if part.strip() not in ("None", "NoneType") and is_collection(part):
                return True
        return False
    return head_of(unwrapped) in COLLECTION_HEADS


def split_arguments(text: str) -> list:
    """

    Split a subscript's arguments on top-level commas only.

    Args:
        text (str): e.g. 'str, Dict[str, int]'

    Returns:
        list[str]: e.g. ['str', 'Dict[str, int]']

    """
    parts = []
    depth = 0
    current = ""
    for character in text:
        if character in "[(":
            depth += 1
        elif character in "])":
            depth -= 1
        if character == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += character
    if current.strip():
        parts.append(current.strip())
    return parts


# ============ READING ONE DECLARATION ============

def base_names(class_node) -> list:
    """

    The classes a class inherits from, by simple name.

    'object' is left out: every class has it, so naming it says nothing.

    Args:
        class_node (ast.ClassDef)

    Returns:
        list[str]: sorted, duplicates removed

    """
    names = set()
    for base in class_node.bases:
        name = head_of(ast.unparse(base))
        if name and name != "object":
            names.add(name)
    return sorted(names)


def is_public_name(name: str) -> bool:
    """

    Whether a member name is part of the public surface.

    Anything starting with an underscore is not, dunders included. See the
    module docstring for why '__init__' is excluded rather than argued about.

    Args:
        name (str)

    Returns:
        bool

    """
    return not name.startswith("_")


def decorator_heads(node) -> set:
    """

    The decorator names on a declaration, by simple name.

    Args:
        node (ast.AST): a class or function definition

    Returns:
        set[str]: e.g. {'property', 'cached_property'}

    """
    heads = set()
    for decorator in node.decorator_list:
        heads.add(head_of(ast.unparse(decorator)))
    return heads


def is_property(function_node) -> bool:
    """

    Whether a 'def' in a class body is really an attribute.

    Args:
        function_node (ast.FunctionDef | ast.AsyncFunctionDef)

    Returns:
        bool

    """
    heads = decorator_heads(function_node)
    if "property" in heads or "cached_property" in heads:
        return True
    # a setter is written '@name.setter', whose head is the property's name
    for decorator in function_node.decorator_list:
        text = ast.unparse(decorator)
        if text.endswith(".setter") or text.endswith(".getter") or text.endswith(".deleter"):
            return True
    return False


def public_method_names(class_node) -> list:
    """

    The public methods a class declares, by name.

    Properties are left out: they are fields by role. Inherited methods are left
    out too, because the question says 'declares'.

    Args:
        class_node (ast.ClassDef)

    Returns:
        list[str]: sorted, duplicates removed

    """
    names = set()
    for item in class_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if is_property(item):
            continue
        if is_public_name(item.name):
            names.add(item.name)
    return sorted(names)


def annotated_fields(class_node) -> list:
    """

    The annotated class-level attributes, as (name, annotation) pairs.

    An '@property' is included, with its return annotation, because a caller
    reads it as an attribute. An attribute assigned without an annotation is
    not: there is no type to be asked about.

    Args:
        class_node (ast.ClassDef)

    Returns:
        list[tuple[str, str]]: in source order

    """
    fields = []
    for item in class_node.body:
        if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            fields.append((item.target.id, annotation_text(item.annotation)))
        elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and is_property(item):
            fields.append((item.name, annotation_text(item.returns)))
    return fields


def collection_field_names(class_node) -> list:
    """

    The fields of a class whose type holds a collection.

    Args:
        class_node (ast.ClassDef)

    Returns:
        list[str]: sorted, duplicates removed

    """
    names = set()
    for name, annotation in annotated_fields(class_node):
        if is_public_name(name) and is_collection(annotation):
            names.add(name)
    return sorted(names)


def parameter_names(function_node) -> list:
    """

    The parameters a function takes, in declaration order.

    'self' and 'cls' cannot appear (only module-level functions are asked
    about). '*args' and '**kwargs' are named as written, because arity is part
    of the signature a reader needs.

    Args:
        function_node (ast.FunctionDef | ast.AsyncFunctionDef)

    Returns:
        list[str]: in order, e.g. ['path', 'encoding', '*extra']

    """
    arguments = function_node.args
    names = []
    for argument in list(arguments.posonlyargs) + list(arguments.args):
        names.append(argument.arg)
    if arguments.vararg is not None:
        names.append("*" + arguments.vararg.arg)
    for argument in arguments.kwonlyargs:
        names.append(argument.arg)
    if arguments.kwarg is not None:
        names.append("**" + arguments.kwarg.arg)
    return names


# ============ THE SYMBOL TABLE ============

def new_table(root: str) -> dict:
    """

    An empty symbol table for a repository.

    Args:
        root (str): the directory every recorded file is relative to

    Returns:
        dict: 'root', 'classes', 'functions' (name -> list of records),
            'files' (how many were read), 'nested_classes' (counted, not asked)

    """
    return {
        "root": os.path.abspath(root),
        "classes": {},
        "functions": {},
        "files": 0,
        "nested_classes": 0,
    }


def relative_file(table: dict, path: str) -> str:
    """

    A file's path relative to the table's root, with forward slashes.

    Args:
        table (dict): the symbol table
        path (str): an absolute path

    Returns:
        str

    """
    relative = os.path.relpath(os.path.abspath(path), table["root"])
    return relative.replace(os.sep, "/").replace("\\", "/")


def count_declared_functions(class_node) -> int:
    """

    How many 'def' / 'async def' a class declares, whatever their visibility.

    Args:
        class_node (ast.ClassDef)

    Returns:
        int

    """
    total = 0
    for item in class_node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            total += 1
    return total


def count_nested_classes(class_node) -> int:
    """

    How many classes are declared inside a class.

    Args:
        class_node (ast.ClassDef)

    Returns:
        int

    """
    total = 0
    for item in class_node.body:
        if isinstance(item, ast.ClassDef):
            total += 1 + count_nested_classes(item)
    return total


def record_module(table: dict, tree, path: str) -> None:
    """

    Add one parsed module's top-level declarations to the table.

    Args:
        table (dict): the table being built (modified in place)
        tree (ast.Module): the parsed file
        path (str): the file it came from

    """
    where = relative_file(table, path)
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            table["nested_classes"] += count_nested_classes(node)
            record = {
                "name": node.name,
                "file": where,
                "line": node.lineno,
                "bases": base_names(node),
                "methods": public_method_names(node),
                "collection_fields": collection_field_names(node),
                # Counted so a question whose answer is guessable without reading anything is never asked: "how many public methods"
                # on a class that declares none, or "which fields hold a collection" on a class with no annotated field at all
                "annotated_fields": len(annotated_fields(node)),
                "declared_functions": count_declared_functions(node),
            }
            table["classes"].setdefault(node.name, []).append(record)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record = {
                "name": node.name,
                "file": where,
                "line": node.lineno,
                "parameters": parameter_names(node),
            }
            table["functions"].setdefault(node.name, []).append(record)


def enclosing_name(stack: list) -> str:
    """

    The declaration a call site sits in.

    Args:
        stack (list[str]): the names of the enclosing declarations

    Returns:
        str: the innermost one, or '<module>' at file level

    """
    if not stack:
        return MODULE_SCOPE
    return stack[-1]


def visit_for_calls(node, stack: list, calls: dict) -> None:
    """

    Walk a subtree, recording each call by name against the declaration it
    sits in.

    Args:
        node (ast.AST): the subtree to walk
        stack (list[str]): the names of the enclosing declarations
        calls (dict): called name -> set of caller names (modified in place)

    """
    declares = isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))

    for child in ast.iter_child_nodes(node):
        # A decorator is a call APPLIED TO this declaration by the scope around it, not a call this declaration makes. Walking it as part of the body
        # put a false fact in the ground truth: jsonschema's '_checks_drafts' came back as "called by" the twenty functions it decorates
        if declares and child in node.decorator_list:
            continue
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            visit_for_calls(child, stack + [child.name], calls)
            continue
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
            caller = enclosing_name(stack)
            calls.setdefault(child.func.id, set()).add(caller)
        visit_for_calls(child, stack, calls)


def record_call_sites(calls: dict, tree) -> None:
    """

    Record, for every called name, the declarations that call it.

    Syntactic and by name only: a call written 'helpers.run()' is NOT recorded
    against 'run', because the oracle does not resolve attribute access or
    imports. See the module docstring: this family is a lower bound, and it is
    the same lower bound for every subject.

    Args:
        calls (dict): called name -> set of caller names (modified in place)
        tree (ast.Module): the parsed file

    """
    visit_for_calls(tree, [], calls)


def build_symbol_table(root: str, keep_tests: bool = False, exclude=(), report: dict = None) -> dict:
    """

    Read a Python repository and record what it declares.

    Args:
        root (str): the directory to read
        keep_tests (bool): read test files and directories too
        exclude (tuple[str]): globs to skip, relative to the root
        report (dict): a walk report to fill in, or None

    Returns:
        (dict, dict): the symbol table, and called name -> caller names

    """
    table = new_table(root)
    calls = {}

    for path in iter_source_files(root, (".py",), keep_tests, exclude, report):
        with open(path, encoding="utf-8", errors="replace") as source_file:
            source = source_file.read()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            # A file this interpreter cannot parse is not a fact about the project, and guessing at it would put an invented answer in the
            # ground truth. Skipped, and counted by the caller
            continue
        table["files"] += 1
        record_module(table, tree, path)
        record_call_sites(calls, tree)

    return table, calls


def public_first(names: list) -> list:
    """

    The same names, public ones first, each group alphabetical.

    Taking the first N of a plain alphabetical list is not neutral: '_' sorts
    before every letter, so on jsonschema every function question landed on a
    private helper. That skews the comparison against the subjects that
    deliberately summarise the PUBLIC surface (a repo map ranks it, an outline
    keeps it), which would have been read as those formats answering badly.

    Args:
        names (list[str]): candidate names, already sorted

    Returns:
        list[str]: public names first, then the private ones

    """
    public = []
    private = []
    for name in names:
        if is_public_name(name):
            public.append(name)
        else:
            private.append(name)
    return public + private


def unique_names(table: dict) -> dict:
    """

    The names that identify exactly one declaration in the repository.

    A name used twice (a class and a function, or a class in two modules) is
    left out: the question would have several right answers.

    Args:
        table (dict): a symbol table

    Returns:
        dict: 'classes' and 'functions', each a list of names, public first

    """
    classes = []
    for name in sorted(table["classes"]):
        if len(table["classes"][name]) == 1 and name not in table["functions"]:
            classes.append(name)

    functions = []
    for name in sorted(table["functions"]):
        if len(table["functions"][name]) == 1 and name not in table["classes"]:
            functions.append(name)

    return {"classes": public_first(classes), "functions": public_first(functions)}


# ============ THE QUESTIONS ============

def append_question(questions: list, family: str, subject: str, prompt: str, answer) -> None:
    """

    Append one question, numbering it from the current length.

    Args:
        questions (list): the list being built (modified in place)
        family (str): the question family
        subject (str): the class or function it is about
        prompt (str): what the model is asked
        answer: the fact, from the source

    """
    questions.append({
        "id": len(questions) + 1,
        "type": family,
        "subject": subject,
        "prompt": prompt,
        "answer": answer,
        "expressible_in": list(SUBJECTS_BY_FAMILY[family]),
    })


def build_questions(table: dict, calls: dict, limit: int) -> list:
    """

    Build the question set of eval/DESIGN.md section 4 from the symbol table.

    Every answer is a fact about the source. Classes AND module-level functions
    are asked about (rule R2), so a tool that models only types scores zero on
    the function families instead of never being asked.

    Args:
        table (dict): a symbol table
        calls (dict): called name -> caller names
        limit (int): max questions per family

    Returns:
        list[dict]: each {id, type, subject, prompt, answer, expressible_in}

    """
    unique = unique_names(table)
    questions = []

    # Who does a class inherit from? Only classes that inherit from something: "nothing" is a right answer that a subject can score by staying silent
    for name in unique["classes"]:
        record = table["classes"][name][0]
        if not record["bases"]:
            continue
        if count_family(questions, "inherits") >= limit:
            break
        prompt = (f"Which types does the class '{name}' inherit from or implement? "
                  f"Answer with type names only.")
        append_question(questions, "inherits", name, prompt, record["bases"])

    # Who inherits from a class? Computed across the whole repository
    children_by_base = {}
    for name in sorted(table["classes"]):
        for record in table["classes"][name]:
            for base in record["bases"]:
                children_by_base.setdefault(base, set()).add(name)

    for name in unique["classes"]:
        if name not in children_by_base:
            continue
        if count_family(questions, "implementors") >= limit:
            break
        prompt = (f"List every type that extends or implements '{name}'. "
                  f"Answer with type names only.")
        append_question(questions, "implementors", name, prompt, sorted(children_by_base[name]))

    # Which file is it declared in? Asked about classes and functions alike
    for name in unique["classes"][:limit]:
        record = table["classes"][name][0]
        prompt = f"Which source file declares the class '{name}'? Answer with the path only."
        append_question(questions, "defined_in", name, prompt, record["file"])

    # How many public methods does a class declare? Only classes that declare at least one 'def': on a class with none the answer is guessable
    for name in unique["classes"]:
        record = table["classes"][name][0]
        if not record["declared_functions"]:
            continue
        if count_family(questions, "members") >= limit:
            break
        prompt = (f"How many public methods does '{name}' declare? Count methods "
                  f"declared on the type itself, not inherited ones, and do not "
                  f"count properties or names starting with an underscore.")
        append_question(questions, "members", name, prompt, len(record["methods"]))

    # Which fields hold a collection? Only classes that have annotated fields, so an empty answer means "none of them is a collection" - a real
    # discrimination - rather than "this class has no fields at all"
    for name in unique["classes"]:
        record = table["classes"][name][0]
        if not record["annotated_fields"]:
            continue
        if count_family(questions, "field_types") >= limit:
            break
        prompt = (f"Which fields of '{name}' have a collection type (list, dict, "
                  f"set, tuple or an equivalent)? Answer with field names only.")
        append_question(questions, "field_types", name, prompt, record["collection_fields"])

    # What does a module-level function take? This is the declared blind spot
    for name in unique["functions"][:limit]:
        record = table["functions"][name][0]
        prompt = (f"What parameters does the function '{name}' take? Answer with "
                  f"parameter names, in order.")
        append_question(questions, "function_params", name, prompt, record["parameters"])

    # What calls it? A lower bound, the same one for every subject
    for name in unique["functions"]:
        if name not in calls:
            continue
        if count_family(questions, "callers") >= limit:
            break
        callers = []
        for caller in sorted(calls[name]):
            # Not itself (recursion is not an answer to "what calls this"), and not a file-level call site: the prompt asks for functions
            if caller != name and caller != MODULE_SCOPE:
                callers.append(caller)
        if not callers:
            continue
        prompt = (f"Which functions or methods call '{name}'? Answer with names only.")
        append_question(questions, "callers", name, prompt, callers)

    return questions


def count_family(questions: list, family: str) -> int:
    """

    How many questions of one family are in the set so far.

    Args:
        questions (list): the set being built
        family (str): the family to count

    Returns:
        int

    """
    total = 0
    for question in questions:
        if question["type"] == family:
            total += 1
    return total


def summarise(questions: list) -> dict:
    """

    How many questions there are per family.

    Args:
        questions (list): the question set

    Returns:
        dict: family -> count

    """
    counts = {}
    for question in questions:
        counts[question["type"]] = counts.get(question["type"], 0) + 1
    return counts


# ============ CLI ============

def main(argv=None):
    examples = (
        "examples:\n"
        "  python eval/oracle.py veltro\n"
        "  python eval/oracle.py ./pydantic/pydantic --out eval/subjects/pydantic/questions.json\n"
    )
    parser = argparse.ArgumentParser(
        description="Ground truth for the eval, read from the source with 'ast' (see eval/DESIGN.md, rule R1)",
        epilog=examples,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("repository", help="path to the Python package or repository")
    parser.add_argument("--out", help="where to write the questions JSON (default: report only)")
    parser.add_argument("--limit", type=int, default=10, help="max questions per family (default: 10)")
    add_walk_arguments(parser)
    arguments = parser.parse_args(argv)

    report = new_report()
    table, calls = build_symbol_table(arguments.repository, arguments.include_tests, arguments.exclude, report)
    unique = unique_names(table)
    questions = build_questions(table, calls, arguments.limit)

    print(f"[INFO] - {describe(report)}")
    print(f"[INFO] - top-level: {len(table['classes'])} class names, {len(table['functions'])} function names")
    print(f"[INFO] - uniquely named: {len(unique['classes'])} classes, {len(unique['functions'])} functions")
    print(f"[INFO] - nested classes seen but never asked about: {table['nested_classes']}")
    print(f"[INFO] - questions: {len(questions)}")
    counts = summarise(questions)
    for family in sorted(counts):
        print(f"[INFO] -     {family:18} {counts[family]}")

    if not questions:
        print("[ERROR] - no questions could be built: nothing uniquely named was found")
        return 1

    if arguments.out:
        directory = os.path.dirname(os.path.abspath(arguments.out))
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(arguments.out, "w", encoding="utf-8", newline="\n") as out_file:
            json.dump(questions, out_file, indent=2, ensure_ascii=False)
            out_file.write("\n")
        print(f"[INFO] - written: {arguments.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
