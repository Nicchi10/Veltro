# Veltro Language Specification v0

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

module <Dotted.Path>           <- flat, dotted, NOT nested (saves indent tokens)
  <type declaration>           <- 2-space indent
    <member>                   <- 4-space indent

rel                            <- relation block (optional, usually last)
  <from> <kind> <to>
```

Indentation: **2 spaces per level**, max two levels (type, member), tabs
forbidden.

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
  + Conversation ConversationState
  + Validate() IValidationResult

class ConversationState                               <- optional: `class abstract Foo`
  + TraceId String
  + TurnIndex Int = 0
```

A type with no members is just its declaration line.

---

## 4. Members (one per line)

A member line is `<vis> <name><signature?> <type?>`, fields and methods are
told apart by the presence of `(`.

### 4.1 Fields

```
<vis> <name> <type> [= <default>]
+ TokenBudget Int?
+ TurnIndex Int = 0
+ Metadata Dictionary<String,Object>
```

### 4.2 Methods (name followed by `(...)`)

```
<vis> [$]<name>(<args>) [<ret>]
+ SupportsCapability(String) Boolean
+ New(LlmInvocation)                       <- no return = void / constructor
+ $Success() ValidationResult              <- `$` prefix = static
```

- `args` are comma-separated, each is `name: Type` or, when the name is unknown
  (common from UML import), type-only: `Route(ILlmInvocation)`
- The return type follows the `)` after a single space; absent = void/ctor

### 4.3 Visibility & modifiers

| symbol | meaning              |
|--------|----------------------|
| `+`    | public               |
| `-`    | private              |
| `#`    | protected            |
| `~`    | package              |
| `$`    | static (name prefix) |

Generics keep their commas inline with no space (`Dictionary<String,Object>`);
since separators are spaces, the comma never collides with anything.

---

## 5. Documentation

`>` lines above a declaration are preserved into the model (valuable for AI):

```
> Current conversation status. `TokenBudget Null = unlimited`.
class ConversationState
  ...
```

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

- **Tokens**: measured +16.8% on real data, the gap widens on comment- or
  arrow-heavy diagrams
- **Determinism**: one canonical form, no `!include`, no layout hints
- **Modularity**: flat module union across files, no monolith ever forms
- **Projection**: fhe file is the truth, every diagram is a query over the
  graph computed by the viewer, never authored by hand
