"""Sluttrapport for testsettet 2025-2026. Innholdet ble bestemt før testresultatene var kjent.

Skriver resultater/sluttall.json og en lesbar oversikt. Bruker bare lagrede svar, ingen API-kall.
Bruk: python src/sluttrapport.py
"""
import json, re, sys
from pathlib import Path
import numpy as np, pandas as pd
sys.path.insert(0, "src")
import agent, evaluer as e
from sklearn.metrics import average_precision_score
pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 90); pd.set_option("display.max_rows", 80)
L = json.loads(Path(agent.LAASFIL).read_text()); GRENSE, ANDRE = L["terskel"], L["sekundaer_grense"]
assert L["fingeravtrykk"] == agent.fingeravtrykk(), "Agenten er endret etter låsing"
assert agent.sha(e.FIL) == L["real_votes_sha256"], "Fasitfilen er endret etter låsing"
d = e.last(); tr, te = e.splitt(d, "test")
p = pd.read_csv("resultater/pred_test.csv", dtype=str, keep_default_na=False)
x = te.merge(p, on="rad_id", validate="one_to_one").reset_index(drop=True)
x["k"] = x.konfidens.astype(float); x["flag"] = (x.raastemme != "") & (x.raastemme != x.mgmt_rec)
x["regelmangel"] = x.flag & (x.regel_id == agent.UTGANGSPUNKT); x["sus"] = x.mistenkelig_instruks == "True"; x["risiko"] = np.where(x.flag, x.k, 1 - x.k)
logg = {json.loads(l)["meeting_id"]: json.loads(l) for l in open("resultater/logg_test.jsonl", encoding="utf-8")}
y = (x.y == 1).to_numpy(); G = x.meeting_id.to_numpy(); ut = {"laas": L, "saker": len(x), "moter": int(x.meeting_id.nunique()), "mot_styret": int(y.sum()), "andel_mot": float(y.mean())}
base, r_lr = e.baseliner(tr, te); ut["baseliner"] = {n: e.maal(y, v, G) for n, v in base.items()}
ut["ap"] = {"agent": float(average_precision_score(y, x.risiko)), "tekstmodell": float(average_precision_score(y, r_lr)), "tilfeldig": float(y.mean())}


def driftspunkt(g, maske=None):
    m = np.ones(len(x), bool) if maske is None else maske
    h = ((x.k.values < g) | x.regelmangel.values | x.sus.values)[m]; f = x.flag.values[m] & ~h; yy = y[m]; les = f | h; G_ = G[m]
    r = {"grense": g, "saker": int(m.sum()), "mot_styret": int(yy.sum()), "til_menneske": int(h.sum()), "til_menneske_andel": float(h.mean()), "mot_i_menneskebunken": int((h & yy).sum()),
         "egne_flagg": e.maal(yy, f, G_), "leses": int(les.sum()), "leses_andel": float(les.mean()), "fanger": e.maal(yy, les, G_), "oversett": int((yy & ~les).sum()), "slipper_gjennom": int((~les).sum())}
    r["andel_oversett_av_sluppet"] = r["oversett"] / max(r["slipper_gjennom"], 1)
    return r


ut["uten_grense"] = e.maal(y, x.flag.values, G); ut["hoved"] = driftspunkt(GRENSE); ut["alternativ"] = driftspunkt(ANDRE)
for nv, g in [("hoved", GRENSE), ("alternativ", ANDRE)]:
    n = ut[nv]["leses"]; ut[nv]["tekstmodell_samme_lesing"] = float(y[np.argsort(-r_lr, kind="stable")[:n]].sum() / max(y.sum(), 1))
    ut[nv]["agent_rangert_samme_lesing"] = float(y[np.argsort(-x.risiko.values, kind="stable")[:n]].sum() / max(y.sum(), 1))
