"""Gjoer NBIMs Global Voting Guidelines (PDF) om til en regelfil med stabile ID-er.

Agenten skal sitere regel-ID-er herfra, og koden henter selve regelteksten fra denne filen.
Da kan ikke agenten dikte opp et sitat.  Bruk: python src/regler.py
"""
import json, re, subprocess
from pathlib import Path

PDF = "data/retningslinjer/gvg2024.pdf"
UT = "data/retningslinjer/gvg2024_regler.json"
GRENSE = 0.655  # hovedspalten; sitatboksene i margen starter til hoeyre for dette
SEKSJONER = [("1.1", "Independence of the board"), ("1.2", "Independence of main committees"),
             ("1.3", "Separation of chairperson and CEO"), ("2.1", "Time commitment"), ("2.2", "Industry expertise"),
             ("2.3", "Diversity"), ("3.1", "Board nomination and election"), ("3.2", "Board decisions and conduct"),
             ("3.3", "CEO remuneration"), ("4.1", "Voting rights"), ("4.2", "Shareholder meeting"),
             ("4.3", "Governing documents"), ("5.1", "Auditor"), ("5.2", "Financial statements"), ("5.3", "Sustainability"),
             ("6.1", "Share issuance"), ("6.2", "Mergers, acquisitions and other corporate"), ("6.3", "Related party-transaction")]


def tekst():
    """Bare hovedspalten: sitatboksene i hoeyre marg skjaeres bort."""
    w, h = map(float, re.search(r"Page size:\s+([\d.]+) x ([\d.]+)", subprocess.run(["pdfinfo", PDF], capture_output=True, text=True).stdout).groups())
    return subprocess.run(["pdftotext", "-layout", "-f", "5", "-x", "0", "-y", "0", "-W", str(int(w * GRENSE)), "-H", str(int(h)), "-r", "72", PDF, "-"],
                          capture_output=True, text=True, check=True).stdout


def parse():
    linjer = [l.rstrip() for l in tekst().splitlines()]
    ut, gjeldende, regel = [], None, None
    neste = 0
    for l in linjer:
        s = l.strip()
        if not s or s.startswith("Norges Bank Investment Management") or "Global voting guidelines" in s:
            regel = regel if s else None if regel is None else regel
            continue
        m = re.match(r"^(\d)\.\s+(.+)$", s)
        if neste < len(SEKSJONER) and m and s[3:].strip().lower().startswith(SEKSJONER[neste][1].lower()[:18]) and not l.startswith(" "):
            gjeldende = {"seksjon": SEKSJONER[neste][0], "tittel": SEKSJONER[neste][1], "prinsipp": [], "regler": []}
            ut.append(gjeldende); neste += 1; regel = None; continue
        if gjeldende is None:
            continue
        if m and re.match(r"^(We will|In general|In developed|In emerging|At a )", m.group(2)):
            regel = {"id": f"{gjeldende['seksjon']}.{len(gjeldende['regler']) + 1}", "tekst": m.group(2)}
            gjeldende["regler"].append(regel); continue
        if regel is not None and l.startswith("   "):
            regel["tekst"] += " " + s; continue
        if re.match(r"^\d\.\s+(Board|Shareholder|Company|Capital)\b", s):
            regel = None; continue
        if regel is None:
            gjeldende["prinsipp"].append(s)
        else:
            regel = None; gjeldende["prinsipp"].append(s)
    for g in ut:
        g["prinsipp"] = " ".join(g["prinsipp"])
        for x in g["regler"]:
            x["tekst"] = re.sub(r"(\w)- (\w)", r"\1-\2", x["tekst"])  # orddeling over linjeskift
    return ut


if __name__ == "__main__":
    r = parse()
    assert [x["seksjon"] for x in r] == [s for s, _ in SEKSJONER], [x["seksjon"] for x in r]
    Path(UT).write_text(json.dumps(r, indent=1, ensure_ascii=False))
    print(f"{len(r)} seksjoner, {sum(len(x['regler']) for x in r)} regler -> {UT}")
