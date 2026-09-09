# Veltro - LLM comprehension eval

**Status: built and run** (OpenAI + Anthropic APIs), four model tiers, four
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
  generate.py          model -> subjects/<name>/<name>.{vel,mmd,puml,d2} + .questions.json (ground truth)
  run.py               ask via paid API (--provider openai|anthropic, --repeat N)
  score.py             score answers vs ground truth, grouped by (provider, model); --save -> CSV
  report.py            leaderboard.csv -> subjects/<name>/REPORT.md (format x system pivots)
  plot_hero.py         leaderboard.csv -> images/comprehension_vs_tokens{,-dark}.{svg,png} (README hero)
  leaderboard.csv      the editable, version-controlled results dataset (all projects)
  subjects/<name>/     per project: the rendered diagrams + questions + generated REPORT.md
    <name>.{vel,mmd,puml,d2}   the same model rendered in each format (the subjects shown to the LLM)
    <name>.questions.json      the structural questions + ground-truth answers
    REPORT.md                  the per-project leaderboard (token cost + exact% + F1, format x model)
  results/             raw model answers + token usage, one JSON per project x format x model
                       (re-scoreable offline, so a run can be audited without re-querying)
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

Across model tiers (gpt-4.1-mini, gpt-5.4-mini, Sonnet, Opus) and four languages
(Python, Java, C#, TypeScript) the accuracy ranking shuffles by model and the
formats land in overlapping bands: with n=5 error bars, Veltro / Mermaid /
PlantUML / D2 are statistically tied. There is no robust comprehension
winner. The durable, deterministic result is token cost: Veltro is the
cheapest. So the defensible claim is *"fewer tokens at comparable comprehension"*,
not *"Veltro is understood better"*. See each project's `subjects/<name>/REPORT.md`.

**The one honest caveat**: on the strictest metric (exact set-match) Veltro can
trail by a few points on a weak model. The gap closes on a capable model and
under partial-credit (F1) scoring.

This used to be explained by the `rel` block making a type's relations "less
local". That explanation was wrong and has been withdrawn, the subjects
contradict it. Every format puts its relations in a trailing block, because the
Mermaid, PlantUML and D2 subjects are rendered by Veltro's own exporters, which
append edges after the last type:

| subject | veltro | mermaid | plantuml | d2 |
|---------|--------|---------|----------|-----|
| pydantic | 87% | 89% | 89% | 90% |
| nest | 96% | 97% | 96% | 96% |
| spring-beans | 93% | 93% | 93% | 94% |
| MediatR | 88% | 90% | 90% | 91% |

(position of the first relation line in the file). Locality is identical, so it
cannot be what separates them.

What the saved answers actually show, via
[`error_profile.py`](error_profile.py) - offline, no API calls:

- **The gap is not one phenomenon**, and it is not always about relations. On
  nest (-0.15 vs PlantUML on gpt-4.1-mini) the largest contributor is
  `public_method_count`, 65% of it, while Veltro leads on `depends_on`
  (0.32 vs 0.10). On pydantic and spring-beans the relation questions do
  dominate (89% and 69%).
- **Edge direction is not the cause.** Veltro writes child-first
  (`Color extend Representation`) where PlantUML writes parent-first, so a model
  that inverted it would lose exactly these questions. It does not: across all
  four subjects Veltro's wrong relation answers contain 10 reversed names on
  gpt-4.1-mini and zero on Opus. The only notable count anywhere belongs to
  PlantUML (15, on pydantic).
- **One mechanism is confirmed, and it is the direct price of the compression.**
  Nest's four lost counting questions are all types whose only method is a
  constructor. Veltro writes it unmarked, because public is implicit:
  `BadGatewayException(objectOrError any?, descriptionOrOptions Any)`. Mermaid
  and PlantUML write `+` in front of the same line. The model answers 0 on
  Veltro and 1 on the other three. The legend in `run.py` does state the rule
  ("a member line with no marker is public"), so this is not an eval bug: a rule
  given once at the top of a prompt is weaker, for a small model, than a symbol
  repeated on every line. The redundant markers Veltro deletes to save tokens
  are also scaffolding a weak reader leans on.

That last point is the honest form of the caveat: the exact-match gap is not a
side effect of where relations sit, it is partly what compression costs. It
disappears on a model strong enough not to need the scaffolding, on Opus,
spring-beans has Veltro at 0.76 against Mermaid 0.70 and PlantUML 0.69.

Reproduce all of it:

```bash
python eval/error_profile.py                       # all four subjects
python eval/error_profile.py --project nest        # just one
python eval/error_profile.py --model anthropic-claude-opus-4-8
```

**A note on the playing field**: The model has seen vast amounts of PlantUML and
Mermaid in training and none of Veltro, it reads Veltro only from the
one-paragraph legend in `run.py`, while the others enjoy a home-field advantage.
Reaching parity despite that handicap is the real result. Familiarity (few-shot
examples, or fine-tuning) would plausibly lift Veltro further, but we have not
measured this and make no claim about it.

## The hero chart

`images/comprehension_vs_tokens{,-dark}.{svg,png}` (shown on the repo front page)
is generated from `leaderboard.csv` by `plot_hero.py`: each point is a
(format, repo) pair, x = tokens relative to Veltro (Veltro = 1.0x per repo),
y = list F1 on Opus. Veltro lands on the 1.0x line with every other format to its
right at a comparable height: same comprehension, fewer tokens.

```bash
python eval/plot_hero.py            # both light and dark themes -> images/
```
