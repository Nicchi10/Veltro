# Veltro

> *<<...verrà 'l veltro / che la farà morir con doglia.>>* - Dante, *Inferno* I

**Veltro** is a compact, AI-native language for documenting the static
architecture of a codebase as a graph of types and a 'buoyant' viewer
that makes that graph navigable at any scale.

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
- **Modular**: modules nest and split across files, the model is their union
- **Projectable**: every diagram is a query over the graph, computed by the viewer

## Dual mandate 

1. **Primary**: read `.vel` natively, at full power, optimized for AI authoring
2. **Secondary**: act as a gorgeous viewer for imported **PlantUML / UML**, via
   an adapter that maps them onto the same internal graph

One viewer, two citizens: one first-class, one luxury guest.

## Token efficiency (measured, not promised)

Real architecture (consolidated `z_Loom`), vs its PlantUML source
(`o200k_base` tokenizer):

| diagram | PlantUML | Veltro | saved |
|---------|----------|--------|-------|
| `z_Loom` (consolidated) | 1634 | 1056 | **-35.4%** |

And against every other class-diagram format, on a representative slice
(`bench/compare_formats.py`, lower = denser):

| rank | format | tokens | vs Veltro |
|------|--------|--------|-----------|
| 1 | **Veltro** | **237** | - |
| 2 | yUML | 259 | +9% |
| 3 | Nomnoml | 281 | +19% |
| 4 | PlantUML | 334 | +41% |
| 5 | Mermaid | 347 | +46% |
| 6 | D2 | 365 | +54% |
| 7 | Graphviz DOT | 470 | +98% |

Veltro is the densest format measured, and it gets there **without** throwing
away readability: it keeps one member per line (clean git diffs), modules, and
the type-graph model, while the runners-up (yUML, Nomnoml) collapse each type
onto a single unreadable line to compete.

Reproduce with `python bench/token_bench.py` and `python bench/compare_formats.py`
(PlantUML source vendored in `bench/z_Loom.puml`).

> The example architecture is the real [**Loom**](https://github.com/Nicchi10/Loom)
> framework. Its PlantUML diagrams are the source of truth this `.vel` was ported
> from.

## Status

`v0` - founding artifacts:

| File | Role |
|------|------|
| [`SPEC.md`](SPEC.md) | The `.vel` grammar + relation-kind -> UML mapping |
| [`model.schema.json`](model.schema.json) | The intermediate type-graph schema (single source of truth) |
| [`examples/z_Loom.vel`](examples/z_Loom.vel) | Full consolidated architecture (Core+Engine+Providers), ported from the [Loom](https://github.com/Nicchi10/Loom) repo |

## Roadmap

- [ ] `parser` - `.vel` -> `model.schema.json` (TypeScript)
- [ ] `viewer` - WebGL graph, semantic zoom, click-to-highlight (TypeScript)
- [ ] `adapter-plantuml` - PlantUML -> graph
- [ ] `serializer` - graph -> canonical `.vel` (round-trip guarantee)
- [ ] `export-plantuml` - graph -> PlantUML (Rosetta, the other way)

## Stack

TypeScript end to end, viewer renders on Canvas/WebGL (not SVG/DOM it dies past
a few thousand nodes) with a force-directed engine and stable, remembered layout.
