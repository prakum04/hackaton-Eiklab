"""Reproduserer hovedresultatet med ett kall: python reproduser.py

Bruker lagrede svar fra agenten, så det trengs ingen API-nøkkel og det koster ingenting. Skriptet kontrollerer at
data og agent er uendret siden låsing, at fasiten ikke lekker inn i prompten, og at tallene stemmer med det vi har rapportert.
"""
import json, subprocess, sys
from pathlib import Path

PY = sys.executable


def kjor(tittel, *cmd):
    print(f"\n{'=' * 90}\n{tittel}\n{'=' * 90}", flush=True)
    r = subprocess.run([PY, *cmd], capture_output=True, text=True)
    linjer = [l for l in r.stdout.splitlines() if "Warning" not in l]
    print("\n".join(linjer), flush=True)
    if r.returncode != 0:
        print(r.stderr[-1500:]); sys.exit(f"Feilet: {tittel}")


for f in ["data/arrangor/real_votes.csv", "data/retningslinjer/gvg2024_regler.json", "resultater/pred_test.csv", "resultater/logg_test.jsonl", "resultater/laast_agent.json"]:
    if not Path(f).exists():
        sys.exit(f"Mangler {f}. Kjør fra prosjektmappen, og se README.")
laas = json.loads(Path("resultater/laast_agent.json").read_text())
hash_ = {json.loads(l)["system_hash"] for l in open("resultater/logg_test.jsonl", encoding="utf-8")}
if hash_ != {laas["system_hash"]}:
    sys.exit(f"Testloggen er ikke kjørt med den låste agenten: {hash_}")
print(f"Alle svar i testloggen kommer fra den låste agenten (prompt {laas['system_hash']}, låst {laas['laast']}).")
kjor("1. Lekkasjetest: kan fasiten påvirke det agenten ser?", "tests/test_lekkasje.py")
kjor("Bygger agentens svar på nytt fra råloggen", "src/agent.py", "--lag-pred", "--navn", "test")
kjor("2. Sluttest 2025-2026, samme evaluering som mot baselinene", "src/evaluer.py", "--sett", "test", "--pred", "resultater/pred_test.csv", "--ut", "resultater/evaluering_test.json")
kjor("3. Sluttrapport, inkludert kontroll av at agent og data er uendret siden låsing", "src/sluttrapport.py")
kjor("4. Kontroller av testresultatet (gjentakelser, lette saker)", "src/kontroll_test.py")
kjor("5. Motstandstest, runde 1 (lagrede svar)", "src/motstandstest.py", "--rapport")
kjor("6. Motstandstest, runde 2 (lagrede svar)", "src/motstandstest.py", "--runde", "2", "--rapport")

n = json.loads(Path("resultater/sluttall.json").read_text()); fv = json.loads(Path("resultater/forventet.json").read_text())
naa = {"saker": n["saker"], "mot_styret": n["mot_styret"], "presisjon": round(n["uten_grense"]["presisjon"], 4), "recall": round(n["uten_grense"]["recall"], 4), "ap_agent": round(n["ap"]["agent"], 4),
       "leses_andel": round(n["hoved"]["leses_andel"], 4), "fanger": round(n["hoved"]["fanger"]["recall"], 4), "oversett": n["hoved"]["oversett"]}
print(f"\n{'=' * 90}\nHOVEDRESULTAT\n{'=' * 90}")
print(f"Agenten på {naa['saker']} saker fra 2025-2026, {naa['mot_styret']} mot styret: presisjon {naa['presisjon']:.1%}, recall {naa['recall']:.1%}, AP {naa['ap_agent']:.3f}.")
print(f"Med konfidensgrense {n['hoved']['grense']}: et menneske leser {naa['leses_andel']:.1%} av sakene, {naa['fanger']:.1%} av «mot styret» fanges, og {naa['oversett']} oversees.")
avvik = {k: (naa[k], fv[k]) for k in fv if naa.get(k) != fv[k]}
if avvik:
    sys.exit(f"AVVIK fra rapporterte tall: {avvik}")
print("OK: tallene stemmer med det vi har rapportert.")
