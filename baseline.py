"""Baselinene dere maa slaa, med splitt etter tid og riktig metrikk.

Maalvariabel: mot_styret (1 = forvalteren stemte annerledes enn styret anbefalte).
Metrikk: presisjon, recall og F1 paa MOT STYRET - ikke accuracy.

Bruk:
    python baseline.py votes.csv
    python baseline.py votes.csv --split-dato 2025-04-01
    python baseline.py votes.csv --prediksjoner agent_pred.csv   # evaluer agenten

Skriptet:
  1. Fjerner rader uten sammenlignbar stemme og slaar sammen duplikater
     (samme forslag stemt av flere fond i samme trust -> flertallsstemme).
  2. Deler etter TID: alt foer --split-dato er trening, alt etter er test.
     (Standard: datoen der 80 % av moetene ligger foer.)
  3. Skriver train.csv og test.csv, saa agent-teamet jobber paa samme splitt.
  4. Rapporterer paa TESTSETTET:
       A. Alltid med styret           (den offisielle baselinen, 90-95 % accuracy)
       B. Kategori-baseline           (MOT hvis andelen MOT i kategorien paa
                                       treningssettet er over en terskel valgt paa
                                       treningssettet)
       C. Agenten (hvis --prediksjoner er gitt)

Format paa --prediksjoner: CSV med kolonnene id og pred_mot.
    pred_mot = 1 (agenten sier mot styret), 0 (med styret),
               tom eller "MENNESKE" (sendt til menneskelig vurdering).
Rader sendt til menneske telles ikke som feil, men dekningen rapporteres.

ADVARSEL om B: N-PX-kategorien er satt av forvalteren og kan lekke informasjon.
Den er grei som baseline, men agenten boer lage sin egen kategori fra forslagsteksten.
"""

import argparse
import csv
import sys
from collections import Counter, defaultdict


def les(sti):
    with open(sti, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def skriv(sti, rader):
    if not rader:
        return
    with open(sti, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rader[0]))
        w.writeheader()
        w.writerows(rader)


def klargjor(rader):
    """Behold sammenlignbare rader og slaa sammen duplikater med flertallsstemme."""
    samm = [r for r in rader if r.get("mot_styret") in ("0", "1")]
    grupper = defaultdict(list)
    for r in samm:
        grupper[(r["cusip"], r["moetedato"], r["forslag"].lower())].append(r)
    ut = []
    for gruppe in grupper.values():
        mot = sum(int(r["mot_styret"]) for r in gruppe)
        rad = dict(gruppe[0])
        rad["mot_styret"] = "1" if mot * 2 > len(gruppe) else "0"
        rad["antall_fond"] = len(gruppe)
        ut.append(rad)
    ut.sort(key=lambda r: (r["moetedato"], int(r["id"])))
    return ut


def metrikker(faktisk, pred):
    tp = sum(p and f for p, f in zip(pred, faktisk))
    fp = sum(p and not f for p, f in zip(pred, faktisk))
    fn = sum((not p) and f for p, f in zip(pred, faktisk))
    tn = len(faktisk) - tp - fp - fn
    pres = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * pres * rec / (pres + rec) if pres + rec else 0.0
    return dict(n=len(faktisk), tp=tp, fp=fp, fn=fn, tn=tn,
                acc=(tp + tn) / len(faktisk) if faktisk else 0.0,
                pres=pres, rec=rec, f1=f1)


def skriv_rapport(navn, m, ekstra=""):
    print(f"\n=== {navn} ===")
    if ekstra:
        print(ekstra)
    print(f"  Forslag vurdert         : {m['n']}")
    print(f"  Accuracy                : {m['acc']:.1%}   <- ikke bruk alene")
    print(f"  Presisjon paa MOT       : {m['pres']:.1%}")
    print(f"  Recall paa MOT          : {m['rec']:.1%}   <- tallet som teller")
    print(f"  F1 paa MOT              : {m['f1']:.1%}")
    print(f"  Treff / falske pos.     : {m['tp']} / {m['fp']}"
          + (f"  ({m['fp'] / m['tp']:.1f} falske per treff)" if m['tp'] else ""))


def nokkel(r):
    return f"{r.get('kategori') or 'UKJENT'} | {r.get('kilde') or '?'}"


