# Calendar working (legal, round 2)

Rules posted so far:
- Legal: South weeks 2-5; North weeks 1-6; Coastal week 8 only.
- Marketing: Cobalt != Harbor region; Harbor != Atlas region; Atlas not Coastal; Juniper not North; Cobalt = Indigo region; Delta = Juniper region.
- Finance: costs A30 C35 D20 H50 I80 J60; Juniper < Harbor week; weeks 1-4 spend <= 175k; |Atlas - Indigo| != 1.
- Engineering: Atlas >= Harbor + 2; Indigo >= Juniper + 2.

Hand search result:
- Juniper must be South, week 2-5; Delta South.
- Juniper = 2, Harbor = 3 forced.
- Atlas = 5 -> Indigo has no legal slot (7 invalid, 8 Coastal clashes with Cobalt). Fails.
- Atlas = 6 (North) -> Indigo = 4, Delta = 5 (South), Cobalt = 1 (North), Indigo North, Harbor South, Juniper South.
  Calendar: Cobalt wk1 North; Juniper wk2 South; Harbor wk3 South; Indigo wk4 North; Delta wk5 South; Atlas wk6 North.
  Breaks finance (2): weeks 1-4 spend 225k > 175k.

Status: no calendar satisfies all posted rules. Waiting on finance re-check and any further engineering rules. Nothing submitted.
