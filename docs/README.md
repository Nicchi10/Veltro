# Veltro Viewer - the demo

**[Open the live demo](https://nicchi10.github.io/Veltro/)**

Every diagram this shows is a query over the type graph, not a drawing.
Click a type: what it inherits, what it shapes, what it uses and who uses it
light up, the rest fades. Nothing is ever removed, so the map never jumps.

This folder is the whole thing: four files, no build step, no server-side
anything, zero runtime dependencies.

## Run it on your machine

Download this folder (see [Getting the files](#getting-the-files)), then serve
it over HTTP, any static server will do:

```bash
python -m http.server -d . 8000
```

```bash
npx serve .
```

Then open `http://localhost:8000`.

Opening `index.html` with a double click will not work: on a `file://` URL the
browser blocks both `fetch` and module workers, and the layout runs in one. It
has to be served.


## What you can do in it

| gesture | what it answers |
|---------|-----------------|
| click a type | focus: ancestry, descendants, relations, dependents, the rest fades |
| `/` | search types, ids, fields and methods, picking a hit flies the camera to it |
| shift-click a second type | the shortest path: how are these two even related? |
| **Filters** button | by module prefix, node kind, edge kind, and written-vs-derived relations |
| drag a node | move it out of the way to read what is under it |
| wheel / drag | zoom to cursor, pan. Zoom in far enough and types open into cards |
| drop a `.model.json` | load your own model instead of the demo |

The layout is computed once, off the main thread in a Web Worker, by a
high-dimensional embedding: deterministic, so the same model always lands in
the same shape, and remembered per model in `localStorage`, so reopening one
is instant. Nothing wobbles: there is no live simulation to wait out.

## The model on screen

A slice of **[Microsoft Orleans](https://github.com/dotnet/orleans)** (MIT):
`MessageCenter` and everything within three hops of it: the messaging core of
a silo.

| | |
|---|---|
| types | 186 (157 class, 27 interface, 2 enum) |
| relations | 377 (336 assoc, 32 impl, 9 extend) |
| modules | 32 |

It is a **verbatim subset** of Veltro's own parse of that public codebase:
nothing was renamed, invented or hand-authored, so what you see is what the
parser emits. The full parse, all 6,055 types, is
[`examples/Orleans.vel`](../examples/Orleans.vel), and you can reproduce it
yourself:

```bash
python -m veltro examples/Orleans.vel
```

## Bring your own model

The demo is just the model that ships with it. Parse anything you like and
drop the `.model.json` onto the page, it replaces the demo, and its layout
gets remembered too:

```bash
python -m veltro path/to/yours.vel
```

The model lands next to the source (or wherever `--out` points), and that file
is what you drag onto the page.

Extractors for Python, Java, C# and TypeScript live in the
[main README](../README.md), so you can go from a repository you have never
opened to a navigable map of it without writing a `.vel` file by hand.

## What is in this folder

```
index.html               the page (5 KB)
assets/index-*.js        the viewer (34 KB)
assets/worker-*.js       the layout worker (10 KB)
demo.model.json          the Orleans slice (440 KB)
```

About 500 KB in total, most of it the model. The bundle uses relative URLs, so
this folder runs unchanged from a domain root, from a subdirectory, or from a
laptop.

## Getting the files

- **Whole repository**: `git clone https://github.com/Nicchi10/Veltro`, the
  demo is in `docs/`
- **Just this folder**: `npx degit Nicchi10/Veltro/docs veltro-demo`
- **No git, no Node**: download the repository
  [as a zip](https://github.com/Nicchi10/Veltro/archive/refs/heads/main.zip)
  and keep the `docs/` folder

## Scale, honestly

The renderer is Canvas2D, not WebGL, and it holds the frame budget on the full
Orleans model: **2.0 ms frame work at p95, 0% dropped frames**, measured in a
real browser. WebGL stays on the roadmap, not on the critical path.

That run was made against a 7,848-node build of the model. The same file parses
to 6,055 nodes today, because repeated declarations of one type (C#
`partial class`) are now merged instead of each becoming its own node, so the
figure above is a ceiling measured under a heavier load rather than a reading of
what the demo renders now.

Two things this particular demo does not show, because 186 types are too few
to trigger them: the LOD-0 view, where whole modules collapse into single blobs
you can drill into (it needs ~600 types in view), and the dust-collapsing that
big real models need. 

Drop a large model on the page to see both.

## Build

Built from the `veltro-viewer` repository, commit `645ff09`. This folder is
compiled output: anything edited here is overwritten by the next build.

## License

MIT, like the rest of Veltro: the [`LICENSE`](LICENSE) in this folder is the
same one as [the repository's](../LICENSE), restated here so a copy of `docs/`
carries its terms with it. It covers the built viewer you are running.

The demo model is derived from [dotnet/orleans](https://github.com/dotnet/orleans),
MIT, Copyright (c) .NET Foundation and Contributors. It contains only the
public structure of that codebase (type, module and member names).
