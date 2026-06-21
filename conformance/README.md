# Veltro parser conformance suite

One shared, **executable** definition of "parsed correctly", established *before*
a second `.vel` parser exists. The risk with N parsers is silent divergence:
each re-discovers the grammar's edge cases and drifts. This suite is the oracle
they are all measured against, so drift fails a test instead of going unnoticed.

It is the same pattern as [`toml-test`](https://github.com/toml-lang/toml-test)
for TOML or the CommonMark spec tests: a language-agnostic corpus + a harness
that drives any implementation through it.

## The contract

A conforming parser is a **command** that:

- reads `.vel` text on **stdin**
- writes the model JSON (per [`model.schema.json`](../model.schema.json)) on **stdout**
- exits non-zero on a parse error

That's it. The parser's implementation language is irrelevant.

## Layout

```
conformance/
  README.md            this file (the contract + the equality definition)
  adapter_python.py    the REFERENCE adapter: the contract over veltro.parser
  run.py               the harness: drives any adapter through the cases
  cases/
    <rule>.vel           one input per grammar rule
    <rule>.expected.json the frozen golden model for that input
```

## Running it

```bash
# measure the reference parser (veltro.parser)
python conformance/run.py

# measure another implementation: anything after '--' is the parser command
python conformance/run.py -- node dist/cli.js
python conformance/run.py -- ./target/release/veltro-parse

# deliberately changed the grammar? re-freeze the goldens from the reference parser
python conformance/run.py --update
```

The harness exits non-zero if any case fails, so it drops straight into CI.

## The equality definition (the important part)

A test passes when the model the parser prints is **equivalent** to the golden
model. Equivalence is defined on the **set of facts**, never on ordering:

> Two models are equal iff they have the same `veltro` version, the same **set**
> of nodes — each node carrying the same **set** of fields and the same **set**
> of methods — and the same **set** of edges.

Order is never significant: a parser that walks a hash map in a different order,
or appends derived edges in a different place, still conforms. This is enforced
by `canonicalize()` in [`run.py`](run.py), which sorts nodes, edges, fields and
methods by a stable key before comparing. It has teeth in both directions:
re-ordering the same facts stays equal, while changing any single fact (a kind,
a type, a visibility marker) makes it unequal.

Defining equivalence this way is the whole point of the issue: it is what makes
"parsed correctly" something a machine can check, not something two authors
argue about.

## The cases (one per grammar rule)

| case | the rule it pins (see [`SPEC.md`](../SPEC.md)) |
|------|-----------------------------------------------|
| `visibility`     | the `- # @` markers, and public-is-implicit |
| `static`         | the `$` static prefix on a field and a method |
| `defaults`       | a field default `= value` |
| `optional`       | the trailing `?` nullable type |
| `generics`       | generic `<>` and the parser's spacing tolerance |
| `methods`        | named arg, type-only arg, void (no return), return type |
| `enum`           | `enum Name = A, B, C` |
| `modifiers`      | `class abstract` and `interface` |
| `relations`      | written `extend` / `impl` / `depend` edges |
| `derived_assoc`  | an association edge derived from a field's type |
| `keyword_field`  | a public field named like a keyword keeps its `+` |
| `docs`           | a `>` doc line attaching to the next declaration |

Adding a grammar rule means adding a case: keep it **one small `.vel` per rule**,
not a fuzzer. The corpus is meant to stay readable and reviewable.
