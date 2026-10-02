# Veltro Language Specification v0.1

> *<<...verrà 'l veltro / [...] e sua nazion sarà tra feltro e feltro.>>* - Dante, *Inferno* I
>
> The hound that hunts down architectural complexity

Veltro is a **token-frugal source format** for describing the static structure of
a codebase as a graph of types. A `.vel` file is already the adjacency list
of the type graph: the parser reads a model, it does not "extract" one.

**Design rule of thumb**: BPE tokenizers reward spaces and natural words, they
punish dense punctuation, so -> spaces as separators, no braces, no colons, no
repeated scaffolding.

---

## 0. Design laws (non-negotiable)

1. **Nothing in the file the viewer can compute**: no coordinates, colors,
   styling, layout. Only facts
2. **Associations are not written, they are derived**: a typed member
   (`user User`) already encodes an edge to `User`, the viewer infers
   association/composition edges from member types, the `rel` block carries only
   what members cannot express: inheritance, realization, pure dependency
3. **Token frugality first**: spaces over punctuation, no per-type headers, flat
   dotted module paths instead of deep indentation
4. **One canonical serialization per model**: deterministic -> clean diffs,
   reliable AI round-trip

---

## 1. File shape

```
veltro 1                       <- version pragma (line 1)

module <Dotted.Path>           <- flat, dotted, NOT nested
<type declaration>             <- class / interface / enum
<member>                       <- a public member starts with its name; - # @ mark
                                  other visibility; > starts a doc line

rel                            <- relation block (optional, usually last)
<from> <kind> <to>
```

**Indentation is insignificant**: the parser ignores leading whitespace.


Structure comes from the first token of each line: `module` / `class` /
`interface` / `enum` open a block, `rel` opens the relation block, `>` is a doc
line, and anything else inside a type is a member (a leading `- # @` marks
visibility, otherwise the member is public). The canonical serializer
emits no indentation (it costs tokens for nothing), a human may still indent
for readability in their editor, it simply does not count.

---

## 2. Modules

Modules are **flat and dotted**, one per logical package:

```
module Core.Models
module Engine.Context
module Providers.OpenAI
```

The model is the union of all module blocks across all `.vel` files, a type's
id is `<module>.<Name>` (e.g. `Core.Models.LlmInvocation`). No nesting, no
re-declaration stubs, cross-module references resolve by id.

---

## 3. Type declarations

```
enum MessageRole = System, User, Assistant, Tool      <- single line

interface ILlmInvocation                              <- body = members
Conversation ConversationState
Validate() IValidationResult

class ConversationState                               <- optional: `class abstract Foo`
TraceId String
TurnIndex Int = 0
```

A type with no members is just its declaration line.

### 3.1 A type may be declared more than once

The same type may arrive as several declarations, each carrying only part of
the members:

```
class Silo                        <- one file
- messageCenter MessageCenter
class abstract Silo               <- another file: same type, the rest of it
- logger ILogger
```

They are one type. The parser folds them into a single node whose members,
modifiers and enum values are the union of the declarations, in first-seen
order (identical members collapse, overloads differing by signature do not).
This is the union principle of §2 applied inside a module rather than across
files.