ut["streng_mot"] = {"fasit": int(((x.nbim_vote == "MOT") & (x.mgmt_rec == "FOR")).sum()), "agent_uten_grense": e.maal((x.nbim_vote == "MOT") & (x.mgmt_rec == "FOR"), (x.raastemme == "MOT") & (x.mgmt_rec == "FOR"), G)}
ut["avstaa"] = {"fasit": int((x.nbim_vote == "AVSTÅ").sum()), "foreslaatt": int((x.raastemme == "AVSTÅ").sum()), "treff": int(((x.nbim_vote == "AVSTÅ") & (x.raastemme == "AVSTÅ")).sum())}
# Etter kunnskapsgrensen: modellen kan ikke ha sett disse møtene i treningen
etter = (x.dato >= pd.Timestamp("2026-07-01")).to_numpy()
ut["etter_kunnskapsgrense"] = {"uten_grense": e.maal(y[etter], x.flag.values[etter], G[etter]), "hoved": driftspunkt(GRENSE, etter), "ap_agent": float(average_precision_score(y[etter], x.risiko.values[etter])) if y[etter].any() else None, "tekstmodell": e.maal(y[etter], (r_lr >= .5)[etter], G[etter])}
ut["foer_kunnskapsgrense"] = {"uten_grense": e.maal(y[~etter], x.flag.values[~etter], G[~etter]), "hoved": driftspunkt(GRENSE, ~etter)}
# Historikk
hist = np.array([re.search(r"(\d+) mot styret\.", logg[m]["bruker"].split("<saksliste>")[0]) is not None and int(re.search(r"(\d+) mot styret\.", logg[m]["bruker"].split("<saksliste>")[0]).group(1)) > 0 for m in x.meeting_id])
ut["med_mot_i_historikk"] = {"uten_grense": e.maal(y[hist], x.flag.values[hist], G[hist]), "saker": int(hist.sum())}
ut["uten_mot_i_historikk"] = {"uten_grense": e.maal(y[~hist], x.flag.values[~hist], G[~hist]), "saker": int((~hist).sum())}
# Sitater
s = x[x.flag & y & x.rationale_section.str.startswith("GVG")].copy(); s["rett"] = s.seksjon == s.rationale_section
s["i_hist"] = [v in logg[m]["bruker"].split("<saksliste>")[0] for m, v in zip(s.meeting_id, s.rationale_section)]
tab = tr[tr.rationale_section.str.startswith("GVG")].groupby("proposal_type").rationale_section.agg(lambda v: v.value_counts().index[0])
ut["sitater"] = {"vurdert": len(s), "riktig_seksjon": float(s.rett.mean()), "seksjon_i_historikk": int(s.i_hist.sum()), "riktig_naar_i_historikk": float(s[s.i_hist].rett.mean()) if s.i_hist.any() else None, "riktig_naar_ikke_i_historikk": float(s[~s.i_hist].rett.mean()) if (~s.i_hist).any() else None, "ikke_i_historikk": int((~s.i_hist).sum()), "bare_sakstype": float((s.proposal_type.map(tab) == s.rationale_section).mean())}
ut["sakstype_riktig"] = float((x.sakstype == x.proposal_type).mean())
# Mulige duplikater
nk = x.company_id + "|" + x.meeting_date + "|" + x.proposal_text.str.lower().str.replace(r"[^a-z0-9]", "", regex=True); u = ~nk.duplicated().to_numpy()
ut["uten_mulige_duplikater"] = {"fjernet": int((~u).sum()), "uten_grense": e.maal(y[u], x.flag.values[u], G[u])}
# Per år og sakstype
ut["per_aar"] = {int(a): e.maal(y[(x.aar == a).values], x.flag.values[(x.aar == a).values], G[(x.aar == a).values]) for a in sorted(x.aar.unique())}
t = x.assign(tp=x.flag & y).groupby("proposal_type").agg(saker=("y", "size"), mot=("y", "sum"), flagget=("flag", "sum"), treff=("tp", "sum")).sort_values("mot", ascending=False); ut["per_sakstype"] = t[(t.mot + t.flagget) > 0].reset_index().to_dict("records")
fa = x[x.flag & ~y]; ut["falske_per_selskap"] = fa.company.value_counts().head(8).to_dict(); ut["falske_per_regel"] = fa.regel_id.value_counts().head(8).to_dict(); ut["falske_totalt"] = len(fa)
kina = x.proposal_text.str.contains(r"(?i)^amend|^adopt new|articles|rules and procedures|working system|management (?:system|measures)") & (x.country == "China")
ut["kina_regelverk"] = {"saker": int(kina.sum()), "mot": int(y[kina.values].sum()), "flagget": int(x.flag[kina].sum()), "treff": int((x.flag & y)[kina].sum())}
ut["kalibrering"] = [{"fra": float(a), "til": float(b), "saker": int(((x.k > a) & (x.k <= b)).sum()), "riktig": float((x.flag.values == y)[((x.k > a) & (x.k <= b)).values].mean()) if ((x.k > a) & (x.k <= b)).any() else None} for a, b in [(0, .6), (.6, .8), (.8, .9), (.9, 1.0)]]
ut["sus_flagget"] = int(x.sus.sum()); ut["stopp"] = pd.Series([v["meta"].get("stop_reason", v["feil"]) for v in logg.values()]).value_counts().to_dict(); ut["mangler_svar"] = int((x.raastemme == "").sum())
ut["kostnad_usd"] = float(sum(agent.kost(v["meta"]) for v in logg.values()))
Path("resultater/sluttall.json").write_text(json.dumps(ut, indent=1, ensure_ascii=False, default=str))

