"""Hent SEC Form N-PX (strukturert XML) og skriv en flat CSV med en rad per forslag per fond.

Erstatter startpakkens hent_npx.py, som (a) brukte BlackRock Inc. sin innsending, som er en
ren notice report uten stemmer, (b) leste voteRecord, som er en overordnet tagg uten tekst,
og (c) bare hentet nyeste innsending.

Bruk:
    python src/hent_npx.py --cik 52848 --aar 2024 2025 2026 --ut data/votes_52848.csv
    python src/hent_npx.py --cik 52848 --list

Kontaktinfo til SEC leses fra SEC_USER_AGENT i .env (se .env.example).
Innsendinger mellomlagres i data/raw/, saa gjentatte kjoeringer ikke laster ned paa nytt.
"""
import argparse, csv, http.client, io, json, os, re, sys, time, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

RAW = Path("data/raw")
NS = "{http://www.sec.gov/edgar/document/npxproxy/informationtable}"
FELT = ["cik", "accession", "filed", "period", "series", "issuer", "cusip", "isin", "meeting_date",
        "proposal", "categories", "source", "how_voted", "mgmt_rec", "n_vote_records", "split_vote", "shares_voted"]


def user_agent():
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua and Path(".env").exists():
        for l in Path(".env").read_text().splitlines():
            if l.startswith("SEC_USER_AGENT="):
                ua = l.split("=", 1)[1].strip()
    if not ua:
        sys.exit("Sett SEC_USER_AGENT i .env, f.eks. SEC_USER_AGENT=Navn <epost@skole.no>")
    return ua


def hent(url, forsok=5):
    """SEC gir sporadisk 503 paa enkeltfiler, saa vi proever igjen med oekende pause."""
    for i in range(forsok):
        time.sleep(0.15 + 3 * i)  # under SEC sin grense paa 10 kall/sekund
        try:
            req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
            with urllib.request.urlopen(req, timeout=180) as r:
                return r.read()
        except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
            print(f"  [{e}] forsok {i + 1}/{forsok}: {url}", file=sys.stderr)
    return None


def innsendinger(cik):
    data = json.loads(hent(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"))
    r = data["filings"]["recent"]
    ut = []
    for f, a, d, p, rp in zip(r["form"], r["accessionNumber"], r["filingDate"], r["primaryDocument"], r["reportDate"]):
        if f.startswith("N-PX"):
            ut.append({"form": f, "accession": a, "filed": d, "period": rp, "xml": p.endswith(".xml")})
    return data.get("name"), data.get("entityType"), ut


def proxytabell(txt):
    """Plukk ut proxyVoteTable-dokumentet fra den fulle innsendingen (.txt)."""
    m = re.search(rb"<(?:\w+:)?proxyVoteTable.*?</(?:\w+:)?proxyVoteTable>", txt, re.S)
    return m.group(0) if m else None


def parse(xml_bytes, meta):
    rader = []
    for _, el in ET.iterparse(io.BytesIO(xml_bytes)):
        if el.tag != NS + "proxyTable":
            continue
        tekst = lambda t: (el.findtext(NS + t) or "").strip()
        rec = el.findall(f"{NS}vote/{NS}voteRecord")
        stemmer = []
        for v in rec:
            try:
                n = float(v.findtext(NS + "sharesVoted") or 0)
            except ValueError:
                n = 0.0
            stemmer.append(((v.findtext(NS + "howVoted") or "").strip().upper(), n,
                            (v.findtext(NS + "managementRecommendation") or "").strip().upper()))
        topp = max(stemmer, key=lambda s: s[1]) if stemmer else ("", 0.0, "")
        rader.append({**meta, "series": tekst("voteSeries"), "issuer": tekst("issuerName"), "cusip": tekst("cusip"),
                      "isin": tekst("isin"), "meeting_date": tekst("meetingDate"),
                      "proposal": " ".join(tekst("voteDescription").split()),
                      "categories": "|".join((c.text or "").strip() for c in el.iter(NS + "categoryType")),
                      "source": tekst("voteSource"), "how_voted": topp[0], "mgmt_rec": topp[2],
                      "n_vote_records": len(stemmer), "split_vote": int(len({s[0] for s in stemmer}) > 1),
                      "shares_voted": sum(s[1] for s in stemmer)})
        el.clear()
    return rader


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cik", required=True)
    p.add_argument("--aar", nargs="*", default=["2024", "2025", "2026"])
    p.add_argument("--list", action="store_true")
    p.add_argument("--maks", type=int, default=0, help="maks antall innsendinger per aar (0 = alle)")
    p.add_argument("--ut")
    a = p.parse_args()

    navn, typ, alle = innsendinger(a.cik)
    print(f"{a.cik} {navn} ({typ}): {len(alle)} N-PX, {sum(x['xml'] for x in alle)} i XML")
    if a.list:
        for x in alle[:60]:
            print(" ", x)
        return
    valgt, per = [], {}
    for x in alle:
        y = x["filed"][:4]
        if x["xml"] and y in a.aar and (not a.maks or per.get(y, 0) < a.maks):
            valgt.append(x); per[y] = per.get(y, 0) + 1
    print("Valgt:", per)
    RAW.mkdir(parents=True, exist_ok=True)
    ut = a.ut or f"data/votes_{a.cik}.csv"
    n = tom = feil = 0
    with open(ut, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FELT); w.writeheader()
        for x in valgt:
            acc = x["accession"]; nd = acc.replace("-", "")
            c = RAW / f"{a.cik}_{nd}.txt"
            if not c.exists() or c.stat().st_size == 0:
                b = hent(f"https://www.sec.gov/Archives/edgar/data/{int(a.cik)}/{nd}/{acc}.txt")
                if b is None:
                    feil += 1; continue
                c.write_bytes(b)
            t = proxytabell(c.read_bytes())
            if t is None:
                tom += 1; continue
            rader = parse(t, {"cik": a.cik, "accession": acc, "filed": x["filed"], "period": x["period"]})
            w.writerows(rader); n += len(rader)
    print(f"Skrev {n} rader til {ut}. Uten stemmetabell: {tom}. Mislykket nedlasting: {feil}.")
    if feil:
        sys.exit(f"{feil} innsendinger kunne ikke lastes ned. Kjoer paa nytt, ferdige filer gjenbrukes.")


if __name__ == "__main__":
    main()
