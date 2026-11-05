"""Lokal nettside for aa teste og utforske stemmegivningsagenten.

Bruk:
    python app.py              # aapner http://127.0.0.1:8000 i nettleseren
    python app.py --port 8080  # annen port

Tre faner:
  Oversikt          resultater paa testsettet (mot baselinene), per land og per forslagstype
  Utforsk selskaper velg land -> selskap -> generalforsamling; agentens vurdering ved siden av NBIMs faktiske stemme
  Egen saksliste    lim inn forslag, valgfritt med et selskaps historikk

Bare Python 3 standardbibliotek. Kjoerer kun lokalt (127.0.0.1). Agenten avgir bare
anbefalinger - ingen stemmer sendes. Vurderinger fra "Egen saksliste" logges i
resultater/kjoringslogg.jsonl.
"""

import argparse
import collections
import json
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import agent
import baseline

ROT = Path(__file__).parent
VOTES = ROT / "data" / "votes_nbim.csv"
SIDE = ROT / "web" / "index.html"
STEMME_NO = {"FOR": "FOR", "AGAINST": "MOT", "ABSTAIN": "AVSTÅ", "": ""}


# ------------------------------------------------------------------ data og forhaandsberegning

def last_alt():
    t0 = time.time()
    M, KORPUS, GJ, HIST = agent.last_modell()
    if not VOTES.exists():
        subprocess.run([sys.executable, "forbered_data.py"], cwd=ROT, check=True)
    alle = agent.les(VOTES)
    til = M["train_til"]
    # Agenten vurderer alle forslag. Historikk brukes bare fra moeter FOER hvert forslags dato.
    res = {r["id"]: r for r in agent.vurder(alle, M, KORPUS, GJ, HIST)}
    for r in alle:
        r["periode"] = "test" if r["moetedato"] > til else "trening"
    print(f"Vurderte {len(alle)} forslag paa {time.time() - t0:.1f} s")
    return M, KORPUS, GJ, HIST, alle, res


def metr(fasit, pred):
    tp = sum(1 for f, p in zip(fasit, pred) if f and p)
    fp = sum(1 for f, p in zip(fasit, pred) if not f and p)
    return tp, fp, (tp / (tp + fp) if tp + fp else None)


def oversikt(alle, res, M):
    klar = baseline.klargjor([dict(r) for r in alle])     # samme opprydding som baseline.py
    til = M["train_til"]
    train = [r for r in klar if r["moetedato"] <= til]
    test = [r for r in klar if r["moetedato"] > til]
    fasit = [r["mot_styret"] == "1" for r in test]
    n_mot = sum(fasit)
    a = [res[r["id"]] for r in test]

    pred_b, _ = baseline.kategori_baseline(train, test)
    tp_b, fp_b, p_b = metr(fasit, pred_b)
    tp_u, fp_u, p_u = metr(fasit, [x["pred_mot_uten_menneske"] == "1" for x in a])
    agent_mot = [x["rute"] == "AGENT" and x["pred_mot"] == "1" for x in a]
    tp_a, fp_a, p_a = metr(fasit, agent_mot)
    menneske = [x["rute"] == "MENNESKE" for x in a]
    tp_m = sum(1 for f, m in zip(fasit, menneske) if f and m)
    bom = sum(1 for f, x in zip(fasit, a) if f and x["rute"] == "AGENT" and x["pred_mot"] == "0")

    def grupper(nokkel):
        g = collections.defaultdict(lambda: dict(n=0, mot=0, fant=0, menneske=0, bom=0, falske=0))
        for r, x, f in zip(test, a, fasit):
            d = g[nokkel(r, x)]
            d["n"] += 1
            d["mot"] += f
            if x["rute"] == "MENNESKE":
                d["menneske"] += f
            elif x["pred_mot"] == "1":
                d["fant" if f else "falske"] += 1
            elif f:
                d["bom"] += 1
        return [dict(navn=k, **v) for k, v in sorted(g.items(), key=lambda kv: (-kv[1]["mot"], -kv[1]["n"]))]

    return {
        "periode": [test[0]["moetedato"], test[-1]["moetedato"]], "train_til": til,
        "n": len(test), "n_mot": n_mot, "n_menneske": sum(menneske),
        "metoder": [
            {"navn": "Følg alltid styret", "fant": 0, "falske": 0, "presisjon": None},
            {"navn": "Enkel regel (forslagstype)", "fant": tp_b, "falske": fp_b, "presisjon": p_b},
            {"navn": "Agenten, svarer på alt", "fant": tp_u, "falske": fp_u, "presisjon": p_u},
            {"navn": "Agenten + menneske", "fant": tp_a + tp_m, "falske": fp_a, "presisjon": None,
             "merknad": f"agenten {tp_a} + menneske {tp_m}"},
        ],
        "agent": {"fant": tp_a, "menneske_mot": tp_m, "bom": bom, "falske": fp_a, "presisjon": p_a},
        "per_land": grupper(lambda r, x: r["land"] or "Ukjent"),
        "per_type": grupper(lambda r, x: x["type"]),
    }


