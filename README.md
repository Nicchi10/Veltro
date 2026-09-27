<p align="center">
  <em>&lt;&lt;...verrà 'l veltro / che la farà morir con doglia.&gt;&gt;</em> - Dante, <em>Inferno</em> I
</p>

<p align="center">
  <img src="images/veltro.png" alt="Veltro - a compact, AI-native language for documenting the static architecture of a codebase as a graph of types" width="200" />
</p>

<h1 align="center">Veltro</h1>



<p align="center">
  <img src="https://img.shields.io/badge/v-0.1-ff5b00?labelColor=ff5b00" alt="version 0.1" />
</p>

<p align="center">
  <a href="https://github.com/Nicchi10/Veltro/actions/workflows/ci.yml"><img src="https://github.com/Nicchi10/Veltro/actions/workflows/ci.yml/badge.svg" alt="CI" /></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/input_used-19.9k_tokens-ff5b00" alt="Input used" />
  <img src="https://img.shields.io/badge/tokens_saved-17--31%25-ff5b00" alt="Tokens saved" />
  <a href="https://nicchi10.github.io/Veltro/"><img src="https://img.shields.io/badge/demo-live-ff5b00?labelColor=ff5b00" alt="Live demo - the Veltro Viewer" /></a>
</p>

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="images/comprehension_vs_tokens-dark.png" />
    <img alt="Same comprehension, fewer tokens: across pydantic (Python), spring (Java), MediatR (C#) and nest (TypeScript), Veltro reads as well as Mermaid, PlantUML and D2 (list F1 on Opus) while costing ~26% fewer tokens" src="images/comprehension_vs_tokens.png" width="720" />
  </picture>
</p>

<p align="center">
  <em>Reads as well as Mermaid / PlantUML / D2 (list F1, Opus) at the lowest token cost - on real Python, Java, C# and TypeScript codebases.</em>
</p>

---

**Veltro** is a compact, AI-native language for documenting the static
architecture of a codebase as a graph of types, plus a viewer that makes that
graph navigable at any scale.

The file is telegraphic on purpose, all the power lives in the viewer: click a
type and its relations, inheritance chain and dependents light up, the rest fades.

## Why

UML/PlantUML is great for drawing and terrible at scale: it mixes the model
(what exists), the layout (where it sits) and the view (what to show) in one
file, past a few dozen classes it collapses, and it is verbose and ambiguous to
feed to an LLM.

Veltro separates the three:

```
  .vel sources  --parse->  type graph (model.schema.json)  --project->  viewer
  (the truth)               (one truth, JSON)                 (queries, not drawings)
```

- **Compact**: token frugality first, spaces over punctuation, derived edges
- **Deterministic**: one canonical serialization, clean diffs, reliable AI round-trip
- **Modular**: modules split across files, the model is their union
- **Projectable**: every diagram is a query over the graph, computed by the viewer

## Dual mandate

1. **Primary**: read `.vel` natively, at full power, optimized for AI authoring
2. **Secondary**: act as a gorgeous viewer for imported **PlantUML / UML**, via an adapter that maps them onto the same internal graph

One viewer, two citizens: one first-class, one luxury guest.

## Token efficiency (measured, not promised)

The same architecture is extracted from real code, then rendered to Veltro,
PlantUML and Mermaid **from one identical model** (so the comparison is fair),
and counted with `tiktoken` (`o200k_base`).

On whole real projects, extracted then tokenised with one command per row
(`python bench/scale_bench.py <package-or-.vel>`): Python via the AST extractor,
Java via the [Java extractor](veltro/extract/java), C# via the
[tree-sitter extractor](veltro/extract/tree_sitter_csharp.py):

