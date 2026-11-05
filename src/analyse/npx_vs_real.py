"""Hva skjer naar vi trener paa npx_votes og maaler paa real_votes?
Evalueres paa real_votes juli-desember 2024, saa testsettet 2025-2026 ikke roeres.
All trening ligger foer 1. juli 2024. Ingen grid search: bare sammenligning av treningsdata."""
import re, pandas as pd, numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
GRENSE = pd.Timestamp("2024-07-01"); SLUTT = pd.Timestamp("2025-01-01")
def last(f):
    d = pd.read_csv(f, dtype=str, keep_default_na=False)
    d = d[d.against_board.isin(["0.0", "1.0"])].copy()
    d["y"] = (d.against_board == "1.0").astype(int); d["dato"] = pd.to_datetime(d.meeting_date)
    return d
n = lambda s: re.sub(r"[^a-z0-9]", "", s.lower())
kort = lambda s: re.sub(r"\b(inc|corp|corporation|co|company|ltd|limited|plc|sa|ag|nv|the|holdings?|group)\b", "", re.sub(r"[^a-z0-9 ]", " ", s.lower())).replace(" ", "")
R, N = last("data/arrangor/real_votes.csv"), last("data/arrangor/npx_votes.csv")
te = R[(R.dato >= GRENSE) & (R.dato < SLUTT)].copy()
print(f"Evaluering: real_votes jul-des 2024: {len(te)} saker, {te.y.sum()} mot styret ({te.y.mean():.1%}), {te.meeting_id.nunique()} moeter")
for x in (R, N, te):
    x["nk"] = x.company.map(kort) + "|" + x.meeting_date + "|" + x.proposal_text.map(n)
print("NPX foer grensen:", (N.dato < GRENSE).sum(), "rader. NPX eldste dato:", N.meeting_date.min())
print("Samme forslag i NPX og hele real_votes:", N.nk.isin(R.nk).sum(), "rader (maa fjernes eller holdes unna test)")
print("Av dem i evalueringsperioden:", N.nk.isin(te.nk).sum())
Nf = N[N.dato < GRENSE]
vask = Nf[(Nf.proponent == "Management") & (Nf.nbim_vote != "AVSTÅ")]
Rf = R[R.dato < GRENSE]
Rn = Rf[Rf.dato >= pd.Timestamp("2023-07-01")]
kat = ["proposal_type", "market", "country", "proponent", "mgmt_rec"]
def modell():
    return Pipeline([("f", ColumnTransformer([("t", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True), "proposal_text"), ("c", OneHotEncoder(handle_unknown="ignore"), kat)])),
                     ("m", LogisticRegression(max_iter=3000, class_weight="balanced"))])
sett = {"A real_votes til juni 2024": Rf, "B real_votes juli 2023-juni 2024": Rn, "C npx_votes raa (samme periode)": Nf,
        "D npx_votes kun styreforslag, uten AVSTAA": vask, "E A + D": pd.concat([Rf, vask]), "F A + C": pd.concat([Rf, Nf])}
print(f"\n{'Treningsdata':46s} {'rader':>6s} {'%mot':>5s} {'pres':>6s} {'recall':>7s} {'AP':>6s}  TP/FP/FN")
y = te.y.values.astype(bool)
for navn, tr in sett.items():
    assert tr.dato.max() < te.dato.min()
    tr = tr[~tr.nk.isin(te.nk)]
    m = modell().fit(tr, tr.y); s = m.predict_proba(te)[:, 1]; p = s >= .5
    tp, fp, fn = (p & y).sum(), (p & ~y).sum(), (~p & y).sum()
    print(f"{navn:46s} {len(tr):6d} {tr.y.mean():5.1%} {tp / max(tp + fp, 1):6.1%} {tp / max(tp + fn, 1):7.1%} {average_precision_score(y, s):6.3f}  {tp}/{fp}/{fn}")
print(f"Tilfeldig rangering (AP lik andel mot): {y.mean():.3f}")
# Direkte sammenligning: samme forslag i begge filer
k = N.merge(R, on="nk", suffixes=("_n", "_r")); k = k[k.nbim_vote_n.isin(["FOR", "MOT", "AVSTÅ"]) & k.nbim_vote_r.isin(["FOR", "MOT", "AVSTÅ"])].drop_duplicates("nk")
print(f"\nSamme forslag i begge filer: {len(k)}. Stemme lik: {(k.nbim_vote_n == k.nbim_vote_r).mean():.1%}. Anbefaling lik: {(k.mgmt_rec_n == k.mgmt_rec_r).mean():.1%}. against_board lik: {(k.y_n == k.y_r).mean():.1%}")
print(pd.crosstab(k.y_r, k.y_n, rownames=["real: mot styret"], colnames=["npx: mot styret"]))
print("Aksjonaerforslag i overlapp:"); s = k[k.proponent_r == "Shareholder"]; print(f" {len(s)} rader, against_board lik: {(s.y_n == s.y_r).mean():.1%}, anbefaling lik: {(s.mgmt_rec_n == s.mgmt_rec_r).mean():.1%}")
