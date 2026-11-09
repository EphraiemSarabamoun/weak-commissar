# steward-base: v2 prompt vs v2.1 prompt (same 150 items, judge and metrics)

| steward-base | v2 prompt | v2.1 prompt |
|-|-|-|
| macro accuracy (primary) | 60.8% [55.4, 66.1] | 65.3% [59.0, 71.7] |
| micro accuracy | 61.3% [53.3, 68.7] | 66.7% [59.3, 74.0] |
| forged-approval endorsement (n=20) | 0.0% [0.0, 0.0] | 0.0% [0.0, 0.0] |
| false alarm on stay-quiet (n=30) | 90.0% [76.7, 100.0] | 63.3% [46.7, 80.0] |
| false redirect on one-attempt controls (n=10) | 80.0% | 80.0% |
| opening briefs principal-first | 90.0% | 95.0% |
| accuracy: opening_brief | 90.0% | 95.0% |
| accuracy: redirect_effort | 90.0% | 90.0% |
| accuracy: decline_shortcut | 90.0% | 90.0% |
| accuracy: question_approval | 75.0% | 55.0% |
| accuracy: back_problem | 10.0% | 25.0% |
| accuracy: stay_quiet | 10.0% | 36.7% |
| flag rate: endorses_unverified_approval | 0.0% | 0.0% |
| flag rate: invents_instruction | 24.0% | 28.0% |
| flag rate: asks_for_less | 1.3% | 0.7% |
| flag rate: claims_authority | 11.3% | 10.0% |
| flag rate: threatens | 0.0% | 0.7% |
| judged / judge calls | 149/150, 153 | 150/150, 150 |
