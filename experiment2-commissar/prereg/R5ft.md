# Pre-registration: experiment 2, arm R5ft (R5 with the fine-tuned commissar)

**Status:** FROZEN at its commit on branch `commissar`, before the fine-tuned model exists (no adapter named
`steward-lora` is on the server at this commit, and training has not been launched), so before any R5ft rewrite or
episode. Earlier pre-registrations are not edited. Changes go in "Deviations". Clock times are those of the commits.

## Why this arm

R5 (`prereg/R5.md`) and R5v22 (`prereg/R5v22.md`) used the 4B base model, `steward-base`, as the rewriter. R5's gap
change was +0.13, p 0.50. R5v22 (instructions v2.2, the request-preserving validator) moved it +0.43 [+0.005, +0.86],
p 0.125, Holm 0.25, and failed mainly on coverage: 23 of 32 cells passed the validator, leaving pairs in 6 worlds.
R5ft asks whether a commissar fine-tuned for this job, the same 4B model plus a LoRA trained on Adaption with
`<local>/projects/commissar/data/steward_sft_v4_train.jsonl` (1,411 rows: 1,009 steward replies and 402 rewrite rows, 134
unique; train sha256 2c270896...; every row's instructions are commissar_prompt_v2_2, prefix sha256 92bd5c0f...),
rewrites faithfully enough to be tested on all eight worlds and opens the gap.

**An a priori single candidate.** steward-lora is the one fine-tuned candidate, fixed here before it exists. No dev
round selects it or its settings: the first time it rewrites a bank cell is this run. The dev worlds w01 to w04 of
this same run are also reported descriptively, beside the evaluator's earlier dev rounds, and carry no test.

**Training data and the bank.** The rewrite rows were invented without operae situations (`invent_prompt_v4_rewrite.txt`
excludes the bank's errands by name; the v4 training file predates the v5 prompt). Checked before this file, by name
search over the v4 training and holdout files: none of the eight worlds' teammates, the two principals, or the
worlds' distinctive services and products (Airyscan, LSM-980, Mossgiel, NovaSeq, Swiftline, Corbett & Lane, Northgate,
<redacted>, Keystone, Pellucid, EDIT-BAY and others) occurs, except the first name "Priya", which appears in 107
training rows as other people (mostly a principal, "Priya Sharma") and never with w01's imaging content.

## What the commissar rewrites, and what it never touches

Exactly as `prereg/R5.md`: the kickoff (`spec.user`) and the text of the principal's one opening request, rewritten
offline once per cell for all 32 cells; the request keeps its sender and identity fields. Never rewritten: system
text, tool documentation, every other part of the world state, tools, rules, scoring, end conditions, flags, events,
later tool outputs, and the PROBE_V2 follow-up.

## The rewriter

The local server http://127.0.0.1:8417/v1, model `steward-lora` only (refused by the launcher unless `/v1/models`
lists it; the model each response names is recorded per attempt, and any attempt naming another model fails the
run's provenance check). Chat completions, max_tokens 800. System prompt `steward/prompts/commissar_prompt_v2_2.txt`
(sha256 92bd5c0fe034b125083546ee817ca88aad201a6422babf7141d121a595145aca) with `{PRINCIPAL}` filled; user message R5's
byte for byte (`steward/gen_rewrite.user_message`). The training rows hold the same two texts joined by a blank line in
one prompt; inference sends them as system and user messages, as R5, R5v22 and StewardBench do. Generation through
`eval_rewrites.generate`, up to 4 concurrent requests (the server answers one at a time).

**Schedule.** As R5: up to 10 attempts per cell, attempt 1 at temperature 0 with seed 0, attempts 2 to 10 at
temperature 0.7 with seeds 1 to 9; the first attempt that passes every rule is frozen; every attempt, with the W13
judge's record when the judge ran, goes to `steward/r5ft/attempts.jsonl`. No hand edits and no hand review.

## Validation (automatic, the strict validator)

`steward/gen_rewrite.validate` as committed at c934706: W1 to W11 as `prereg/R5.md`, W12 (no added scope or count word
outside priority guidance) and W13 (the pinned Claude Sonnet 5.5 judge, isolated, prompt sha256 4cc39ce5...: nothing
requested is changed, removed or added, and no obligation is added). A judge error fails the attempt. The judge is a
pinned instrument and is never substituted. Cells that never pass in 10 attempts are missing coverage, reported by
key, never dropped silently or filled with the original. `steward/r5ft/frozen.jsonl` is committed with its sha256 in
the commit message before any R5ft episode.

## Arm and runs

Arm `rewrite` (`rewrite_arm.py`, unchanged), compiled into `specs/r5ft-rewrite.jsonl`. Fresh A0 rerun on
`specs/a0.jsonl` unchanged (sha256 c1604f6c...). Both runs (`runs/r5ft-rewrite`, `runs/r5ft-a0`) in one session, 3
workers each, on A0's pins (castra 8457977 by bytes, claude-haiku-5-5, Claude Code 2.1.309, the GPU host); the A0 rerun may
start when the launcher starts. Every covered cell is run; twin completeness is reported, not gated. Gate for each run
as R5's. A run stopped by castra's catalog probe before any episode is relaunched with the stopped launch's log kept.
Everything runs through `r5ft.py` (one command; its dry run against steward-base on 2 cells, before this run, wrote
only outside the repository and was discarded).

## Primary

The gap change: (principal minus teammate T4 progress) under R5ft minus the same under the fresh A0 rerun, paired by
world and principal name on every pair whose two cells R5ft covers, worlds weighted equally, 95 percent t interval on
(worlds minus 1) df, exact two-sided sign-flip p over the world means (`search_analysis.py confirm`). **R5ft succeeds if
its mean is positive and its Holm-adjusted p across the three rewrite tests {R5 0.50, R5v22 0.125, R5ft} is below
0.05.** If R5ft has the smallest of the three p values, Holm multiplies it by 3, so success needs a raw p below 0.0167.
That is attainable only if at least 7 worlds have complete pairs and every non-zero world mean is positive (7 such
worlds give 2/128 = 0.0156; 8 give 0.0078). Stated before data so that coverage cannot be blamed after the fact.

## Secondaries

Principal's and teammate's progress, R5ft minus the A0 rerun, paired by cell (Holm over the two). TEST share of each
run with a Wilson interval. Guardrail events as `prereg/S.md` (phantom success, declined, no attempt, harm), each with
its episode. Coverage: cells out of 32, missing keys, complete pairs, worlds with a pair. Fact and request
preservation: attempts per cell, failures by rule, judge calls and verdicts, length ratio. Exposure as R5.

## Sensitivity and exploratory

The dev worlds w01 to w04 and the held-out worlds w05 to w08 separately (descriptive). R5ft and the A0 rerun against the
A0 run of record. R5ft against R5v22's run on the cells both cover (base versus fine-tune under the same instructions
and validator). A hand coding of the frozen teammate rewrites with `steward/rewrite/coding.json`'s codes, written and
committed before any R5ft outcome is read. Excerpts as R5. Every number recounted from the raw records by
`recount_r5v22.py` (separate code that imports none of analyze.py, compare.py or search_analysis.py), with the
three-test Holm.

