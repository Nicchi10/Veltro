# The Veltro CLI

`python -m veltro <command>`, or just `veltro <command>` after `pip install`.

Six commands. `extract` turns a repository into a `.vel`, `parse` turns a
`.vel` into the JSON model, and `find` / `show` / `deps` / `map` answer a
question about the graph with a bounded payload.

```bash
pip install veltro                  # the core: jsonschema and nothing else
pip install "veltro[extract]"       # + the C# and TypeScript extractors
```

## Start here

```bash
veltro extract .            # your repository -> repo.vel + repo.index.json
veltro find repo.vel Service
veltro show repo.vel MyService --code
```

```
[INFO] - found: java (1 files), python (33 files), typescript (2 files)
[INFO] - python: 33 files, 1 types
[INFO] - typescript: 2 files, 7 types
[INFO] - 8 types, 2 relations
[INFO] - written: Veltro.vel
[INFO] - source index: Veltro.index.json  (8 types)
[WARN] - 1 java files were found but not read: the Java extractor is a standalone Java program, see veltro/extract/java/
[WARN] - only 8 types in 35 files: Veltro models TYPES, so a repository built out of free functions gives it little to describe
```

That is this repository describing itself, warnings included. Both are true and
both are worth knowing before you build anything on the output.

## Why the query commands exist

A real project's `.vel` either fits in a context window or it does not, and
there is nothing in between. `examples/Orleans.vel` is 6,055 types and
**687,997 tokens**: no amount of compression makes that a thing you paste into
a prompt.

So the tool has to answer a question instead of handing over the file.
Measured on Orleans, against reading the whole thing:

| command | tokens | share of the file |
|---------|--------|-------------------|
| `map --module Orleans.Runtime` | 86,718 | 12.60% |
| `map --around Silo --depth 1` | 4,629 | **0.67%** |
| `show Silo` | 945 | **0.14%** |
| `deps Silo` | 163 | **0.02%** |

Reproduce the table with `python bench/query_cost.py` (needs the `[bench]`
extra for `tiktoken`).

Every one of these prints valid `.vel` (`map` and `show`), so a slice can be
fed straight back to a model, or to Veltro itself.

---

## `parse` - validate a file and write the model

```bash
python -m veltro parse examples/pydantic.vel
python -m veltro parse examples/pydantic.vel --out build/pydantic.model.json
python -m veltro parse examples/pydantic.vel --no-derive
```

```
[INFO] - nodes: 360  (332 classes, 23 interfaces, 5 enums)
[INFO] - edges: 286  (247 written, 39 derived)
[INFO] - validation: OK
[INFO] - written: examples/pydantic.model.json
```

| option | meaning |
|--------|---------|
| `--out PATH` | where to write the JSON (default: next to the source, `.model.json`) |
| `--no-derive` | do not derive association edges from field types |
| `--derive-from-signatures` | also derive `depend` edges from method argument and return types ([SPEC §6.2](SPEC.md)) |

Validation runs the model against
[`model.schema.json`](veltro/schemas/model.schema.json) and the one rule the
schema cannot express: node ids must be unique. A model that fails is still
written, it is what you need in order to debug it, but the command exits
non-zero.

`python -m veltro file.vel` (no command) still works and means `parse`.

## `extract` - a repository into one `.vel`

```bash
veltro extract .
veltro extract ../some-repo --out build/some-repo.vel
veltro extract . --lang python,typescript
veltro extract . --exclude "migrations/*" --include-tests
```

| option | meaning |
|--------|---------|
| `--out PATH` | where to write the `.vel` (default: `<repository name>.vel` here) |
| `--lang a,b` | only these languages (default: everything found) |
| `--exclude GLOB` | skip paths matching, relative to the repository root (repeatable) |
| `--include-tests` | read test directories and test files too |

It detects the languages by counting the source files that survive pruning, runs
each extractor that applies, and writes **one** `.vel` plus **one** source
index - the spans from every language rebased onto the repository root, so
`show --code` works across all of them.

It tells you what it could not do. A language that is present but unreadable
is named, with the command that fixes it:

```
[WARN] - 1 typescript files were found but not read: needs the [extract] extra: pip install 'veltro[extract]'
```

Silence there would read as "there is no TypeScript in this repository", which
is a different and false statement. Java is always reported this way: its
extractor is a standalone Java program and cannot be driven from here.

And it tells you when Veltro is the wrong tool. Veltro models types, so a
codebase built out of free functions produces a nearly empty graph. Below one
type per three source files it says so, rather than leaving you to deduce it
from a small file.

