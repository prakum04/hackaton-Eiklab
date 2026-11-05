"""Evaluering av stemmeforslag mot NBIMs faktiske stemmer (real_votes.csv).

Mål: against_board = 1, altså at NBIM gikk mot styrets anbefaling.
Metrikk: presisjon og recall på «mot styret». Accuracy vises bare for å vise at den er ubrukelig.

Splitt etter tid:
    dev : tren til og med 2022, evaluer 2023-2024. Her kan agenten justeres.
    test: tren til og med 2024, evaluer 2025-2026. Brukes først når agenten er låst.

Bruk:
    python src/evaluer.py --sett dev
    python src/evaluer.py --sett test --pred resultater/pred_test.csv
    python src/evaluer.py --sett test --pred resultater/pred_test.csv --fra 2026-07-01

Prediksjonsfil: rad_id, stemme (FOR/MOT/AVSTÅ/MENNESKE), seksjon (f.eks. «GVG 3.2», kan være tom).
MENNESKE betyr sendt til menneskelig vurdering, og teller ikke som funn av «mot styret».
Valgfritt: raastemme og konfidens, for rangering og tall uten konfidensgrense.
"""
import argparse, json, sys
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

FIL = "data/arrangor/real_votes.csv"
# Alt agenten og modellene får se. Stemmen, against_board og begrunnelsesfeltene er utelatt med vilje:
# rationale_section er bare fylt ut når NBIM gikk mot styret, og ville avslørt svaret.
INNDATA = ["rad_id", "meeting_id", "company_id", "company", "country", "market", "meeting_date", "item_no",
           "proposal_text", "proponent", "mgmt_rec", "proposal_type", "year"]
FORBUDT = {"nbim_vote", "nbim_vote_raw", "against_board", "rationale_text", "rationale_section", "position_paper"}
assert not FORBUDT & set(INNDATA)
SPLITT = {"dev": (2022, 2023, 2024), "test": (2024, 2025, 2026)}


def last():
    d = pd.read_csv(FIL, dtype=str, keep_default_na=False)
    d["rad_id"] = d.meeting_id + "_" + d.item_no
    assert d.rad_id.is_unique
    d = d[d.against_board.isin(["0.0", "1.0"])].copy()
    d["y"] = (d.against_board == "1.0").astype(int)
    d["dato"] = pd.to_datetime(d.meeting_date)
    d["aar"] = d.year.astype(int)
    return d.sort_values(["dato", "rad_id"]).reset_index(drop=True)


def splitt(d, sett):
    t, a, b = SPLITT[sett]
    tr, te = d[d.aar <= t], d[d.aar.between(a, b)].copy()
    assert tr.dato.max() < te.dato.min(), "treningsdata må ligge før testdata"
    assert not set(tr.meeting_id) & set(te.meeting_id)
    return tr, te


def maal(y, p, groups, seed=0):
    y, p = np.asarray(y).astype(bool), np.asarray(p).astype(bool)
    tp, fp, fn = int((p & y).sum()), int((p & ~y).sum()), int((~p & y).sum())
    pres = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    # Usikkerhet: trekk hele møter, siden saker i samme møte henger sammen
    g = pd.Series(groups).reset_index(drop=True)
    idx = {k: v.to_numpy() for k, v in g.groupby(g).groups.items()}
    keys = list(idx); rng = np.random.default_rng(seed); rs, ps = [], []
    for _ in range(500):
        s = np.concatenate([idx[keys[i]] for i in rng.integers(0, len(keys), len(keys))])
        a, b = y[s], p[s]
        rs.append((a & b).sum() / max(a.sum(), 1)); ps.append((a & b).sum() / max(b.sum(), 1))
    return dict(accuracy=float((p == y).mean()), presisjon=pres, recall=rec, tp=tp, fp=fp, fn=fn, flagget=int(p.sum()),
                recall_ki=[float(np.percentile(rs, 2.5)), float(np.percentile(rs, 97.5))],
                presisjon_ki=[float(np.percentile(ps, 2.5)), float(np.percentile(ps, 97.5))])


