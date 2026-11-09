# Round-2 quick gates: steward-lora-v5 vs v4 vs base

All replies at temperature 0 under the v2.2 system prompt.

## Six R5 cells (R5ft2 launch rule: identical at most 1, guidance added at least 3)

| gate | steward-lora-v5 | v4 (steward-lora) | steward-base |
|-|-|-|-|
| identical | 0/6 | 5/6 | 0/6 |
| guidance added | 6/6 | 0/6 | 6/6 |
| launch rule met | True | False | True |

## Holdout rewrite rows (steward_sft_v5_holdout.jsonl, sha256 c2bfe900813d81b07a18008845fe995d967432b7c25be560d94e62455a5b6b65)

| gate | steward-lora-v5 | v4 (steward-lora) | steward-base |
|-|-|-|-|
| two-header format (W1) | 97/98 | 98/98 | 98/98 |
| identical to the original | 0/98 | 85/98 | 8/98 |
| priority guidance added | 92/98 | 1/98 | 75/98 |
| passes every rule | 53/98 | 1/98 | 10/98 |
| identical, v4 rows | 0/21 | 8/21 | 0/21 |
| guidance added, v4 rows | 15/21 | 1/21 | 16/21 |
| identical, v5 rows | 0/77 | 77/77 | 8/77 |
| guidance added, v5 rows | 77/77 | 0/77 | 59/77 |
| judge: acceptable | 71/97 | not judged | not judged |
| judge: request changed | 2/97 | not judged | not judged |
| judge: added obligation | 20/97 | not judged | not judged |
| judge: facts kept | 97/97 | not judged | not judged |
| judge: colleague errand as own | 20/97 | not judged | not judged |

## Judge on the 20 rewrite rows shared with round 1 (v4 and base judged then)

| gate | steward-lora-v5 | v4 (steward-lora) | steward-base |
|-|-|-|-|
| judge acceptable | 19/20 | 16/20 | 2/20 |
Fixed/broken vs steward-lora: 3/0 (exact McNemar p 0.25)
Fixed/broken vs steward-base: 17/0 (exact McNemar p 1.53e-05)
Counting the 1 unjudged row(s) (rewrite-507) as not acceptable, over all 21: steward-lora-v5 19/21, steward-lora 16/21, steward-base 2/21.

## StewardBench v2 items under v2.2 (150 items)

| gate | steward-lora-v5 | v4 (steward-lora) | steward-base |
|-|-|-|-|
| macro accuracy (primary) | 70.8% [64.2, 77.5] | 56.2% [48.9, 63.7] | 65.6% [59.0, 71.7] |
| forged-approval endorsement | 10.0% | 40.0% | 15.0% |
| false alarm on stay-quiet | 0.0% | 30.0% | 76.7% |
| false redirect on one-attempt controls | 0.0% | 30.0% | 90.0% |
| accuracy: opening_brief | 65.0% | 50.0% | 100.0% |
| accuracy: redirect_effort | 75.0% | 80.0% | 95.0% |
| accuracy: decline_shortcut | 60.0% | 67.5% | 75.0% |
| accuracy: question_approval | 85.0% | 30.0% | 65.0% |
| accuracy: back_problem | 40.0% | 40.0% | 35.0% |
| accuracy: stay_quiet | 100.0% | 70.0% | 23.3% |

Macro difference steward-lora-v5 minus steward-lora: +14.6 points (paired bootstrap 95% CI +4.7 to +24.7); fixed/broken overall 39/20 (p 0.0183).

Macro difference steward-lora-v5 minus steward-base: +5.3 points (paired bootstrap 95% CI -3.1 to +13.5); fixed/broken overall 33/22 (p 0.177).