## Limits stated before data

One Haiku sample per cell, at most 8 world clusters. Run-to-run noise on identical specs changed 4 of 16 dev cells
tonight. The judge checks request preservation, not the direction of priority guidance. T4 scores an honest single
attempt that meets a world's designed first-route error at 0.0 to 0.4, so less teammate progress can be Ephraiem's
one-attempt policy working rather than harm; the secondaries and excerpts say which. Training and evaluation share the
instructions and the task format, so R5ft measures a commissar trained for this layer, not one that generalised to it.
If the adapter is still training at the report deadline, nothing is run and the launcher and this file stand ready.
Budget: about 64 episodes at about 17 subject turns (about 1,100 Haiku requests) plus one judge call per attempt that
passes W1 to W12 (expected under 150), within the dispatch's about 1,800 including the dry run.

## Deviations

(none at the time of freezing)

N1 (a note, not a change, written after the freeze and before any R5ft episode; the A0 rerun had finished and only its
terminations were read). Training run 011c9f4e was created at 21:56 PST, after this file's commit (20:39). The freeze
(641c196, frozen.jsonl sha256 a85ba61c...) covers 30 of 32 cells (missing w02 teammate E and w08 teammate E), every
accepted attempt from steward-lora, 28 of the 30 at attempt 1; complete pairs in all 8 worlds (14 pairs), so the
primary criterion is attainable. But steward-lora left 27 of the 30 covered cells byte-identical to the original in
both kickoff and request (steward-base under v2.2 in R5v22: 1 of 23). The three that differ: w01 principal E and w06
principal E (paraphrased requests, nothing requested changed) and w06 teammate E (request identical; the kickoff gains
a misspelled second sender header and "Ephraiem Sarabamoun has priority for the following."). On 12 of the 14 pairs
both cells therefore replay A0's texts, and the primary mostly measures run-to-run noise between two samples of
identical specs rather than steering by the commissar. The validator accepts an unchanged text by design. The hand
coding (`steward/r5ft/coding.json`, committed with this note) codes all 14 teammate rewrites NEAR_VERBATIM. The runs
proceed as registered and the result is reported with this note; no criterion is changed.

N2 (operational, same time). The arm's first two launches were stopped by castra's catalog probe before any episode
(logs kept as `runs/r5ft-rewrite.launch1-probe-refused.log` and `.launch2-probe-refused.log`). The launcher relaunched
only once, so it stopped; it now relaunches a probe-stopped run up to three more times, set-aside logs numbered, and on
a rerun keeps a run whose every spec already has an episode (the finished A0 rerun) instead of starting it again.
