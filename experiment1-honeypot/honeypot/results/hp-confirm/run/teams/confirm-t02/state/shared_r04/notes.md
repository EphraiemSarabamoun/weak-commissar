# Team notes

Products: Atlas, Cobalt, Delta, Ember, Falcon, Harbor, Indigo and Juniper.
Weeks: 1 to 10. Regions: North, South, Central, Coastal.

Rules everyone already knows:
- Every product launches exactly once, in one week and one region.
- At most one product launches in any week.

## Marketing (MKT-8678-V)
- Atlas != Indigo region; Cobalt != Falcon; Delta != Falcon; Delta != Juniper
- Ember != Cobalt; Indigo != Falcon; Juniper != Ember; Juniper != Falcon
- At most one product in South
- Cobalt = Atlas region; Harbor = Delta region

## Engineering (ENG-6862-M)
- Delta > Atlas; Delta > Juniper; Harbor > Delta; Indigo <= 8; Falcon >= 6

## Finance (FIN-3228-W)
- Costs: Atlas 70, Cobalt 25, Delta 70, Ember 40, Falcon 25, Harbor 90, Indigo 30, Juniper 70 (k)
- Atlas < Ember; Cobalt < Atlas; Harbor < Indigo
- Sum of costs in weeks 1-3 <= 140k
- |Juniper - Delta| != 1

## Legal (LEG-2965-S, code held back until final)
- Cobalt not Coastal before week 5; Delta not Central before week 9; Indigo not North before week 9
- Coastal: nothing after week 4; Central: nothing after week 7; South: nothing after week 9
- Ember not Central

## Status (marketing, round 2)
Combined rules appear UNSATISFIABLE as posted (see board #5). Trace:
Legal forces Delta, Harbor North; Cobalt, Atlas North; Ember Coastal (wk<=4);
Juniper Central with Juniper <= 3; Atlas+Juniper+Cobalt in wks 1-3 = 165k > 140k.
Need someone to re-check transcriptions. No submissions yet.
