# Veltro parser conformance suite

This is the language-agnostic definition of what it means to parse Veltro
correctly. It exists so the reference Python parser and any future port
(TypeScript, Rust, ...) can be held to the same truth, instead of each
re-discovering the grammar's edge cases and silently diverging.

> If you only ever read one thing before writing a second parser, read this.

## The contract

A conforming parser is an executable that:

1. reads a `.vel` source (UTF-8) on **stdin**
2. on success, writes the model JSON (see [`model.schema.json`](../../model.schema.json))
   to **stdout** and exits `0`
3. on a syntax error, writes `{"error": {"line": <int>, "reason": <str>}}` to
   **stdout** and exits non-zero

That is the entire interface: no flags, no files, no logging on stdout. The
Python reference implementation of this contract is
[`ref_adapter.py`](ref_adapter.py) - a thin wrapper over `veltro.parser`.

## A case

Each case is a `.vel` file in [`cases/`](cases) paired with its expected result:

| pairing | meaning |
|---------|---------|
| `<name>.vel` + `<name>.expected.json` | must parse to **exactly** this model |
| `<name>.vel` + `<name>.error.json`    | must **fail**; `{"line", "reason_contains"}` |

Model comparison is by value (parsed JSON), so object key order is free,
list order (nodes, edges, fields, args, enum values) is significant and part of
the contract. 
For error cases the reported `line` must match exactly and the
reason must contain `reason_contains` (so wording can evolve without breaking
ports).

## Running it

```bash
# check the reference parser (default)
python tests/conformance/run.py

# check another implementation - it just has to obey the contract above
python tests/conformance/run.py --parser "node dist/cli.js"
python tests/conformance/run.py --parser "target/release/veltro-parse"
```

Exit code is non-zero if any case fails, so this drops straight into CI.

## Changing the grammar

When you intentionally change the language, update or add cases, then
regenerate the expected files from the reference parser (never hand-edit a
mismatch away):

```bash
python tests/conformance/run.py --generate
```

Review the resulting diff: it is the precise, reviewable record of how the
model changed. Then make every other implementation green again.

## What the cases cover

| case | what it pins down |
|------|-------------------|
| `01-minimal` | version pragma, empty type, module qualification |
| `02-enum` | enum values, doc line on an enum |
| `03-visibility` | implicit public, explicit `+`, `-` `#` `@` markers |
| `04-static-members` | `$` static fields and methods, field default |
| `05-methods` | void method, named/unnamed args, generic arg not split on inner comma |
| `06-type-spacing` | sloppy spacing inside generics is normalized away |
| `07-doc-attachment` | `>` attaches to the following type, dangling doc before `rel` is dropped |
| `08-relations` | explicit `impl` / `extend` / `depend`, name->id resolution |
| `09-derived-assoc` | assoc derived from field type, self-ref skipped, explicit edge wins; container generic mined |
| `10-keyword-name-member` | a member named like a keyword needs an explicit `+` |
| `11-ambiguous-names` | a non-unique simple name is left unresolved for the author to qualify |
| `12-abstract-modifier` | `class abstract Foo` -> `modifiers: ["abstract"]` |
| `e01`-`e03` | bad relation arity, unknown relation kind, unrecognised line |

These mirror the rules in [`SPEC.md`](../../SPEC.md), when the two disagree,
the spec is the intent and a case is either a bug or a missing clarification
fix whichever is wrong, don't paper over it.
