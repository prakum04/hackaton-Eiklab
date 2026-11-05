"""Er testresultatet for godt til å være sant? Disse kontrollene ble lagt til etter at testresultatene var kjent, fordi tallene var bedre enn på dev.
De endrer ikke agenten eller hovedtallene. Bruk: python src/kontroll_test.py"""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "src")
import agent, evaluer as e
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 120); pd.set_option("display.max_rows", 60)
d = e.last(); tr, te = e.splitt(d, "test")
print(f"Brukbare saker totalt: {len(d)} | selskaper {d.company_id.nunique()} | møter {d.meeting_id.nunique()} | mot styret {d.y.sum()} ({d.y.mean():.1%}) | årsspenn {d.aar.min()}-{d.aar.max()}")
p = pd.read_csv("resultater/pred_test.csv", dtype=str, keep_default_na=False); x = te.merge(p, on="rad_id", validate="one_to_one").reset_index(drop=True)
x["k"] = x.konfidens.astype(float); x["flag"] = (x.raastemme != "") & (x.raastemme != x.mgmt_rec); y = x.y == 1
logg = {json.loads(l)["meeting_id"]: json.loads(l) for l in open("resultater/logg_test.jsonl", encoding="utf-8")}
def r(n, f, yy):
    tp = (f & yy).sum(); print(f"  {n:58s} flagg {f.sum():4d} treff {tp:4d} presisjon {tp / max(f.sum(), 1):6.1%} recall {tp / max(yy.sum(), 1):6.1%}")
print("\nA) Lette saker"); r("Alle", x.flag, y); ob = x.proposal_type == "OTHER_BUSINESS"; r("Uten «Other Business»", x.flag[~ob], y[~ob]); shp = x.proponent == "Shareholder"; r("Bare styreforslag", x.flag[~shp & ~ob], y[~shp & ~ob]); r("Bare aksjonærforslag", x.flag[shp], y[shp])
print("\nB) Gjentakelse: finnes samme tekst med mot styret tidligere hos selskapet?")
key = lambda v: re.sub(r"[^a-z0-9]", "", v.lower()); tidl = {}
for m in x.itertuples():
    h = d[(d.company_id == m.company_id) & (d.dato < m.dato) & (d.y == 1)]
    tidl[m.rad_id] = key(m.proposal_text) in {key(t) for t in h.proposal_text}
x["samme_tekst_mot"] = x.rad_id.map(tidl); r("Samme tekst har fått mot styret før", x.flag[x.samme_tekst_mot], y[x.samme_tekst_mot]); r("Ikke samme tekst", x.flag[~x.samme_tekst_mot], y[~x.samme_tekst_mot])
print("\nC) Forrige møte: hadde selskapet mot styret på samme sakstype på forrige møte?")
mt = d.groupby(["company_id", "proposal_type", "dato"], as_index=False).y.max().sort_values("dato"); hist = {k: g[["dato", "y"]].to_numpy() for k, g in mt.groupby(["company_id", "proposal_type"])}
sist = []
for m in x.itertuples():
    h = hist.get((m.company_id, m.proposal_type)); v = 0
    if h is not None:
        f = h[h[:, 0] < m.dato]; v = f[-1, 1] if len(f) else 0
    sist.append(bool(v))
x["sist"] = sist; r("Mot styret på forrige møte", x.flag[x.sist], y[x.sist]); r("Ikke mot styret på forrige møte", x.flag[~x.sist], y[~x.sist])
print("  Av agentens treff er", int((x.flag & y & x.sist).sum()), "gjentakelser og", int((x.flag & y & ~x.sist).sum()), "nye. Av alle mot styret er", int((y & x.sist).sum()), "gjentakelser og", int((y & ~x.sist).sum()), "nye.")
sammendrag = {"treff_gjentakelser": int((x.flag & y & x.sist).sum()), "treff_nye": int((x.flag & y & ~x.sist).sum()), "mot_gjentakelser": int((y & x.sist).sum()), "mot_nye": int((y & ~x.sist).sum()),
              "uten_other_business": {"flagg": int(x.flag[~ob].sum()), "treff": int((x.flag & y)[~ob].sum()), "mot": int(y[~ob].sum())}, "brukbare_saker": len(d), "selskaper": int(d.company_id.nunique()), "moter": int(d.meeting_id.nunique()), "mot_styret_alle": int(d.y.sum())}
