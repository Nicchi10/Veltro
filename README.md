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
| [MediatR](https://github.com/jbogard/MediatR) | C# | 220 | 8,529 | +30% | +37% |
| [Orleans](https://github.com/dotnet/orleans) | C# | 7,848 | 687,417 | +21% | +27% |

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
each format. Run across four model tiers (see [`eval/`](eval) and the generated
per-project report, e.g. [`eval/subjects/pydantic/REPORT.md`](eval/subjects/pydantic/REPORT.md)).

The honest result: the accuracy ranking shuffles by model and the formats
sit in overlapping bands, there is no robust comprehension winner. Which
is the point: **the token savings cost no measurable comprehension.** Veltro
reads as well as PlantUML/Mermaid/D2 while being the cheapest. We do not claim
"Veltro is understood better", only "as well, for fewer tokens".

### Reproduce it

```bash
pip install -r requirements.txt

# 1. whole-project comparison (Veltro vs PlantUML vs Mermaid), all from one model
python bench/scale_bench.py path/to/some/package

# 2. the 7-format ranking on the bundled pydantic slice
python bench/compare_formats.py

# 3. just extract a Python package to .vel
python -m veltro.extract.python_ast path/to/some/package --out build/out.vel

# 4. the comprehension eval (ground truth + ask a model + score -> leaderboard)
python eval/generate.py examples/pydantic.vel          # subjects + ground truth
python eval/run.py pydantic --provider openai           # answer via API (openai or anthropic)
python eval/score.py pydantic --save eval/leaderboard.csv
python eval/report.py                                   # -> eval/subjects/<project>/REPORT.md
```

The examples are not hand-written: they are **extracted from real projects**
(Rich, Pydantic) with the AST extractor, so the numbers are not cherry-picked.

## Repository layout

```
veltro/                   the Python package
  parser.py               .vel  ->  type-graph model (the ONE parser, format is language-agnostic)
  extract/python_ast.py   Python source  ->  .vel  (AST extractor; one per source language)
  export/                 model  ->  PlantUML / Mermaid / D2 (fair benchmarking, the Rosetta way out)
  __main__.py             CLI: parse a .vel, validate it, write the JSON model
model.schema.json         the type-graph contract (nodes + edges) shared by every piece
SPEC.md                   the .vel language specification
examples/                 real architectures extracted to .vel (e.g. pydantic.vel)
bench/                    token benchmarks + the vendored PlantUML sample
  formats/                the same slice encoded in 7 formats, for the ranking
eval/                     LLM comprehension eval: generate/run/score/report
  leaderboard.csv         the editable results dataset -> per-project subjects/<name>/REPORT.md (see eval/README.md)
tests/                    unit tests (parser, extractor, exporters, scorer)
```

The funnel: many extractors feed one format, and from there everything is single.

```
extract_python |
extract_ts     |--> .vel --> parser (1) --> model (1) --> viewer (1)
extract_java   |
```

## Status

`v0` - working today:

| Piece | Role |
|-------|------|
| [`SPEC.md`](SPEC.md) | The `.vel` grammar + relation-kind -> UML mapping |
| [`model.schema.json`](model.schema.json) | The intermediate type-graph schema (single source of truth) |
| [`veltro/parser.py`](veltro/parser.py) | `.vel` -> model, with schema validation |
| [`veltro/extract/python_ast.py`](veltro/extract/python_ast.py) | Python source -> `.vel` (deterministic, no LLM) |
| [`veltro/export/`](veltro/export) | model -> PlantUML / Mermaid / D2 |
| [`examples/pydantic.vel`](examples/pydantic.vel) | Pydantic's architecture, extracted to `.vel` |
| [`eval/`](eval) | comprehension eval (OpenAI / Anthropic APIs) + token/accuracy leaderboard |

## Roadmap

- [x] **LLM comprehension eval** built and run (OpenAI + Anthropic APIs),
      across four model tiers and four formats. Result so far: comparable
      comprehension, fewer tokens. See [`eval/`](eval)
- [ ] **Java extractor** (Kafka, Spring) so people lick their fingers
- [ ] **VS Code extension** (and other IDEs) once the gain is clear
- [ ] **Parser in TypeScript / Rust** (the reference parser is Python today)
- [ ] **The viewer**: WebGL graph, semantic zoom, click-to-highlight
- [ ] **PlantUML / Mermaid -> Veltro** translator (the inbound Rosetta direction)

## Stack

The language tooling (parser, extractor, exporters, benchmarks) is **Python**,
standard library only at runtime. The viewer will be **TypeScript** on
Canvas/WebGL (not SVG/DOM, which dies past a few thousand nodes) with a
force-directed engine and a stable, remembered layout.
