"""Viser hvor mye en lekkasje blåser opp tallene: samme tekstmodell med og uten rationale_section, testet på 2025-2026."""
import sys
import numpy as np
sys.path.insert(0, "src")
import evaluer as e
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
d = e.last(); tr, te = e.splitt(d, "test"); kat = ["proposal_type", "market", "country", "proponent", "mgmt_rec"]; y = te.y.values.astype(bool)
for navn, k in [("Uten lekkasje", kat), ("Med rationale_section (ikke bruk)", kat + ["rationale_section"])]:
    m = Pipeline([("f", ColumnTransformer([("t", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True), "proposal_text"), ("c", OneHotEncoder(handle_unknown="ignore"), k)])), ("m", LogisticRegression(max_iter=2000, class_weight="balanced"))]).fit(tr, tr.y)
    p = m.predict_proba(te)[:, 1] >= .5; t = (p & y).sum(); print(f"{navn:36s} presisjon {t / p.sum():.1%}, recall {t / y.sum():.1%}")
