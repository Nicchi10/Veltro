# Veltro - LLM comprehension eval

**Status: planned (scaffolding).** This folder defines how we will prove the
claim that matters most and is still unproven: that an LLM understands a
`.vel` description at least as well as the same architecture in Mermaid or
PlantUML, at fewer tokens.

Token count alone only proves Veltro is cheaper. This eval is what turns
"cheaper" into "cheaper and at least as accurate" a defensible claim.

## The idea

The trick is that the ground truth comes from the model itself, so scoring
is automatic, deterministic and verifiable no human judging, no second LLM.

```
real project --extract--> model   --> Veltro   (.vel)   
                                  --> Mermaid  (.mmd)   --> ask the LLM the SAME questions
                                  --> PlantUML (.puml)               |
                                                                     v
                                  --> questions + correct answers   score accuracy per format,
                                      (generated FROM the model)     normalised by token cost
```

Because the questions and their answers are generated from the same `model`
(`model.schema.json`), the "correct answer" is a fact, not an opinion.

## Question types (all answerable from the graph)

- "Which types implement `X`?"  (edges, kind = impl/extend)
- "What does `Y` depend on?"     (outgoing edges, incl. derived associations)
- "Which fields of `Z` are collections?"  (field types with a generic wrapper)
- "Which module is `W` in?"      (node.module)
- "How many public methods does `V` have?"  (members + visibility)

## Planned layout

```
eval/
  README.md          this file (methodology)
  generate.py        model -> {questions.json with ground-truth answers}   (planned)
  run.py             ask an LLM each format, collect answers               (planned)
  score.py           compare answers to ground truth, report per-format    (planned)
  subjects/          the rendered .vel/.mmd/.puml under test                (planned)
  results/           raw model answers + scored tables                     (planned)
```

## How it will be run (and reproduced)

```bash
python eval/generate.py path/to/package      # build questions + ground truth
python eval/run.py        --model <id>        # query the LLM per format
python eval/score.py                          # accuracy per format, per token
```

Every step is deterministic except the LLM call itself, raw responses are saved
under `results/` so a run can be re-scored and audited without re-querying.

## What would make Veltro win here

Same or higher accuracy than Mermaid/PlantUML while spending ~20% fewer tokens.
If that holds, the pitch becomes: more architecture per token, understood just
as well.
