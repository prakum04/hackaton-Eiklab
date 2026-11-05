"""Stemmer NBIM slik retningslinjene sier? Bonusspørsmålet i casen.
Vi ser bare på regler som kan sjekkes rett fra forslagsteksten. Andre regler krever fakta om styret, som vi ikke har.
Ingen API-kall. Bruker alle år med fasit, siden dette beskriver NBIM og ikke måler agenten."""
import pandas as pd
pd.set_option("display.width", 200); pd.set_option("display.max_colwidth", 95)
d = pd.read_csv("data/arrangor/real_votes.csv", dtype=str, keep_default_na=False)
d = d[d.nbim_vote.isin(["FOR", "MOT", "AVSTÅ"])]
SJEKK = [("5.2.2", "Other business", "MOT", r"(?i)other business"),
         ("1.3.3", "Skille styreleder og CEO", "FOR", r"(?i)independent (?:board )?chair|separate.*(?:chair|ceo)"),
         ("3.1.2", "Avvikle klassifisert styre", "FOR", r"(?i)declassif"),
         ("3.1.1", "Innføre klassifisert styre", "MOT", r"(?i)(?<!de)classif(?:y|ied)|stagger")]
tot = ok = 0
for regel, navn, venter, m in SJEKK:
    q = d[d.proposal_text.str.contains(m)]
    a = int((q.nbim_vote == venter).sum()); tot += len(q); ok += a
    print(f"Regel {regel} {navn}: venter {venter}, {a} av {len(q)} følger regelen")
    avvik = q[q.nbim_vote != venter]
    if len(avvik):
        print(avvik[["company", "meeting_date", "proposal_text", "proponent", "mgmt_rec", "nbim_vote", "rationale_section"]].to_string(index=False))
print(f"Totalt: {ok} av {tot} følger regelen")
v = d[(d.company == "Volkswagen AG") & (d.proposal_type == "DISCHARGE")]
print("\nPraksis som endrer seg: ansvarsfritak i Volkswagen per år (saker, MOT):", {y: (len(g), int((g.nbim_vote == "MOT").sum())) for y, g in v.groupby("year")})
