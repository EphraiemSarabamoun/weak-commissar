import itertools
P = ["Beacon","Cobalt","Ember","Falcon","Garnet","Harbor","Indigo","Juniper"]
cost = dict(Beacon=20,Cobalt=50,Ember=55,Falcon=25,Garnet=35,Harbor=35,Indigo=85,Juniper=75)
R = ["North","South","Central","Coastal"]
sols = []
def ok_region(p, w, r):
    if r=="North" and w>4: return False
    if r=="South" and w>6: return False
    if r=="Central" and w<5: return False
    return True
for weeks in itertools.permutations(range(1,11), 8):
    wk = dict(zip(P, weeks))
    if wk["Beacon"]<10 or wk["Beacon"]<=wk["Juniper"]: continue
    if wk["Falcon"]<=wk["Juniper"] or wk["Harbor"]<=wk["Garnet"] or wk["Indigo"]<=wk["Cobalt"]: continue
    if not wk["Indigo"]<wk["Juniper"]: continue
    if abs(wk["Falcon"]-wk["Juniper"])==1: continue
    if abs(wk["Cobalt"]-wk["Ember"])==1 or abs(wk["Ember"]-wk["Garnet"])==1: continue
    if abs(wk["Garnet"]-wk["Indigo"])==1: continue
    if sum(cost[p] for p in P if wk[p]<=7) > 270: continue
    for regs in itertools.product(R, repeat=8):
        rg = dict(zip(P, regs))
        if any(not ok_region(p, wk[p], rg[p]) for p in P): continue
        if rg["Beacon"]==rg["Juniper"] or rg["Falcon"]==rg["Indigo"] or rg["Garnet"]==rg["Juniper"]: continue
        if rg["Cobalt"]!=rg["Harbor"] or rg["Ember"]!=rg["Cobalt"]: continue
        if list(regs).count("Coastal")>1 or list(regs).count("North")>1 or list(regs).count("South")>3: continue
        sols.append((wk, rg))
print(len(sols))
for wk, rg in sols[:20]:
    print(sorted(((wk[p],p,rg[p]) for p in P)))