def selskaper(alle):
    g = {}
    for r in alle:
        s = g.setdefault(r["cusip"], dict(id=r["cusip"], navn=r["utsteder"], land=r["land"], marked=r["marked"],
                                          moter=set(), forslag=0, mot=0, test=0))
        s["moter"].add(r["moete_id"])
        s["forslag"] += 1
        s["mot"] += r["mot_styret"] == "1"
        s["test"] += r["periode"] == "test"
    ut = []
    for s in g.values():
        s["moter"] = len(s["moter"])
        ut.append(s)
    return sorted(ut, key=lambda s: s["navn"].lower())


def selskap_detalj(alle, res, sid):
    rader = [r for r in alle if r["cusip"] == sid]
    if not rader:
        return None
    moter = collections.OrderedDict()
    for r in sorted(rader, key=lambda r: (r["moetedato"], r["moete_id"], int(float(r["punkt"] or 0)))):
        x = res[r["id"]]
        f = r["mot_styret"]
        if x["rute"] == "MENNESKE":
            utfall = "menneske"
        elif f not in ("0", "1"):
            utfall = "ukjent"
        else:
            utfall = "riktig" if x["pred_mot"] == f else "feil"
        m = moter.setdefault(r["moete_id"], dict(id=r["moete_id"], dato=r["moetedato"], periode=r["periode"], punkter=[]))
        m["punkter"].append({
            "punkt": r["punkt"], "forslag": r["forslag"], "kilde": r["kilde"],
            "styret": STEMME_NO.get(r["styrets_anbefaling"], r["styrets_anbefaling"]),
            "nbim": STEMME_NO.get(r["stemme"], r["stemme"]), "nbim_mot": f,
            "nbim_seksjon": r["fasit_seksjon"], "nbim_begrunnelse": r["fasit_begrunnelse"],
            "anbefaling": x["anbefaling"], "rute": x["rute"], "pred_mot": x["pred_mot"],
            "p_mot": x["p_mot"], "konfidens": x["konfidens"], "type": x["type"],
            "retningslinje": x["retningslinje"], "retningslinje_rolle": x["retningslinje_rolle"],
            "retningslinje_sitat": x["retningslinje_sitat"], "begrunnelse": x["begrunnelse"],
            "utfall": utfall,
        })
    s = rader[0]
    return {"id": sid, "navn": s["utsteder"], "land": s["land"], "marked": s["marked"],
            "moter": list(reversed(moter.values()))}


# ------------------------------------------------------------------ server

class App:
    def __init__(self):
        self.M, self.KORPUS, self.GJ, self.HIST, self.alle, self.res = last_alt()
        self.oversikt = oversikt(self.alle, self.res, self.M)
        self.selskaper = selskaper(self.alle)
        self.land = sorted({k.split("=", 1)[1] for k in self.M["vekter"] if k.startswith("land=") and k != "land="}
                           | {s["land"] for s in self.selskaper if s["land"]})
        self.meta = {"trent": self.M.get("trent", "")[:10], "train_til": self.M["train_til"],
                     "t_mot": self.M["t_mot"], "t_lav": self.M["t_lav"], "land": self.land}

    def vurder_tekst(self, data):
        a = SimpleNamespace(land=data.get("land") or "United States", marked=data.get("marked") or "DM",
                            selskap=data.get("selskap") or "WEB")
        linjer = [l.strip() for l in str(data.get("tekst", "")).splitlines()]
        rader = [agent.tolk_linje(i, l, a) for i, l in enumerate(linjer) if l and not l.startswith("#")]
        if not rader:
            raise ValueError("Sakslisten er tom.")
        ut = agent.vurder(rader, self.M, self.KORPUS, self.GJ, self.HIST)
        agent.logg("web", ut, self.M)
        return ut


APP = None


class Handler(BaseHTTPRequestHandler):
    def _json(self, kode, obj):
        self._svar(kode, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

    def _svar(self, kode, tekst, type_):
        body = tekst.encode("utf-8")
        self.send_response(kode)
        self.send_header("Content-Type", type_)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._svar(200, SIDE.read_text(encoding="utf-8"), "text/html; charset=utf-8")
            if u.path == "/api/meta":
                return self._json(200, APP.meta)
            if u.path == "/api/oversikt":
                return self._json(200, APP.oversikt)
            if u.path == "/api/selskaper":
                return self._json(200, APP.selskaper)
            if u.path == "/api/selskap":
                d = selskap_detalj(APP.alle, APP.res, (q.get("id") or [""])[0])
                return self._json(200, d) if d else self._json(404, {"feil": "Fant ikke selskapet."})
            self._json(404, {"feil": "ikke funnet"})
        except Exception as e:
            self._json(500, {"feil": str(e)})

    def do_POST(self):
        if urlparse(self.path).path != "/api/vurder":
            return self._json(404, {"feil": "ikke funnet"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            if n > 1_000_000:
                return self._json(413, {"feil": "For stor saksliste."})
            self._json(200, {"resultater": APP.vurder_tekst(json.loads(self.rfile.read(n) or b"{}"))})
        except ValueError as e:
            self._json(400, {"feil": str(e)})
        except Exception as e:
            self._json(500, {"feil": str(e)})

    def log_message(self, fmt, *args):
        pass


def main():
    global APP
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--ikke-aapne", action="store_true", help="ikke aapne nettleseren automatisk")
    a = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    APP = App()
    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    url = f"http://127.0.0.1:{a.port}"
    print(f"Stemmegivningsagenten kjoerer paa {url}  (Ctrl+C for aa stoppe)")
    if not a.ikke_aapne:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStoppet.")


if __name__ == "__main__":
    main()
