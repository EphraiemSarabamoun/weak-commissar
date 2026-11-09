# steward-base vs steward-lora (v4)

## StewardBench v2.2 (150 items, v2.2 system prompt)

| metric | steward-base | steward-lora |
|-|-|-|
| macro accuracy (primary) | 65.6% [59.0, 71.7] | 56.2% [48.9, 63.7] |
| micro accuracy | 64.0% [56.0, 71.3] | 58.7% [50.7, 66.0] |
| forged-approval endorsement | 15.0% | 40.0% |
| false alarm on stay-quiet | 76.7% | 30.0% |
| false redirect on one-attempt controls | 90.0% | 30.0% |
| accuracy: opening_brief | 100.0% | 50.0% |
| accuracy: redirect_effort | 95.0% | 80.0% |
| accuracy: decline_shortcut | 75.0% | 67.5% |
| accuracy: question_approval | 65.0% | 30.0% |
| accuracy: back_problem | 35.0% | 40.0% |
| accuracy: stay_quiet | 23.3% | 70.0% |
| flag rate: invents_instruction | 18.0% | 3.3% |
| flag rate: claims_authority | 4.7% | 0.7% |
| flag rate: asks_for_less | 0.0% | 0.0% |

## Rewrite fidelity (v4 holdout rewrite rows, temperature 0)

| placement / metric | steward-base | steward-lora |
|-|-|-|
| system: two-header format (W1) | 21/21 | 21/21 |
| system: passes every rule | 1/21 | 1/21 |
| system: judge: acceptable | 2/21 | 16/21 |
| system: judge: request changed | 9/21 | 1/21 |
| system: judge: added obligation | 18/21 | 0/21 |
| user: two-header format (W1) | 21/21 | 21/21 |
| user: passes every rule | 0/21 | 5/21 |
| user: judge: acceptable | n/a | n/a |
| user: judge: request changed | n/a | n/a |
| user: judge: added obligation | n/a | n/a |

## Paired: what the fine-tune fixed and broke (exact McNemar p)

| scope | fixed | broken | p |
|-|-|-|-|
| StewardBench opening_brief | 0 | 10 | 0.00195 |
| StewardBench redirect_effort | 1 | 4 | 0.375 |
| StewardBench decline_shortcut | 4 | 7 | 0.549 |
| StewardBench question_approval | 1 | 8 | 0.0391 |
| StewardBench back_problem | 3 | 2 | 1.0 |
| StewardBench stay_quiet | 14 | 0 | 0.000122 |
| StewardBench all | 23 | 31 | 0.341 |
| rewrite system: passes all rules | 1 | 1 | 1.0 |
| rewrite system: judge acceptable | 14 | 0 | 0.000122 |
| rewrite user: passes all rules | 5 | 0 | 0.0625 |

Macro accuracy difference, lora minus base: -9.3 points (paired bootstrap 95% CI -17.5 to -0.8).
