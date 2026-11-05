"""Fremtidstest: tren paa alt foer et aar, predikter det aaret, og flytt vinduet ett aar fram.
Tester ogsaa saker etter 30. juni 2026, som ligger etter kunnskapsgrensen til Claude Opus 5.5."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "src")
import evaluer as e
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
d = e.last(); kat = ["proposal_type", "market", "country", "proponent", "mgmt_rec"]
def fit(tr):
    m = Pipeline([("f", ColumnTransformer([("t", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True), "proposal_text"), ("c", OneHotEncoder(handle_unknown="ignore"), kat)])),
                  ("m", LogisticRegression(max_iter=3000, class_weight="balanced"))])
    return m.fit(tr, tr.y)
def rad(navn, tr, te):
    assert tr.dato.max() < te.dato.min()
    s = fit(tr).predict_proba(te)[:, 1]; p = s >= .5; y = te.y.values.astype(bool); tp = (p & y).sum()
    print(f"{navn:26s} {len(tr):6d} {len(te):6d} {y.sum():5d} {tp / max(p.sum(), 1):7.1%} {tp / max(y.sum(), 1):7.1%} {average_precision_score(y, s):7.3f} {y.mean():7.3f}")
print(f"{'Predikert periode':26s} {'tren':>6s} {'test':>6s} {'mot':>5s} {'pres':>7s} {'recall':>7s} {'AP':>7s} {'tilf.':>7s}")
for y in range(2021, 2027):
    rad(str(y), d[d.aar < y], d[d.aar == y])
g = pd.Timestamp("2026-07-01"); ny = d[d.dato >= g]
print(f"\nEtter 30.06.2026: {len(ny)} saker, {ny.y.sum()} mot styret, {ny.meeting_id.nunique()} moeter, siste dato {ny.meeting_date.max()}")
if len(ny) and ny.y.sum(): rad("jul-sep 2026", d[d.dato < g], ny)
print("Per maaned 2026:", d[d.aar == 2026].groupby(d.dato.dt.month).agg(saker=("y", "size"), mot=("y", "sum")).to_dict("index"))