| project | language | types | Veltro | Mermaid | PlantUML |
|---------|----------|-------|--------|---------|----------|
| [Rich](https://github.com/Textualize/rich) | Python | 173 | 12,795 | +20% | +33% |
| [Pydantic](https://github.com/pydantic/pydantic) | Python | 360 | 20,168 | +20% | +30% |
| [Spring](https://github.com/spring-projects/spring-framework) (spring-beans) | Java | 323 | 41,463 | +22% | +34% |
| [Kafka](https://github.com/apache/kafka) (clients) | Java | 1,287 | 174,594 | +10% | +32% |
| [MediatR](https://github.com/jbogard/MediatR) | C# | 216 | 9,875 | +24% | +32% |
| [Orleans](https://github.com/dotnet/orleans) | C# | 6,055 | 687,997 | +18% | +26% |
| [NestJS](https://github.com/nestjs/nest) (packages) | TS | 599 | 39,236 | +32% | +36% |
| [Angular](https://github.com/angular/angular) (packages) | TS | 3,274 | 206,067 | +29% | +35% |

Every row but Rich is recomputed on each push by
[`bench/check_readme_table.py`](bench/check_readme_table.py) — a table nobody
re-measures goes stale in silence, and this one already had. Rich is the
exception because no `rich.vel` is committed, so reproducing it needs a checkout
of Rich itself.

The Java, C# and TypeScript rows are cross-language evidence: the token saving
holds on real Python, Java, C# and TypeScript code, not a single ecosystem, and
on Orleans it scales to **~6,000 types** without breaking down.

Against every other class-diagram format, on a representative slice of pydantic
(`python bench/compare_formats.py`, lower = denser):

| rank | format | tokens | vs Veltro |
|------|--------|--------|-----------|
| 1 | **Veltro** | **211** | - |
| 2 | yUML | 213 | +1% |
| 3 | Nomnoml | 222 | +5% |
| 4 | Mermaid | 261 | +24% |
| 5 | D2 | 304 | +44% |
| 6 | PlantUML | 332 | +57% |
| 7 | Graphviz DOT | 352 | +67% |

Veltro is the densest format measured, and it gets there **without** throwing
away readability: it keeps one member per line (clean git diffs), modules, and
the type-graph model, while the runners-up (yUML, Nomnoml) collapse each type
onto a single unreadable line to compete.

## From a repository to a map, in one command

```bash
pip install "veltro[extract]"
veltro extract .
```

```
[INFO] - found: java (1 files), python (33 files), typescript (2 files)
[INFO] - python: 33 files, 1 types
[INFO] - typescript: 2 files, 7 types
[INFO] - 8 types, 2 relations
[INFO] - written: Veltro.vel
[INFO] - source index: Veltro.index.json  (8 types)
[WARN] - 1 java files were found but not read: the Java extractor is a standalone Java program
[WARN] - only 8 types in 35 files: Veltro models TYPES, so a repository built out of free functions gives it little to describe
```

One command, every language in the repository, **one** `.vel` and **one** source
index mapping each type back to `file:line`. Virtualenvs, `node_modules`, build
output and tests are pruned, and it prints what it skipped.

Both warnings above are Veltro describing *itself*, and both are true. A
language it found but could not read is named with the command that fixes it,
because silence would read as "that language is not here". And when a codebase
is built out of free functions rather than types, it says so instead of handing
you an empty map: that is the format's blind spot, and you should learn it in
the first thirty seconds, not the first afternoon.

## Query it, don't read it

Being the cheapest format is not enough at scale. `examples/Orleans.vel` is
6,055 types and **687,997 tokens**: no compression ratio turns that into
something you paste into a prompt. So the CLI answers a question with a
bounded payload instead of handing over the file.

```bash
python -m veltro find  examples/pydantic.vel Encoder          # which types are there
python -m veltro show  examples/pydantic.vel Base64Encoder    # one type, as .vel
python -m veltro deps  examples/pydantic.vel Base64Encoder    # what it touches, what touches it
python -m veltro map   examples/Orleans.vel --around Silo --depth 1   # a slice of the graph
python -m veltro map   examples/Orleans.vel --around Silo --budget 2000  # as much as fits
```

Measured on Orleans, against reading the whole file
(`python bench/query_cost.py`):

| command | tokens | share of the file |
|---------|--------|-------------------|
| `map --module Orleans.Runtime` | 86,718 | 12.60% |
| `map --around Silo --depth 1` | 4,629 | **0.67%** |
| `show Silo` | 945 | **0.14%** |
| `deps Silo` | 163 | **0.02%** |

`show` and `map` print valid `.vel`, so a slice goes straight back into a
prompt. `map --budget N` is the one an agent wants: it walks outward from a
type and stops at the last one that still fits in N tokens, nearest first. It
needs a real tokenizer and refuses without one, because a measured `chars / 4`
estimate is off by up to +55% on real slices and a budget that can overshoot by
half is not a budget. A bare name that means two types is refused, with the candidates
listed, rather than silently answered about the wrong one. And with the source
index the extractor writes beside the `.vel`, `show --code` prints the
declaration's actual source.

**Full reference: [`CLI.md`](CLI.md)** - every command, every option, the source
index, and how to call the same logic from Python (it is pure functions in
[`veltro/query.py`](veltro/query.py), so the viewer and any future editor
plugin reuse it rather than reimplement it).

## Comprehension (does the model still understand it?)

Fewer tokens are worthless if the model reads the diagram worse. So we test it:
50 structural questions whose answers are facts derived from the type graph
(automatic, deterministic scoring), asked of the same architecture rendered in
each format, across several model tiers and four languages (Python, Java, C#, TS).

The honest result: there is **no robust comprehension winner** - the ranking
shuffles by model and the formats sit in overlapping bands. Veltro reads **as
well** as PlantUML / Mermaid / D2 (matched on partial-credit F1) at the lowest
token cost, we claim parity, not superiority. On the strict exact-match metric it
can trail a few points on a weak model, and that closes on a capable one. We used
to blame the distant `rel` block for it; measuring the subjects killed that
explanation (every format puts relations at 87-96% of the file) and pointed at
something more interesting: part of the gap is the price of the compression
itself, because the redundant `+` markers Veltro deletes are also cues a weak
reader leans on. The evidence is in
[`eval/error_profile.py`](eval/error_profile.py).

The full methodology, the per-language results, the honest caveats (and the
home-field handicap Veltro reads under) and how to reproduce them all live in
**[`eval/README.md`](eval/README.md)**, with a per-project report for each
codebase (e.g. [`eval/subjects/pydantic/REPORT.md`](eval/subjects/pydantic/REPORT.md)).

### Reproduce it

> Note: the repo has many separate "test sections", so the dependencies are split
> into extras. Reading a `.vel` (parse / find / show / deps / map / export) needs
> only `jsonschema`; the commands below need `[bench]`, and the eval needs
> `[eval]`. `pip install -r requirements.txt` still installs everything

```bash
pip install -e ".[bench]"        # or: pip install -e .          (core only)
                                 # or: pip install -e ".[dev]"   (everything)

# 1. whole-project comparison (Veltro vs PlantUML vs Mermaid), all from one model
python bench/scale_bench.py path/to/some/package

# 2. the 7-format ranking on the bundled pydantic slice
python bench/compare_formats.py

# 3. just extract a Python package to .vel (writes the source index beside it)
python -m veltro.extract.python_ast path/to/some/package --out build/out.vel
#    virtualenvs, caches, build output and tests are pruned; it says what it skipped --exclude GLOB to skip more, --include-tests to keep the tests

# 4. what a bounded answer costs against reading the whole graph
python bench/query_cost.py
```

The comprehension eval (generate -> ask a model -> score -> leaderboard) has its
own quickstart in [`eval/README.md`](eval/README.md).

The examples are not hand-written: they are extracted from real projects
(Rich, Pydantic) with the AST extractor, so the numbers are not cherry-picked.

## Repository layout

```
veltro/                        the Python package
  |--- parser.py               .vel  ->  type-graph model (the ONE parser, format is language-agnostic)
  |--- query.py                find / show / deps / map, as pure functions the CLI and the viewer share
  |--- index.py                the sidecar: every type id -> the file:line it is declared at
  |--- __main__.py             the command line (see CLI.md)
  |--- export/                 model  ->  PlantUML / Mermaid / D2 (fair benchmarking, the Rosetta way out)
  |--- extract/                repository -> .vel file (cover more languages)
  |     |--- project.py        a whole repo -> ONE .vel + ONE index, every language at once
  |     |--- walk.py           which files an extractor may read, shared by all of them
  |--- schemas/                the type-graph contract (nodes + edges) shared by every piece
SPEC.md                        the .vel language specification
CLI.md                         the command line reference
pyproject.toml                 the package: a one-dependency core, plus extras per section
docs/                          the built viewer, published as the live demo (GitHub Pages)
examples/                      real architectures extracted to .vel (e.g. pydantic.vel)
bench/                         token benchmarks + the vendored PlantUML sample
  |--- formats/                the same slice encoded in 7 formats, for the ranking
  |--- check_readme_table.py   recompute the README token table, fail if it drifted
  |--- query_cost.py           what a bounded answer costs against reading the whole .vel
.github/workflows/ci.yml       core install on 3.9/3.13 + Windows, extras, conformance, the table
eval/                          LLM comprehension eval: generate/run/score/report (see eval/README.md)
  |--- leaderboard.csv         the editable results dataset -> per-project subjects/<name>/REPORT.md 
  |--- results/                a .json for each repo and the responses to the questions
  |--- subjects/               the rendered diagrams (vel/puml/mmd/d2) + questions.json + REPORT.md
tests/                         unit tests (parser, extractor, exporters, scorer)
conformance/                   the parser rules for every parser implementations
grammars/                      the canonical, editor-agnostic definition of how Veltro source is tokenised for colour
```

The funnel: many extractors feed one format, and from there everything is single.

```
extract_python |
extract_ts     |--> .vel --> parser (1) --> model (1) --> viewer (1)
extract_java   |
```

## Status

`v0.1` - working today:

| Piece | Role |
|-------|------|
| [`SPEC.md`](SPEC.md) | The `.vel` grammar + relation-kind -> UML mapping |
| [`CLI.md`](CLI.md) | The command line: `extract` / `parse` / `find` / `show` / `deps` / `map` |
| [`veltro/schemas/model.schema.json`](veltro/schemas/model.schema.json) | The intermediate type-graph schema (single source of truth) |
| [`veltro/parser.py`](veltro/parser.py) | `.vel` -> model, with schema validation |
| [`veltro/extract/python_ast.py`](veltro/extract/python_ast.py) | Python source -> `.vel` (deterministic, no LLM) |
| [`veltro/extract/tree_sitter_csharp.py`](veltro/extract/tree_sitter_csharp.py) | C# source -> `.vel` (deterministic, no LLM) |
| [`veltro/extract/java/VeltroJavaExtractor.java`](veltro/extract/java/VeltroJavaExtractor.java) | Java source -> `.vel` (deterministic, no LLM) |
| [`veltro/query.py`](veltro/query.py) | find / show / deps / map, as pure functions over model + index |
| [`veltro/index.py`](veltro/index.py) | the sidecar mapping every type back to `file:line` |
| [`veltro/export/`](veltro/export) | model -> PlantUML / Mermaid / D2 |
| [`examples/pydantic.vel`](examples/pydantic.vel) | Pydantic's architecture, extracted to `.vel` |
| [`eval/`](eval) | comprehension eval (OpenAI / Anthropic APIs) + token/accuracy leaderboard |
| [`docs/`](docs) | the viewer, built and published [live demo](https://nicchi10.github.io/Veltro/) |

## Roadmap

- [x] **LLM comprehension eval** built and run (OpenAI + Anthropic APIs + Ollama...),
      across multiple models, n languages and four formats. Result so far: comparable
      comprehension, fewer tokens. See [`eval/`](eval)
- [x] **Java extractor** (Kafka, Spring) so people lick their fingers
- [x] **C# extractor** (MediatR, Orleans) via tree-sitter
- [x] **JS/TS extractor** to complete the picture
- [ ] **few-shot test** If the LLM knew Veltro, would it be more accurate?
- [ ] **VS Code extension** (and other IDEs) once the gain is clear
- [ ] **Parser in TypeScript** (the reference parser is Python today)
- [x] **The viewer**: [live demo](https://nicchi10.github.io/Veltro/) - Canvas2D
      graph, semantic zoom, click-to-highlight
- [ ] **PlantUML / Mermaid -> Veltro** translator (the inbound Rosetta direction)

## Stack

The language tooling (parser, extractor, exporters, benchmarks) is **Python**,
standard library only at runtime. The viewer is **TypeScript** on Canvas2D (not
SVG/DOM, which dies past a few thousand nodes), with the layout computed off the
main thread in a Web Worker by a high-dimensional embedding, deterministic, so
the same model always lands in the same shape, and remembered per model.
WebGL is the escape hatch if a model ever outgrows Canvas2D: at the ~7,800 nodes
of the largest model measured, it has not.
