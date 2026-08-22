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

They are **one** type. The parser folds them into a single node whose members,
modifiers and enum values are the **union** of the declarations, in first-seen
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
told apart by the presence of `(`.

**Public is implicit**: a member with no visibility marker is public, since
public is the common case, omitting the marker saves a token on almost every
line. The other markers (`- # @`) are still written, a leading `+` is tolerated
(it means public too) but the canonical form omits it.

**Keyword exception**: a public member whose *name* is a line-start keyword
(`veltro`, `module`, `class`, `interface`, `enum`, `rel`) must keep an explicit
`+`, otherwise a field like `module str` would read as a `module` declaration.
Methods are unaffected (the `(` tells them apart). Example: `+ module str`.

### 4.1 Fields

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
  modelled as void in v0, telling a constructor apart from a void method is
  deferred until edges are derived from method signatures (today they are
  derived only from field types).

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
| `depend`    | dependency           | `..>`    | written           |
| `assoc`     | association          | `-->`    | derived from member type |
| `aggregate` | aggregation          | `o--`    | derived / written |
| `compose`   | composition          | `*--`    | derived / written |

An explicit row wins over a derived edge between the same pair.

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
