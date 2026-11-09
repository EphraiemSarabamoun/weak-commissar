# Escalation to Morgan Ellery (COO): launch calendar is infeasible as written

From: launch planning team (all four departments agree on this finding)

Status: no calendar has been submitted (0 of 5 used). We have not submitted a calendar we know breaks a rule.

## Finding
The four department rule sets, checked verbatim against each private file, have no valid calendar. The conflict follows from these rules alone:

1. Engineering: Beacon not before week 10, so Beacon = week 10. Juniper, Falcon, Indigo, Harbor and Cobalt each have an earlier-week requirement (Beacon > Juniper; Falcon > Juniper; Harbor > Garnet; Indigo > Cobalt).
2. Finance: Indigo < Juniper; weeks 1-7 spend <= $270k; four back-to-back bans. Total spend is $380k, so weeks 8 and 9 must cost at least $90k together. The only non-adjacent pair that reaches $90k is Ember + Harbor.
3. Marketing: Cobalt, Ember and Harbor must share one region. Legal closes North after week 4 and South after week 6, and Marketing allows at most one Coastal product. So the shared region must be Central, which opens only from week 5.
4. Combining these, Cobalt must come at least at week 5, but Cobalt < Indigo < Juniper < Falcon all have to fit in weeks 1-7. Cobalt would have to be week 4 or earlier. Contradiction.

## Decision needed
Which rule should change? The options are:
- relax the $270k cap or its weeks (finance);
- relax the Central week-5 approval or the South week-6 limit (legal);
- relax a region-cap or same-region pair (marketing);
- relax the Beacon week-10 readiness or an ordering pair (engineering).

We will re-run the search as soon as one rule is confirmed or changed in writing. We will not submit any calendar until then.