It is not a convenience: real languages spread one type over several files
(C# `partial class`, TypeScript interface merging), so an extractor meets the
slices one at a time and can never know it has seen the last one. Emitting one
node per declaration would break the model's primary key, since `<module>.<Name>`
must identify exactly one type: every consumer would then have to invent its own
tie-break and would silently show a type with some of its members missing.

Merging is keyed on the **id**, never on the simple name: `a.Ping` and `b.Ping`
are two different types and stay separate.

---

## 4. Members (one per line)

A member line is `[<vis>] <name><signature?> <type?>`, fields and methods are
told apart by the `(` that **opens an argument list**.

Not by any `(`: a field's default may legitimately contain one
(`validators dict<str,int> = field(default_factory=dict)`, or a string constant
that happens to mention a bracket). An argument list always comes before the
`=` of a default, and that is what separates the two:

```
run(ttl int) bool                             <- method: '(' before any '='
validators dict<str,int> = field(x=dict)      <- field:  '(' after the '='
```

A parenthesis inside a type cannot be told apart this way, so an extractor
must not emit one (a C# named tuple `Task<(Foo a,bool b)>` becomes `Any`).
Spaces inside a type are fine: a field's type is everything between its name and
the `=`, so `path list<int | str>` reads back exactly as written.

**Public is implicit**: a member with no visibility marker is public, since
public is the common case, omitting the marker saves a token on almost every
line. The other markers (`- # @`) are still written, a leading `+` is tolerated
(it means public too) but the canonical form omits it.

**Keyword exception**: a public member whose *name* is a line-start keyword
(`veltro`, `module`, `class`, `interface`, `enum`, `rel`) must keep an explicit
`+`, otherwise a field like `module str` would read as a `module` declaration.
Methods are unaffected (the `(` tells them apart). Example: `+ module str`.

### 4.1 Fields

The type is required: a line carrying only a name is a syntax error, not a
field with an unknown type (conformance case `field_needs_a_type`). Tolerance
about spacing is not tolerance of a missing type - a bare name is what a file
cut short mid-write looks like, and accepting it produced a model that validated
clean and told nobody.

```
[<vis>] <name> <type> [= <default>]
TokenBudget Int?                           <- public (implicit)
TurnIndex Int = 0
- _cache Dictionary<String,Object>         <- private
```

### 4.2 Methods (name followed by `(...)`)

```
[<vis>] [$]<name>(<args>) [<ret>]
SupportsCapability(String) Boolean
New(LlmInvocation)                         <- no return type = void
$Failure(errors IEnumerable<String>) Foo   <- named arg: same `name Type` shape as a field
$Success() ValidationResult                <- `$` prefix = static
```

- `args` are comma-separated: each uses the same `name Type` shape as a field
  (no colon spaces over punctuation), or, when the name is unknown (common
  from UML import), is type-only: `Route(ILlmInvocation)`
- The return type follows the `)` after a single space; **absent = void**.
  Constructors are written like any other method (e.g. `New(...)`) and are
  modelled as void. Deriving edges from signatures (§6.2) does not need to tell
  them apart: a constructor's parameters are dependencies exactly like any other
  method's, so the model keeps no constructor flag.

### 4.3 Visibility & modifiers

| symbol   | meaning                       |
|----------|-------------------------------|
| *(none)* | public (implicit, canonical)  |
| `+`      | public (explicit, tolerated)  |
| `-`      | private                       |
| `#`      | protected                     |
| `@`      | package                       |
| `$`      | static (name prefix)          |

Generics keep their commas inline with no space (`Dictionary<String,Object>`),
since separators are spaces, the comma never collides with anything. The parser
is **tolerant** of sloppy spacing inside a type and normalises it: a written
`Dictionary<String, Object>` is read back as the canonical `Dictionary<String,Object>`,
so the model never depends on how the author spaced a generic.

---

## 5. Documentation

`>` lines above a declaration are preserved into the model (valuable for AI):

```
> Current conversation status. `TokenBudget Null = unlimited`
class ConversationState
  ...
```

A `>` line always documents the following declaration, never the preceding
one. So between two types a doc line belongs to the second:

```
class Foo
> documents Bar, not Foo
class Bar
```

`>` lines accumulate in a buffer that is flushed onto the next
`class`/`interface`/`enum`, a type keyword (or the `rel` block) resets the
"current type", so a member can never leak into the wrong type, doc lines left
dangling at end of file, or just before `rel`, are dropped.

---

## 6. Relations

Only relations not implied by member types go here, space-delimited, no
header:

```
rel
  LlmInvocation impl ILlmInvocation
  OpenAIAdapter impl IProviderAdapter
```

References are simple names when unique, else module-qualified.

### 6.1 Relation kinds -> UML mapping

| `kind`      | UML                  | PlantUML | written / derived |
|-------------|----------------------|----------|-------------------|
| `extend`    | generalization       | `<\|--`  | written           |
| `impl`      | realization          | `<\|..`  | written           |
| `depend`    | dependency           | `..>`    | written / derived from a signature (opt-in, §6.2) |
| `assoc`     | association          | `-->`    | derived from a field type |
| `aggregate` | aggregation          | `o--`    | derived / written |
| `compose`   | composition          | `*--`    | derived / written |

An explicit row wins over a derived edge between the same pair.

### 6.2 Dependencies derived from signatures (opt-in)

A type that receives its collaborators through a constructor or a method
(`Service(repository Repository)`, `setLogger(logger Logger)`) holds no field of
their type, so §0.2's field-based derivation gives it no edge. A parser MAY
offer, **off by default**, a second derivation:

- every type named in a method's argument types or return type becomes a
  `depend` edge marked `derived: true`, never `assoc`: a parameter is "uses a",
  a field is "holds a", and the model keeps them distinct;
- the same filters as field derivation: names that are not types of the model
  (primitives, external types) and self references produce nothing;
- a pair that already has an edge, written or derived from a field, keeps it,
  because that edge says more than a signature does; a pair named by several
  signatures is one edge.

It is opt-in because it changes the graph, and with it the answer to "what does
`X` depend on" for anything built from the model. Measured on the shipped
examples (`python bench/signature_edges.py`) it adds 0.2x to 1.4x the edges -
most on NestJS, least on pydantic - and roughly halves the types with no edge
at all. A conforming parser run with default options derives nothing from a
signature (conformance case `signature_not_derived`).

---

## 7. Why this beats raw PlantUML

- **Tokens**: measured **-35.4%** vs PlantUML on the real consolidated diagram
  (o200k_base), across every class-diagram format benchmarked Veltro is the
  densest measured and unlike the runners-up (yUML, Nomnoml) it stays
  readable, modular and line-diffable. See `bench/`
- **Determinism**: one canonical form, no `!include`, no layout hints
- **Modularity**: flat module union across files, no monolith ever forms
- **Projection**: fhe file is the truth, every diagram is a query over the
  graph computed by the viewer, never authored by hand
