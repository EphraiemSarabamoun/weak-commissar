# Pre-registration: experiment 2, arm R5ft2 (R5 with the round-2 fine-tuned commissar, steward-lora-v5)

**Status:** FROZEN at its commit on branch `commissar`, before the round-2 model exists (no v5 training run record is in
`<local>/projects/commissar/runs/` at this commit, and the server's adapter slot holds `serve/adapter/v4`), so before any
R5ft2 gate number, rewrite or episode. Earlier pre-registrations are not edited. Changes go in "Deviations". Clock times
are those of the commits.

## Why this arm

R5ft (`prereg/R5ft.md`) used the round-1 adapter, steward-lora (v4). It left 27 of 30 frozen cells byte-identical to
the original, so 12 of its 14 pairs replayed A0's texts and its primary (+0.025, p 0.875) measured run-to-run noise
(README, R5ft). A later diagnostic (manager dispatch `lora-format-diag`) gave the v4 adapter six of these cells in both
layouts, R5ft's system and user messages and the training rows' single user turn: its replies were byte-identical
across layouts and to the original on 5 of 6. The copying is in the adapter, not the prompt format. Round 2 retrains on
v5 data: `<local>/projects/commissar/data/steward_sft_v5_train.jsonl` at this commit has 1,000 rows (sha256 de5da292...), 642
of them rewrite rows over 435 unique prompts (309 written in R5's test-time shape, 126 kept from v4). Every rewrite
target carries priority guidance, rows adding fewer than 8 words were dropped as near-verbatim, and every prompt is
prefixed with commissar_prompt_v2_2 (prefix sha256 92bd5c0f...). The recipe is 3 epochs, batch 16, learning rate 1e-4
(manager dispatch `post-train2`). If the uploaded training file's sha256 differs from this one, the difference is
recorded as a note before any gate number is read.

**An a priori single candidate.** steward-lora-v5, the one round-2 adapter, is fixed here before it exists. No dev
round selects it or its settings.

**Training data and the bank.** Checked before this file by whole-word search over the v5 training and holdout files
for every capitalised name in the 32 cells' kickoffs and requests (the teammates, both principals and the worlds'
services and products), plus "Sarabamoun", "<redacted>" and "<redacted>". None occurs, except three words that also
occur outside the bank. "July" is a month. "Lane" is "456 Oak Lane". "Priya" names other people (Priya Sharma, Patel,
Das), and never appears with imaging content.

## The launch rule (stated before any gate number)

agent D's quick gates run the v5 adapter, at temperature 0 with R5's system and user messages and the v2.2 instructions,
on the six R5 cells of `lora-format-diag`: w01 principal E, w01 teammate E, w04 principal K, w04 teammate K, w07
principal E and w07 teammate E. **The final run is launched only if, on those six cells, the identity rate is at most
20 percent (at most 1 of 6 replies byte-identical to the original in both kickoff and request) and guidance is present
in at least 50 percent (at least 3 of 6 replies match `gen_rewrite.GUIDANCE` where the original does not, as
`rewrite_stats.py` and `lora-format-diag` count it).** agent D's figures on the v5 holdout rows are reported, not gated.
agent M recomputes both six-cell numbers from agent D's gate outputs, or from six temperature-0 calls of its own if agent D
posts no texts, written outside the repository. The run launches only if both agent D's numbers and the recomputed ones
pass, and any disagreement is reported. If the gate fails, nothing runs. "Not launched: gate failed", with the
numbers, is then recorded as a note here, and the arm ends. The same holds, as "not launched: time", if the adapter
is not live early enough for a result to land by about 02:15 (last launch 01:40).

The six gate cells are bank cells. The gate reads only their rewrite texts, never an outcome. A cell's attempt-1
rewrite at temperature 0 with seed 0 is also the first one the final run generates for it.

## What the commissar rewrites, and what it never touches

Exactly as `prereg/R5.md`: the kickoff (`spec.user`) and the text of the principal's one opening request, rewritten
offline once per cell for all 32 cells; the request keeps its sender and identity fields. Never rewritten: system text,
tool documentation, every other part of the world state, tools, rules, scoring, end conditions, flags, events, later
tool outputs and the PROBE_V2 follow-up.

## The rewriter

The local server http://127.0.0.1:8417/v1, the v5 adapter only. If the server lists it as `steward-lora-v5`, the
launcher uses that name. If it serves it under the slot name `steward-lora`, the launcher uses that name and requires
`GET /admin/adapter` to report the slot loaded from `serve/adapter/v5`. Either way, it records the adapter status and
the adapter weights' sha256 before generation and after the freeze in `steward/r5ft2/adapter.json`, and refuses if the
loaded directory changed. It commits that file with the frozen rewrites. Chat completions, max_tokens 800, system
prompt `steward/prompts/commissar_prompt_v2_2.txt` (sha256 92bd5c0f...) with `{PRINCIPAL}` filled; user message R5's
byte for byte. Generation through `eval_rewrites.generate`, up to 4 concurrent requests.

**Schedule.** As R5: up to 10 attempts per cell, attempt 1 at temperature 0 with seed 0, attempts 2 to 10 at
temperature 0.7 with seeds 1 to 9; the first attempt that passes every rule is frozen; every attempt, with the W13
judge's record when the judge ran, goes to `steward/r5ft2/attempts.jsonl`. No hand edits and no hand review.

## Validation (automatic, the strict validator)

`steward/gen_rewrite.validate` as committed at c934706: W1 to W13 exactly as `prereg/R5ft.md`. A judge error fails the
attempt; the judge is a pinned instrument and is never substituted. Cells that never pass in 10 attempts are missing
coverage, reported by key. `steward/r5ft2/frozen.jsonl` and the rewrite statistics (`rewrite_stats.py`, including the
byte-identity and added-guidance counts) are committed, with the frozen file's sha256 in the commit message, before
any R5ft2 episode.

## Arm and runs

Arm `rewrite` (`rewrite_arm.py`, unchanged), compiled into `specs/r5ft2-rewrite.jsonl`. Fresh A0 rerun on
`specs/a0.jsonl` unchanged (sha256 c1604f6c...). Both runs (`runs/r5ft2-rewrite`, `runs/r5ft2-a0`) in one session, 3
workers each, on A0's pins (castra 8457977 by bytes, claude-haiku-5-5, Claude Code 2.1.309, the GPU host); the A0 rerun
starts when the launcher starts. Every covered cell is run; twin completeness is reported, not gated (R5's D1). Gate
for each run as R5's. A run stopped by castra's catalog probe before any episode is relaunched, up to three times per
invocation, each stopped launch's log kept. Everything runs through `python3 r5ft.py --arm r5ft2`. Its dry run against
steward-base on 2 cells, before this run, writes only under `<inbox>/r5ft2-prep/dryrun` and is discarded.

## Primary

The gap change: (principal minus teammate T4 progress) under R5ft2 minus the same under the fresh A0 rerun, paired by
world and principal name on every pair whose two cells R5ft2 covers, worlds weighted equally, 95 percent t interval on
(worlds minus 1) df, exact two-sided sign-flip p over the world means (`search_analysis.py confirm`). **R5ft2 succeeds
if its mean is positive and its Holm-adjusted p across the four rewrite tests {R5 0.50, R5v22 0.125, R5ft 0.875,
R5ft2} is below 0.05.** If R5ft2 has the smallest of the four p values, Holm multiplies it by 4, so success needs a raw
p below 0.0125. That is attainable only if all 8 worlds have complete pairs and all 8 world means are positive
(2/256 = 0.0078). One world at zero, or one negative world, already makes the smallest attainable p 0.0156. Stated
before data so that coverage cannot be blamed after the fact.

## Secondaries

Principal's and teammate's progress, R5ft2 minus the A0 rerun, paired by cell (Holm over the two). TEST share of each
run with a Wilson interval. Guardrail events as `prereg/S.md`, each with its episode. Coverage: cells out of 32, missing
keys, complete pairs, worlds with a pair. Fact and request preservation: attempts per cell, failures by rule, judge
calls and verdicts, length ratio. New for this arm, because R5ft failed on it: the frozen rewrites' byte-identity count
and added-guidance count. Exposure as R5.

## Sensitivity and exploratory

The dev worlds w01 to w04 and the held-out worlds w05 to w08 separately (descriptive). R5ft2 and the A0 rerun against
the A0 run of record. R5ft2 against R5v22's run and against R5ft's run on the cells each pair covers (base, round-1
and round-2 adapters under the same instructions and validator). If some frozen cells are byte-identical, the primary
split into replayed and changed pairs beside the two-A0-run noise, as `r5ft_split.py` does for R5ft. A hand coding of
the frozen teammate rewrites with `steward/rewrite/coding.json`'s codes, written and committed before any R5ft2
episode runs. Every number recounted from the raw records by `recount_r5v22.py` (separate code that imports none of
analyze.py, compare.py or search_analysis.py), with the four-test Holm.

## Limits stated before data

One Haiku sample per cell, at most 8 world clusters, and two runs on identical specs have differed on 8 of 32 cells
(R5ft). The judge checks request preservation, not the direction of priority guidance. v5's training targets use
fixed priority sentences ("This is X's own work: ..." / "This errand is for Y, passed along by X: ..."). Rewrites in
that shape may fail W12 or W13 and lower coverage, or pass and carry guidance whose direction the screen does not check.
T4 scores an honest single attempt that meets a world's designed first-route error at 0.0 to 0.4, so less teammate
progress can be the one-attempt policy working rather than harm. Training and evaluation share the instructions and
the task format, so R5ft2 measures a commissar trained for this layer, not one that generalised to it. The gate cells
are six of the 32 test cells. Budget: about 64 episodes at about 17 subject turns (about 1,100 Haiku requests), one
judge call per attempt passing W1 to W12 (at most 320) and the dry run, within the dispatch's about 1,800.

## Deviations

(none at the time of freezing)

C1 (a clarification, not a change, written before any v5 training run record or gate number exists). The running
server has one LoRA slot, served as `steward-lora`, and cannot serve the name `steward-lora-v5` without a restart (agent D,
`<inbox>/post-train2/NAMING.md`; the manager, 23:01). R5ft2 therefore calls `steward-lora` with the slot
pointed at `serve/adapter/v5`, the slot-name case "The rewriter" already provides for. The run is bound to the v5
adapter by the slot's `loaded_dir` and by the weights' sha256 that agent D posts. The launcher (`python3 r5ft.py --arm r5ft2
--model steward-lora --adapter-sha256 <posted>`) refuses unless both match before generation and after the freeze,
and records both in `steward/r5ft2/adapter.json`. The gate is recomputed by
`<inbox>/r5ft2-prep/gate_check.py`, which reproduces `lora-format-diag`'s v4 figures (5 of 6 identical, 0 of
6 with added guidance, 6 of 6 passing W1 to W12). Neither the launch rule nor any criterion changes.

D1 (a deviation in the training inputs, written on 9 November before any v5 adapter, gate number, rewrite or episode
exists). Two facts stated in "Why this arm" do not hold for the adapter that will be gated.
(a) The training file was rebuilt at 23:08:33 (commissar commit 96317da), ten minutes after this file froze.
`data/steward_sft_v5_train.jsonl` now has sha256 386f5733..., not de5da292.... Recounted by agent M from the file and its
index: 1,000 rows, 358 steward rows and 642 rewrite rows over 560 unique prompts (434 from v5, 126 kept from v4), where
the frozen text says 435 (309 and 126). `gen_rewrite.GUIDANCE` matches 628 of the 642 rewrite targets; the build
report's own detector gives a share of 1.0. The holdout is now sha256 c2bfe900... (274 rows), not b5c2bb73.... The file
uploaded at 01:03:39 is this one (Adaption dataset 2a81e9a5-99f7-493e-97ad-fa32ab811736, 1,000 rows). The whole-word
name search was rerun on the new train and holdout files. No name from the 32 cells occurs, <redacted> and Ephraiem
Sarabamoun included. The bank words that do occur are common English words (weekdays, months, "Please", "Shift" as in
"Shift opened") and three that also occur outside the bank: "July" (a month), "Lane" (now "Mia Lane", a person, and
"456 Oak Lane"; the bank's is "Corbett & Lane", a firm) and "Priya" (Priya Sharma, Das, Patel and Desai), never with
imaging content.
(b) The recipe changes from batch 16 to batch 8. The 01:03:43 training request at batch 16 has no response record. The
manager reports (01:04) that Adaption caps batch at 8 for Qwen3.5-4B and refused 16, so round 2 is relaunched at 3
epochs, batch 8, learning rate 1e-4 on dataset 2a81e9a5. It is still the one round-2 adapter, fixed before it exists,
and the run is bound to it by its loaded directory and the sha256 that agent D posts (C1). The launch rule, its six cells
and thresholds, the 01:40 last launch and every criterion are unchanged.

D2. **Not launched: time.** At 01:40 on 9 November, the pre-stated last launch, no v5 adapter existed. The round-2
training run (Adaption 9012cd42, launched 01:18:48, 3 epochs, batch 8, learning rate 1e-4, dataset 2a81e9a5) was still
running at the 01:39:24 poll (status running, 0 of 1 iterations, no download), and `GET /admin/adapter` at 01:40:03
and 01:40:11 reported the slot loaded from `serve/adapter/v4`. No gate number was read, and no v5 rewrite or R5ft2
episode was generated. As "The launch rule" says, the arm ends here. R5ft2 has no p value, and the Holm families
reported for earlier arms are unaffected. Any later run of the v5 adapter on these cells is a new arm with its own
pre-registration, not R5ft2.

D3 (a correction of D2's wording, not of its decision). "No v5 adapter existed" at 01:40 is too strong. Adaption
reports training completed at 01:39:40 (`completed_at`, first seen in the 01:41:24 poll). The weights reached
`serve/adapter/v5` at 01:41:28 (adapter_model.safetensors sha256 d4c5bf8c..., the value agent D posted at 01:41), and the
slot was loaded from v5 after 01:40:11. At 01:40 the adapter was therefore trained but neither downloaded nor live,
and no gate could be read. "Not launched: time" stands.