## `find` - which types are there

```bash
python -m veltro find examples/pydantic.vel Encoder
```

```
pydantic.types.EncoderProtocol  interface
pydantic.types.Base64Encoder  class
pydantic.types.Base64UrlEncoder  class
```

| option | meaning |
|--------|---------|
| `--kind class\|interface\|enum` | keep only one kind |
| `--module PREFIX` | keep only modules starting with this |
| `--limit N` | how many to print (default 20) |

The pattern matches the name or the id, and may be empty, so
`find x.vel "" --kind enum --module pydantic.v1` is a legitimate listing. When
more matched than were shown, the command says so rather than truncating in
silence.

With a [source index](#the-source-index) beside the `.vel`, each row also
carries `file:line`.

## `show` - one type, as `.vel`

```bash
python -m veltro show examples/pydantic.vel Base64Encoder
```

```
module pydantic.types
class Base64Encoder
$decode(data bytes) bytes
$encode(value bytes) bytes
$get_json_format() Literal<base64>
rel extend pydantic.types.EncoderProtocol
# no source index: run the extractor to create one
```

| option | meaning |
|--------|---------|
| `--code` | also print the declaration's source, using the index |
| `--root PATH` | read the source from here instead of the root recorded in the index |

`--root` is for a checkout that has moved since the index was built.

## `deps` - what it touches, and what touches it

```bash
python -m veltro deps examples/pydantic.vel Base64Encoder
```

```
out (1):
  extend     pydantic.types.EncoderProtocol
in (0):
```

| option | meaning |
|--------|---------|
| `--direction in\|out\|both` | default `both` |
| `--limit N` | how many per direction (default 30) |
| `--derive-from-signatures` | also count what the type receives or returns through its methods |

Edges derived from a field type are marked `(derived)`, so a written
inheritance relation is never confused with an association Veltro inferred.

By default a dependency passed in through a constructor or a method is
invisible, because associations are derived from **fields**. `BeanFactoryAware`
receives its `BeanFactory` through a setter and holds no field of that type:

```bash
python -m veltro deps examples/spring-beans.vel BeanFactoryAware --derive-from-signatures
```

```
out (2):
  extend     org.springframework.beans.factory.Aware
  depend     org.springframework.beans.factory.BeanFactory  (derived)
in (8):
  ...
```

Without the flag the `depend` row is not there. It is opt-in because it changes
the graph - 0.2x to 1.4x more edges across the shipped examples
(`python bench/signature_edges.py`).

## `map` - a slice of the graph

```bash
python -m veltro map examples/pydantic.vel --around Base64Encoder --depth 1
```

```
veltro 1

module pydantic.types
interface EncoderProtocol
$decode(data bytes) bytes
$encode(value bytes) bytes
$get_json_format() str
class Base64Encoder
$decode(data bytes) bytes
$encode(value bytes) bytes
$get_json_format() Literal<base64>

rel
Base64Encoder extend EncoderProtocol
```

| option | meaning |
|--------|---------|
| `--around TYPE` | only this type's neighbourhood |
| `--depth N` | how many relations to follow from `--around` (default 1, or as far as the budget allows with `--budget`) |
| `--module PREFIX` | only the types of this module |
| `--budget N` | keep the slice under N tokens, nearest types first |
| `--encoding NAME` | the tiktoken encoding `--budget` counts with (default `o200k_base`) |

With none of them it prints the whole graph, which is a round trip through the
canonical serializer rather than a copy of the input: indentation is dropped,
generics are normalised, repeated declarations are merged.

### `--budget`: as much architecture as fits

An agent has a context window, not a wish. `--budget` walks outward from the
subject and stops at the last type that still fits:

```bash
python -m veltro map examples/Orleans.vel --around Silo --budget 2000
```

```
[INFO] - 5 of 4872 types, 1513 of 2000 tokens
```

(the report goes to **stderr**, so stdout stays a clean `.vel` you can pipe.)

What gets dropped is what is furthest away: the walk is breadth-first, so the
budget is spent on the subject and its nearest neighbours first. Without an
explicit `--depth` the walk goes as far as the graph allows and the budget
alone decides where to stop.

**It refuses to run without a tokenizer** (`pip install "veltro[tokenizer]"`),
rather than estimating. Measured on real slices of the shipped examples, a
`characters / 4` estimate lands between −22% and +55% of the true count and a
lexical one between −48% and +44%. A budget that can overshoot by half is not a
budget, so this follows the same rule as `show`: refuse rather than guess.

---

## A bare name that means two types is refused

`show`, `deps` and `map --around` take a node id (`pydantic.main.BaseModel`) or
a simple name. When the simple name is ambiguous they do not guess: they
list the candidates and exit non-zero.

```bash
python -m veltro show examples/pydantic.vel BaseModel
```

```
[ERROR] - 'BaseModel' is declared in 2 modules, say which:
  pydantic.main.BaseModel
  pydantic.v1.main.BaseModel
```

That is deliberate. Picking the first match would quietly answer a question
about the wrong type, and in a pipeline nobody would ever find out.

## The source index

A `.vel` is a map with no coordinates: a C# namespace has no relation to the
directory tree, and a TS module path is ambiguous when a file name contains
dots. So the way back from the graph to the code is an explicit sidecar,
`x.vel` -> `x.index.json`, described by
[`index.schema.json`](veltro/schemas/index.schema.json).

The extractors write it automatically:

```bash
python -m veltro.extract.python_ast path/to/package --out build/thing.vel
# [INFO] - 32 files read, 10 directories pruned (__pycache__, .git, build, tests, venv)
# [INFO] - written: build/thing.vel
# [INFO] - source index: build/thing.index.json  (<n> types)
```

### What an extractor reads

| language | command |
|----------|---------|
| Python | `python -m veltro.extract.python_ast <dir> --out x.vel` |
| C# | `python -m veltro.extract.tree_sitter_csharp <dir> --out x.vel` |
| TypeScript / JavaScript | `python -m veltro.extract.tree_sitter_typescript <dir> --out x.vel` |
| Java | `veltro/extract/java/` (a standalone Java program, see its README) |

All three share one pruning policy
([`veltro/extract/walk.py`](veltro/extract/walk.py)) and print what they left
out, because silence is how someone ends up believing their project has 25,000
types. Pointing the Python extractor at this repository's root used to return
exactly that, 99.6% of it from the virtualenv.

Pruned everywhere: `.git`, `node_modules`, `venv` / `.venv` / `site-packages`,
`__pycache__` and the other caches, `vendor`, `third_party`, `coverage`.
Build output is pruned per language, `bin` / `obj` / `packages` for C#,
`dist` / `out` / `build` for TypeScript, `build` / `dist` for Python, because a
monorepo keeps its *source* in `packages` (nest and angular both do), and
pruning that name everywhere would quietly return an empty graph.

Test directories and test files (`tests/`, `test_*.py`, `*.spec.ts`, `*Tests.cs`)
are skipped too: they mirror the production types and drown them.

| option | meaning |
|--------|---------|
| `--exclude GLOB` | skip anything matching, relative to the source root (repeatable) |
| `--include-tests` | read the tests as well |

`.gitignore` is not read. A half-implemented ignore file silently drops real
source, which is a worse failure than reading too much; use `--exclude`.

- It lives outside the `.vel` on purpose. The `.vel` is what enters a
  model's context; a `file:line` on every type would cost tokens on every read,
  for something only tools use.
- A location is a list, because one type is legitimately declared in several
  files. On Orleans that is 1,578 types - and `Silo`'s first span is a 22-line
  API stub while the real 668-line implementation is the second, so recording
  only the first would hide the actual code.
- It is a build artefact and is gitignored. Line numbers move at the first
  edit, and an index pointing at the wrong line is worse than no index.
- The Java extractor does not produce one yet (it is a standalone Java program).

Without an index everything still works except `show --code`, `show` and `find`
just stop printing locations, and `show` says so.

## Exit codes

`0` on success. Non-zero when a file does not parse, a model fails validation, a
bare name is ambiguous, a type does not exist, or `--code` is asked for without
an index.

## Using it from Python

The CLI is a thin wrapper: the logic is pure functions in
[`veltro/query.py`](veltro/query.py) over `(model, index)`, so a viewer, an
editor plugin or an agent tool reuses it instead of shelling out or
reimplementing it.

```python
from veltro.parser import parse_file
from veltro.query import find_types, neighbourhood_ids, resolve_one, slice_vel

model = parse_file("examples/pydantic.vel")
node, candidates = resolve_one(model, "Base64Encoder")
wanted = neighbourhood_ids(model, node["id"], 1)
print(slice_vel(model, wanted))
```

`resolve_one` returns `(None, candidates)` for an ambiguous name, the same rule
the CLI enforces, in the same place, for the same reason.
