"""Hent stemmegivningsdata (SEC Form N-PX) for en forvalter og lag en ren CSV.

Hver rad i utfilen er ett forslag forvalteren stemte over, med:
    utsteder, cusip, isin, moetedato (ISO), forslag (ordrett fra stemmeseddelen),
    kategori, kilde (ISSUER = styret / SHAREHOLDER = aksjonaerforslag),
    stemme, styrets_anbefaling, aksjer, delt_stemme, mot_styret, aar_rapport

Maalvariabelen er `mot_styret` (1/0, tom hvis ikke sammenlignbar):
    1 = forvalteren stemte annerledes enn styret anbefalte.
Det er IKKE det samme som "stemte AGAINST": styret anbefaler ofte AGAINST
aksjonaerforslag, og da er en AGAINST-stemme aa stemme MED styret.

Bruk:
    python hent_npx.py --cik 1100663 --liste            # se N-PX-innsendingene
    python hent_npx.py --cik 1100663 --inspect          # se taggene i nyeste fil
    python hent_npx.py --cik 1100663 --ut votes.csv     # nyeste innsending
    python hent_npx.py --cik 1100663 --alle --ut votes.csv   # alle aar (anbefalt:
                                                         # gir tidsrekke for splitt)

VIKTIG OM VALG AV CIK:
  * Forvaltere som leverer N-PX som "institutional manager" (Act 34, filnr 028-...)
    rapporterer BARE say-on-pay-stemmer (lederloenn). Da faar dere bare en
    kategori.
  * Fond/trust (Act 40, filnr 811-...) rapporterer ALLE stemmer. Velg et slikt.
  * --liste viser filnummeret slik at dere ser hvilken type det er.
  Finn CIK: https://www.sec.gov/cgi-bin/browse-edgar?company=<navn>&type=N-PX

Bare Python 3 standardbibliotek. SEC krever User-Agent med kontaktinfo:
sett din egen e-post i USER_AGENT under (eller miljoevariabelen SEC_USER_AGENT).
"""

import argparse
import collections
import csv
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "Hackathon 2026 student din.epost@skole.no"  # <-- endre denne
)
CACHE = Path(__file__).with_name("data_cache")

# Bekreftet mot ekte N-PX-XML (proxyVoteTable-skjemaet, 2024-):
#   proxyTable > issuerName, cusip, isin, meetingDate, voteDescription,
#                voteCategories > voteCategory > categoryType, voteSource,
#                sharesVoted, sharesOnLoan,
#                vote > voteRecord > howVoted, sharesVoted, managementRecommendation
T_RAD = "proxyTable"
T_STEMMEPOST = "voteRecord"

# Stemmeverdier som regnes som en faktisk stemme. Alt annet (DID NOT VOTE osv.) -> ikke sammenlignbar.
GYLDIGE_STEMMER = {"FOR", "AGAINST", "ABSTAIN", "WITHHOLD", "1 YEAR", "2 YEARS", "3 YEARS"}
# Styret har gitt en anbefaling vi kan sammenligne med.
GYLDIGE_ANBEFALINGER = {"FOR", "AGAINST", "ABSTAIN", "1 YEAR", "2 YEARS", "3 YEARS"}


# ---------------------------------------------------------------- nedlasting

def hent(url, cache=True):
    """GET med User-Agent, enkel disk-cache og respekt for SECs rate-limit (10/s)."""
    sti = CACHE / re.sub(r"[^A-Za-z0-9._-]", "_", url.split("://", 1)[-1])
    if cache and sti.exists():
        return sti.read_bytes()
    if "din.epost@skole.no" in USER_AGENT:
        sys.exit("Sett din egen e-post i USER_AGENT i hent_npx.py (SEC krever det).")
    for forsok in range(4):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and forsok < 3:
                time.sleep(2 ** forsok * 2)
                continue
            raise SystemExit(f"HTTP {e.code} for {url}")
    time.sleep(0.15)
    if cache:
        CACHE.mkdir(exist_ok=True)
        sti.write_bytes(data)
    return data


