"""Sammenligner agenten vår med agenten i grenen Barz, på nøyaktig de samme sakene.
Bruker lagrede svar fra begge, ingen API-kall. Kjøres etter at testresultatene er kjent, så dette er en beskrivelse, ikke en ny test.
Bruk: python src/analyse/sammenlign_med_barz.py <mappe med agent_forklaring.csv fra grenen Barz>"""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.metrics import average_precision_score
sys.path.insert(0, "src")
import evaluer as e
pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 90)
mappe = Path(sys.argv[1])
B = pd.read_csv(mappe / "agent_forklaring.csv", dtype=str, keep_default_na=False)
d = e.last(); _, te = e.splitt(d, "test")
p = pd.read_csv("resultater/pred_test.csv", dtype=str, keep_default_na=False); x = te.merge(p, on="rad_id", validate="one_to_one")
nk = lambda s: s.str.lower().str.replace(r"[^a-z0-9]", "", regex=True)
for q, c, dt, f in [(x, "company", "meeting_date", "proposal_text"), (B, "utsteder", "moetedato", "forslag")]:
    q["n"] = nk(q[c]) + "|" + q[dt] + "|" + nk(q[f]); q["nr"] = q.groupby("n").cumcount()
m = x.merge(B, on=["n", "nr"], how="inner", suffixes=("", "_b")); print(f"Barz: {len(B)} saker | vår test: {len(x)} | felles: {len(m)} | Barz uten treff hos oss: {len(B) - len(m)}, første dato {B.moetedato.min()}")
y = (m.y == 1).to_numpy(); G = m.meeting_id.to_numpy(); print(f"Felles saker: {len(m)}, mot styret {y.sum()} ({y.mean():.1%}), møter {m.meeting_id.nunique()}, fra {m.meeting_date.min()} til {m.meeting_date.max()}")
k = m.konfidens.astype(float).to_numpy(); vf = ((m.raastemme != "") & (m.raastemme != m.mgmt_rec)).to_numpy(); r_v = np.where(vf, k, 1 - k); r_b = m.p_mot.astype(float).to_numpy()
ur = (m.pred_mot_uten_menneske == "1").to_numpy(); bf = (m.pred_mot == "1").to_numpy(); bh = (m.rute != "AGENT").to_numpy()
vh = ((k < .8) | (m.mistenkelig_instruks == "True").to_numpy() | (vf & (m.regel_id == "0.0").to_numpy())); ve = vf & ~vh
def l(n, f):
    r = e.maal(y, f, G); print(f"  {n:46s} flagg {r['flagget']:4d} treff {r['tp']:4d} falske {r['fp']:4d} presisjon {r['presisjon']:6.1%} ({r['presisjon_ki'][0]:.1%}-{r['presisjon_ki'][1]:.1%}) recall {r['recall']:6.1%} ({r['recall_ki'][0]:.1%}-{r['recall_ki'][1]:.1%}) F1 {2 * r['tp'] / max(r['flagget'] + y.sum(), 1):.3f}")
    return r
print("\nA) Uten menneske"); ra = l("Vår agent", vf); rb = l("Barz, svarer på alt", ur); l("Barz, egne flagg (pred_mot)", bf)
print("\nB) Rangering: AP vår %.3f | Barz %.3f | tilfeldig %.3f" % (average_precision_score(y, r_v), average_precision_score(y, r_b), y.mean()))
print("\nC) Arbeidsdeling"); 
for n, f, h in [("Vår, grense 0,80", ve, vh), ("Barz, tersklene deres", bf, bh)]:
    les = f | h; print(f"  {n:24s} menneske {h.sum():4d} egne flagg {f.sum():3d} leser {les.mean():6.1%} fanger {(les & y).sum():3d} ({(les & y).sum() / y.sum():.1%}) oversett {(y & ~les).sum()} av {(~les).sum()} ({(y & ~les).sum() / (~les).sum():.1%})")
print("\nD) Samme lesemengde, rangert på risiko: andel fanget")
print(f"  {'leser':>7s} {'vår':>7s} {'Barz':>7s} {'snitt rang':>10s}")
sn = (pd.Series(r_v).rank(pct=True) + pd.Series(r_b).rank(pct=True)).to_numpy() / 2
for a in [.02, .05, .069, .106, .15, .20, .30]:
    n = int(round(a * len(m))); f = lambda r: y[np.argsort(-r, kind="stable")[:n]].sum() / y.sum(); print(f"  {a:7.1%} {f(r_v):7.1%} {f(r_b):7.1%} {f(sn):10.1%}")
print("  AP snitt av rangering (utforskende, valgt etter å ha sett test): %.3f" % average_precision_score(y, sn))
print("\nE) Overlapp i treff: begge", int((vf & ur & y).sum()), "| bare vår", int((vf & ~ur & y).sum()), "| bare Barz", int((~vf & ur & y).sum()), "| ingen", int((~vf & ~ur & y).sum()))
print("\nF) Sitat, samme nevner: alle saker der NBIM gikk mot styret og oppga seksjon")
g = m[y & m.rationale_section.str.startswith("GVG")]; print(f"  Antall {len(g)} | vår regel i samme seksjon {(g.seksjon == g.rationale_section).mean():.1%} | Barz toppseksjon {(g.retningslinje == g.rationale_section).mean():.1%} | Barz topp 3 {[r in (a + ' ' + b) for r, a, b in zip(g.rationale_section, g.retningslinje, g.alternative_seksjoner)].count(True) / len(g):.1%}")
g2 = g[vf[y & m.rationale_section.str.startswith("GVG").to_numpy()]]; print(f"  Bare der vår agent flagget: {len(g2)}, vår {(g2.seksjon == g2.rationale_section).mean():.1%} | Barz toppseksjon der Barz flagget: {(lambda q: (q.retningslinje == q.rationale_section).mean())(g[ur[y & m.rationale_section.str.startswith('GVG').to_numpy()]]):.1%}")
print("\nG) Gjentakelser og nye saker")
mt = d.groupby(["company_id", "proposal_type", "dato"], as_index=False).y.max().sort_values("dato"); hist = {a: b[["dato", "y"]].to_numpy() for a, b in mt.groupby(["company_id", "proposal_type"])}
sist = []
for r in m.itertuples():
    h = hist.get((r.company_id, r.proposal_type)); v = 0
    if h is not None:
        f = h[h[:, 0] < r.dato]; v = f[-1, 1] if len(f) else 0
    sist.append(bool(v))
s = np.array(sist)
for n, f in [("Vår", vf), ("Barz", ur)]:
    print(f"  {n:5s} gjentakelser {(f & y & s).sum()} av {(y & s).sum()} ({(f & y & s).sum() / (y & s).sum():.1%}) | nye {(f & y & ~s).sum()} av {(y & ~s).sum()} ({(f & y & ~s).sum() / (y & ~s).sum():.1%}) | falske på sakstype uten MOT sist: {(f & ~y & ~s).sum()}")
print("\nH) Etter kunnskapsgrensen (fra 01.07.2026)"); et = (m.dato >= pd.Timestamp("2026-07-01")).to_numpy(); 
for n, f in [("Vår", vf), ("Barz", ur)]:
    print(f"  {n:5s} saker {et.sum()} mot {y[et].sum()} flagg {f[et].sum()} treff {(f & y)[et].sum()}")
