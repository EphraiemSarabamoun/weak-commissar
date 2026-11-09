# Figure 2: every arrangement of the commissar on operae v0.2 (Experiment 2)

**What it shows.** For each arrangement, panel A gives the change in T4 progress (0 to 1) on the principal's errand
(blue circles) and on a teammate's errand (orange squares), and panel B the change in the gap between them (principal
minus teammate). Each is paired by world and principal name with its reference, weights each world equally and
carries a 95 percent t interval over worlds. A1, A1L and A1E put the commissar's message on the team chat (faithful,
principal-first, and principal-first after the principal's endorsement). A1W is the principal's own one-line wish
with no commissar. R2 to R4, shaded, are the exploratory search: one commissar-written text per principal name,
forwarded by the principal (R2), posted by a steward the operator appoints (R3), or set as the agent's system-prompt
policy (R4). R5, the preregistered a priori primary, has the commissar rewrite the task before the agent reads it, and
R5v22, the second preregistered rewriting test, does the same with version 2.2 instructions and the request-preserving
validator.

**References and coverage.** A1 to A1W and R2 to R4 are compared with the A0 run of record. R5 and R5v22 are each
compared with their own fresh A0 rerun made in the same session (those reruns' gaps differed from the record's by 0.125
and 0.075). The arms cover 16, 14, 12, 32, 32, 32, 32, 29 and 23 of 32 cells. R5's gap rests on 13 twin pairs in 7
worlds, and R5v22's on 9 pairs in 6 worlds.

**Reading.** In panel B, only A1W's gap change (+0.54, 0.28 to 0.79) meets its preregistered test, and it opens the gap
mostly by lowering effort on the teammate's errand. R5v22's gap interval (+0.43, 0.005 to 0.86) excludes zero, but its
preregistered exact sign-flip test does not (p 0.125; Holm 0.25 across R5 and R5v22 as registered, 0.375 across R5, R5v22
and R5ft), so its criterion is not met. R5ft, the third rewriting test, is not plotted (paper Section 3). No
other arrangement's gap interval excludes zero. In panel A, the intervals for R5's principal change (+0.20, 0.0002 to
0.40) and R5v22's teammate change (-0.29, -0.57 to -0.01) exclude zero, but both are secondaries whose corrected
sign-flip tests are not significant (Holm 0.125 each). Codex reproduced R5v22's numbers (r5v22-verify).

**Data.** `figures/fig2.csv` (one row per plotted number, with its source file and key); script `figures/fig2.py`,
which reads operae branch `commissar` read-only.

**Regenerate.** Regenerate with `python3 figures/fig2.py` from the paper repository; it reads operae branch commissar (results through 0f634d8) read-only and is deterministic.
