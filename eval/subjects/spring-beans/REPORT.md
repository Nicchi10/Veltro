# Veltro eval leaderboard - spring-beans

Generated from `eval/leaderboard.csv` by `eval/report.py`. Columns are model (provider): all runs are via paid API (OpenAI / Anthropic). Compare formats within a column.

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format, API runs only)

| format | tokens | vs Veltro |
|---|---|---|

### Exact accuracy (mean +/- std)

| format | claude-opus-4-8 (anthropic) |
|---|---|
| veltro | 76+/-2% |
| mermaid | 70+/-1% |
| plantuml | 69+/-2% |
| d2 | 80+/-1% |

### List-question F1 (mean +/- std)

| format | claude-opus-4-8 (anthropic) |
|---|---|
| veltro | 0.81+/-0.02 |
| mermaid | 0.63+/-0.05 |
| plantuml | 0.62+/-0.02 |
| d2 | 0.85 |

Legend: `-` = combination not tested (not a zero). `*` = contaminated run (pre-fix or weak model), indicative only. Cells without `+/-` are single runs (n=1, no variance).
