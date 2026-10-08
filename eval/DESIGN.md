# Comparing Veltro against the real alternatives - the design, before the numbers

This document is written before the experiment runs, and it is committed so
that it cannot be modified secretly once the results are in. It answers
[issue #12](https://github.com/Nicchi10/Veltro/issues/12): the published
comparison is against diagram formats, and nobody feeds a 6,000-line Mermaid
diagram to an LLM.

The subjects worth comparing against are the ones an agent actually has today:
the raw source read through grep, a token-budgeted repo map, `ctags`, tree-sitter
outlines and, since it exists and does very nearly this job,
[graphify](https://github.com/Graphify-Labs/graphify).

Nothing here needs an API key. The paid sweep comes last, and only once the
design below is settled, because a sweep run on a flawed question set costs the
same as a sweep run on a good one.

---

## 1. Why the current design cannot be reused as it is

The existing eval is fair for what it measures. Every subject is a rendering of one model, 
so no subject knows anything the others do not, and the ground truth generated from that 
model is genuinely a fact rather than an opinion. `eval/README.md` says so, and it is
right.

That property dies the moment a subject is produced by a different tool.
A repo map, `ctags` and graphify each have their own ontology, their own idea of
what a dependency is, and their own extractor. Against those, "the ground truth
comes from the Veltro model" means "the ground truth is Veltro's answer", and
every disagreement is scored as the competitor's error. Four concrete ways that
bite, all measured on what this repository ships today:

**(a) The current test is taking place on home turf:** the answers the test
considers "right" are created only with Veltro's rules and model. So anyone who
adopts a different approach could be punished simply for reasoning differently,
and not because they are in the wrong

**(b) Different choices:** Veltro automatically infers some type relations from
data types. If another tool (like `graphify`) chooses to be more accurate by not
making that inference, the test will still flag it as an error

**(c) The questions are rigged from the start:** a lot of questions ask for
specific details about a class (public methods, fields, and so on). Other tools
do not record that information, by choice: asking such questions means already
knowing that they will fail

**(d) Veltro's weak points are hidden:** the test asks only about the elements
Veltro can see. If Veltro has a blind spot (for instance, it does not see
module-level Python functions, as happened with its own code), the test will
never ask questions about those functions. Another tool that does see them,
however, will receive no credit

None of this makes the published diagram numbers wrong. It makes them unusable
as a template for the comparison issue #12 asks for.

---

## 2. Three rules that make the comparison mean something

**R1 - Ground truth comes from source code, not from Veltro:** correct answers must 
be determined by an independent "oracle" reading the raw code. If Veltro disagrees with the 
oracle, it represents a flaw in Veltro—which is the whole point of running the test

**R2 - Questions are sampled from the codebase, not Veltro's nodes:** test targets must be drawn 
from the full source code (including functions, not just classes). Veltro will score zero on 
functions, but publishing this known blind spot is more honest and useful than hiding it

**R3 - Fair evaluation in fixed-budget tests:** in limited-size tests, no tool should see the 
question before producing its output slice. Otherwise, Veltro's built-in filtering would give it 
an unfair advantage, testing its retrieval mechanism rather than the format itself

**Extra Rule - Mark missing data as "absent", not "wrong":** If a tool cannot physically express 
certain details (like ctags lacking field types), it must be scored as absent rather than incorrect. 
Lacking a feature is not the same as giving a wrong answer

---

## 3. Two experiments, deliberately not one

Mixing these is how the comparison gets rigged in one direction or the other.

### E1 - What does one context window of architecture buy?

One API call per question. Every subject is truncated to the same budget `B`,
question-agnostically (R3), and the model answers from that text alone.

| subject | the `B` tokens it gets |
|---|---|
| `veltro` | the `.vel`, globally budgeted |
| `source` | whole source files, largest-first until `B` (a realistic agent slice) |
| `repomap` | an Aider-style tree-sitter + PageRank repo map, truncated |
| `ctags` | `ctags -R` output, truncated (flags recorded, not assumed) |
| `outline` | tree-sitter declaration outlines, truncated |
| `graphify` | a budgeted serialisation of `graph.json` (plus `GRAPH_REPORT.md`) |

Budgets: `B` = 4k, 16k, 64k tokens, `o200k_base`, measured not estimated (the
existing `--budget` machinery refuses an estimate for a reason: `chars / 4` is
off by up to +55% on real slices).

**What E1 does not measure, and the report must say so:** graphify is not built
to be pasted into a context. Its design is a graph you query. Putting it in E1
measures its serialisation, which is the fairest thing that can be done to it
inside a format arm, and it is not the thing it is good at.

### E2 - What does an answer cost when each tool is used as intended?

The same questions, but the model gets tools instead of a text dump, runs a
real agentic loop, and we count every token the session spent, not the
subject's size.

| arm | what the model can call |
|---|---|
| `grep` | plain file search + read (the baseline every coding agent is) |
| `veltro` | `veltro map/find/show/deps` over a pre-built `.vel` + index |
| `graphify` | `graphify query/explain/path` over a pre-built `graph.json` |

Two numbers per arm: accuracy, and tokens-to-answer. This is the experiment that
answers issue #12's actual complaint, it is the one that justifies the MCP
server the issue proposes, and it is the expensive one, so it runs last, after
E1 has been read.

---

## 4. The question families, pre-declared

Each row says where truth comes from and which subjects can express an answer at
all. Declared now, so that a family cannot be dropped later because it
embarrassed someone.

| family | question | oracle | expressible in |
|---|---|---|---|
| `inherits` | what does `X` extend or implement? | `ast` bases | all |
| `implementors` | what extends or implements `X`? | `ast`, repo-wide | all |
| `defined_in` | which file is `X` declared in? | `ast` + path | all |
| `members` | how many public methods does `X` declare? | `ast`, name-mangling rules | veltro, source, graphify, outline |
| `field_types` | which fields of `X` hold a collection? | `ast` annotations | veltro, source |
| `functions` | what does the module-level function `f` take and return? | `ast` signature | source, graphify, outline, ctags |
| `callers` | what calls `f`? | `ast` call sites | source, graphify |

The last two exist to measure the blind spot from the outside. `field_types`
stays even though only two subjects can express it, because a question only
Veltro and the raw source can answer is still a true statement about what the
format carries - as long as the others are scored absent rather than wrong.

**Scoring:** per item, exact match for scalars, precision / recall / F1 for
lists, reported separately so a recall-rich tool is not punished by set
equality. Three outcomes, never two: correct, wrong, absent. The scorer stays
deterministic, no LLM judge, which is the one methodological advantage this
harness already has over every benchmark it will be compared to, and it is not
being given up.

**What is not compared:** graphify publishes its own benchmark numbers (LOCOMO,
LongMemEval, a grep/read baseline). Those were produced on its harness with its
question design, and quoting them next to numbers from this harness would
compare two question sets, not two tools. Either both run here, or there is no
comparison.

---

## 5. Pre-registered expectations, and what would kill the claim

Written before the run so that whatever happens is a result rather than a story.

1. **E1, structural questions, low `B`:** Veltro leads per token. Its whole
   design is omitting what a structural question does not need
2. **E1, high `B`:** the gap narrows and `source` catches up, because at 64k the
   raw files start to fit and they contain everything
3. **`functions` and `callers`:** Veltro scores at or near zero. Expected, and
   the honest headline is "Veltro is a type-graph layer", not "Veltro replaces
   reading the code"
4. **E2:** the ordering is genuinely unknown. A queryable graph with an agent
   interface may well beat a budgeted dump, and graphify has had far more
   engineering aimed at exactly that

**Kill criteria - the results that change the README rather than decorate it:**

- if `source` matches Veltro at every budget, the format's claim is not
  compression of architecture and the headline must change
- if a repo map or graphify wins per token on the structural families, the value
  of this project is in the viewer, the extractors and the `file:line` index,
  not in the format, and it should be said in that order
- if Veltro's answers disagree with the `ast` oracle anywhere, that is an
  extractor bug and it is fixed before anything is published

---

## 6. Order of work

1. `eval/oracle.py` - the source-of-truth answerer, with its own unit tests
   (free)
2. regenerate the question set under R1 and R2, and report how much the set
   changes (free, and it is the first evidence this document was needed)
3. the E1 subject builders: `source`, `ctags`, `outline`, `repomap`, `graphify`
   (free, each one's command is recorded so the slice can be rebuilt)
4. E1 on one project, one cheap model, to shake out the harness (small spend)
5. E1 across projects and model tiers (the sweep)
6. E2 (the expensive arm), last

Steps 1-3 are the ones that decide whether the numbers mean anything, and they
cost nothing but time.
