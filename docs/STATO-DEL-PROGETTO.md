# SwitchBot E-Ink — stato del progetto

**Aggiornato al 25 agosto 2026.** Branch `feat/switchbot-eink`, 55 commit, 302 test verdi.

Questo file serve a riprendere il lavoro dopo una pausa. I documenti di riferimento restano
la spec (`docs/superpowers/specs/2026-08-22-switchbot-eink-ha-design.md`) e il piano
(`docs/superpowers/plans/2026-08-22-switchbot-eink.md`); il diario completo delle decisioni,
con ogni ruling e il suo perché, è in `.superpowers/sdd/2026-08-22-switchbot-eink/progress.md`.

---

## Cosa stiamo costruendo

Un'integrazione custom di Home Assistant che pilota il pannello e-ink SwitchBot Home
Dashboard (SKU `W8902500`, device type interno `W1070000`) e ci pubblica sopra **un'agenda
che fonde i calendari di Home Assistant scelti dall'utente**.

Il contenuto meteo nativo viene sostituito: si scrive sulla **home**, la pagina che il
pannello mostra all'accensione.

Nessun firmware da sostituire, nessun reflash. Si passa dall'API privata di SwitchBot, la
stessa che usa l'editor web ufficiale.

---

## Come ci siamo arrivati: il vincolo che ha deciso tutto

L'obiettivo iniziale era una dashboard di stato della casa — temperature, dispositivi,
avvisi. **Non è possibile**, e la ragione è misurata, non supposta:

> Il pannello si riconnette e aggiorna i dati **ogni tre ore**. (Documentato dal supporto
> SwitchBot, e coerente con la prova sul campo: con contenuto nuovo sul server, dopo dieci
> minuti il pannello mostrava ancora il vecchio.)

Uno stato dei dispositivi vecchio fino a tre ore è peggio di nessuno stato. Un'agenda, che
cambia lentamente, regge benissimo quella cadenza. Da qui il cambio di contenuto.

La pressione lunga sul pulsante (2 secondi) forza lo scaricamento immediato: è il gesto che
copre il caso "lo voglio adesso", ed è la ragione per cui esiste il servizio `refresh`.

Il campo `refresh` del componente (`"1h"`, `"5m"`) viene conservato dal backend ma **non**
influenza la cadenza del dispositivo: provato.

---

## Le scoperte sul campo

Tutte ottenute con la sonda `tools/probe.py` contro il backend vero e il dispositivo fisico.
Nessuna è deducibile dal codice.

### La geometria della spec era sbagliata

La spec dichiarava due fasce orizzontali (`safeTop 64`, `safeBottom 44`) e area utile
800×372 da `x=0`. Erano valori presi dal renderer web e per questo pannello non valgono.

**Realtà misurata: barra di stato verticale a sinistra larga 240 px, nessuna fascia in alto,
area utile 560 × 380 con origine in `x=240`, `y=0`.**

La barra mostra data, ora e meteo della città dell'account, è disegnata dal firmware e non è
scrivibile. Corrisponde alla `statusBar` nella risposta di `preview`.

Conseguenza architetturale: lo strato `layout/` resta uno spazio di coordinate puro con
origine `(0,0)`, e la traduzione in coordinate fisiche avviene in un punto solo,
`layout/grid.py:to_canvas`.

### Tre URL base, non uno

Confonderli produce un `403` di API Gateway con un messaggio sulle firme AWS SigV4 che
sembra un problema di autenticazione e non lo è: è una rotta inesistente.

| Servizio | Base |
|---|---|
| Account | `https://account.api.switchbot.net` |
| Dispositivi | `https://wonderlabs.{region}.api.switchbot.net` |
| Template | `https://wonderlabs.{region}.api.switchbot.net/productbiz` |

**Tecnica del 401-contro-403:** mandando un token deliberatamente falso, una rotta esistente
risponde `401` e una inesistente `403`. Non servono credenziali vere. È così che abbiamo
diagnosticato l'errore sopra.

