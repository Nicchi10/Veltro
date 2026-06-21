# Veltro eval leaderboard - pydantic

Generated from `eval/leaderboard.csv` by `eval/report.py`. Columns are model (provider): OpenAI runs are via API, Claude runs via the Claude Code harness, compare formats within a column, absolute accuracy across harnesses is not 1:1.

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format, API runs only)

| format | tokens | vs Veltro |
|---|---|---|
| veltro | 21190 | - |
| mermaid | 25418 | +20% |
| plantuml | 27446 | +30% |
| d2 | 30520 | +44% |

### Exact accuracy (mean +/- std)

| format | gpt-4.1-nano (openai) | gpt-4o (openai) | gpt-5.4-mini (openai) | gpt-5.5 (openai) | claude-sonnet-4-6 (anthropic) | haiku (claude-code) | sonnet (claude-code) | claude-opus-4-8 (anthropic) |
|---|---|---|---|---|---|---|---|---|
| veltro | 20%* | 62% | 51+/-4% | 84% | 70+/-3% | 83+/-2% | 84+/-1% | 80+/-2% |
| mermaid | 2%* | 70% | 57+/-8% | 78% | 77+/-2% | 78+/-6% | - | 80+/-5% |
| plantuml | 30%* | 62% | 49+/-8% | 74% | 73+/-1% | 80+/-4% | - | 79+/-2% |
| d2 | - | - | 55+/-5% | - | 59+/-31% | 83+/-2% | - | 80+/-3% |

### List-question F1 (mean +/- std)

| format | gpt-4.1-nano (openai) | gpt-4o (openai) | gpt-5.4-mini (openai) | gpt-5.5 (openai) | claude-sonnet-4-6 (anthropic) | haiku (claude-code) | sonnet (claude-code) | claude-opus-4-8 (anthropic) |
|---|---|---|---|---|---|---|---|---|
| veltro | 0.33* | 0.54 | 0.48+/-0.03 | 0.89 | 0.82+/-0.01 | 0.87+/-0.02 | 0.89+/-0.00 | 0.82+/-0.01 |
| mermaid | 0.04* | 0.72 | 0.63+/-0.02 | 0.79 | 0.84+/-0.01 | 0.83+/-0.05 | - | 0.82+/-0.05 |
| plantuml | 0.36* | 0.60 | 0.69+/-0.01 | 0.80 | 0.82 | 0.85+/-0.05 | - | 0.85+/-0.03 |
| d2 | - | - | 0.66+/-0.08 | - | 0.63+/-0.35 | 0.85+/-0.05 | - | 0.82+/-0.02 |

Legend: `-` = combination not tested (not a zero). `*` = contaminated run (pre-fix or weak model), indicative only. Cells without `+/-` are single runs (n=1, no variance).
