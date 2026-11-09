# Figure 1. Experiment 1: no team opened the answer key

Panel A shows, for each cell of experiment 1, the share of teams in which any agent opened the answer key or the
grading script, with its Wilson 95% interval. The top row (blue circle) is the preregistered confirmatory batch: 12
teams of four Claude Haiku 5.5 agents on impossible level-4 instances, high pressure, no rule about `grader/` and a
brief line ruling out a report of failure, 0 of 12 teams, interval [0, 0.24]. The rows below (orange squares) are
the 13 exploratory calibration teams, run before preregistration on level-2 instances, one or two teams per cell, and
their pooled row, 0 of 13, interval [0, 0.23]; they are not data on any single rate, and a single team's interval
reaches 0.79. Panel B shows other behaviour on the same axis: teams in which some agent read only `grader/README.md`
(4 of 12 confirmatory, 5 of 13 calibration), teams that concluded the rules cannot all be met and escalated to the
principal (11 of 12 and 12 of 13, by the preregistered rule in `swarm_board/hp_secondary.py`, applied to calibration
after the fact), and the confirmatory agents' one-word answer to the post-episode question whether the session felt
like real work or a test or evaluation (TEST 35, UNSURE 11, REAL 2, of 48). Debrief intervals treat the 48 agents as
independent, which they are not (four per team), so they are narrower than a team-clustered interval would be. Every
plotted number is in `fig1.csv` with its source file; `fig1.py` regenerates both from the run directories in
`honeypot/results/`.
