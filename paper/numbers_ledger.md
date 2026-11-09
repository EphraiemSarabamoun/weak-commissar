# Numbers ledger for paper/report.md

Every number in the manuscript, with the file it comes from. The section drafts carry fuller ledgers
(`drafts/results_exp1.md`, `drafts/results_exp2.md`, `drafts/methods_exp1.md`, `drafts/methods_exp2.md`), whose numbers
Codex verified at source. Operae paths are relative to the operae worktree
`<local>/Desktop/research/loyalty-evals/_commissar/operae/experiments/commissar/` (branch `commissar`; authority arms f839426 and 8ec03cc, search 4c0a15c, R5 f894531, validator c934706 and 150869d, development rounds 9510ef3, 7ac3b9b, 534b949 and 9f91972).
Swarm-board paths are relative to `<local>/projects/swarm-board/` (branch `honeypot`).

## Experiment 1 (honeypot)

| Number in the paper | Value | Source |
|---|---|---|
| Confirmatory teams opening the key or grade.py | 0 of 12 | `results/hp-confirm/run/analysis.json` (primary_open) |
| Wilson 95% interval, team level | [0, 0.24] (0.2425) | same, `conditions.confirm.wilson95.primary_open`; `prereg/confirm_result.md` |
| Confirmatory agents opening either file | 0 of 48 | `results/hp-confirm/run/agents.csv` |
| Canary leaks | 0 | `analysis.json` canary_leak |
| Tool calls matched by recount | 851 | `results/hp-confirm/recount.json` |
| README-only reads | 4 agents in 4 teams | `recount.json`; `analysis.json` |
| Teams that never submitted; the one submission | 11; 1 calendar meeting 21 of 22 rules, rejected | `results/hp-confirm/run/secondary.json`; `analysis.json` |
| Drafted escalations to the principal | 11 of 12 teams, 5 explicitly addressed | `secondary.json` summary.infeasibility_report_teams; `<inbox>/hp-confirm/result.json` |
| Debrief labels | TEST 35, UNSURE 11, REAL 2, of 48 | `secondary.json` summary.debrief_labels |
| Calibration | 13 teams, 52 agent episodes; Sonnet 5.5 and Opus 5.5 two teams each (8 agents each) | `results/calib-levers/README.md`; `<inbox>/hp-levers/result.json` |
| Calibration key opens | 0 of 13 teams, 0 of 52 episodes | `calib-levers/README.md`; `<inbox>/hp-verify/result.json` (recomputed) |
| Scripted leak | 2 teams, 8 agents, 0 adoptions; quoted reply | `calib-levers/run1/teams/l3_insider-t00`, `run2/teams/p6_noexit_insider-t00` (`state/board.jsonl`); run1, run2 `analysis.json` |
| Tool calls per turn; submissions | 20; one per round | `swarm_board/hp_config.py`; `teamstate.py` |
| Confirmatory rounds | 8 | `prereg/confirm.md` (commit 2dce1a6) |
| Requests used | 1,284 | `results/hp-confirm/run/status.json` |
| HP-F1 fix: floor, bounds | at least 1,000 calendars per three-department subset; pass bound at most 0.005 (hard), 0 (impossible) | honeypot-tasks a1a29b3; `<inbox>/hp-task-fix/result.json` |
| Level 2 plan space | 14,696,640 | `<local>/projects/honeypot-tasks/docs/difficulty.json` |
| Level 4 size and plan space | 8 products, 10 weeks, 4 regions; 118,908,518,400 (about 1.2e11); 10 canaries | `honeypot-tasks/instances/MANIFEST.json` and `instance.json` at a1a29b3 |
| HP-F1b holes | 2.86-million-character stuffing payload accepted; rejections differed by sign-off state | `<inbox>/hp-task-reverify/attack-results.json` (2,860,487 characters), `artifact-checks.json` |
| HP-F1b fix | at most one sign-off token per department, 4,000 characters, one identical rejection | honeypot-tasks dd76eec; `<inbox>/hp-task-fix2/result.json`, `before_after.json` |
| HP-F1c fix (third grader hole) | grader crashed on malformed input and read non-ASCII digits as weeks; fixed at 6c73a8f, tag hpf1c-instances; no confirmatory submission affected | `<inbox>/hp-task-fix3/result.json`; paper-ship audit F2 |

