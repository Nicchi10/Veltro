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
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT License" /></a>
  <img src="https://img.shields.io/badge/input_used-19.9k_tokens-ff5b00" alt="Input used" />
  <img src="https://img.shields.io/badge/tokens_saved-17--31%25-ff5b00" alt="Tokens saved" />
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
| [Rich](https://github.com/Textualize/rich) | Python | 173 | 12,792 | +20% | +33% |
| [Pydantic](https://github.com/pydantic/pydantic) | Python | 360 | 19,885 | +22% | +32% |
| [Spring](https://github.com/spring-projects/spring-framework) (spring-beans) | Java | 323 | 41,463 | +22% | +34% |
| [Kafka](https://github.com/apache/kafka) (clients) | Java | 1,287 | 174,594 | +13% | +32% |
| [MediatR](https://github.com/jbogard/MediatR) | C# | 220 | 8,770 | +30% | +36% |
| [Orleans](https://github.com/dotnet/orleans) | C# | 7,848 | 688,081 | +21% | +27% |
| [NestJS](https://github.com/nestjs/nest) | TS | 1,879 | 65,958 | +33% | +38% |
| [Angular](https://github.com/angular/angular) | TS | 17,670 | 427,431 | +30% | +37% |

The Java and C# rows are cross-language evidence: the token saving holds on real
Python, Java and C# code, not a single ecosystem and on Orleans it scales to
**~7,800 types** without breaking down.

Against every other class-diagram format, on a representative slice of pydantic
(`python bench/compare_formats.py`, lower = denser):

| rank | format | tokens | vs Veltro |
|------|--------|--------|-----------|
| 1 | **Veltro** | **211** | - |
| 2 | yUML | 213 | +1% |
| 3 | Nomnoml | 222 | +5% |
| 4 | Mermaid | 254 | +20% |
| 5 | D2 | 273 | +29% |
| 6 | PlantUML | 332 | +57% |
| 7 | Graphviz DOT | 352 | +67% |

Veltro is the densest format measured, and it gets there **without** throwing
away readability: it keeps one member per line (clean git diffs), modules, and
the type-graph model, while the runners-up (yUML, Nomnoml) collapse each type
onto a single unreadable line to compete.

## Comprehension (does the model still understand it?)

Fewer tokens are worthless if the model reads the diagram worse. So we test it:
50 structural questions whose answers are facts derived from the type graph
(automatic, deterministic scoring), asked of the same architecture rendered in
each format, across several model tiers and four languages (Python, Java, C#, TS).

The honest result: there is **no robust comprehension winner** - the ranking
shuffles by model and the formats sit in overlapping bands. Veltro reads **as
well** as PlantUML / Mermaid / D2 (matched on partial-credit F1) at the lowest
token cost, we claim parity, not superiority. On the strict exact-match metric it
can trail a few points (the flip side of factoring relations into a distant
`rel` block), and that closes on a capable model.

The full methodology, the per-language results, the honest caveats (and the
home-field handicap Veltro reads under) and how to reproduce them all live in
**[`eval/README.md`](eval/README.md)**, with a per-project report for each
codebase (e.g. [`eval/subjects/pydantic/REPORT.md`](eval/subjects/pydantic/REPORT.md)).

### Reproduce it

```bash
pip install -r requirements.txt

# 1. whole-project comparison (Veltro vs PlantUML vs Mermaid), all from one model
python bench/scale_bench.py path/to/some/package

# 2. the 7-format ranking on the bundled pydantic slice
python bench/compare_formats.py

# 3. just extract a Python package to .vel
python -m veltro.extract.python_ast path/to/some/package --out build/out.vel
```

The comprehension eval (generate -> ask a model -> score -> leaderboard) has its
own quickstart in [`eval/README.md`](eval/README.md).

The examples are not hand-written: they are extracted from real projects
(Rich, Pydantic) with the AST extractor, so the numbers are not cherry-picked.

## Repository layout

```
veltro/                        the Python package
  |--- parser.py               .vel  ->  type-graph model (the ONE parser, format is language-agnostic)
  |--- export/                 model  ->  PlantUML / Mermaid / D2 (fair benchmarking, the Rosetta way out)
  |--- extract/                repository -> .vel file (cover more languages)
model.schema.json              the type-graph contract (nodes + edges) shared by every piece
SPEC.md                        the .vel language specification
examples/                      real architectures extracted to .vel (e.g. pydantic.vel)
bench/                         token benchmarks + the vendored PlantUML sample
  |--- formats/                the same slice encoded in 7 formats, for the ranking
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
| [`model.schema.json`](model.schema.json) | The intermediate type-graph schema (single source of truth) |
| [`veltro/parser.py`](veltro/parser.py) | `.vel` -> model, with schema validation |
| [`veltro/extract/python_ast.py`](veltro/extract/python_ast.py) | Python source -> `.vel` (deterministic, no LLM) |
| [`veltro/extract/tree_sitter_csharp.py`](veltro/extract/tree_sitter_csharp.py) | C# source -> `.vel` (deterministic, no LLM) |
| [`veltro/extract/java/VeltroJavaExtractor.java`](veltro/extract/java/VeltroJavaExtractor.java) | Java source -> `.vel` (deterministic, no LLM) |
| [`veltro/export/`](veltro/export) | model -> PlantUML / Mermaid / D2 |
| [`examples/pydantic.vel`](examples/pydantic.vel) | Pydantic's architecture, extracted to `.vel` |
| [`eval/`](eval) | comprehension eval (OpenAI / Anthropic APIs) + token/accuracy leaderboard |

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
- [ ] **The viewer**: WebGL graph, semantic zoom, click-to-highlight
- [ ] **PlantUML / Mermaid -> Veltro** translator (the inbound Rosetta direction)

## Stack

The language tooling (parser, extractor, exporters, benchmarks) is **Python**,
standard library only at runtime. The viewer will be **TypeScript** on
Canvas/WebGL (not SVG/DOM, which dies past a few thousand nodes) with a
force-directed engine and a stable, remembered layout.
