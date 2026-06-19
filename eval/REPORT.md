# Veltro eval leaderboard - pydantic

Generated from `eval/leaderboard.csv` by `eval/report.py`. Provider: OpenAI. One question set (50 ground-truth questions derived from the type-graph model).

**Read it honestly:** token cost is deterministic and solid, comprehension accuracy is model-dependent and the formats land in overlapping bands, no robust comprehension winner. The durable result is fewer tokens at comparable comprehension.

### Token cost (o200k_base, per format)

| format | tokens | vs Veltro |
|---|---|---|
| veltro | 21190 | - |
| mermaid | 25418 | +20% |
| plantuml | 27446 | +30% |
| d2 | 30520 | +44% |

### Exact accuracy (mean +/- std)

| format | gpt-4.1-nano | gpt-4o | gpt-5.4-mini | gpt-5.5 |
|---|---|---|---|---|
| veltro | 20%* | 62% | 51+/-4% | 84% |
| mermaid | 2%* | 70% | 57+/-8% | 78% |
| plantuml | 30%* | 62% | 49+/-8% | 74% |
| d2 | - | - | 55+/-5% | - |

### List-question F1 (mean +/- std)

| format | gpt-4.1-nano | gpt-4o | gpt-5.4-mini | gpt-5.5 |
|---|---|---|---|---|
| veltro | 0.33* | 0.54 | 0.48+/-0.03 | 0.89 |
| mermaid | 0.04* | 0.72 | 0.63+/-0.02 | 0.79 |
| plantuml | 0.36* | 0.60 | 0.69+/-0.01 | 0.80 |
| d2 | - | - | 0.66+/-0.08 | - |

Legend: `-` = combination not tested (not a zero). 
`*` = contaminated run (pre-fix or weak model), indicative only. 
Cells without `+/-` are single runs (n=1, no variance).