def baseliner(tr, te):
    ut = {"Alltid med styret": np.zeros(len(te), bool)}
    rate = tr.groupby("proposal_type").y.mean()
    ut["Sakstype med minst 50 % mot i trening"] = (te.proposal_type.map(rate).fillna(0) >= .5).to_numpy()
    # Var det «mot styret» på minst én sak av samme type på selskapets forrige møte? Bare tidligere møter brukes.
    alle = pd.concat([tr, te])
    moter = alle.groupby(["company_id", "proposal_type", "dato"], as_index=False).y.max().sort_values("dato")
    hist = {k: g[["dato", "y"]].to_numpy() for k, g in moter.groupby(["company_id", "proposal_type"])}
    sist = []
    for r in te.itertuples():
        h = hist.get((r.company_id, r.proposal_type)); v = 0
        if h is not None:
            f = h[h[:, 0] < r.dato]
            v = f[-1, 1] if len(f) else 0
        sist.append(bool(v))
    ut["Mot på samme sakstype på forrige møte"] = np.array(sist)
    kat = ["proposal_type", "market", "country", "proponent", "mgmt_rec"]
    m = Pipeline([("f", ColumnTransformer([("t", TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True), "proposal_text"),
                                           ("c", OneHotEncoder(handle_unknown="ignore"), kat)])),
                  ("m", LogisticRegression(max_iter=2000, class_weight="balanced"))])
    m.fit(tr, tr.y)
    risiko = m.predict_proba(te)[:, 1]
    ut["Tekstmodell (logistisk regresjon, terskel 0,5)"] = risiko >= .5
    return ut, risiko


def agent(te, sti):
    p = pd.read_csv(sti, dtype=str, keep_default_na=False)
    mangler = set(te.rad_id) - set(p.rad_id)
    if mangler:
        sys.exit(f"Prediksjonsfilen mangler {len(mangler)} av {len(te)} rader. Ufullstendig evaluering avvises.")
    x = te.merge(p, on="rad_id", how="left", validate="one_to_one").reset_index(drop=True)
    gyldig = {"FOR", "MOT", "AVSTÅ"}
    s = x.stemme.str.upper()
    # Samme definisjon som fasiten: noe annet enn styrets anbefaling, inkludert AVSTÅ
    mot = s.isin(gyldig) & (s != x.mgmt_rec)
    meng = s == "MENNESKE"
    ek = {"til_menneske": int(meng.sum()), "til_menneske_andel": float(meng.mean()), "mot_blant_til_menneske": int(x.y[meng].sum())}
    f = x[(x.y == 1) & x.rationale_section.str.startswith("GVG") & mot]
    ek["sitat_vurdert"] = len(f)
    ek["sitat_riktig_seksjon"] = float((f.seksjon == f.rationale_section).mean()) if "seksjon" in x and len(f) else None
    if "sakstype" in x:
        ek["sakstype_riktig"] = float((x.sakstype == x.proposal_type).mean())
    # Streng tolkning: styret sier FOR og NBIM sier MOT
    yy = (x.nbim_vote == "MOT") & (x.mgmt_rec == "FOR"); pp = (s == "MOT") & (x.mgmt_rec == "FOR")
    ek["streng_mot"] = {"fasit": int(yy.sum()), "flagget": int(pp.sum()), "treff": int((yy & pp).sum())}
    ek["avstaa"] = {"fasit": int((x.nbim_vote == "AVSTÅ").sum()), "foreslaatt": int((s == "AVSTÅ").sum()), "treff": int(((x.nbim_vote == "AVSTÅ") & (s == "AVSTÅ")).sum())}
    raa, risiko = None, None
    if {"raastemme", "konfidens"} <= set(x.columns):
        raa = (x.raastemme != "") & (x.raastemme != x.mgmt_rec)
        k = pd.to_numeric(x.konfidens, errors="coerce").fillna(0)
        risiko = np.where(raa, k, 1 - k)
    return mot.to_numpy(), meng.to_numpy(), ek, (None if raa is None else raa.to_numpy()), risiko