yy = x.nbim_vote == "MOT"; pa = x.raastemme == "MOT"; pb = x.mgmt_rec == "MOT"
sammendrag["mot_bokstavelig"] = {"fasit": int(yy.sum()), "agent": {"flagg": int(pa.sum()), "treff": int((yy & pa).sum()), "presisjon": float((yy & pa).sum() / pa.sum()), "recall": float((yy & pa).sum() / yy.sum())},
                                 "stem_som_styret": {"flagg": int(pb.sum()), "treff": int((yy & pb).sum()), "presisjon": float((yy & pb).sum() / pb.sum()), "recall": float((yy & pb).sum() / yy.sum())}}
sammendrag["med_styret_per_aar"] = {int(a): float(1 - g_.y.mean()) for a, g_ in d.groupby("aar")}
print("\nMOT-stemmer bokstavelig (NBIM MOT uansett styret):", sammendrag["mot_bokstavelig"]); print("Andel med styret per år:", {k: round(v, 3) for k, v in sammendrag["med_styret_per_aar"].items()})
Path("resultater/kontroll_test.json").write_text(json.dumps(sammendrag, indent=1))
print("\nD) Nevner begrunnelsen utfall agenten ikke skal kunne vite? Søk etter datoer etter møtet og «faktisk stemte»")
sus = []
for m in x[x.flag].itertuples():
    ar = [int(v) for v in re.findall(r"\b(20[12]\d)\b", m.begrunnelse)]
    if any(v > m.dato.year for v in ar) or re.search(r"(?i)faktisk stemte|ifølge NBIMs (?:avstemning|stemmeregister)", m.begrunnelse):
        sus.append((m.company, m.meeting_date, m.proposal_text[:60], m.begrunnelse[:200]))
print("  Saker:", len(sus)); [print("  ", s) for s in sus[:8]]
print("\nE) Stabilitet over tid"); 
for a, b, n in [("2025-01-01", "2025-06-30", "1. halvår 2025"), ("2025-07-01", "2025-12-31", "2. halvår 2025"), ("2026-01-01", "2026-06-30", "1. halvår 2026"), ("2026-07-01", "2026-12-31", "Etter kunnskapsgrensen")]:
    q = (x.dato >= a) & (x.dato <= b); r(f"{n}: {q.sum()} saker, {y[q].sum()} mot", x.flag[q], y[q])
print("\nF) Andel av treffene fra de 10 selskapene med flest treff:", round(x[x.flag & y].company.value_counts().head(10).sum() / (x.flag & y).sum(), 3), "| selskaper med treff:", x[x.flag & y].company.nunique())
print("\nG) Demo-kandidater etter kunnskapsgrensen, treff:")
c = x[(x.dato >= "2026-07-01") & x.flag]; print(c[["company", "meeting_date", "meeting_id", "proposal_text", "mgmt_rec", "nbim_vote", "raastemme", "k", "regel_id", "begrunnelse"]].to_string())
s = x[x.dato >= "2026-07-01"].groupby(["company", "meeting_id", "meeting_date"]).agg(saker=("y", "size"), mot=("y", "sum"), flagg=("flag", "sum")).reset_index().sort_values("mot", ascending=False); print(s.head(8).to_string(index=False))
print("\nH) Bommet etter kunnskapsgrensen:"); print(x[(x.dato >= "2026-07-01") & y & ~x.flag][["company", "proposal_text", "k", "rationale_section", "begrunnelse"]].to_string())
print("\nI) Treff med regeltekst, fem tilfeldige:"); print(x[x.flag & y & ~ob].sample(5, random_state=7)[["company", "meeting_date", "proposal_text", "regel_id", "rationale_section", "k", "begrunnelse"]].to_string())
