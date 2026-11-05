"""Reproduser hovedresultatet med ett kall:

    python kjor_alt.py

Steg: forbered data -> tidssplitt + baseliner -> tren agent (kun train.csv)
-> prediker test.csv -> evaluer mot NBIMs faktiske stemmer -> motstandstest.
Alt skrives til resultater/ (rapport.md er sammendraget).
"""

import csv
import subprocess
import sys
from pathlib import Path

PY = sys.executable
ROT = Path(__file__).parent
UT = ROT / "resultater"


def kjor(*args):
    print(f"\n$ python {' '.join(args)}", flush=True)
    r = subprocess.run([PY, *args], cwd=ROT, capture_output=True, text=True, encoding="utf-8",
                       env={**__import__("os").environ, "PYTHONIOENCODING": "utf-8"})
    print(r.stdout, end="")
    if r.returncode:
        print(r.stderr)
        sys.exit(f"Feilet: {' '.join(args)}")
    return r.stdout


def main():
    UT.mkdir(exist_ok=True)
    (UT / "kjoringslogg.jsonl").unlink(missing_ok=True)
    kjor("forbered_data.py")
    base = kjor("baseline.py", "data/votes_nbim.csv")
    kjor("agent.py", "tren")
    pred = kjor("agent.py", "prediker", "test.csv")
    uten = kjor("baseline.py", "data/votes_nbim.csv", "--ingen-filer",
                "--prediksjoner", "resultater/agent_pred_uten_menneske.csv")
    med = kjor("baseline.py", "data/votes_nbim.csv", "--ingen-filer",
               "--prediksjoner", "resultater/agent_pred.csv")
    motstand = kjor("agent.py", "motstandstest", "test.csv")

    # Fangst med menneske i loopen: MOT som agenten flagget + MOT sendt til menneske
    fasit = {r["id"]: r["mot_styret"] for r in csv.DictReader(open(ROT / "test.csv", encoding="utf-8"))}
    forkl = list(csv.DictReader(open(UT / "agent_forklaring.csv", encoding="utf-8")))
    mot = [r for r in forkl if fasit.get(r["id"]) == "1"]
    agent_mot = sum(r["rute"] == "AGENT" and r["pred_mot"] == "1" for r in mot)
    til_menneske = sum(r["rute"] == "MENNESKE" for r in mot)
    bom = sum(r["rute"] == "AGENT" and r["pred_mot"] == "0" for r in mot)
    andel_menneske = sum(r["rute"] == "MENNESKE" for r in forkl) / len(forkl)
    fangst = (f"MOT-stemmer i test: {len(mot)}. Agenten flagget {agent_mot}, sendte {til_menneske} til menneske, "
              f"bommet paa {bom} (sa FOR med hoey konfidens).\n"
              f"Fangst med menneske i loopen: {(agent_mot + til_menneske) / len(mot):.1%} av MOT-stemmene, "
              f"mens menneske ser {andel_menneske:.1%} av alle forslag.")
    print("\n" + fangst)

    rapport = ["# Resultater (generert av kjor_alt.py)\n",
               "## Baseliner og tidssplitt\n```", base.strip(), "```\n",
               "## Agenten uten menneske (svarer paa alt)\n```", uten.split("--- RESULTATER")[1].strip(), "```\n",
               "## Agenten med ruting til menneske\n```", med.split("=== C.")[1].strip(), "```\n",
               "## Prediksjon og sitering\n```", pred.strip(), "```\n",
               "## Fangst med menneske i loopen\n```", fangst, "```\n",
               "## Motstandstest\n```", motstand.strip(), "```"]
    (UT / "rapport.md").write_text("\n".join(rapport) + "\n", encoding="utf-8")
    print(f"\nSammendrag skrevet til {UT / 'rapport.md'}")


if __name__ == "__main__":
    main()