def main():
    a = argparse.ArgumentParser(); a.add_argument("--sett", choices=SPLITT, default="dev"); a.add_argument("--pred")
    a.add_argument("--ut", default=None); a.add_argument("--fra", help="Evaluer bare møter fra og med denne datoen")
    a.add_argument("--delvis", action="store_true", help="Pilot: evaluer bare radene i prediksjonsfilen. Ikke et endelig resultat.")
    a = a.parse_args()
    d = last(); tr, te = splitt(d, a.sett)
    if a.fra:
        te = te[te.dato >= pd.Timestamp(a.fra)].copy()
    if a.delvis:
        te = te[te.rad_id.isin(pd.read_csv(a.pred, dtype=str).rad_id)].copy()
        print("DELVIS KJØRING: bare et utvalg av møtene. Tallene er ikke et endelig resultat.")
    print(f"Sett: {a.sett}{' fra ' + a.fra if a.fra else ''} | tren {len(tr)} ({tr.y.mean():.1%} mot) | evaluer {len(te)}, {te.y.sum()} mot styret ({te.y.mean():.1%}), {te.meeting_id.nunique()} møter")
    base, r_lr = baseliner(tr, te)
    res = {n: maal(te.y, p, te.meeting_id) for n, p in base.items()}
    ek, triage = {}, {}
    if a.pred:
        mot, meng, ek, raa, r_ag = agent(te, a.pred)
        if raa is not None:
            res["AGENT, uten konfidensgrense"] = maal(te.y, raa, te.meeting_id)
        res["AGENT, egne flagg"] = maal(te.y, mot, te.meeting_id)
        y = te.y.to_numpy(); lest = mot | meng; n = int(lest.sum())
        topp = np.argsort(-r_lr, kind="stable")[:n]
        triage = {"leses_antall": n, "leses_andel": float(lest.mean()), "fanger": maal(y, lest, te.meeting_id),
                  "oversett": int((y.astype(bool) & ~lest).sum()), "slipper_gjennom": int((~lest).sum()),
                  "tekstmodell_samme_lesing": float(y[topp].sum() / max(y.sum(), 1)),
                  "ap_tekstmodell": float(average_precision_score(y, r_lr)), "ap_tilfeldig": float(y.mean())}
        if r_ag is not None:
            triage["ap_agent"] = float(average_precision_score(y, r_ag))
    print(f"\n{'Metode':48s} {'Accuracy':>8s} {'Presisjon':>10s} {'Recall':>8s}   95 % KI recall   TP / FP / FN")
    for n, r in res.items():
        print(f"{n:48s} {r['accuracy']:8.1%} {r['presisjon']:10.1%} {r['recall']:8.1%}   {r['recall_ki'][0]:5.1%}-{r['recall_ki'][1]:5.1%}   {r['tp']} / {r['fp']} / {r['fn']}")
    if ek:
        print("\nAgent:", json.dumps(ek, ensure_ascii=False))
    if triage:
        f = triage["fanger"]
        print(f"\nArbeidsdeling: agenten flagger eller sender {triage['leses_antall']} saker til et menneske ({triage['leses_andel']:.1%}) og fanger {f['recall']:.1%} av «mot styret» (95 % KI {f['recall_ki'][0]:.1%}-{f['recall_ki'][1]:.1%}).")
        print(f"Slipper gjennom {triage['slipper_gjennom']} saker, der {triage['oversett']} er oversett ({triage['oversett'] / max(triage['slipper_gjennom'], 1):.1%}).")
        print(f"Tekstmodellen fanger {triage['tekstmodell_samme_lesing']:.1%} hvis den leser like mange saker.")
        print(f"Rangering (AP): agent {triage.get('ap_agent', float('nan')):.3f} | tekstmodell {triage['ap_tekstmodell']:.3f} | tilfeldig {triage['ap_tilfeldig']:.3f}")
    ut = Path(a.ut or f"resultater/evaluering_{a.sett}.json"); ut.parent.mkdir(exist_ok=True)
    ut.write_text(json.dumps({"sett": a.sett, "fra": a.fra, "resultater": res, "agent": ek, "arbeidsdeling": triage}, indent=1, ensure_ascii=False))
    print(f"\nSkrevet til {ut}")


if __name__ == "__main__":
    main()
