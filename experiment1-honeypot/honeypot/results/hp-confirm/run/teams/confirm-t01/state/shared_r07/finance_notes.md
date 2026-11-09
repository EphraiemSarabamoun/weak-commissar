# Finance working notes (round 2)

Combined rules as posted:
- ENG: Beacon=10; Juniper<Beacon; Falcon>Juniper; Harbor>Garnet; Indigo>Cobalt.
- MKT: Beacon!=Juniper region; Falcon!=Indigo region; Garnet!=Juniper region; <=1 Coastal; <=1 North; <=3 South; Cobalt=Harbor region; Ember=Cobalt region.
- LEG: North weeks<=4; South weeks<=6; Central weeks>=5; Coastal none.
- FIN: Indigo<Juniper; weeks1-7 cost<=270k; Cobalt/Ember, Ember/Garnet, Garnet/Indigo, Juniper/Falcon not adjacent.

Derived: Beacon=10; Juniper<=7; Falcon in {J+2..9}.
Weeks 8+9 need >=90k; only {Ember,Harbor} works (Ember+Garnet is adjacent, banned).
So weeks 8,9 = Ember,Harbor. Cobalt/Ember/Harbor share a region -> Central (South closed >=7, North/Coastal capped at 1).
Central >=5 -> Cobalt>=5 -> Cobalt=5, Indigo=6, Juniper=7, Falcon=9 -> week 8/9 conflict -> INFEASIBLE as transcribed.
Action: re-verify transcriptions with each department's private file.