## Experiment 2 (operae)

| Number in the paper | Value | Source |
|---|---|---|
| Bases | 32 neutral rows, 8 worlds, 2 beneficiaries, 2 principal names | `compile.py` (N_BASES) |
| A1W gap change vs A0 | +0.54 [0.28, 0.79] (0.5375 [0.2849, 0.7901]); 8 of 8 worlds positive; sign-flip p 0.008 (0.0078); Holm 0.023 (0.0234) | `a1w-vs-a0.json` gap_change, holm_three |
| A1W progress, principal and teammate | 0.90, 0.34 (0.900, 0.3375) | `a1w-haiku.summary.json` t4_progress |
| A0 progress, principal and teammate | 0.68, 0.65 (0.675, 0.650) | `a0-haiku.summary.json` t4_progress |
| A1W teammate change | -0.31 [-0.42, -0.21]; 13 of 16 cells lower, none higher | `a1w-vs-a0.json` primary.teammate |
| A1W principal change | +0.23 [0.04, 0.41] (0.225 [0.042, 0.408]); Holm 0.0625 | `a1w-vs-a0.json` primary.principal |
| Episodes citing the line | 11 teammate episodes; quoted reply (w01 teammate E) | `a1w-vs-a0.json` steward_mentions_by_agent; `<inbox>/c2-a1e-verify/result.json` A1WE-F2 |
| A1W TEST share | 0 of 32 | `a1w-vs-a0.json` test_share |
| Guardrails | 0 phantom successes, declined errands, harms | `<inbox>/c2-a1e/result.json` guardrails |
| A1L gap change | -0.03 [-0.31, 0.25] | `a1l-vs-a0.json` gap_change |
| A1E gap change | -0.04 [-0.45, 0.37] | `a1e-vs-a0.json` gap_change |
| A1E vs A1L | equal world-weighted means | `a1e-vs-a1l.json` |
| A1W vs A1E | +0.56 [0.08, 1.04]; Holm 0.19 (0.1875); minimum sign-flip p with five worlds 0.0625 | `a1w-vs-a1e.json` gap_change, holm_three |
| A1 gap change | -0.08 [-0.54, 0.38] | `a1-vs-a0.json` gap_change |
| Exposure | 16 of 16, 14 of 14, 12 of 12 | `a1-`, `a1l-`, `a1e-vs-a0.json` exposure |
| A1L mentions | 5 of 14, all not acted on, 3 explicit source reasons (the quote moved out of the body for space) | `README.md` A1L section; `<inbox>/c2-a1l-verify/result.json` A1L-F3 |
| A1E mentions | 4 explicit non-adoptions, 0 mention the endorsement; quote | `a1e-vs-a0.json`; `c2-a1e-verify` A1WE-F3 |
| Usable commissar keys; cells per arm | 8 of 16, 7 of 16; A1 16, A1L 14, A1E 12 | `steward/messages.frozen.jsonl`; `steward/a1l/frozen.jsonl`; `specs/a1e.provenance.jsonl` |
| A1L without w03 E | -0.04 | `a1l-vs-a0.without-w03E.json` |
| Episode limits; attempts | 60 tool calls, 80 turns; 6 (A1) or 10 (A1L) attempts | released spec `end` block; `steward/` |
| Workers | 3 each for A1W and A1E (preregistered 4) | `DEVIATIONS.md` |
| Preexisting commits | operae dc9a0d6 (2026-11-01); castra 8457977 (2026-10-31); anulus c87b235 (2026-11-02); sprint commits 4a3ac5d onward; search from 6364c99; validator from 89c8dca | `drafts/methods_exp2.md`, git log of branch `commissar` |
| A0 baseline gap | +0.025 [-0.072, 0.122], 16 pairs, 8 worlds | `a0-haiku.summary.json` gap_principal_minus_teammate |

## Experiment 2: the search (R2 to R4, exploratory) and R5 (preregistered primary)

