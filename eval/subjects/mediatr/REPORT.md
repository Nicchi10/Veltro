# Veltro eval leaderboard - MediatR

Generated from `eval/leaderboard.csv` by `eval/report.py`. Columns are model (provider): all runs are via paid API (OpenAI / Anthropic). Compare formats within a column.

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format, API runs only)

| format | tokens | vs Veltro |
|---|---|---|
| veltro | 10096 | - |
| mermaid | 12624 | +25% |
| plantuml | 13155 | +30% |
| d2 | 16055 | +59% |

### Exact accuracy (mean +/- std)

| format | claude-opus-4-8 (anthropic) | gpt-4.1-mini (openai) |
|---|---|---|
| veltro | 90+/-1% | 76+/-9% |
| mermaid | 96+/-1% | 72+/-2% |
| plantuml | 96+/-2% | 70+/-2% |
| d2 | 96+/-1% | 80+/-3% |

### List-question F1 (mean +/- std)

| format | claude-opus-4-8 (anthropic) | gpt-4.1-mini (openai) |
|---|---|---|
| veltro | 0.95+/-0.00 | 0.82+/-0.08 |
| mermaid | 0.99+/-0.00 | 0.79+/-0.05 |
| plantuml | 0.97+/-0.05 | 0.75+/-0.01 |
| d2 | 0.99 | 0.81+/-0.01 |

Legend: `-` = combination not tested (not a zero). `*` = contaminated run (pre-fix or weak model), indicative only. Cells without `+/-` are single runs (n=1, no variance).
