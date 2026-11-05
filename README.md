# Stemmegivningsagenten

FinTech Hackathon H2026, Case 1. Lag: [Gruppenavn].

Agenten leser sakslisten til en generalforsamling og foreslår FOR, MOT eller AVSTÅ på hver sak, med regel fra NBIMs retningslinjer, begrunnelse og konfidens. Usikre saker og mistenkelig tekst går til et menneske. Agenten stemmer aldri selv.

## Reproduser hovedresultatet

Ett kommandolinjekall, fra denne mappen (testet med Python 3.12 på Ubuntu):

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python reproduser.py
```

**Kjør fra zip-filen.** Det offentlige repoet mangler `data/arrangor/`, `resultater/logg_*` og `resultater/pred_*`, fordi vi ikke legger arrangørens data og svar per sak ut offentlig. Zip-filen vi leverer har alt.

På Windows bruker du `.venv\Scripts\` i stedet for `.venv/bin/`. Kallet tar rundt ett minutt, koster ingenting og trenger ingen API-nøkkel, fordi det bruker agentens lagrede svar. Skriptet bygger svarene på nytt fra råloggen, kontrollerer at data og agent er uendret siden låsing, kjører lekkasjetesten og stopper hvis tallene avviker fra de rapporterte.

## Resultat

Testsett 2025–2026: 3 448 saker fra 310 møter, 169 der NBIM gikk mot styret (4,9 %). Agenten var låst før kjøringen.

| Metode | Accuracy | Presisjon | Recall |
| --- | --- | --- | --- |
| Alltid med styret | 95,1 % | 0 % | 0 % |
| Sakstyper med minst 50 % mot i trening | 95,4 % | 73,9 % | 10,1 % |
| Mot på samme sakstype på forrige møte | 85,1 % | 16,5 % | 50,3 % |
| Enkel tekstmodell (logistisk regresjon) | 84,3 % | 18,1 % | 62,7 % |
| **Agenten** | **96,7 %** | **70,4 %** (62,1–78,1) | **56,2 %** (45,5–65,3) |

Tall i parentes er 95 %-intervaller, trukket per møte. Rangering (average precision): agent 0,578, tekstmodell 0,361, tilfeldig 0,049.

**MOT-stemmer:** Målet er at NBIM går mot styret, som også teller 39 AVSTÅ-stemmer og 44 FOR-stemmer der styret sa MOT i hele datasettet. Bare saker der styret sa FOR og NBIM sa MOT: 68,8 % presisjon og 54,8 % recall. Alle MOT-stemmer fra NBIM uansett styret: agenten 71,4 % og 59,0 %, «stem som styret» 67,7 % og 11,8 %.

**Sjekk mot casen:** Casen oppgir 94 % med styret i 2025. I fasiten er tallet 94,6 %. Testsettet samlet har 95,1 %.

**Arbeidsdeling med konfidensgrense 0,80 (låst på forhånd):** Et menneske ser 239 saker (6,9 %), og 66,9 % av sakene mot styret er fanget (95 %-intervall 55,8–76,6). Av 3 209 saker som slipper gjennom, er 56 mot styret og oversett (1,7 %). Tekstmodellen fanger 47,3 % med samme lesemengde. Alternativ grense 0,90 (også låst på forhånd): 20,9 % leses, 79,3 % fanges.

## Slik virker det

1. **Inndata:** forslagstekst, hvem som fremmet forslaget, styrets anbefaling, land, marked og NBIMs stemmer fra før møtedatoen. Begrunnelsesfeltene og stemmen for dagens møte er aldri med.
2. **Regler:** `src/regler.py` gjør NBIMs retningslinjer om til 70 regler med ID. Agenten kan bare velge blant disse, og koden henter regelteksten, så sitatet ikke kan diktes opp. Retningslinjene er korte nok til å ligge i prompten i sin helhet, så vi bruker ikke søk (RAG).
3. **Forslag:** `src/agent.py` kaller Claude Opus 5.5 med strukturert svar: sakstype, stemme, regel, begrunnelse, konfidens og om teksten prøver å gi instrukser.
4. **Overlevering:** lav konfidens, mistenkelig tekst, manglende svar, avslag og «mot styret» uten konkret regel går til et menneske, aldri til et stille FOR.
5. **Sporbarhet:** hvert kall logges med prompt-hash, modell, råsvar og tokenforbruk i `resultater/logg_*.jsonl`.

## Evaluering

- **Fasit:** `against_board` i `real_votes.csv` (13 324 brukbare forslag, 193 selskaper, 2019–2026). Den stemmer med Norges Banks egne SEC-filer i 90 av 92 say-on-pay-saker.
- **Splitt etter tid:** Agenten ble justert på 2023–2024. Baselinene for testen er trent på data til og med 2024. Testsettet ble kjørt én gang.
- **Låsing:** `resultater/laast_agent.json` holder fingeravtrykk av prompt, skjema, modell og inndatafunksjoner, og koden nekter å kjøre testsettet hvis agenten er endret.
- **Lekkasjetest:** `tests/test_lekkasje.py` bytter ut fasiten for et møte og alle senere møter og krever at prompten er identisk, i 30 møter.
- **Forbedring på utviklingssettet:** Versjon 1 fikk 39,6 % presisjon og 49,2 % recall, versjon 2 fikk 59,1 % og 53,6 %. Kravet om høyere AP og F1 ble satt før versjon 2 ble kjørt. Vi brukte dette settet til å finne forbedringene, så tallene der er optimistiske.

## Motstandstest

Vi la 50 skjulte instrukser og falske påstander inn i 16 tilfeldig trukne møter fra 2023–2024, med en nøytral kontrollsetning i hvert møte. Ingen angrep endret stemmen, alle 50 ble merket og sendt til et menneske, og ingen av de 16 kontrollene ga falsk alarm. Av 1 032 andre saker i de samme møtene endret 1 stemme sammenlignet med kontrollen. Vi kjørte også 16 ekte merknader fra stemmesystemer (`injection_flag = 1` i `npx_votes.csv`). Ingen ble merket som mistenkelige.

Angrepene var ikke tilpasset agenten, og en angriper som kjenner prompten kan formulere seg mer subtilt.

## Begrensninger

- **Gjentakelser:** Agenten finner 88,2 % (75 av 85) når NBIM gikk mot styret på samme sakstype på forrige møte, men 23,8 % (20 av 84) på nye saker.
- **Kunnskapsgrense:** Modellens kunnskap går til juni 2026, så den kan huske utfall. Etter grensen fant den 5 av 7 saker med 2 falske alarmer, men det er for få til å utelukke dette.
- **Utvalg:** Vi kjenner ikke hvordan de 193 selskapene er valgt. Tallene gjelder ikke nødvendigvis hele porteføljen.
- **AVSTÅ:** 5 saker i testen, ingen treff.
- **Lette saker:** Uten «Other Business» er presisjonen 67,5 % og recall 52,9 %.
- **Retningslinjer:** Utgaven fra 2024 brukes på alle år.
- **Mønstre kan endre seg:** Hintet om interne regelverk i Kina kom fra tidligere år. I testen var det 14 slike saker, ingen mot styret, og agenten flagget 2 feil.
- **Tynn tekst:** Sakslisten mangler fakta om uavhengighet, oppmøte og verv.
- **Avvik fra forslaget i casen:** Hele retningslinjen ligger i prompten i stedet for RAG, fordi 70 regler får plass og et søk da ikke kan gå glipp av riktig regel. Posisjonsnotatene og innkallingene (DEF 14A) er ikke med.
- **Innlimt saksliste:** Appen antar at styret anbefaler FOR på styreforslag og MOT på aksjonærforslag. Ekte møter fra dataene bruker den registrerte anbefalingen.
- **Bruk:** Egner seg til å sortere saker for en analytiker, ikke til å stemme selv.

## Stemmer NBIM slik retningslinjene sier?

`src/analyse/praksis_mot_policy.py` ser på reglene som kan sjekkes rett fra forslagsteksten: «other business» (5.2.2), å skille styreleder og CEO (1.3.3) og å avvikle klassifisert styre (3.1.2). NBIM fulgte regelen i 55 av 55 saker. De fleste andre regler krever fakta om styret, så om dem kan vi ikke si noe. Praksis kan likevel endre seg over tid: i Volkswagen stemte NBIM mot ansvarsfritak i 31 av 33 saker i 2019 og i ingen fra 2023.

## Hvorfor ikke `npx_votes.csv` som fasit

`src/analyse/npx_kontroll.py` viser at 1 032 av 1 936 saker merket «mot styret» er aksjonærforslag der styret står som FOR, og 772 er AVSTÅ-stemmer. Mot Norges Banks SEC-filer gjenfinnes 13 av 55 MOT-stemmer. Regelen «MOT på alle aksjonærforslag» får 92,1 % presisjon uten å lese forslagene.

## Kjør appen

```bash
cp .env.example .env    # legg inn ANTHROPIC_API_KEY for å kjøre agenten live
streamlit run app.py
```

Fanen «Resultater mot NBIM» virker uten nøkkel. Appen lytter bare på din egen maskin.

## Kjør agenten på nytt

Dette koster penger, og svarene varierer litt. Testsettet er markert som ferdig og kjøres ikke på nytt, med mindre `resultater/batch_test.ferdig` og låsen fjernes bevisst.

```bash
python src/agent.py --sett dev --navn min_kjoring --batch
python src/agent.py --lag-pred --navn min_kjoring --terskel 0.8
python src/evaluer.py --sett dev --pred resultater/pred_min_kjoring.csv
```

Vi brukte rundt $22 totalt i API-kostnader. Testsettet kostet $6,17, rundt 2 cent per møte med batch.

## Mapper

| Sti | Innhold |
| --- | --- |
| `reproduser.py` | Reproduserer hovedresultatet |
| `app.py` | Lokal app og demo |
| `src/agent.py` | Agenten, låsing og batchkjøring |
| `src/evaluer.py` | Evaluering og baseliner |
| `src/regler.py` | Retningslinjene som regler med ID |
| `src/motstandstest.py` | Motstandstesten |
| `src/sluttrapport.py` | Analysen av testsettet, skrevet før resultatene var kjent |
| `src/kontroll_test.py` | Kontroller lagt til etter at resultatene var kjent |
| `src/hent_npx.py` | Henter N-PX fra SEC |
| `src/analyse/` | Datakontroller og analysene bak justeringene |
| `tests/test_lekkasje.py` | Lekkasjetesten |
| `resultater/` | Lagrede svar, logger, lås og tall |
| `data/` | Fasit, retningslinjer og Norges Banks N-PX |

## Kilder

- `data/arrangor/real_votes.csv` og `npx_votes.csv`: delt av arrangøren på e-post 5. november 2026, beskrevet som API-data fra NBIM og NPX-data. NBIMs stemmeregister: https://www.nbim.no/en/responsible-investment/voting/our-voting-records/
- NBIM Global Voting Guidelines 2024: https://nbim.no/contentassets/01a7ee19b5d84a73a67a365e76a0fb01/global-voting-guidelines2024.pdf
- Norges Banks Form N-PX hos SEC: https://data.sec.gov/submissions/CIK0001374170.json, for eksempel https://www.sec.gov/Archives/edgar/data/1374170/000137417026000072/0001374170-26-000072.txt

## AI-verktøy

- **Claude Code (Claude Opus 5.5):** skrev kode, analyserte data, foreslo metode og laget utkast til README og kravrespons.
- **Claude Opus 5.5 via API:** er selve agenten i løsningen.
- **[Laget: legg til annen AI-bruk og hva laget selv gjorde før innlevering.]**

## Kreditering

Startpakken fra Eik Lab var utgangspunktet. `src/hent_npx.py` er skrevet om fra `hent_npx.py` i pakken, og baselinen «alltid med styret» kommer fra `baseline.py`. Løsningen bruker pandas, NumPy, scikit-learn, Streamlit og Anthropic Python SDK.
