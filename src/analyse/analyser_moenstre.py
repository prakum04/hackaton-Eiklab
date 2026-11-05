"""Moenstre i NBIMs stemmer til og med 2024. Testsettet 2025-2026 er filtrert bort foer noe annet skjer."""
import sys, re, numpy as np, pandas as pd
sys.path.insert(0, "src")
import evaluer as e
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 105); pd.set_option("display.max_rows", 90)
d = e.last(); d = d[d.aar <= 2024].copy(); assert d.dato.max() < pd.Timestamp("2025-01-01")
print("Saker til og med 2024:", len(d), "mot styret:", d.y.sum())
print("\nA) Bare saker der styret anbefaler FOR, per fremmet av:"); print(d.groupby(["proponent", "mgmt_rec"]).y.agg(["size", "sum", "mean"]).round(3))
p = pd.read_csv("resultater/pred_dev.csv", dtype=str, keep_default_na=False); x = d.merge(p, on="rad_id"); x["flag"] = (x.raastemme != x.mgmt_rec)
n = x[x.flag & (x.regel_id == "0.0")]
print("\nB) Agenten gikk mot styret, men siterte regel 0.0 (stoett styret):", len(n)); print(n[["company", "proposal_text", "proponent", "mgmt_rec", "raastemme", "nbim_vote", "begrunnelse"]].head(9).to_string())
print("\nC) Sakstype og land, minst 25 saker, sortert paa andel mot:")
t = d.groupby(["proposal_type", "country"]).y.agg(["size", "sum", "mean"]).reset_index(); print(t[(t["size"] >= 25) & (t["sum"] >= 3)].sort_values("mean", ascending=False).head(26).round(3).to_string(index=False))
print("\nD) Endring av styringsdokumenter/interne regler i tekst, per land og aar:")
am = d[d.proposal_text.str.contains(r"(?i)^amend|^adopt new|articles|rules and procedures|working system|management (?:system|measures)")]
print(am.groupby(["market"]).y.agg(["size", "sum", "mean"]).round(3)); t = am.groupby("country").y.agg(["size", "sum", "mean"]).reset_index(); print(t[t["sum"] >= 2].sort_values("sum", ascending=False).round(3).to_string(index=False))
ch = am[am.country == "China"]; print(" Kina per aar:", ch.groupby("aar").y.agg(["size", "sum"]).T.to_dict()); print(" Kina per selskap, mot:", ch[ch.y == 1].company.value_counts().head(10).to_dict())
print(" Kina-tekster med mot:", ch[ch.y == 1].proposal_text.str[:70].value_counts().head(12).to_dict())
print(" Kina-tekster uten mot:", ch[ch.y == 0].proposal_text.str[:70].value_counts().head(10).to_dict())
print(" Begrunnelse paa Kina-mot:", ch[ch.y == 1].rationale_text.str[:230].value_counts().head(2).to_dict())
print("\nE) Begrunnelser for GVG 3.2 og 1.1 (hyppigste tekster):")
for s_ in ["GVG 3.2", "GVG 1.1", "GVG 4.3"]:
    g = d[(d.rationale_section == s_)]; print(s_, len(g), g.proposal_type.value_counts().head(4).to_dict(), g.market.value_counts().to_dict(), "selskaper", g.company.nunique())
print("\nF) Gjentar NBIM seg? For selskap+sakstype: stemme paa forrige moete mot stemme paa dette (per sak):")
mt = d.groupby(["company_id", "proposal_type", "meeting_id", "dato"]).y.max().reset_index().sort_values("dato"); mt["forrige"] = mt.groupby(["company_id", "proposal_type"]).y.shift(1); mt = mt.dropna(subset=["forrige"]); print(pd.crosstab(mt.forrige, mt.y)); 
print(" P(mot | mot sist): %.3f | P(mot | ikke mot sist): %.3f" % (mt[mt.forrige == 1].y.mean(), mt[mt.forrige == 0].y.mean()))
mt["to_siste"] = mt.groupby(["company_id", "proposal_type"]).y.shift(1).fillna(0) ; 
print("\nG) Treff etter om selskapet har MOT i historikk paa SAMME type, dev:")
print("\nH) Anbefalingsfeltet: andel FOR-stemmer der styret sier MOT paa aksjonaerforslag per land topp:"); s = d[(d.proponent == "Shareholder")]; print(s.groupby(["mgmt_rec", "nbim_vote"]).size().to_dict())
print("\nI) Personer: mot paa samme navn tidligere?")
de = d[d.proposal_type == "DIRECTOR_ELECTION"].copy(); de["nm"] = de.proposal_text.str.lower().str.replace(r"[^a-z ]", " ", regex=True).str.replace(r"\b(elect|reelect|re elect|director|as|non|independent|executive|to|the|board|supervisory|member|of|and|ratify|appoint|nominee|shareholder|no|with)\b", " ", regex=True).str.split().str.join(" ")
de = de.sort_values("dato"); de["for_mot"] = de.groupby(["company_id", "nm"]).y.shift(1); q = de.dropna(subset=["for_mot"]); print(pd.crosstab(q.for_mot, q.y)); print(" P(mot | samme person mot sist): %.3f | P(mot | samme person ikke mot sist): %.3f | foerste gang: %.3f" % (q[q.for_mot == 1].y.mean(), q[q.for_mot == 0].y.mean(), de[de.for_mot.isna()].y.mean()))
