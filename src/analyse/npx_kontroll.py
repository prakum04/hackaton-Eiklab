"""Hvorfor npx_votes.csv ikke brukes som NBIM-fasit. Sammenlignes med Norges Banks egne SEC-filer og real_votes.
Krever data/votes_nbim.csv (lages med: python src/hent_npx.py --cik 1374170 --ut data/votes_nbim.csv)."""
import re, pandas as pd
rd = lambda f: pd.read_csv(f, dtype=str, keep_default_na=False)
N, R, S = rd("data/arrangor/npx_votes.csv"), rd("data/arrangor/real_votes.csv"), rd("data/votes_nbim.csv")
S["d"] = pd.to_datetime(S.meeting_date, format="%m/%d/%Y", errors="coerce").dt.strftime("%Y-%m-%d"); S["v"] = S.how_voted.map({"FOR": "FOR", "AGAINST": "MOT", "WITHHOLD": "MOT"})
kort = lambda s: re.sub(r"\b(inc|corp|corporation|co|company|ltd|limited|plc|sa|ag|nv|the|holdings?|group)\b", "", re.sub(r"[^a-z0-9 ]", " ", s.lower())).replace(" ", "")
S["k"] = S.issuer.map(kort); R["k"] = R.company.map(kort); sf = S[S.v.notna()].drop_duplicates(["k", "d"]); sc = S[S.v.notna()].drop_duplicates(["cusip", "d"])
b = R[R.proposal_type == "SAY_ON_PAY"].merge(sf, left_on=["k", "meeting_date"], right_on=["k", "d"], suffixes=("", "_s"))
b = b[b.nbim_vote.isin(["FOR", "MOT"])]; print(f"real_votes mot Norges Banks N-PX (say-on-pay): {len(b)} par, {(b.nbim_vote == b.v).sum()} like")
a = N[N.proposal_type == "SAY_ON_PAY"].merge(sc, left_on=["company_id", "meeting_date"], right_on=["cusip", "d"], suffixes=("", "_s"))
a = a[a.nbim_vote.isin(["FOR", "MOT"])]; print(f"npx_votes mot Norges Banks N-PX (say-on-pay): {(a.v == 'MOT').sum()} MOT i SEC-filene der npx har en stemme, {((a.v == 'MOT') & (a.nbim_vote == 'MOT')).sum()} av dem er MOT også i npx_votes")
x = N[N.against_board.isin(["0.0", "1.0"])].copy(); x["y"] = x.against_board == "1.0"; p = x.proponent == "Shareholder"; tp = (p & x.y).sum()
print(f"npx_votes: regelen «MOT på alle aksjonærforslag» gir presisjon {tp / p.sum():.1%} og recall {tp / x.y.sum():.1%} uten å lese forslagene")
print("npx_votes «mot styret» fordelt:"); print(x[x.y].groupby(["proponent", "mgmt_rec", "nbim_vote"]).size().sort_values(ascending=False).to_string())
s = x[x.proposal_type == "SAY_ON_PAY"]; print(f"Say-on-pay mot styret i npx_votes: {s.y.sum()} av {len(s)} = {s.y.mean():.1%}")
