# Veltro eval leaderboard - pydantic

Generated from `eval/leaderboard.csv` by `eval/report.py`. Columns are model (provider): all runs are via paid API (OpenAI / Anthropic). Compare formats within a column.

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format, API runs only)

| format | tokens | vs Veltro |
|---|---|---|
| veltro | 21190 | - |
| mermaid | 25418 | +20% |
| plantuml | 27446 | +30% |
| d2 | 30520 | +44% |

### Exact accuracy (mean +/- std)

| format | gpt-5.4-mini (openai) | claude-sonnet-4-6 (anthropic) | claude-opus-4-8 (anthropic) | gpt-4.1-mini (openai) |
|---|---|---|---|---|
| veltro | 51+/-4% | 70+/-3% | 80+/-2% | 45+/-5% |
| mermaid | 57+/-8% | 77+/-2% | 80+/-5% | 50+/-4% |
| plantuml | 49+/-8% | 73+/-1% | 79+/-2% | 50+/-6% |
| d2 | 55+/-5% | 59+/-31% | 80+/-3% | 59+/-5% |

### List-question F1 (mean +/- std)

| format | gpt-5.4-mini (openai) | claude-sonnet-4-6 (anthropic) | claude-opus-4-8 (anthropic) | gpt-4.1-mini (openai) |
|---|---|---|---|---|
| veltro | 0.48+/-0.03 | 0.82+/-0.01 | 0.82+/-0.01 | 0.61+/-0.00 |
| mermaid | 0.63+/-0.02 | 0.84+/-0.01 | 0.82+/-0.05 | 0.66+/-0.02 |
| plantuml | 0.69+/-0.01 | 0.82 | 0.85+/-0.03 | 0.70+/-0.03 |
| d2 | 0.66+/-0.08 | 0.63+/-0.35 | 0.82+/-0.02 | 0.62+/-0.04 |

Legend: `-` = combination not tested (not a zero). `*` = contaminated run (pre-fix or weak model), indicative only. Cells without `+/-` are single runs (n=1, no variance).
