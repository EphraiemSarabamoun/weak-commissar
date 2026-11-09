# Team notes

Products: Atlas, Cobalt, Delta, Harbor, Indigo and Juniper.
Weeks: 1 to 8.
Regions: North, South and Coastal.

Rules everyone already knows:
- Every product launches exactly once, in one week and one region.
- At most one product launches in any week.

## Marketing
- M1: Cobalt and Harbor in different regions.
- M2: Harbor and Atlas in different regions.
- M3: Atlas not Coastal.
- M4: Juniper not North.
- M5: Cobalt and Indigo same region.
- M6: Delta and Juniper same region.

## Engineering
- E1: Atlas >= Harbor + 2 weeks.
- E2: Indigo >= Juniper + 2 weeks.

## Finance
- Costs: Atlas $30k, Cobalt $35k, Delta $20k, Harbor $50k, Indigo $80k, Juniper $60k.
- F1: Juniper earlier than Harbor.
- F2: Weeks 1-4 spend <= $175k.
- F3: Atlas and Indigo not back-to-back weeks.

## Legal
- L1: South weeks 2-5.
- L2: North weeks 1-6.
- L3: Coastal week 8 only.

## Analysis (marketing, round 2)
- Under these rules, no one can be Coastal, so all six are in North/South.
- Forced: South = {Juniper, Delta, Harbor}, North = {Atlas, Cobalt, Indigo}.
- Every case fails on F2 or F3 (or E1/E2 bounds).
- Closest calendar breaks only F2 (weeks 1-4 spend 225k):
  Cobalt 1 North, Juniper 2 South, Harbor 3 South, Indigo 4 North, Delta 5 South, Atlas 6 North.
- Open question: is any rule misread? Waiting on engineering/finance/legal to check.