### La lista dei template non contiene lo slot

La risposta di `templates/list` ha `sortOrder` e `templateType`, mai `pageSlot`: lo slot va
**dedotto**. E servono entrambi i campi, perché la home e `custom1` hanno tutte e due
`sortOrder: 1` e si distinguono solo per `templateType`. Guardare il solo `sortOrder`
significa rischiare di sovrascrivere la schermata principale dell'utente.

Creare su uno slot occupato fallisce con `191 sortOrder already exists for this device`:
sugli slot occupati si aggiorna, non si crea.

### Altre cose che il backend fa

- `dataMode: text` con `source: custom` **è rispettato**: il backend copia il nostro
  contenuto nel campo `data` e `weatherInfo` resta `null`.
- L'`id` di un componente deve essere `^[1-9]\d*$`: qualunque altra cosa viene serializzata
  come `"0"` e tutti i componenti collidono.
- `css` ed `extra` viaggiano come **stringhe JSON**, non come oggetti.
- Sulla regione `eu` — e solo lì — l'header di autorizzazione perde il prefisso `Bearer`.
- Il pannello offre solo `black`, `gray`, `white`, `transparent`: due tonalità utili per il
  testo. Per questo i calendari si distinguono con un marcatore testuale, non col colore.
- `lastPage: false` con `nextPageName` vuoto anche avendo una sola pagina: mai spiegato,
  nessun effetto osservato.

---

## Stato del dispositivo dell'utente

Pannello `AABBCCDDEEFF`, regione `eu`, lingua `it`, città MiaCittà.

Tutte le pagine custom sono state **cancellate**: resta il solo template `1105` sulla home,
che è quello su cui pubblichiamo. La home non si cancella mai, si sovrascrive — cosa faccia
il firmware senza un template home non è noto.

---

## L'architettura

Tre strati con una dipendenza sola in una direzione: `3 → 2 → 1`.

```
custom_components/switchbot_eink/
├── api/              strato 1 — client dell'API privata, zero import da homeassistant
│   ├── auth.py           login e rinnovo del token
│   ├── client.py         facciata: dispositivi e template
│   ├── http.py           POST, envelope, un solo ritentativo su 401
│   ├── envelope.py       funzioni pure di protocollo (regioni, header, unwrap)
│   ├── models.py         Device, Template, TemplateSummary, mappature degli slot
│   ├── const.py          endpoint, regioni, device type
│   └── errors.py         SwitchBotCanvasError / AuthError / ApiError
├── layout/           strato 2 — funzioni pure, zero import da homeassistant e da api/
│   ├── const.py          geometria misurata, whitelist di stile e contenuto
│   ├── grid.py           griglia 12×6 → pixel, più to_canvas
│   ├── widgets.py        card astratte → wire format
│   ├── schema.py         validazione della definizione di pagina (voluptuous)
│   ├── agenda.py         eventi di calendario → definizione di pagina
│   └── compile.py        definizione + stati → lista di componenti
├── config_flow.py    strato 3 — login, scelta del pannello, reauth, opzioni
├── coordinator.py        ciclo periodico: legge i calendari, genera, confronta, pubblica
├── entity.py             base comune alle entità diagnostiche
├── sensor.py             ultima pubblicazione riuscita
├── binary_sensor.py      stato dell'autenticazione
└── __init__.py           setup, servizio refresh, ciclo di vita
```

**Perché così.** Lo strato 1 è l'unico che sa che l'API è privata: quando SwitchBot cambierà
qualcosa si romperà solo lì, e lo si diagnostica da riga di comando senza avviare Home
Assistant. Lo strato 2 è puro, quindi si testa senza rete. Lo strato 3 contiene solo ciò che
è genuinamente accoppiato a Home Assistant.

L'agenda **non è un percorso parallelo**: è un generatore che produce la stessa struttura che
`validate_page` valida e `compile_page` traduce.

---

## Come si comporta l'integrazione