m = lambda r: f"presisjon {r['presisjon']:.1%} ({r['presisjon_ki'][0]:.1%}-{r['presisjon_ki'][1]:.1%}), recall {r['recall']:.1%} ({r['recall_ki'][0]:.1%}-{r['recall_ki'][1]:.1%}), TP {r['tp']}, FP {r['fp']}, FN {r['fn']}"
print(f"TESTSETT 2025-2026: {ut['saker']} saker, {ut['moter']} møter, {ut['mot_styret']} mot styret ({ut['andel_mot']:.1%}). Mangler svar: {ut['mangler_svar']}. Stopp: {ut['stopp']}. Kostnad ${ut['kostnad_usd']:.2f}")
for n, r in ut["baseliner"].items():
    print(f"  {n:48s} accuracy {r['accuracy']:.1%} | {m(r)}")
print(f"  {'AGENT, uten grense':48s} accuracy {ut['uten_grense']['accuracy']:.1%} | {m(ut['uten_grense'])}")
print(f"AP: agent {ut['ap']['agent']:.3f} | tekstmodell {ut['ap']['tekstmodell']:.3f} | tilfeldig {ut['ap']['tilfeldig']:.3f}")
for nv in ["hoved", "alternativ"]:
    r = ut[nv]; print(f"\n{nv.upper()} grense {r['grense']}: egne flagg {m(r['egne_flagg'])}\n  til menneske {r['til_menneske']} ({r['til_menneske_andel']:.1%}), hvorav {r['mot_i_menneskebunken']} mot styret | leses totalt {r['leses']} ({r['leses_andel']:.1%}) | fanger {r['fanger']['recall']:.1%} (KI {r['fanger']['recall_ki'][0]:.1%}-{r['fanger']['recall_ki'][1]:.1%}) | oversett {r['oversett']} av {r['slipper_gjennom']} sluppet ({r['andel_oversett_av_sluppet']:.1%}) | tekstmodell ved samme lesing {r['tekstmodell_samme_lesing']:.1%}")
print("\nStreng MOT (styret FOR, NBIM MOT):", ut["streng_mot"]["fasit"], "|", m(ut["streng_mot"]["agent_uten_grense"]))
print("AVSTÅ:", ut["avstaa"]); r = ut["etter_kunnskapsgrense"]; print("\nETTER KUNNSKAPSGRENSEN (fra 01.07.2026):", r["hoved"]["saker"], "saker,", r["hoved"]["mot_styret"], "mot styret | agent", m(r["uten_grense"]), "| AP", r["ap_agent"], "\n  tekstmodell", m(r["tekstmodell"]), "\n  med grense: fanger", f"{r['hoved']['fanger']['recall']:.1%}", "leser", f"{r['hoved']['leses_andel']:.1%}")
print("FØR KUNNSKAPSGRENSEN:", m(ut["foer_kunnskapsgrense"]["uten_grense"]))
print("\nMED MOT I HISTORIKK:", ut["med_mot_i_historikk"]["saker"], m(ut["med_mot_i_historikk"]["uten_grense"])); print("UTEN MOT I HISTORIKK:", ut["uten_mot_i_historikk"]["saker"], m(ut["uten_mot_i_historikk"]["uten_grense"]))
print("\nSITATER:", ut["sitater"]); print("Sakstype riktig:", f"{ut['sakstype_riktig']:.1%}"); print("Uten mulige duplikater:", ut["uten_mulige_duplikater"]["fjernet"], "fjernet |", m(ut["uten_mulige_duplikater"]["uten_grense"]))
print("Per år:", {k: f"{v['presisjon']:.1%}/{v['recall']:.1%}" for k, v in ut["per_aar"].items()}); print("Kina regelverk:", ut["kina_regelverk"]); print("\nPer sakstype:"); print(t[(t.mot + t.flagget) > 0].to_string())
print("\nFalske alarmer:", ut["falske_totalt"], "| per selskap", ut["falske_per_selskap"], "| per regel", ut["falske_per_regel"]); print("Kalibrering:", [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items()} for c in ut["kalibrering"]]); print("Mistenkelig tekst flagget i testsettet:", ut["sus_flagget"])
