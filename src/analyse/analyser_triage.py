"""Gratis analyse paa dev (2023-2024): hva tilfoerer agenten utover den enkle tekstmodellen?
Bruker lagrede svar. Ingen API-kall, og testsettet 2025-2026 roeres ikke."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "src")
import evaluer as e
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 90); pd.set_option("display.max_rows", 80)
navn = sys.argv[1] if len(sys.argv) > 1 else "dev"
d = e.last(); tr, te = e.splitt(d, "dev"); assert te.aar.max() <= 2024
p = pd.read_csv(f"resultater/pred_{navn}.csv", dtype=str, keep_default_na=False)
x = te.merge(p, on="rad_id", validate="one_to_one").reset_index(drop=True)
x["k"] = x.konfidens.astype(float); x["flag"] = (x.raastemme != x.mgmt_rec) & (x.raastemme != "")
# Agentens egen risiko for "mot styret": konfidens hvis den flagger, ellers 1 - konfidens
x["r_agent"] = np.where(x.flag, x.k, 1 - x.k)
kat = ["proposal_type", "market", "country", "proponent", "mgmt_rec"]
m = Pipeline([("f", ColumnTransformer([("t", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True), "proposal_text"), ("c", OneHotEncoder(handle_unknown="ignore"), kat)])), ("m", LogisticRegression(max_iter=3000, class_weight="balanced"))]).fit(tr, tr.y)
x["r_lr"] = m.predict_proba(x)[:, 1]
x["r_snitt"] = (x.r_agent.rank(pct=True) + x.r_lr.rank(pct=True)) / 2
y = x.y.values
print(f"{len(x)} saker, {y.sum()} mot styret. Tilfeldig AP {y.mean():.3f}")
print("AP: agent %.3f | tekstmodell %.3f | snitt av rangering %.3f" % (average_precision_score(y, x.r_agent), average_precision_score(y, x.r_lr), average_precision_score(y, x.r_snitt)))
print("\nHvis en analytiker leser de N saken med hoeyest risiko: andel av mot-styret-sakene som fanges")
print(f"{'lest':>6s} {'andel':>6s} {'agent':>7s} {'tekstm.':>8s} {'snitt':>7s}")
for n in [50, 100, 181, 300, 400, 600, 800, 1000, 1500]:
    f = lambda c: y[np.argsort(-x[c].values, kind="stable")[:n]].sum() / y.sum()
    print(f"{n:6d} {n / len(x):6.1%} {f('r_agent'):7.1%} {f('r_lr'):8.1%} {f('r_snitt'):7.1%}")
fl = x.flag & (x.k >= .8); h = x.k < .8
print(f"\nDagens regel (grense 0,80): leses {fl.sum() + h.sum()} saker ({(fl.sum() + h.sum()) / len(x):.1%}) og fanger {(y[fl] .sum() + y[h].sum()) / y.sum():.1%}")
print("\nFEILANALYSE, agenten")
x["utfall"] = np.select([x.flag & (y == 1), x.flag & (y == 0), ~x.flag & (y == 1)], ["treff", "falsk", "bom"], "rett_for")
t = pd.crosstab(x.proposal_type, x.utfall); t = t[(t.get("treff", 0) + t.get("falsk", 0) + t.get("bom", 0)) > 0]; print(t.sort_values("bom", ascending=False))
print("\nBom per NBIM-punkt:"); print(x[x.utfall == "bom"].rationale_section.replace("", "(tom)").value_counts().head(12).to_dict())
print("Bom per marked:", x[x.utfall == "bom"].market.value_counts().to_dict(), "| Treff per marked:", x[x.utfall == "treff"].market.value_counts().to_dict())
print("Falske per marked:", x[x.utfall == "falsk"].market.value_counts().to_dict())
print("Falske per regel:", x[x.utfall == "falsk"].regel_id.value_counts().head(10).to_dict())
print("Falske per selskap topp:", x[x.utfall == "falsk"].company.value_counts().head(8).to_dict())
print("\nAnsvarsfritak: NBIM mot styret per aar i treningsdata (til og med 2022):")
print(tr[tr.proposal_type == "DISCHARGE"].groupby("aar").y.agg(["size", "sum"]).T.to_string())
print(" Selskaper bak MOT paa ansvarsfritak i trening:", tr[(tr.proposal_type == "DISCHARGE") & (tr.y == 1)].company.value_counts().head(6).to_dict())
print("\nBom med lav eller hoey sikkerhet:", pd.cut(x[x.utfall == "bom"].k, [0, .6, .7, .8, .9, 1]).value_counts().sort_index().to_dict())
print("\nEksempler paa bom i ARTICLES/OTHER_MGMT/RPT:"); print(x[(x.utfall == "bom") & x.proposal_type.isin(["ARTICLES", "OTHER_MGMT", "RPT"])].sample(8, random_state=2)[["company", "country", "proposal_text", "k", "rationale_section"]].to_string())
