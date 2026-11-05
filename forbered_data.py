"""Gjoer NBIM-stemmene (data/real_votes.csv) om til formatet baseline.py forventer.

Bruk:
    python forbered_data.py                      # data/real_votes.csv -> data/votes_nbim.csv
    python forbered_data.py --inn data/npx_votes.csv --ut data/votes_npx.csv

Maalvariabel: mot_styret = against_board (1 = NBIM stemte annerledes enn styret anbefalte).
Tom naar styret ikke ga anbefaling eller NBIM ikke stemte.

Kolonner som bare finnes FORDI NBIM stemte mot (rationale_text, rationale_section,
position_paper) tas med som fasit-kolonner med prefiks fasit_. Agenten skal aldri
bruke dem som input - de brukes bare til aa bygge retningslinje-korpuset fra
treningsperioden og til aa sjekke siteringen etterpaa.
"""

import argparse
import csv

STEMME = {"FOR": "FOR", "MOT": "AGAINST", "AVSTÅ": "ABSTAIN", "": ""}


def mal(v):
    v = (v or "").strip()
    if v in ("1.0", "1"):
        return "1"
    if v in ("0.0", "0"):
        return "0"
    return ""


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--inn", default="data/real_votes.csv")
    p.add_argument("--ut", default="data/votes_nbim.csv")
    a = p.parse_args()

    with open(a.inn, encoding="utf-8") as f:
        raa = list(csv.DictReader(f))
    raa.sort(key=lambda r: (r["meeting_date"], r["meeting_id"], int(float(r["item_no"] or 0))))

    ut = []
    for i, r in enumerate(raa):
        ut.append({
            "id": i,
            "utsteder": r["company"],
            "cusip": r["company_id"],          # selskaps-ID (brukes av baseline.py til duplikatsjekk)
            "isin": "",
            "moetedato": r["meeting_date"],
            "forslag": " ".join(r["proposal_text"].split()),
            "kategori": r["proposal_type"],
            "kilde": "SECURITY HOLDER" if r["proponent"] == "Shareholder" else "ISSUER",
            "stemme": STEMME.get(r["nbim_vote"], r["nbim_vote"]),
            "styrets_anbefaling": STEMME.get(r["mgmt_rec"], r["mgmt_rec"]),
            "aksjer": "",
            "delt_stemme": "",
            "mot_styret": mal(r["against_board"]),
            "aar_rapport": r["year"],
            "land": r["country"],
            "marked": r["market"],
            "moete_id": r["meeting_id"],
            "punkt": r["item_no"],
            "injeksjon": r.get("injection_flag", "0"),
            "fasit_seksjon": r.get("rationale_section", ""),
            "fasit_begrunnelse": r.get("rationale_text", ""),
            "fasit_posisjonsnotat": r.get("position_paper", ""),
        })

    with open(a.ut, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(ut[0]))
        w.writeheader()
        w.writerows(ut)
    n = sum(r["mot_styret"] in ("0", "1") for r in ut)
    m = sum(r["mot_styret"] == "1" for r in ut)
    print(f"Skrev {len(ut)} forslag til {a.ut}: {n} sammenlignbare, {m} mot styret ({m / max(1, n):.1%}).")


if __name__ == "__main__":
    main()
