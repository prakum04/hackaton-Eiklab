"""Sammenligner to agentversjoner paa samme dev-saker. Krav satt paa forhaand: den nye brukes bare hvis baade AP og F1 er hoeyere."""
import sys, numpy as np, pandas as pd
sys.path.insert(0, "src")
import evaluer as e
from sklearn.metrics import average_precision_score
pd.set_option("display.width", 220); pd.set_option("display.max_colwidth", 90); pd.set_option("display.max_rows", 90)
_, te = e.splitt(e.last(), "dev")
def last(n):
    p = pd.read_csv(f"resultater/pred_{n}.csv", dtype=str, keep_default_na=False)
    x = te.merge(p, on="rad_id", validate="one_to_one").sort_values("rad_id").reset_index(drop=True)
    x["k"] = x.konfidens.astype(float); x["flag"] = (x.raastemme != "") & (x.raastemme != x.mgmt_rec)
    x["regelmangel"] = x.flag & (x.regel_id == "0.0"); x["risiko"] = np.where(x.flag, x.k, 1 - x.k)
    return x
A, B = last("dev"), last("dev2"); assert (A.rad_id == B.rad_id).all()
y = A.y.values.astype(bool)
def rad(x, g=None):
    f = x.flag.values
    if g is not None:
        f = f & (x.k.values >= g) & ~x.regelmangel.values
    tp = (f & y).sum(); pr = tp / max(f.sum(), 1); re = tp / y.sum(); return f.sum(), tp, pr, re, 2 * pr * re / max(pr + re, 1e-9)
print(f"{'':18s} {'flagg':>6s} {'treff':>6s} {'pres':>7s} {'recall':>7s} {'F1':>7s} {'AP':>7s}")
for n, x in [("v1", A), ("v2", B)]:
    f, t, p, r, F = rad(x); print(f"{n:18s} {f:6d} {t:6d} {p:7.1%} {r:7.1%} {F:7.3f} {average_precision_score(y, x.risiko):7.3f}")
# Parvis bootstrap paa moeter
idx = {k: v.to_numpy() for k, v in A.groupby("meeting_id").groups.items()}; ks = list(idx); rng = np.random.default_rng(0); dF, dA = [], []
for _ in range(1000):
    i = np.concatenate([idx[ks[j]] for j in rng.integers(0, len(ks), len(ks))])
    def f1(x):
        f = x.flag.values[i]; t = (f & y[i]).sum(); return 2 * t / max(f.sum() + y[i].sum(), 1)
    dF.append(f1(B) - f1(A)); dA.append(average_precision_score(y[i], B.risiko.values[i]) - average_precision_score(y[i], A.risiko.values[i]))
print(f"Forskjell v2 - v1: F1 {np.mean(dF):+.3f} (95 % KI {np.percentile(dF, 2.5):+.3f} til {np.percentile(dF, 97.5):+.3f}) | AP {np.mean(dA):+.3f} (95 % KI {np.percentile(dA, 2.5):+.3f} til {np.percentile(dA, 97.5):+.3f})")
print("\nGrense for konfidens")
print(f"{'grense':>7s} | {'v1: lese%':>9s} {'fanger':>7s} {'pres':>6s} {'rec':>6s} {'ovs':>4s} | {'v2: lese%':>9s} {'fanger':>7s} {'pres':>6s} {'rec':>6s} {'ovs':>4s}")
for g in [.5, .6, .65, .7, .75, .8, .85, .9, .95]:
    s = f"{g:7.2f}"
    for x in (A, B):
        h = (x.k.values < g) | x.regelmangel.values; f = x.flag.values & ~h; tp = (f & y).sum(); l = h | f
        s += f" | {l.mean():9.1%} {(y & l).sum() / y.sum():7.1%} {tp / max(f.sum(), 1):6.1%} {tp / y.sum():6.1%} {(y & ~l).sum():4d}"
    print(s)
print("\nLest N saker etter risiko, andel fanget")
print(f"{'N':>5s} {'v1':>6s} {'v2':>6s}")
for n in [50, 100, 181, 300, 400, 600, 800, 1000]:
    print(f"{n:5d} {y[np.argsort(-A.risiko.values, kind='stable')[:n]].sum() / y.sum():6.1%} {y[np.argsort(-B.risiko.values, kind='stable')[:n]].sum() / y.sum():6.1%}")
print("\nPer sakstype (flagg / treff)")
t = pd.DataFrame({"n": A.groupby("proposal_type").size(), "mot": A.groupby("proposal_type").y.sum(), "v1_flagg": A.groupby("proposal_type").flag.sum(), "v1_treff": A[A.flag & (A.y == 1)].groupby("proposal_type").size(), "v2_flagg": B.groupby("proposal_type").flag.sum(), "v2_treff": B[B.flag & (B.y == 1)].groupby("proposal_type").size()}).fillna(0).astype(int).sort_values("mot", ascending=False); print(t[(t.mot + t.v1_flagg + t.v2_flagg) > 0])
for n, x in [("v1", A), ("v2", B)]:
    fa = x[x.flag & (x.y == 0)]; print(f"\n{n}: falske alarmer per selskap:", fa.company.value_counts().head(8).to_dict(), "| per regel:", fa.regel_id.value_counts().head(6).to_dict())
    m = x[x.flag & (x.y == 1) & x.rationale_section.str.startswith("GVG")]; print(f"{n}: sitat riktig seksjon {(m.seksjon == m.rationale_section).mean():.1%} av {len(m)} | sakstype riktig {(x.sakstype == x.proposal_type).mean():.1%} | AVSTAA foreslaatt {(x.raastemme == 'AVSTÅ').sum()} | regel 0.0 mot styret {x.regelmangel.sum()}")
    g = x.proposal_text.str.contains(r"(?i)^amend|^adopt new|articles|rules and procedures|working system|management (?:system|measures)") & (x.country == "China"); print(f"{n}: Kina regelverk: {g.sum()} saker, {x[g].y.sum()} mot, flagg {x[g].flag.sum()}, treff {(x[g].flag & (x[g].y == 1)).sum()}")
    hist_mot = x.groupby("company_id").y.transform("sum")
print("\nEndrede svar paa samme sak: v1 flagg -> v2 ikke flagg:", (A.flag & ~B.flag).sum(), "(riktig fjernet:", (A.flag & ~B.flag & ~y).sum(), ", tapte treff:", (A.flag & ~B.flag & y).sum(), ") | v1 ikke -> v2 flagg:", (~A.flag & B.flag).sum(), "(nye treff:", (~A.flag & B.flag & y).sum(), ", nye falske:", (~A.flag & B.flag & ~y).sum(), ")")
print("\nv2 tapte treff, eksempler:"); print(B[A.flag & ~B.flag & y].sample(min(6, (A.flag & ~B.flag & y).sum()), random_state=1)[["company", "proposal_text", "k", "begrunnelse"]].to_string())
