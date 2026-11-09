# Combined-rules analysis (marketing)

Rules combined from all four departments (as posted on board):
- Marketing: C!=H region; H!=A region; A not Coastal; J not North; C==I region; D==J region.
- Legal: South weeks 2-5; North weeks 1-6; Coastal week 8 only.
- Finance: cost J<H week; weeks 1-4 spend <=175k (A30,C35,D20,H50,I80,J60); |A-I| != 1.
- Engineering: A >= H+2; I >= J+2.
- Global: one launch per week, each product once.

Derivation:
1. J not North, Coastal only week 8 and J<H<=8 -> J is South, weeks 2-5. D is South too.
2. A <= 6 (not Coastal) and A >= H+2 -> H in {3,4}; J<H -> J in {2,3}.
3. I >= J+2 >= 4. I in Coastal would need week 8 and C also week 8 -> impossible. So I,C in N or S.
4. Case analysis: I=5 or I=6 leads to contradiction on A. I=4 forces H=3, J=2, A=6 (N), H=S, D=5 (S), C=N week 1.
5. Only candidate: 1 C North | 2 J South | 3 H South | 4 I North | 5 D South | 6 A North.
   Weeks 1-4 spend = 35+60+50+80 = 225k > 175k cap (breaks finance rule (2) by 50k).

Conclusion: under the posted rules, no calendar meets all rules. Finance and Legal/Engineering to re-verify exact rule wording before any submission.
