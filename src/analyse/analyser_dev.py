"""Dypere analyse av agenten paa dev: konfidens, sitater, sakstyper og feil. Brukes ikke paa test foer agenten er laast."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, "src")
import evaluer as e
pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 95); pd.set_option("display.max_rows", 60)
navn = sys.argv[1] if len(sys.argv) > 1 else "dev"
d = e.last(); _, te = e.splitt(d, "dev")
p = pd.read_csv(f"resultater/pred_{navn}.csv", dtype=str, keep_default_na=False)
x = te.merge(p, on="rad_id", validate="one_to_one"); x["k"] = x.konfidens.astype(float)
x["fs"] = x.raastemme.map({"FOR": "FOR", "MOT": "MOT", "AVSTÅ": "AVSTÅ"}); x["flag"] = (x.fs != x.mgmt_rec) & x.fs.notna()
print("Rader:", len(x), "| stemmer:", x.raastemme.value_counts().to_dict(), "| mangler:", (x.raastemme == "").sum())
print("Fordeling konfidens:", x.k.describe().round(3).to_dict())
print("\nKonfidensgrense (lavere = til menneske):")
for t in [0, .5, .6, .7, .75, .8, .85, .9, .95]:
    h = x[x.k < t]; a = x[x.k >= t]; tp = (a.flag & (a.y == 1)).sum(); fl = a.flag.sum()
    print(f" {t:4.2f}: til menneske {len(h):5d} ({len(h)/len(x):5.1%}), MOT blant dem {h.y.sum():3d} | agent: flagg {fl:3d}, pres {tp/max(fl,1):5.1%}, recall {tp/max(x.y.sum(),1):5.1%} | funnet + til menneske {(tp+h.y.sum())/x.y.sum():5.1%}")
f = x.groupby(pd.cut(x.k, [0, .5, .7, .8, .9, 1.0], include_lowest=True), observed=True).apply(lambda g: pd.Series({"n": len(g), "riktig": ((g.flag.astype(int)) == g.y).mean()}))
print("\nKalibrering (riktig mot/ikke mot styret):"); print(f.round(3))
s = x[x.flag & (x.y == 1) & x.rationale_section.str.startswith("GVG")]
print(f"\nSitater paa treff: {len(s)}, riktig seksjon {(s.seksjon == s.rationale_section).mean():.1%}")
print(s.groupby("rationale_section").apply(lambda g: f"{(g.seksjon == g.rationale_section).sum()}/{len(g)}").to_dict())
print(f"Sakstype riktig: {(x.sakstype == x.proposal_type).mean():.1%}")
t = x.groupby("proposal_type").apply(lambda g: pd.Series({"n": len(g), "mot": g.y.sum(), "flagget": g.flag.sum(), "tp": (g.flag & (g.y == 1)).sum()})).sort_values("mot", ascending=False)
print("\nPer sakstype"); print(t[t.mot + t.flagget > 0])
print("\nMistenkelig instruks:", (x.mistenkelig_instruks == "True").sum())
print("\nBommet (fn) topp:"); print(x[(x.y == 1) & ~x.flag].sample(min(7, ((x.y == 1) & ~x.flag).sum()), random_state=1)[["company", "proposal_text", "k", "rationale_section"]].to_string())
print("\nFalske alarmer:"); print(x[(x.y == 0) & x.flag].sample(min(6, ((x.y == 0) & x.flag).sum()), random_state=1)[["company", "proposal_text", "k", "regel_id"]].to_string())