def finn_npx_filer(cik, med_endringer=False):
    """Returner liste med dict for alle N-PX-innsendinger, nyeste foerst."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    data = json.loads(hent(url, cache=False))
    print(f"Filer: {data.get('name', '?')} (CIK {int(cik)})")
    blokker = [data["filings"]["recent"]]
    for ekstra in data["filings"].get("files", []):  # eldre innsendinger
        blokker.append(json.loads(hent("https://data.sec.gov/submissions/" + ekstra["name"])))
    treff = []
    for b in blokker:
        for i, form in enumerate(b["form"]):
            if form == "N-PX" or (med_endringer and form == "N-PX/A"):
                treff.append({
                    "form": form,
                    "accession": b["accessionNumber"][i].replace("-", ""),
                    "dato": b["filingDate"][i],
                    "periode": b.get("reportDate", [""] * len(b["form"]))[i],
                    "filnr": b.get("fileNumber", [""] * len(b["form"]))[i],
                })
    # Strukturert XML finnes bare fra 2024. Eldre N-PX er fritekst og kan ikke parses her.
    treff = [t for t in treff if t["dato"] >= "2024-07-01"]
    return sorted(treff, key=lambda t: t["dato"], reverse=True)


def hent_stemmetabell(cik, accession):
    """Finn og returner XML-en med selve stemmene (ikke forsiden primary_doc.xml)."""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}"
    indeks = json.loads(hent(f"{base}/index.json"))
    kandidater = []
    for post in indeks["directory"]["item"]:
        navn = post["name"]
        lav = navn.lower()
        if lav.endswith(".xml") and lav != "primary_doc.xml":
            kandidater.append(navn)
        elif lav.endswith(".zip"):
            kandidater.append(navn)
    # Typiske navn: ProxyVotingTable.xml, proxytable.xml, FormN-PX_ProxyVoteTable.xml
    kandidater.sort(key=lambda n: ("vot" not in n.lower() and "proxy" not in n.lower(), n))
    for navn in kandidater:
        data = hent(f"{base}/{navn}")
        if navn.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(data))
            for indre in z.namelist():
                if indre.lower().endswith(".xml"):
                    innhold = z.read(indre)
                    if b"proxyVoteTable" in innhold[:2000]:
                        return innhold
        elif b"proxyVoteTable" in data[:2000]:
            return data
    raise SystemExit(f"Fant ingen stemmetabell (proxyVoteTable) i {base}")


# ---------------------------------------------------------------- parsing

def _lokal(tag):
    return tag.rsplit("}", 1)[-1]


def _tekst(node, navn):
    for el in node:
        if _lokal(el.tag) == navn:
            return (el.text or "").strip()
    return ""


def _norm_stemme(v):
    v = " ".join(v.upper().split())
    return {"WITHHOLD": "AGAINST", "WITHHELD": "AGAINST", "1 YEARS": "1 YEAR",
            "ONE YEAR": "1 YEAR", "TWO YEARS": "2 YEARS", "THREE YEARS": "3 YEARS"}.get(v, v)


def _iso_dato(s):
    m = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
    return s[:10]


def _til_int(s):
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return 0


def parse(xml_bytes, aar_rapport=""):
    """Gaa gjennom proxyTable-elementene i stroem (taaler store filer)."""
    rader = []
    for _, node in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        if _lokal(node.tag) != T_RAD:
            continue
        kategorier = sorted({
            (el.text or "").strip() for el in node.iter()
            if _lokal(el.tag) == "categoryType" and (el.text or "").strip()
        })
        poster = []
        for el in node.iter():
            if _lokal(el.tag) == T_STEMMEPOST:
                poster.append({
                    "stemme": _norm_stemme(_tekst(el, "howVoted")),
                    "anbefaling": _norm_stemme(_tekst(el, "managementRecommendation")),
                    "aksjer": _til_int(_tekst(el, "sharesVoted")),
                })
        if not poster:
            node.clear()
            continue
        # Delt stemme: flere voteRecord med ulik retning. Bruk den med flest aksjer.
        hoved = max(poster, key=lambda p: p["aksjer"])
        delt = len({p["stemme"] for p in poster}) > 1
        stemme, anbef = hoved["stemme"], hoved["anbefaling"]
        if stemme in GYLDIGE_STEMMER and anbef in GYLDIGE_ANBEFALINGER:
            mot = "1" if stemme != anbef else "0"
        else:
            mot = ""  # ikke sammenlignbar (stemte ikke / styret ga ingen anbefaling)
        rader.append({
            "utsteder": _tekst(node, "issuerName"),
            "cusip": _tekst(node, "cusip"),
            "isin": _tekst(node, "isin"),
            "moetedato": _iso_dato(_tekst(node, "meetingDate")),
            "forslag": " ".join(_tekst(node, "voteDescription").split()),
            "kategori": "; ".join(kategorier),
            "kilde": _tekst(node, "voteSource").upper(),
            "stemme": stemme,
            "styrets_anbefaling": anbef,
            "aksjer": sum(p["aksjer"] for p in poster),
            "delt_stemme": int(delt),
            "mot_styret": mot,
            "aar_rapport": aar_rapport,
        })
        node.clear()
    return rader


def inspiser(xml_bytes):
    """Skriv ut tagger og verdifordeling, saa dere ser at dataene er som forventet."""
    teller = collections.Counter()
    verdier = collections.defaultdict(collections.Counter)
    for _, el in ET.iterparse(io.BytesIO(xml_bytes), events=("end",)):
        tag = _lokal(el.tag)
        if el.text and el.text.strip():
            teller[tag] += 1
            if tag in ("howVoted", "managementRecommendation", "voteSource", "categoryType"):
                verdier[tag][el.text.strip()] += 1
    print("\nTagger (antall med tekst):")
    for tag, n in teller.most_common(40):
        print(f"{n:9d}  {tag}")
    for tag, c in verdier.items():
        print(f"\nVerdier for {tag}:")
        for v, n in c.most_common(15):
            print(f"{n:9d}  {v}")


# ---------------------------------------------------------------- hovedprogram

def oppsummer(rader):
    n = len(rader)
    samm = [r for r in rader if r["mot_styret"] != ""]
    mot = sum(r["mot_styret"] == "1" for r in samm)
    print(f"\n{n} forslag totalt, {len(samm)} sammenlignbare med styrets anbefaling.")
    if samm:
        print(f"Mot styret: {mot} ({mot / len(samm):.1%})")
    kat = collections.Counter(r["kategori"] for r in rader)
    if len(kat) <= 2:
        print("ADVARSEL: bare 1-2 kategorier. Dette er trolig en forvalter-N-PX (bare "
              "say-on-pay). Velg et fond/trust (filnr 811-...) for alle stemmer.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--cik", required=True)
    p.add_argument("--liste", action="store_true", help="vis N-PX-innsendinger og avslutt")
    p.add_argument("--inspect", action="store_true", help="vis tagger i nyeste stemmetabell")
    p.add_argument("--alle", action="store_true", help="hent alle aar, ikke bare nyeste")
    p.add_argument("--endringer", action="store_true", help="ta med N-PX/A")
    p.add_argument("--ut", default="votes.csv")
    a = p.parse_args()

    filer = finn_npx_filer(a.cik, a.endringer)
    if not filer:
        sys.exit("Ingen strukturerte N-PX-innsendinger (2024-) funnet for denne CIK-en.")

    if a.liste:
        print(f"\n{'innsendt':12} {'periode':12} {'filnr':14} {'form':7} accession")
        for f in filer:
            print(f"{f['dato']:12} {f['periode']:12} {f['filnr']:14} {f['form']:7} {f['accession']}")
        print("\nfilnr 811-... = fond (alle stemmer). 028-... = forvalter (bare say-on-pay).")
        return

    valgte = filer if a.alle else filer[:1]
    if a.inspect:
        inspiser(hent_stemmetabell(a.cik, valgte[0]["accession"]))
        return

    alle = []
    for f in valgte:
        print(f"Henter {f['form']} innsendt {f['dato']} (periode {f['periode']}) ...")
        xml = hent_stemmetabell(a.cik, f["accession"])
        rader = parse(xml, aar_rapport=f["periode"][:4])
        print(f"  {len(rader)} forslag")
        alle.extend(rader)

    if not alle:
        sys.exit("Ingen rader. Kjoer --inspect og sjekk taggene mot T_RAD/T_STEMMEPOST.")

    alle.sort(key=lambda r: (r["moetedato"], r["utsteder"]))
    for i, r in enumerate(alle):
        r["id"] = i
    kolonner = ["id"] + [k for k in alle[0] if k != "id"]
    with open(a.ut, "w", newline="", encoding="utf-8") as fil:
        w = csv.DictWriter(fil, fieldnames=kolonner)
        w.writeheader()
        w.writerows(alle)
    print(f"\nSkrev {len(alle)} forslag til {a.ut}")
    oppsummer(alle)


if __name__ == "__main__":
    main()
