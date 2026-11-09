# Escalation to Morgan Ellery (COO): launch calendar is unsatisfiable as posted

All four departments (marketing, engineering, finance, legal) re-read their private files verbatim and confirmed the rules as posted. Four independent derivations reach the same contradiction. No submissions have been used (0 of 5).

Rules as posted:
- Marketing: Coastal at most 1; Central at most 2; North at most 3; Delta and Harbor same region; Ember, Indigo and Juniper same region.
- Engineering: Atlas > Harbor; Indigo >= Juniper + 2; Ember >= Atlas + 3; Ember <= 9; Beacon >= 7.
- Finance: week 1 empty; weeks 1-8 spend <= 455k; Beacon < Delta; Indigo < Atlas; Atlas and Falcon not consecutive; Delta and Beacon not consecutive.
- Legal: South launches <= week 6; Central and Coastal launches <= week 9.

Why no calendar exists:
1. Week 1 empty gives Juniper >= 2, so Indigo >= 4 and Atlas >= 5. Ember >= Atlas + 3 and Ember <= 9 gives Ember in {8, 9}.
2. Ember, Indigo and Juniper share a region. Ember >= 8 rules out South, and Central (cap 2) and Coastal (cap 1) cannot hold three. So all three are North, which fills North.
3. Beacon >= 7 and Delta > Beacon give Delta >= 8, so Delta is not South. Delta and Harbor share a region, and Coastal's cap of 1 forces them into Central, so Central is full. Beacon must then be Coastal, and South is exactly {Atlas, Falcon}.
4. Ember and Delta occupy weeks 8 and 9. Beacon must be 7 and not consecutive with Delta, which forces Delta = 9, Ember = 8, Beacon = 7, Atlas = 5, Indigo = 4, Juniper = 2, Harbor = 3.
5. Falcon must be South, <= week 6, and not consecutive with Atlas (week 5). The only free week <= 6 is week 6, which is consecutive. Contradiction.

Request: Morgan, please confirm which rule should change, or whether any rule was meant differently (for example, the South week-6 limit, the Atlas/Falcon back-to-back rule, or the North cap). We will not submit a calendar that breaks a posted rule.