def kategori_baseline(train, test):
    """Andel MOT per (kategori, kilde) paa trening; terskel valgt paa trening."""
    tot, mot = Counter(), Counter()
    for r in train:
        tot[nokkel(r)] += 1
        mot[nokkel(r)] += int(r["mot_styret"])
    global_andel = sum(mot.values()) / max(1, sum(tot.values()))

    def andel(r):
        k = nokkel(r)
        # Glatting mot global andel, saa sjeldne kategorier ikke faar ekstreme verdier.
        return (mot[k] + 5 * global_andel) / (tot[k] + 5)

    fasit_tr = [r["mot_styret"] == "1" for r in train]
    beste = (0.0, 0.5)
    for t in sorted({round(andel(r), 4) for r in train}):
        f1 = metrikker(fasit_tr, [andel(r) >= t for r in train])["f1"]
        if f1 > beste[0]:
            beste = (f1, t)
    terskel = beste[1]
    pred = [andel(r) >= terskel for r in test]

    topp = sorted(tot, key=lambda k: mot[k] / tot[k], reverse=True)[:8]
    tabell = "  Hoeyest andel MOT paa trening (kategori | kilde):\n" + "\n".join(
        f"    {mot[k] / tot[k]:6.1%}  ({mot[k]:>5}/{tot[k]:<6}) {k[:80]}" for k in topp)
    return pred, f"  Terskel valgt paa trening: {terskel:.1%}\n{tabell}"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("votes")
    p.add_argument("--split-dato", help="YYYY-MM-DD. Moeter fra og med denne datoen = test.")
    p.add_argument("--prediksjoner", help="CSV med id,pred_mot fra agenten")
    p.add_argument("--ingen-filer", action="store_true", help="ikke skriv train.csv/test.csv")
    a = p.parse_args()

    raa = les(a.votes)
    print("Fordeling stemme -> styrets anbefaling (raadata):")
    for (s, an), n in Counter((r["stemme"], r["styrets_anbefaling"]) for r in raa).most_common(10):
        print(f"  {n:8d}  stemte {s!r:12} styret anbefalte {an!r}")

    rader = klargjor(raa)
    if not rader:
        sys.exit("Ingen sammenlignbare rader. Sjekk kolonnen mot_styret i votes.csv.")
    print(f"\n{len(raa)} rader -> {len(rader)} unike, sammenlignbare forslag.")

    datoer = sorted(r["moetedato"] for r in rader)
    split = a.split_dato or datoer[int(len(datoer) * 0.8)]
    train = [r for r in rader if r["moetedato"] < split]
    test = [r for r in rader if r["moetedato"] >= split]
    if not train or not test:
        sys.exit(f"Splitt paa {split} ga tomt trenings- eller testsett. Velg en annen --split-dato.")
    print(f"Splitt etter tid paa {split}:")
    print(f"  trening {len(train):6d} forslag  {train[0]['moetedato']} .. {train[-1]['moetedato']}"
          f"  MOT {sum(r['mot_styret'] == '1' for r in train) / len(train):.1%}")
    print(f"  test    {len(test):6d} forslag  {test[0]['moetedato']} .. {test[-1]['moetedato']}"
          f"  MOT {sum(r['mot_styret'] == '1' for r in test) / len(test):.1%}")
    if not a.ingen_filer:
        skriv("train.csv", train)
        skriv("test.csv", test)
        print("  Skrev train.csv og test.csv (bruk samme filer for agenten).")

    fasit = [r["mot_styret"] == "1" for r in test]
    print("\n--------------- RESULTATER PAA TESTSETTET ---------------")
    skriv_rapport("A. Alltid med styret (offisiell baseline)", metrikker(fasit, [False] * len(test)))
    pred_b, info = kategori_baseline(train, test)
    skriv_rapport("B. Kategori-baseline (N-PX-kategori + kilde)", metrikker(fasit, pred_b), info)

    if a.prediksjoner:
        agent = {r["id"]: r.get("pred_mot", "").strip().upper() for r in les(a.prediksjoner)}
        vurdert = [(r, agent[r["id"]]) for r in test
                   if r["id"] in agent and agent[r["id"]] in ("0", "1")]
        menneske = sum(1 for r in test if agent.get(r["id"], "") in ("", "MENNESKE"))
        mangler = sum(1 for r in test if r["id"] not in agent)
        if not vurdert:
            sys.exit("Ingen av agentens prediksjoner matchet id-er i testsettet.")
        m = metrikker([r["mot_styret"] == "1" for r, _ in vurdert], [p == "1" for _, p in vurdert])
        # Recall over HELE testsettet: MOT-forslag sendt til menneske regnes som ikke funnet av agenten.
        alle_mot = sum(fasit)
        rec_total = m["tp"] / alle_mot if alle_mot else 0.0
        skriv_rapport(
            "C. Agenten", m,
            f"  Dekning: {len(vurdert)}/{len(test)} besvart, {menneske} sendt til menneske"
            + (f", {mangler} uten prediksjon" if mangler else "")
            + f"\n  Recall over hele testsettet (inkl. de sendt til menneske): {rec_total:.1%}")


if __name__ == "__main__":
    main()
