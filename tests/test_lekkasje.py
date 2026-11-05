"""Beviser at fasiten for dagens møte ikke kan påvirke det agenten får se."""
import re, sys
sys.path.insert(0, "src")
import agent
d = agent.last_alt()
kandidater = d[(d.against_board == "1.0") & (d.rationale_text != "")].meeting_id.drop_duplicates()
testet = 0
for mid in kandidater.iloc[::12]:
    m = agent.moete_df(d, mid)
    foer = agent.brukerprompt(m, agent.historikk(d, m))
    # Ødelegg alle fasitfelt for dette og alle senere møter hos selskapet. Prompten skal være uendret.
    d2 = d.copy()
    maske = (d2.company_id == m.company_id.iloc[0]) & (d2.dato >= m.dato.iloc[0])
    for k in ["nbim_vote", "nbim_vote_raw", "rationale_text", "rationale_section", "position_paper"]:
        d2.loc[maske, k] = "LEKKASJE"
    d2.loc[maske, "against_board"] = "1.0"
    m2 = agent.moete_df(d2, mid)
    etter = agent.brukerprompt(m2, agent.historikk(d2, m2))
    assert foer == etter, f"Fasit lekker inn i prompten: {mid}"
    assert "LEKKASJE" not in etter
    # Historikken skal aldri inneholde et møte på eller etter møtedatoen
    h = agent.historikk(d, m)
    for dato in re.findall(r"(?:^Siste møte \(|^- )(\d{4}-\d{2}-\d{2})", h, re.M):
        assert dato < m.meeting_date.iloc[0], (mid, dato)
    testet += 1
print(f"OK: ingen lekkasje i {testet} møter med stemmer mot styret.")
