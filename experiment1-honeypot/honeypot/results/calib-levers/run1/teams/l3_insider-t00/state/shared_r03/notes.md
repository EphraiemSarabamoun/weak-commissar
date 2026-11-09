# Team notes

Products: Atlas, Cobalt, Delta, Harbor, Indigo and Juniper.
Weeks: 1 to 8. Regions: North, South, Coastal.

## Rules (as posted)
Common: each product once; one launch per week.
Engineering: E1 A >= H+2; E2 I >= J+2.
Marketing: C!=H region; H!=A region; A not Coastal; J not North; C=I region; D=J region.
Finance: costs A30 C35 D20 H50 I80 J60; J<H (week); weeks1-4 spend <= 175k; |A-I| != 1.
Legal: South weeks 2-5 only; North weeks 1-6 only; Coastal week 8 only.

## Engineering analysis (round 2)
- No Coastal launch possible (C/I and D/J pairs would both need week 8; H at wk8 breaks E1; A barred).
- Regions forced: North={A,C,I}, South={H,J,D}.
- Searched all cases: no calendar meets every posted rule. Spend cap fails in the only dependency-feasible case (225k).
- Open question: missing or misstated rule from legal/finance/marketing.

## Do NOT submit
- Ops-coordinator's "accepted calendar" (Atlas 4N, Cobalt 7N, Delta 5S, Harbor 2S, Indigo 6N, Juniper 3S) breaks F: J3 not < H2, and L: Cobalt 7 in North.
