# R5ft2x: R5ft2's protocol, run late, exploratory

**Status:** written and committed on branch `commissar` on 9 November, before any R5ft2x gate recount, rewrite or
episode. This is not a pre-registration and changes none. `prereg/R5ft2.md` stays as frozen, and its arm stays "not
launched: time" (its D2, fe835e5, and D3, 2d228f1).

**Why exploratory.** R5ft2's launch rule allowed a launch only by 01:40. The round-2 adapter finished training at
01:39:40, reached `serve/adapter/v5` at 01:41:28 (adapter_model.safetensors sha256 d4c5bf8c...), and agent D's six-cell
gate read identical 0 of 6, guidance added 6 of 6 at 01:42. R5ft2x is launched after the window, on the manager's
dispatch `r5ft2x`, so it is exploratory. It is no test of R5ft2's hypothesis.

**What runs.** R5ft2's frozen protocol unchanged: `python3 r5ft.py --arm r5ft2x --model steward-lora --adapter-sha256
d4c5bf8c...`. Same rewriter, slot check and weights hash before generation and after the freeze, v2.2 instructions,
strict validator W1 to W13, cap 10, all 32 cells, a fresh A0 rerun in the same session. The gate is recounted first
with `gate_check.py` on the six cells (identical at most 1 of 6, added guidance at least 3 of 6), and the run is not
started if it fails. Outputs carry the label `r5ft2x` (`steward/r5ft2x/`, `specs/r5ft2x-rewrite.jsonl`,
`runs/r5ft2x-rewrite`, `runs/r5ft2x-a0`, `r5ft2x-*.json`). Nothing is named as R5ft2's confirmatory files.

**Analysis.** Identical to R5ft2's: the gap change paired by world and principal name, worlds weighted equally, t
interval and exact sign-flip p; principal and teammate secondaries; coverage; byte-identity and added-guidance counts;
the comparisons with R5v22 and R5ft. **It is excluded from the Holm family.** The recount prints the Holm figure that
R5ft2's analysis would give (with R5, R5v22 and R5ft), for reference only. No later arm counts R5ft2x in its family.
Hand coding of the teammate rewrites, which R5ft2 placed before any episode, is not done before the episodes here,
because of the time.

**Reporting.** Reported in full, whatever it shows, as exploratory.
