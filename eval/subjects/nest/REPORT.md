# Veltro eval leaderboard - nest

Generated from `eval/leaderboard.csv` by `eval/report.py`. Columns are model (provider): all runs are via paid API (OpenAI / Anthropic). Compare formats within a column.

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format, API runs only)

| format | tokens | vs Veltro |
|---|---|---|
| veltro | 38215 | - |
| mermaid | 50393 | +32% |
| plantuml | 52209 | +37% |
| d2 | 56155 | +47% |

### Exact accuracy (mean +/- std)

| format | gpt-4.1-mini (openai) | claude-opus-4-8 (anthropic) |
|---|---|---|
| veltro | 60+/-4%* | 85+/-6%* |
| mermaid | 71+/-2% | 85+/-4% |
| plantuml | 75+/-5% | 96% |
| d2 | 70+/-2% | 86% |

### List-question F1 (mean +/- std)

| format | gpt-4.1-mini (openai) | claude-opus-4-8 (anthropic) |
|---|---|---|
| veltro | 0.65+/-0.06* | 0.90+/-0.05* |
| mermaid | 0.64+/-0.11 | 0.90+/-0.10 |
| plantuml | 0.68+/-0.06 | 0.95 |
| d2 | 0.65+/-0.06 | 0.72 |

Legend: `-` = combination not tested (not a zero). `*` = Veltro run with the **corrected prompt legend** (a typed field/parameter is declared an association, as in UML, and `<from> <kind> <to>` reads from = subtype, to = supertype), which fixes a bias that suppressed `depends_on` on field-derived dependencies. Because of this, nest's Veltro numbers are **not** directly comparable to the other projects' Veltro (run with the older legend). Cells without `+/-` are single runs, **except** plantuml/Opus (5 runs, zero variance); d2/Opus is a single-run probe (n=1) because the batch hit the Anthropic credit limit before finishing d2.