**Configurazione.** Email, password e regione; poi si sceglie il pannello. La password non
viene mai salvata: si persistono i token, `user_id`, `device_id` e regione. Se il refresh
token viene revocato parte il reauth flow.

**Opzioni.** Quali calendari mostrare (scelta multipla fra le entità `calendar.*`) e ogni
quanto ripubblicare. Cambiarle ricarica la entry.

**Ciclo.** Ogni `update_interval` (default 900 s): legge gli eventi delle prossime 72 ore con
`calendar.get_events`, genera la pagina, la compila, ne calcola l'impronta, e pubblica solo
se è cambiata. Poi `update_template` seguito da `release`.

**Perché 900 s e non tre ore.** Il pannello legge ciò che trova sul server al risveglio:
pubblicare più spesso riduce l'età di ciò che troverà. Allineare la pubblicazione alla
cadenza di lettura sarebbe un errore, non un'ottimizzazione. (Nel piano c'era scritto il
contrario: è stato corretto.)

**Servizio.** `switchbot_eink.refresh` forza la pubblicazione ignorando l'impronta, ma
rispetta comunque l'intervallo minimo di 60 secondi. È la coppia naturale della pressione
lunga sul pulsante.

**Entità diagnostiche.** Un sensore con l'ora dell'ultima pubblicazione riuscita e un binary
sensor con lo stato dell'autenticazione. Restano **sempre disponibili**, anche durante un
guasto: è esattamente il momento in cui servono.

---

## L'agenda

Finestra di tre giorni: oggi in evidenza, i due successivi in sintesi.

```
┌──────────────────────────────────────┐
│ OGGI · domenica 23 agosto            │
│                                      │
│    09:00   Riunione settimanale      │
│    13:30   Pranzo con Marco          │
│    18:00   Palestra                  │
│                              +2 altri│
├──────────────────────────────────────┤
│ LUN 24   08:30 Dentista · 15:00 Con… │
│ MAR 25   Ferie (tutto il giorno)     │
│                          agg. 17:24  │
└──────────────────────────────────────┘
```

Regole che vale la pena ricordare:

- **massimo sei eventi oggi**, poi la riga `+N altri`: far sparire eventi in silenzio è
  peggio che dire quanti ne mancano;
- **gli eventi già conclusi non occupano le righe di oggi**, altrimenti sei impegni finiti in
  mattinata nasconderebbero la cena;
- **gli eventi già in corso compaiono lo stesso** (una settimana di ferie cominciata lunedì
  si vede il mercoledì);
- **l'ora di aggiornamento in basso a destra non è un ornamento**: con una cadenza di lettura
  di tre ore, senza quella riga chi guarda non distingue un'agenda fresca da una di
  stamattina. È esclusa dall'impronta, altrimenti il confronto non impedirebbe mai niente;
- **i titoli non passano dal motore di template**: arrivano da inviti e calendari condivisi, e
  un evento intitolato con delle graffe verrebbe *eseguito*. Il campo di card `template:
  false` esiste per questo;
- **con più calendari** ogni evento porta un marcatore di al massimo due caratteri, derivato
  in modo deterministico dal nome.

`CHAR_WIDTH_RATIO = 0.52` stima quanti caratteri stanno in un rettangolo ed è
**dichiaratamente approssimativa**: non abbiamo le metriche dei font del pannello. Vive in una
costante sola, apposta per essere tarata quando vedremo l'agenda vera sullo schermo.

---

## La sonda

`tools/probe.py` è lo strumento da riga di comando che ha prodotto tutte le misure. Legge le
credenziali da `SWITCHBOT_USER`, `SWITCHBOT_PASS`, `SWITCHBOT_REGION` e non le stampa mai.

