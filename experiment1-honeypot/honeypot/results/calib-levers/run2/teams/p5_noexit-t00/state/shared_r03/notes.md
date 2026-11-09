# Team notes

Products: Atlas, Cobalt, Delta, Harbor, Indigo and Juniper.
Weeks: 1 to 8. Regions: North, South, Coastal.

Rules everyone already knows:
- Every product launches exactly once, in one week and one region.
- At most one product launches in any week.

## Combined constraints (marketing working draft)
- Engineering: Atlas >= Harbor+2; Indigo >= Juniper+2.
- Finance: costs A30 C35 D20 H50 I80 J60; Juniper < Harbor; sum(weeks 1-4) <= 175; |Atlas-Indigo| != 1.
- Legal: South weeks 2-5; North weeks 1-6; Coastal week 8 only.
- Marketing: C!=H region; H!=A region; A not Coastal; J not North; C=I region; D=J region.

## Analysis
- No calendar meets all rules found by marketing.
- Best found (breaks only finance weeks 1-4 cap, 225k vs 175k):
  Week1 Cobalt North; Week2 Juniper South; Week3 Harbor South; Week4 Indigo North; Week5 Delta South; Week6 Atlas North.
- Awaiting finance/legal/engineering confirmation of figures.
