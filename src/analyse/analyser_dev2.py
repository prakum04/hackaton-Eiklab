"""Kontroll av agentens dev-resultat: er sitatene kopiert fra historikken? Hvor robust er tallene?"""
import sys, re, json, numpy as np, pandas as pd
sys.path.insert(0, "src")
import evaluer as e
pd.set_option("display.width", 210); pd.set_option("display.max_colwidth", 100); pd.set_option("display.max_rows", 60)
d = e.last(); _, te = e.splitt(d, "dev")
p = pd.read_csv("resultater/pred_dev.csv", dtype=str, keep_default_na=False)
x = te.merge(p, on="rad_id", validate="one_to_one"); x["k"] = x.konfidens.astype(float)
x["flag"] = (x.raastemme != x.mgmt_rec) & (x.raastemme != ""); x["tp"] = x.flag & (x.y == 1)
logg = {json.loads(l)["meeting_id"]: json.loads(l)["bruker"] for l in open("resultater/logg_dev.jsonl", encoding="utf-8")}
def hist(mid): return logg[mid].split("<saksliste>")[0]
x["i_hist"] = [bool(re.search(re.escape(s) + r"\b", hist(m))) if s else False for m, s in zip(x.meeting_id, x.rationale_section)]
x["har_mot_hist"] = [" mot styret." in hist(m) and not re.search(r"\b0 mot styret\.", hist(m)) for m in x.meeting_id]
s = x[x.tp & x.rationale_section.str.startswith("GVG")].copy(); s["rett"] = s.seksjon == s.rationale_section
print(f"SITATER paa {len(s)} treff: riktig seksjon {s.rett.mean():.1%}")
print(" fasitens seksjon staar i selskapets historikk:", int(s.i_hist.sum()), "| riktig blant dem:", f"{s[s.i_hist].rett.mean():.1%}" if s.i_hist.any() else "-")
print(" fasitens seksjon staar IKKE i historikken:", int((~s.i_hist).sum()), "| riktig blant dem:", f"{s[~s.i_hist].rett.mean():.1%}" if (~s.i_hist).any() else "-")
print(" Enkel sammenligning, seksjon gitt av sakstype: ", end="")
tab = d[(d.aar <= 2022) & d.rationale_section.str.startswith("GVG")].groupby("proposal_type").rationale_section.agg(lambda v: v.value_counts().index[0])
print(f"{(s.proposal_type.map(tab) == s.rationale_section).mean():.1%}")
print(" Fordeling fasit:", s.rationale_section.value_counts().head(8).to_dict())
print("\nFUNN med og uten historikk paa selskapet (MOT i tidligere moeter):")
for navn, g in [("med MOT i historikk", x[x.har_mot_hist]), ("uten MOT i historikk", x[~x.har_mot_hist])]:
    tp = g.tp.sum(); print(f" {navn:24s} saker {len(g):5d} mot {g.y.sum():4d} | flagg {g.flag.sum():4d} pres {tp / max(g.flag.sum(), 1):6.1%} recall {tp / max(g.y.sum(), 1):6.1%}")
print("\nPer aar:")
for y, g in x.groupby("aar"):
    tp = g.tp.sum(); print(f" {y} saker {len(g)} mot {g.y.sum()} flagg {g.flag.sum()} pres {tp / max(g.flag.sum(), 1):.1%} recall {tp / max(g.y.sum(), 1):.1%}")
print("\nPer sakstype:")
t = x.groupby("proposal_type").agg(n=("y", "size"), mot=("y", "sum"), flagget=("flag", "sum"), tp=("tp", "sum")).sort_values("mot", ascending=False); print(t[t.mot + t.flagget > 0].to_string())
print(f"\nSakstype riktig klassifisert: {(x.sakstype == x.proposal_type).mean():.1%}")
print("Mistenkelig instruks flagget:", (x.mistenkelig_instruks == "True").sum())
# Mulige dobbeltregistreringer: samme selskap, dato og tekst, ulik moete-ID
n = lambda v: re.sub(r"[^a-z0-9]", "", v.lower()); x["nk"] = x.company_id + "|" + x.meeting_date + "|" + x.proposal_text.map(n)
dup = x[x.groupby("nk").meeting_id.transform("nunique") > 1]; u = x.drop_duplicates("nk")
print(f"\nMULIGE DUPLIKATER i dev: {len(dup)} rader i {dup.nk.nunique()} grupper")
for navn, g in [("alle", x), ("uten duplikater", u)]:
    tp = g.tp.sum(); print(f" {navn:18s} saker {len(g)} mot {g.y.sum()} pres {tp / max(g.flag.sum(), 1):.1%} recall {tp / max(g.y.sum(), 1):.1%}")
print("\nBOOTSTRAP per moete for agent uten menneske, og med grense 0,80:")
for t_ in (0, .8):
    a = x.k >= t_; r = []; ids = x.meeting_id.values; idx = {k: v.to_numpy() for k, v in x.reset_index(drop=True).groupby("meeting_id").groups.items()}; ks = list(idx); rng = np.random.default_rng(0)
    fl = (x.flag & a).to_numpy(); y = (x.y == 1).to_numpy()
    for _ in range(1000):
        i = np.concatenate([idx[ks[j]] for j in rng.integers(0, len(ks), len(ks))]); r.append(((fl[i] & y[i]).sum() / max(fl[i].sum(), 1), (fl[i] & y[i]).sum() / max(y[i].sum(), 1)))
    r = np.array(r); print(f" grense {t_}: presisjon {np.percentile(r[:, 0], 2.5):.1%}-{np.percentile(r[:, 0], 97.5):.1%} | recall {np.percentile(r[:, 1], 2.5):.1%}-{np.percentile(r[:, 1], 97.5):.1%}")
print("\nBommet:"); print(x[(x.y == 1) & ~x.flag].sample(8, random_state=1)[["company", "proposal_text", "k", "rationale_section", "begrunnelse"]].to_string())
print("\nFalske alarmer:"); print(x[(x.y == 0) & x.flag].sample(6, random_state=1)[["company", "proposal_text", "k", "regel_id", "begrunnelse"]].to_string())