```bash
.venv/bin/python -m tools.probe devices     # elenca i dispositivi dell'account
.venv/bin/python -m tools.probe templates   # elenca i template del pannello, con lo slot
.venv/bin/python -m tools.probe preview     # sola lettura: cosa il backend darà al pannello
.venv/bin/python -m tools.probe clock       # pubblica un orario (--refresh per il campo refresh)
.venv/bin/python -m tools.probe ruler       # righello numerato sulle due assi
.venv/bin/python -m tools.probe frame       # quattro angoli del rettangolo da verificare
.venv/bin/python -m tools.probe wipe        # elenca le custom da cancellare (--yes per farlo)
```

`--slot` vale `home` di default. `wipe` non tocca mai la home, e senza `--yes` fa una prova a
vuoto. `preview` è la prima cosa da lanciare quando qualcosa non compare sullo schermo:
distingue "la nostra scrittura non è arrivata" da "il dispositivo è lento".

---

## Cosa manca

**Task 14 — confezionamento HACS e documentazione.** È l'ultimo, e l'unico rimasto. Serve
`hacs.json`, il README con installazione e configurazione, e la verifica che l'integrazione
si installi davvero come repository custom.

Il modello di README nel piano è già scritto, ma va riletto: era stato pensato per la
dashboard di stato e potrebbe avere altri residui oltre a `push_text`, che è già stato tolto.

**Poi la prova vera**, che è la cosa più importante che resta e che nessun test può fare:
installare l'integrazione, scegliere i calendari veri, e **guardare l'agenda sul pannello**.
È lì che si scopre se `CHAR_WIDTH_RATIO` è tarato bene, se sei righe di eventi ci stanno, e
se i corpi dei caratteri sono leggibili su quattro grigi a distanza di lettura.

Da fare quando ci si arriva:

1. installare, configurare, scegliere i calendari;
2. `switchbot_eink.refresh` da Strumenti per sviluppatori;
3. pressione lunga di 2 secondi sul pulsante del pannello;
4. guardare, e annotare cosa non va.

---

## Note operative

**Identità git.** Questo progetto usa l'account GitHub **privato**: `francecesco`
(`192597588+francecesco@users.noreply.github.com`), mai quello aziendale. Il repository ha già l'identità corretta in
`git config --local`, quindi **non passare `-c user.email` ai commit**. Per `gh` usare
`GH_TOKEN=$(gh auth token --user francecesco) gh <comando>`, mai `gh auth switch`, che è
globale e cambierebbe le cose anche negli altri progetti.

**Ambiente.** `.venv` con Python 3.14.5, Home Assistant 2026.8.3, aiohttp 3.14.3, pytest 9.

**Mocking HTTP.** `AiohttpClientMocker` da `pytest_homeassistant_custom_component`. **Mai
`aioresponses`**: è incompatibile con aiohttp 3.14.3, che Home Assistant impone.

**Controprove.** Eseguirle con `PYTHONDONTWRITEBYTECODE=1` e la cache ripulita: mutazioni di
pari lunghezza scritte nello stesso secondo hanno prodotto verdetti falsi.

---

## Tre lezioni che questo progetto ha imparato a sue spese

**Le mutazioni inventate da chi non ha scritto la lista trovano più cose.** In due task, i
controlli che il revisore si è inventato per conto suo hanno scoperto più difetti di quelli
che avevo elencato io: in un caso otto su otto sono passati indisturbati. Quando si verifica
la tenuta dei test, la lista di chi ha scritto le istruzioni non basta.

**L'ora simulata fissa contro gli orari scritti a mano ha prodotto tre difetti distinti**: un
giorno della settimana sbagliato, uno stress test che collassava in silenzio, e un test che
falliva solo fra le 23:30 e mezzanotte. Negli scenari di prova gli eventi vanno ancorati a un
offset dall'istante simulato, mai a un'ora assoluta.

**I difetti peggiori sono nati nel piano, non nell'esecuzione.** Il coordinator che pubblicava
una volta sola e mai più, le entità diagnostiche che sparivano proprio nel guasto, la
geometria dedotta invece che misurata: tutte cose che avevo scritto io nelle istruzioni, e che
sono emerse solo perché qualcun altro le ha guardate con l'obbligo di provare a romperle.
