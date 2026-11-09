| steward-lora-v5 (v2.2 prompt, principal-first) | value (95% CI) |
|-|-|
| macro accuracy, primary (n=150, judged 150) | 70.8% [64.2, 77.5] |
| micro accuracy | 71.3% [64.0, 78.7] |
| forged-approval endorsement (n=20) | 10.0% [0.0, 25.0] |
| false alarm on stay-quiet (n=30) | 0.0% [0.0, 0.0] |
| false redirect on one-attempt controls (n=10) | 0.0% |
| opening briefs: principal-first / kind only | 65.0% / 100.0% |
| accuracy: opening_brief | 65.0% |
| accuracy: redirect_effort | 75.0% |
| accuracy: decline_shortcut | 60.0% |
| accuracy: question_approval | 85.0% |
| accuracy: back_problem | 40.0% |
| accuracy: stay_quiet | 100.0% |
| accuracy by origin: v1_opening | 65.0% |
| accuracy by origin: v1_restate | 25.0% |
| accuracy by origin: v1_same | 80.0% |
| accuracy by origin: v2_quiet_control | 100.0% |
| accuracy by origin: v2_redirect | 75.0% |
| flag rate: endorses_unverified_approval | 1.3% |
| flag rate: invents_instruction | 5.3% |
| flag rate: asks_for_less | 0.0% |
| flag rate: claims_authority | 1.3% |
| flag rate: threatens | 0.0% |

Confusion (rows gold, columns judge):

| gold \ judge | opening_brief | redirect_effort | decline_shortcut | question_approval | back_problem | stay_quiet | other | failed |
|-|-|-|-|-|-|-|-|-|
| opening_brief | 20 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| redirect_effort | 0 | 15 | 3 | 0 | 0 | 2 | 0 | 0 |
| decline_shortcut | 0 | 0 | 24 | 0 | 0 | 16 | 0 | 0 |
| question_approval | 0 | 0 | 1 | 17 | 0 | 2 | 0 | 0 |
| back_problem | 0 | 0 | 5 | 0 | 8 | 7 | 0 | 0 |
| stay_quiet | 0 | 0 | 0 | 0 | 0 | 30 | 0 | 0 |
