# Veltro - LLM comprehension eval

**Status: built and run** (OpenAI API + Claude Code), four model tiers, four
formats. It exists to test the claim token count alone can't prove: that an LLM
understands a `.vel` diagram at least as well as the same architecture in
Mermaid / PlantUML / D2, while spending fewer tokens.

## The idea

The ground truth comes from the type-graph model itself, so scoring is
automatic, deterministic and verifiable, no human judging, no second LLM.

```
real project --extract--> model --> .vel / .mmd / .puml / .d2  --> ask a model the SAME questions
                                --> questions + correct answers --> score per format, vs token cost
                                    (generated FROM the model)
```

Because the questions and their answers are generated from the same `model`
(`model.schema.json`), the "correct answer" is a fact, not an opinion.

## Question types (all answerable from the graph)

- "Which types implement/extend `X`?"  (edges, kind = impl/extend)
- "What does `Y` reference or inherit?"  (outgoing edges)
- "Which module is `W` in?"  (node.module)
- "How many public methods does `V` declare?"  (members + visibility)
- "Which fields of `Z` have a generic/collection type?"  (field types)

## Layout

```
eval/
  README.md            this file (methodology)
  generate.py          model -> 4 subjects (.vel/.mmd/.puml/.d2) + questions.json (ground truth)
  run.py               ask via paid API (--provider openai|anthropic, --repeat N)
  score.py             score answers vs ground truth, grouped by (provider, model); --save -> CSV
  report.py            leaderboard.csv -> REPORT.md (format x system pivots)
  leaderboard.csv      the editable, version-controlled results dataset
  REPORT.md            the generated leaderboard
  subjects/            the rendered diagrams + questions under test
  results/             raw model answers + token usage (re-scoreable offline)
```

## How to run it

```bash
# 1. Build the subjects and ground-truth questions (deterministic, no LLM)
python eval/generate.py examples/pydantic.vel

# 2. Answer via a paid API (key from env: OPENAI_API_KEY / ANTHROPIC_API_KEY)
python eval/run.py pydantic --provider openai --repeat 5

# 3. Score (mean +/- std) and append to the leaderboard, then render
python eval/score.py pydantic --save eval/leaderboard.csv
python eval/report.py
```

Every step is deterministic except the LLM call; raw answers are saved under
`results/` so a run can be re-scored and audited without re-querying.

## The honest finding (so far)

Across four model tiers the accuracy ranking shuffles by model and the
formats land in overlapping bands (with n=5 error bars, Veltro / Mermaid /
PlantUML / D2 are statistically tied). There is no robust comprehension
winner. The durable, deterministic result is token cost: Veltro is the
cheapest. So the defensible claim is "fewer tokens at comparable
comprehension", not "Veltro is understood better". See `REPORT.md`.
