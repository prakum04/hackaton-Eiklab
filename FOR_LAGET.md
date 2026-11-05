# Til laget: Stemmegivningsagenten

**Vi har nå to løsninger på Case 1, her og i grenen `Barz`, og vi kan bare levere én kravrespons innen fredag kl. 12:00.** Dette dokumentet forklarer hva denne grenen er, hvordan de to står mot hverandre, og hva vi må bestemme.

Grenen er laget med Claude Code. Mye av koden og teksten er skrevet av AI, og det står i README. Alle som presenterer, må kunne forklare den.

## Hva agenten gjør

1. Den leser sakslisten til et møte.
2. Den får NBIMs 70 regler for stemmegivning og NBIMs tidligere stemmer på selskapet, bare fra før møtedatoen.
3. Claude foreslår FOR, MOT eller AVSTÅ per sak, med regel, begrunnelse og hvor sikker den er.
4. Er den usikker, eller prøver teksten å gi den instrukser, går saken til et menneske.
5. Den stemmer aldri selv, og alt logges.

## Resultatet

Agenten ble justert på 2023–2024, låst, og kjørt én gang på 2025–2026: 3 448 saker, der NBIM gikk mot styret i 169.

- **Presisjon 70,4 %:** Når den sier «mot styret», har den rett 7 av 10 ganger.
- **Recall 56,2 %:** Den finner over halvparten av nei-sakene. «Alltid med styret» finner ingen.
- **Arbeidsdeling:** Et menneske ser 6,9 % av sakene, og da er 66,9 % av nei-sakene fanget.
- **Motstandstest:** 50 forsøk på å lure den med skjult tekst. Ingen endret stemmen.
- **Største svakhet:** Den finner 88,2 % av gjentakelser, men bare 23,8 % av nye saker.

## Sammenligning med `Barz`, på nøyaktig de samme sakene

Begge agentene er målt på de 2 642 sakene i testsettet til `Barz`, med de samme 123 nei-sakene. Svarene er hentet fra grenene, ingen ny kjøring.

| | Denne grenen | `Barz` |
| --- | --- | --- |
| Presisjon | **65,0 %** | 52,7 % |
| Recall | **54,5 %** | 39,0 % |
| Rangering (AP, tilfeldig er 0,047) | **0,533** | 0,410 |
| Andel saker et menneske ser | **7,2 %** | 14,1 % |
| Nei-saker fanget da | **67,5 %** | 59,3 % |
| Gjentakelser funnet | **87,7 %** | 59,6 % |
| Nye saker funnet | 25,8 % | 21,2 % |
| Sitat i riktig seksjon, alle nei-saker | 54,2 % | **65,0 %** (80,0 % blant topp 3) |
| Kostnad å kjøre | Rundt 2 cent per møte, krever API-nøkkel | **Gratis, ingen nøkkel** |
| Metode | Språkmodell, hele retningslinjen i prompten | Egen modell og søk i retningslinjene (RAG), **slik casen foreslår** |
| Testsettet kjørt | **Én gang, låst** | Tre ganger, oppgitt åpent |
| Kan modellen huske utfall? | **Ja, det er en mulig svakhet** | **Nei** |

**Tre forbehold:**

- Denne agenten ser også møter tidligere i testperioden, mens `Barz` bare bruker historikk fra treningsperioden. Det kan forklare noe av forspranget på gjentakelser.
- Etter modellens kunnskapsgrense (juli–september 2026) fant denne 5 av 7 nei-saker og `Barz` 1 av 7, men det er for få saker til å konkludere.
- Vi brukte disse tallene etter at begge testene var kjørt, så de beskriver forskjellen, de er ikke en ny test.

Hele utskriften ligger i `resultater/sammenligning_med_barz.txt`, og skriptet er `src/analyse/sammenlign_med_barz.py`.

## Det vi må bestemme

Vi leverer én kravrespons, én kodepakke og én demo.

- **Alternativ A, denne agenten som hovedløsning:** Bedre tall på samme saker og en ren, låst test. `Barz` kan være den sterkeste baselinen i tabellen, og Barz må krediteres. Krever API-nøkkel for live demo.
- **Alternativ B, `Barz` som hovedløsning:** Gratis, enkel å kjøre, følger casens forslag og kan ikke huske utfall. Denne agenten kan nevnes som sammenligning. Lavere tall, og testen er kjørt tre ganger.

**Forslag:** Alternativ A, hvis den som presenterer kan stå inne for hvordan agenten virker. Reglene sier at juryen ikke belønner mest treffsikker modell, men forståelse og ærlig evaluering. Velg derfor den løsningen laget faktisk kan forklare.

## Dette trengs uansett

- [ ] Velg løsning.
- [ ] Velg gruppenavn og hvem som presenterer.
- [ ] Oppgi all AI-bruk i README.
- [ ] Bestem om Malk sine visualiseringer skal brukes.
- [ ] Spør Milad om de to uklarhetene i reglene: fem overskrifter mot tre deler, og fem juryspørsmål der bare tre er listet.
- [ ] Spør Milad om dataene kan ligge offentlig. `real_votes.csv` og `npx_votes.csv` ligger nå i de offentlige grenene `Barz` og `Malk`, men ikke her.
- [ ] Øv på demoen og send inn før kl. 12:00.

## Slik kjører du dette

Den komplette pakken er zip-filen `stemmegivningsagenten.zip`, som deles på Teams. Den trenger ingen nøkkel for å gjenskape tallene:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && .venv/bin/python reproduser.py
```

For å prøve agenten selv legger du API-nøkkelen i `.env` og kjører `.venv/bin/streamlit run app.py`. Fanen «Resultater mot NBIM» virker uten nøkkel.

## Hvor du finner hva

| Fil | Innhold |
| --- | --- |
| `KRAVRESPONS.pdf` | Utkast til kravrespons på én side |
| `README.md` | Teknisk forklaring, kilder og begrensninger |
| `app.py` | Appen til demoen |
| `src/agent.py` | Selve agenten |
| `src/evaluer.py` | Målingene og baselinene |
| `src/motstandstest.py` | Testen av skjulte instrukser |
