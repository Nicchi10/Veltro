# Veltro eval leaderboard - spring-beans

Generated from `eval/leaderboard.csv` by `eval/report.py`. Columns are model (provider): all runs are via paid API (OpenAI / Anthropic). Compare formats within a column.

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format, API runs only)

| format | tokens | vs Veltro |
|---|---|---|
| veltro | 42792 | - |
| mermaid | 51648 | +21% |
| plantuml | 56823 | +33% |
| d2 | 58450 | +37% |

### Exact accuracy (mean +/- std)

| format | claude-opus-4-8 (anthropic) | gpt-4.1-mini (openai) |
|---|---|---|
| veltro | 76+/-2% | 41+/-1% |
| mermaid | 70+/-1% | 51+/-5% |
| plantuml | 69+/-2% | 46+/-2% |
| d2 | 80+/-1% | 60+/-10% |

### List-question F1 (mean +/- std)

| format | claude-opus-4-8 (anthropic) | gpt-4.1-mini (openai) |
|---|---|---|
| veltro | 0.81+/-0.02 | 0.40+/-0.05 |
| mermaid | 0.63+/-0.05 | 0.42+/-0.07 |
| plantuml | 0.62+/-0.02 | 0.34+/-0.04 |
| d2 | 0.85 | 0.65+/-0.06 |

Legend: `-` = combination not tested (not a zero). `*` = contaminated run (pre-fix or weak model), indicative only. Cells without `+/-` are single runs (n=1, no variance).