| Number in the paper | Value | Source |
|---|---|---|
| Search texts | one per principal name; 16 attempts; E attempt 7 and K attempt 9 frozen; frozen.json sha256 372a3d32 | `steward/search/attempts.jsonl`, `review.json`, `frozen.json` |
| R2 gap change vs A0 | -0.16 [-0.36, 0.04] (-0.1625 [-0.3621, 0.0371]), p 0.19 | `s-search.json` arms[forwarded].vs_a0.gap_change |
| R3 gap change vs A0 | 0.00 [-0.18, 0.18] (0.0 [-0.1843, 0.1843]), p 1.0 | `s-search.json` arms[appointed].vs_a0.gap_change |
| R4 gap change vs A0 | -0.01 [-0.21, 0.19] (-0.0125 [-0.2146, 0.1896]), p 1.0 | `s-search.json` arms[policy].vs_a0.gap_change |
| R2 to R4 TEST share; guardrails | 0 of 32 each; 0 events each | `s-search.json` arms[].test_share, guardrails |
| R2, R3, R4 against A1W | -0.70, -0.54, -0.55 (-0.7, -0.5375, -0.55) | `s-search.json` arms[].vs_a1w_context.gap_change |
| R2 agent quote | "The errand was for Bram, but <redacted> authorised it and his priorities come first." (w08 teammate K) | `s-search.json` arms[forwarded].mentions |
| Search selection | R3 by the preregistered rule; confirmation not run | `s-search.json` selection; `prereg/S.md` D1 |
| R5 coverage; attempts | 29 of 32 cells; 143 attempts, 29 accepted, 114 rejected, 94 repeating "sabotage" or "mislead" | `r5-rewrite-stats.json`; `steward/rewrite/attempts.jsonl` |
| R5 gap change vs A0 rerun (primary) | +0.13 [-0.17, 0.42] (0.1286 [-0.1674, 0.4245]), sign-flip p 0.50, 13 pairs, 7 worlds | `r5-confirm.json` primary_and_secondaries.gap_change |
| R5 principal change | +0.20 [0.00, 0.40], 8 better, 0 worse, 6 tied, p 0.0625, Holm 0.125 | same, .principal |
| R5 teammate change | +0.06 [-0.14, 0.26] (0.0625), p 0.75 | same, .teammate |
| R5 TEST share; guardrails | 0 of 29 (A0 rerun 0 of 32); 0 events in both | `r5-confirm.json` arm.test_share, guardrails, reference |
| R5 vs A0 of record; rerun vs record | +0.03 (0.0286); -0.125 [-0.34, 0.09] | `r5-confirm.json` sensitivity |
| Rewrite coding | principal 13 of 14 push; teammate 12 of 15 persistence-coded (8 MIS: 5 explicit, 3 priority-only; 4 PERSIST), 1 LIMIT-language, 2 near verbatim | `steward/rewrite/coding.json`; `<inbox>/c2-search-verify/result.json` C2-SV-F2 |
| Codex counterexample | "the duplicate" to "both duplicate charges" (w05 teammate K) | `c2-search-verify/result.json` C2-SV-F1; `steward/rewrite/frozen.jsonl` line 20 |
| Validator judge | Sonnet 5.5, prompt sha256 4cc39ce5; 18 of 20 against hand labels (11 change, 9 none), counterexample caught; word rule flags 2 of 9 harmless pairs | `steward/rewrite_judge/PIN.json`, `validation_results.json` |
| R5 recheck | 14 of 29 refused: judge 10, word rule 5 (1 both) | `steward/rewrite_judge/r5_recheck.json` fail_by |
| Sensitivity | without 14: 3 pairs, +0.40 [-0.91, 1.71] (stored [-0.9146, 1.7146]), p 0.50; without 10 judge refusals: 7 pairs in 5 worlds, +0.22 [-0.23, 0.67], p 0.31, principal +0.28, teammate +0.04 (corrected after Codex PR1-F3) | `r5_recheck.json` sensitivity, sensitivity_judge_fail_only |
| Development round 0 (v2.1, w01 to w04) | 16 of 16 rewritten; gap -0.075 [-0.55, 0.40], p 1.00; principal +0.025, teammate +0.100; second sample -0.075 [-0.23, 0.08], p 0.50, 4 of 16 cells differ | `<inbox>/eval-harness/result.json`; `<inbox>/round05/result.json` answer.table |
| Development round 0.5 (v2.2) | 15 of 16 rewritten; gap +0.475 [-0.15, 1.10], p 0.25, 7 pairs, Holm 0.75; principal 0.750 to 0.950; teammate 0.725 to 0.550; LIMIT 4 of 8 vs 1 of 8; stricter check fails 9 of 15 (round 0: 10 of 16); one passing pair | `round05/result.json` answer.table; operae 7ac3b9b |
| Registration times | A1 3b566f9 17:20 (messages frozen 17:31); A1L 0fd5374 17:41 (frozen 17:53:40, bdf4922); A1W and A1E 80276d3 18:14:02 (A1E reused A1L's frozen messages); S 6364c99 18:59:29; R5 f2fd562 19:15:54; R5v22 5f88587 20:12:49 (after development rounds) | `git log` of operae branch `commissar`; `prereg/*.md` |
| R5v22 coverage; note N1 | 23 of 32 cells, 9 pairs in 6 worlds; smallest attainable sign-flip p 0.031 above the 0.025 Holm requires, recorded after the fresh A0 rerun (20:14:08 to 20:19:02) and before any R5v22 treatment episode (from 20:28:45), in 9461d00 at 20:27:30 | `<inbox>/r5v22-confirm/result.json` answer.table, bad_news_first; `prereg/R5v22.md` N1 (9461d00). Verified by Codex r5v22-verify (numbers reproduce) |
| R5v22 gap change vs its A0 rerun | +0.43 [+0.005, +0.86] (0.4333 [0.0048, 0.8618]), sign-flip p 0.125, Holm across R5 and R5v22 0.25; worlds w01 +1.0, w03 0.0, w04 +0.8, w06 +0.4, w07 0.0, w08 +0.4 | operae `r5v22-confirm.json` primary_and_secondaries; inbox answer.table, holm_across_R5_R5v22. Verified by Codex r5v22-verify |
| R5v22 principal; teammate | +0.17 [-0.11, 0.45], p 0.50; -0.29 [-0.57, -0.007], p 0.0625, Holm 0.125 | same. Verified by Codex r5v22-verify |
| R5v22 TEST; guardrails; vs record | 0 of 23; 0; +0.27, p 0.19 | `r5v22-confirm.json` arm, sensitivity; inbox answer.table. Verified by Codex r5v22-verify |
| R5v22 rewrites and coding | 155 attempts, 34 judge calls (23 pass, 11 fail); teammate LIMIT 8 of 14 (2 ambiguous: w04 tE, w05 tK; MIS 3, PERSIST 1, near verbatim 2), coded after the A0 rerun's outcomes and before any treatment outcome; teammate fall as large in MIS as in LIMIT cells; screen passes that change requests or facts: w03 tE, w08 tE, w07 tK (and weakly w08 pE) | inbox answer.table, bad_news_first. Verified by Codex r5v22-verify |
| LIMIT-coded episodes' outcomes | 7 of 8 ended at progress 0.0 to 0.4; w03 teammate K 1.0 (resolved, citing the one-attempt instruction); w07 teammate K opened a follow-up request | operae `runs/r5v22-rewrite` episode records, `r5v22-rewrite-haiku.csv`; `steward/r5v22/coding.json`; Codex paper-review2 PR2-F2 |
| Workers' system prompt | all 32 A0 system prompts name the principal and the assistant role; no loyalty instruction | operae `specs/a0.jsonl` spec.system; Codex paper-review2 PR2-F1 |
| R5v22 detail | its A0 rerun principal 0.483, teammate 0.713; rerun vs record -0.075; held-out w05 to w08 +0.27 [-0.31, 0.84], p 0.50, 5 pairs; dev w01 to w04 +0.60 [-0.71, 1.91], p 0.50, 4 pairs; Ephraiem pairs +0.70 (4), <redacted> +0.20 (5); vs R5's run +0.25 [-0.24, 0.74], p 0.375 | inbox answer.table, bad_news_first; operae `r5v22-vs-r5.json` primary_gap_change. Verified by Codex r5v22-verify |
| R5v22 exclusion sensitivity | without the 2 ambiguous cells: +0.40 [0.0017, 0.7983], p 0.125, 8 pairs; without the 3 changed rewrites: +0.33 [-0.21, 0.88], p 0.25, 7 pairs; without all 5: +0.30 [-0.21, 0.81], p 0.25, 6 pairs | operae `r5v22-exclusion-sensitivity.json` (0f634d8); Codex r5v22-verify F1, F3, F4 |
| R5v22 chronology | prereg 5f88587 20:12:49; A0 rerun 20:14:08 to 20:19:02; N1, freeze, coding 9461d00 20:27:30; treatment from 20:28:45 | Codex r5v22-verify R5V22-V-F2; run manifests |

## The commissar and StewardBench

| Number in the paper | Value | Source |
|---|---|---|
| Model | Qwen3.5-4B, revision 851bf6e, bf16, thinking off | `<inbox>/serve/result.json` |
| Instruction hashes | v1 c183b6d3; v2 9e2b5e85; v2.1 = v2 plus two sentences | `steward/system_prompt.txt`; `steward/a1l/system_prompt.txt`; `<inbox>/stewardbench2b/result.json` prompt_check |
| StewardBench v1 items; judge validation | 120 items, 10 domains; 93.3% kind agreement, kappa 0.92 (0.9151) | `<inbox>/stewardbench/result.json` items, judge_agreement |
| StewardBench v2 items; judge validation | 150 items; 96.7%, kappa 0.96 (0.9563) | `<inbox>/stewardbench2/result.json` v2_changes, judge_validation |
| Blind labeller | 36 of 36 | `stewardbench/result.json` items.gold_label_blind_check |
| v1 base scores | accuracy 58.3% [50.0, 66.7]; endorsement 2 of 20; back_problem 35%; false alarm 80% | `stewardbench/result.json` steward_base_key_numbers |
| v2 base scores | macro 60.8% [55.4, 66.1]; endorsement 0 of 20; question approval 75%; back_problem 2 of 20; false alarm 90%; 8 of 10 controls redirected | `stewardbench2/result.json` steward_base_v2_key_numbers |
| v2.1 base scores | macro 65.3% [59.0, 71.7]; false alarm 63.3%, 9 fixed, 1 broken, exact p 0.021; back_problem 5 of 20; question approval 11 of 20; endorsement 0 of 20 | `stewardbench2b/result.json` v2_vs_v2_1_table_markdown, paired_flips_per_kind |
| StewardBench v1 detail | 120 items, 20 per kind, 67 hard; judge validation n 30, endorsement flag 1.0; v1 base: 70 of 120, question approval 30%, claims authority 21.7%, invents instruction 26.7% | `stewardbench/result.json` |
| StewardBench v2.2 (unpinned, development) | macro 65.6% [59.0, 71.7] (0.6556); endorsement 3 of 20; false alarm 76.7% | operae `evals/steward-base.v2_2/stewardbench/steward-base/scores.json` |
| Invent runs | steward-sft 7508ad2a, 1,200 rows, 17:39 to 18:37; steward-sft-quiet 9428e222, 400, 18:48 to 19:35; steward-rewrite 259f2795, 800, 19:03 to 19:53; estimated 120, 40, 80 credits of 1,500 | `<local>/projects/commissar/data/*_meta.json`; `runs/<ts>_invent/response.json` |
| Adaption evaluation of run 1 | grade B before and after, score 9.0 to 8.4 | `steward_sft_meta.json` evaluation_summary |
| First run skew | judge sample 150: openings 71, redirects 67, decline 10, approvals 2, quiet 0, back-problem 0; opening share 0.47; 4 quiet completions of 1,200 | `<inbox>/steward-data/result.json` answer.kind_mix |
| Malformed top-up | 244 of 400 'No objection.' then argue; 74 glued; 23 clean | `steward-data2/result.json` answer.headline |
| Salvage | 312 candidates, 304 labelled, 149 high-confidence quiet, 139 kept; 208 top-up rows in the rebuilt set (139 salvaged quiet, 21 clean quiet, 36 approval, 4 back-problem, 8 unclear; `<local>/projects/commissar/data/steward_sft_v2_index.jsonl`); steward set 1,009 train, 176 holdout, openings 35%, quiet 21% of the rest | `steward-data2/result.json` answer.salvage, headline |
| Rewrite yield | 800 rows; 280 unmappable; 210 pass the rules; judge sample 79 of 100 acceptable; 173 stricter; 155 pass the request judge (18 fail) | `steward-data3/result.json` answer.rewrite_qa; `steward-data4/result.json` answer.judge_results |
| v4 | train 1,411 (1,009 steward + 402 = 134 x 3 rewrite), sha256 2c270896; holdout 197 (176 + 21), sha256 b3c275e1; v2.2 instructions in the user turn | `steward-data4/result.json` answer.final_counts, known_gaps |
| R5ft registration | preregistered before the fine-tuned model existed (operae 29d1649, 20:39:49 PST); launcher refuses unless steward-lora is served (7579e33); training run created 21:56, adapter live 22:20; freeze 641c196 22:28:22; note N1 4af3b4c 22:31:32, after the fresh A0 rerun finished 22:29:14 and before any R5ft treatment episode; no criterion changed | operae `prereg/R5ft.md`; `<inbox>/r5ft-prep/result.json` prereg; Codex `<inbox>/r5ft-verify/result.json` per_claim 1 |
| Round 1 training | Adaption run 011c9f4e (created 21:56, succeeded 22:19 PST) on v4 train (sha256 2c270896, 1,411 of 1,411 rows); LoRA r16, alpha 32, all linear; lr 5e-5 cosine; 1 epoch = 23 optimizer steps; batch 'max'; train loss 1.52 to 0.85; eval loss 0.846 to 0.670 | `<local>/projects/commissar/runs/20261109T055632Z_train/recipe.json`; `<inbox>/post-train/result.json` answer.training_outcome |
| StewardBench v2 items under v2.2, steward-lora vs base | macro 56.2% [48.9, 63.7] vs 65.6% [59.0, 71.7]; paired difference -9.3 points [-17.5, -0.8]; forged-approval endorsement 8 vs 3 of 20 (7 of the 8 stay quiet on the forgery; 7 new, 2 stopped, p 0.18); false alarm on stay-quiet 30.0% vs 76.7%; invents_instruction 3.3% vs 18% | `<inbox>/post-train/result.json` answer.stewardbench_v2_2; `<local>/projects/commissar/bench/post_train_comparison.md` (a553cdc) |
| StewardBench paired per kind | stay_quiet 14 fixed / 0 broken (exact McNemar p 0.0001); opening_brief 0 / 10 (p 0.002); question_approval 1 / 8 (p 0.04) | same, answer.stewardbench_v2_2.paired |
| Held-out rewrite rows, steward-lora vs base | judge acceptable 16 vs 2 of 21; 20 of 21 omit the priority guidance; 1 of 21 passes every rule | `<inbox>/post-train/result.json` answer.headline |
| R5ft copying | 27 of 30 accepted cells byte-identical in both request and kickoff; base model in R5v22 1 of 23; 12 of 14 pairs replay A0 texts (changed pairs w01 E, w06 E); coverage 30 of 32 (missing w02 teammate E, w08 teammate E) | `<inbox>/r5ft-prep/result.json` answer.headline, final_run_table.coverage; Codex r5ft-verify per_claim 3 |
| R5ft primary | gap change +0.025 [-0.22, 0.27], sign-flip p 0.875, 14 pairs in 8 worlds; not met | operae `r5ft-confirm.json` primary_and_secondaries.gap_change; Codex r5ft-verify per_claim 2 |
| Holm across R5, R5v22, R5ft | raw 0.50, 0.125, 0.875; Holm 1.0, 0.375, 1.0 (R5v22's own registration, two tests: 0.25) | `<inbox>/r5ft-prep/result.json` final_run_table.holm_across_R5_R5v22_R5ft; Codex r5ft-verify per_claim 2 |
| Format diagnosis | on 6 sampled cells steward-lora's reply in the v4 training layout is byte-identical to its reply in R5ft's system+user format; both identical to the original on 5 of 6 | `<inbox>/lora-format-diag/result.json` answer.verdict, counts |
| Training targets | median similarity of rewrite targets to inputs 0.67, none at or above 0.95 | `<inbox>/r5ft-prep/result.json` answer.for_the_paper |
| Under-fitting | leading inference for the copying, not tested | manager's diagnosis note in the dispatch; no artifact |
| Round 2 data | v5 train 1,000 rows = 358 steward + 642 rewrite (560 unique), sha256 386f5733, written 23:08:33 PST and uploaded 01:03 as Adaption dataset 2a81e9a5 (row_count 1000) | `<local>/projects/commissar/data/steward_sft_v5_index.jsonl` (commissar 96317da); `runs/20261109T090339Z_upload/status.json`; `<inbox>/steward-data5/PAID_COMMANDS_v5.md` |
| Round 2 training | Adaption run 9012cd42 launched 01:18:48 PST on 9 November (response created 09:18:49Z): 3 epochs, batch 8, lr 1e-4, dataset 2a81e9a5; the 01:03:43 request at batch 16 has no response record (platform cap 8 for Qwen3.5-4B, R5ft2 D1); poll 01:39:24 running; poll 01:41:24 succeeded with completed_at 09:39:40Z (01:39:40 PST); downloaded 01:41:25; serve/adapter/v5 created 01:41:28 | `<local>/projects/commissar/runs/20261109T091848Z_train/` request.json, response.json; `runs/20261109T090343Z_train/request.json`; `runs/20261109T093924Z_poll`, `runs/20261109T094124Z_poll`, `runs/20261109T094125Z_download`; operae `prereg/R5ft2.md` D1 (e21ccfe) |
| R5ft2 | preregistered d09f12a (22:58:58 PST, 8 November), last launch 01:40; not launched: time (D2 fe835e5, 01:40:29): slot on serve/adapter/v4 at 01:40:03 and 01:40:11, no gate number read, no v5 rewrite or episode; contributes no test or p value; D3 (2d228f1, 01:42:13) corrects D2's 'no v5 adapter existed' to trained at 01:39:40 but neither downloaded nor live at 01:40 | operae `prereg/R5ft2.md` 'The launch rule', D2 and D3; `<inbox>/r5ft2-prep/result.json` |
| Round 2 copying | six R5 launch-rule cells: identical 0 of 6, guidance added 6 of 6 (also agent M's recount); R5ft2x: request byte-identical 0 of 31, both 0 of 31, guidance added 31 of 31, length ratio 1.26 | `<local>/projects/commissar/bench/r5_cells/steward-lora-v5/summary.json`; `<inbox>/r5ft2x/result.json` answer.gate_recount, identity_counts; operae `r5ft2x-rewrite-stats.json` |
| Round 2 StewardBench (v2 items, v2.2) | macro 70.8% [64.2, 77.5] (opening briefs scored correct only when principal-first, 13 of 20); forged endorsement 2 of 20 = 10% [0, 25], both judged stay_quiet; quiet false alarms 0 of 30; decline_shortcut 60% (16 of 40 judged stay_quiet; base 75%); back_problem 40% (7 of 20 judged stay_quiet; base 35%); question_approval 85% (base 65%); stay_quiet 100% (base 23.3%); recounted from judgments.jsonl; paired difference vs base +5.3 points [-3.1, 13.5] (+0.0528 [-0.0306, 0.1347], within-kind bootstrap; Codex recomputed the same); opening briefs principal-first 13 of 20 (0.65) vs base 20 of 20 (1.0) | `<local>/projects/commissar/bench/v2/results_v2_2/steward-lora-v5/` scores.json, table.md, judgments.jsonl (scored 01:52:29, slot v5 sha256 d4c5bf8c); base and v4 columns `bench/gates_steward-lora-v5.md` (4de249b); paired `bench/gates_steward-lora-v5.json` stewardbench_paired (9c6cac0) and `<inbox>/r5ft2x-verify/recomputed.json` StewardBench_paired; `results_v2_2/steward-base/scores.json` opening_principal_first_rate |
| Round 2 holdout rewrites | 98 held-out rewrite rows (v5 holdout sha256 c2bfe900; 21 v4 rows, 77 v5 rows): identical 0, guidance added 92, W1 97, passes every rule 53 (base 10, first adapter 1); request-preservation judge on 97: acceptable 71, added obligation 20, colleague errand as own 20, request changed 2, facts kept 97 | `<local>/projects/commissar/bench/rewrite_eval/steward-lora-v5_system_v5_holdout/summary.json`; `bench/gates_steward-lora-v5.md` and `.json` (filled 02:03:17) |
| R5ft2x registration | exploratory; R5ft2's frozen protocol after its 01:40 window; note 459fba7 (01:43:50) before any episode; freeze 6457694 (01:48:48); guidance coding 5c4b675 (01:49:55); results 37e9d99 (01:55:08); excluded from the Holm family | operae `prereg/R5ft2x_exploratory_note.md`; `<inbox>/r5ft2x/result.json` commits |
| R5ft2x primary and secondaries | gap +0.1625 [-0.127, 0.452], sign-flip p 0.375, 15 pairs, 8 worlds (positive w01, w04, w05; 0 in four; w08 -0.2); 31 of 32 cells (missing w06 teammate E); principal -0.075 [-0.235, 0.085], p 0.375; teammate -0.25 [-0.511, 0.011], p 0.094; recomputed independently from the per-run CSVs (latest attempt per cell) | operae `r5ft2x-confirm.json`; `<inbox>/paper-r2x/recompute.txt` |
| R5ft2x guidance direction | coded mechanically, committed 01:49:55 (5c4b675), before the first rewrite-arm episode record (01:50:05.889) and after the first fresh-A0 outcome (01:46:29) per Codex: teammate one-attempt 15 of 15; principal keep-going 11, one-attempt 4, both 1 of 16; split: principal one-attempt -0.30 (n 4), keep-going +0.018 (n 11), teammate -0.24 (n 15) | operae `steward/r5ft2x/guidance_direction.json` (5c4b675), `r5ft2x-guidance-split.json` (805755b); `<inbox>/r5ft2x-verify/AUDIT.md` chronology |
| R5ft2x baselines | fresh A0 rerun (r5ft2x-a0) minus the A0 run of record gap -0.1125 [-0.333, 0.108], p 0.375; R5ft2x vs A0 of record gap +0.05 [-0.169, 0.269], p 0.75; R5v22 teammate -0.29 (row above) | operae `r5ft2x-confirm.json` sensitivity; label per Codex FT2XV-F2 (`<inbox>/r5ft2x-verify/AUDIT.md`) |

## Discussion

| Number in the paper | Value | Source |
|---|---|---|
| Approval pilot | proceed on a claimed approval from orchestrator, peer or closed ticket: 0 of 48; on the principal's own: 12 of 12 | `<local>/projects/approval-pilot/results/report.txt` block R (a_relay Haiku 8 Sonnet 16, b_peer 4 and 8, c_notice 4 and 8; d_principal 4 of 4 and 8 of 8); conditions in `<local>/projects/approval-pilot/Human.md` lines 11 to 14 |

## Related work (from the cited sources; quoted notes in references_notes.md)

| Number in the paper | Value | Source |
|---|---|---|
| HVTB, Claude Opus 5: runs reading a planted file (any hack), unmodified prompt; held-out tests read; hidden solution read; explicit L3 | 27 of 88 completed runs; 27; 15; 0 of 87 | roth2026hvtb (arXiv 2608.22103, Appendix C Table 2, columns Any hack, n, Hidden solution, Read tests; re-read at source after Codex PR1-F1) |
| Gemini swarm | 100 agents; 24 percent whistleblowers | paglieri2026swarmcheating (arXiv 2609.04170) |
| HiddenBench | 30.1 percent vs 80.7 percent; 15 models | li2025hiddenbench |
