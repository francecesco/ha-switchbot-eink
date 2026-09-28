# SwitchBot E-Ink Home Dashboard per Home Assistant

Mostra sul pannello e-ink da 7.5" del SwitchBot E-Ink Home Dashboard (SKU `W8902500`)
**un'agenda che fonde i calendari di Home Assistant** scelti dall'utente.

Il dispositivo non viene modificato: niente firmware da sostituire, niente reflash.
L'integrazione scrive sulla pagina home del pannello attraverso la stessa API che usa
l'editor web ufficiale di SwitchBot, e ne sostituisce il contenuto meteo. La barra a
sinistra, con data, ora e meteo, è disegnata dal firmware e resta com'è.

```
┌────────────┬──────────────────────────────────────┐
│            │  C  14:30  Riunione settimanale      │
│  lun 28    │  L  16:30  Pranzo con Marco          │
│  settembre │  C  17:30  Revisione del progetto…   │
│            │  L  18:30  Spesa                     │
│  15:30     │  C  19:30  Palestra                  │
│            │                             +3 altri │
│  meteo     ├──────────────────────────────────────┤
│  (firmware)│  DOMANI                              │
│            │  C  08:30  Dentista                  │
│            │  L  15:00  Consegna documenti        │
│            │  MER 30   Ferie (tutto il giorno)    │
│            │                          agg. 15:30  │
└────────────┴──────────────────────────────────────┘
```

## Come funziona

Ogni 15 minuti (intervallo configurabile) l'integrazione legge gli eventi dei prossimi
tre giorni dai calendari scelti, compone la pagina e la pubblica, **solo se il
contenuto è cambiato**.

Il pannello però **scarica il contenuto per conto suo, circa ogni tre ore**, e questa
cadenza non si può cambiare. Pubblicare spesso serve a fargli trovare un'agenda fresca
quando si sveglia. Per averla subito, **si tiene premuto il pulsante del pannello per due
secondi**: il pannello riscarica immediatamente.

Per la stessa ragione in basso a destra c'è l'ora dell'ultimo aggiornamento (`agg.
15:30`): con una lettura ogni tre ore, senza quella riga non si distingue un'agenda
aggiornata da una di stamattina.

## Cosa mostra

- **Oggi**: fino a cinque eventi, con ora e titolo. Gli eventi già conclusi lasciano il
  posto a quelli che devono ancora arrivare; quelli già in corso compaiono comunque.
  Oltre il quinto, una riga `+N altri`: nessun evento sparisce in silenzio.
- **Domani**: un'anteprima dei primi due eventi, con il suo `+N altri`.
- **Dopodomani**: una riga riassuntiva.
- **Più calendari**: il pannello ha solo nero e grigio, quindi i calendari non si
  distinguono col colore. Ogni evento porta un marcatore di una o due lettere, ricavato
  dal nome del calendario (`C` per Casa, `L` per Lavoro). Con un calendario solo i
  marcatori non compaiono.

I titoli degli eventi non passano dal motore di template di Home Assistant: arrivano da
inviti e calendari condivisi, e un titolo con delle graffe non deve essere eseguito.

## Requisiti

- Un SwitchBot E-Ink Home Dashboard aggiunto al proprio account nell'app SwitchBot, con
  **il firmware aggiornato** (vedi [Risoluzione dei problemi](#risoluzione-dei-problemi))
- Home Assistant 2026.8 o successivo
- Almeno un'entità `calendar.*` in Home Assistant (Google Calendar, CalDAV, Local
  Calendar, …)

## Installazione

**Via HACS.** In HACS, menu ⋮ → *Repository personalizzati*, aggiungere
`https://github.com/francecesco/switchbot-eink` con categoria *Integrazione*. Poi
installare **SwitchBot E-Ink Home Dashboard** e riavviare Home Assistant.

**Manualmente.** Copiare `custom_components/switchbot_eink` nella cartella
`custom_components` della configurazione di Home Assistant e riavviare.

## Configurazione

Da **Impostazioni → Dispositivi e servizi → Aggiungi integrazione → SwitchBot E-Ink Home
Dashboard**:

1. email, password e regione dell'account SwitchBot (`eu`, `us` o `ap`);
2. il pannello da usare.

La password non viene salvata: dopo il login restano memorizzati solo i token. Se il
token viene revocato, Home Assistant chiede di accedere di nuovo.

Poi, da **Configura** sull'integrazione:

| Opzione | Default | Note |
|---|---|---|
| Calendari da mostrare | nessuno | scelta multipla fra le entità `calendar.*` |
| Secondi fra una pubblicazione e l'altra | 900 | minimo 60 |

Finché non si sceglie almeno un calendario, il pannello mostra "Nessun evento nei
prossimi 3 giorni".

## Servizio

`switchbot_eink.refresh` rigenera l'agenda e la pubblica subito, anche se il contenuto
non è cambiato. Rispetta comunque un intervallo minimo di 60 secondi fra due
pubblicazioni. Dopo averlo chiamato, la pressione lunga sul pulsante fa comparire
l'agenda senza aspettare il prossimo risveglio del pannello.

## Entità

| Entità | Cosa dice |
|---|---|
| Sensore *Ultima pubblicazione* | quando l'agenda è stata pubblicata con successo l'ultima volta |
| Binary sensor *Autenticazione* | se l'accesso all'account SwitchBot funziona |

Restano disponibili anche quando la pubblicazione fallisce: è proprio il momento in cui
servono.

## Risoluzione dei problemi

**Il pannello mostra il meteo di SwitchBot invece dell'agenda.** Succede per esempio
dopo un ripristino alle impostazioni di fabbrica: il server ha l'agenda, ma il pannello
continua a mostrare la sua home nativa. Nel caso osservato si è risolto **installando
l'aggiornamento del firmware** proposto dall'app SwitchBot e poi tenendo premuto il
pulsante per due secondi.

**L'agenda è vecchia.** Il pannello scarica circa ogni tre ore. Controllare *Ultima
pubblicazione*, poi tenere premuto il pulsante per due secondi.

**Nei log compaiono errori di autenticazione.** Il binary sensor *Autenticazione* va a
*problema* e Home Assistant propone di accedere di nuovo dalla pagina delle integrazioni.

### Diagnostica da riga di comando

Lo strato che parla con SwitchBot si usa anche da solo, senza Home Assistant, da un
clone del repository:

```bash
python -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install --group dev
export SWITCHBOT_USER='tua@email' SWITCHBOT_REGION=eu
read -s "SWITCHBOT_PASS?Password: " && export SWITCHBOT_PASS   # zsh; in bash: read -rsp

.venv/bin/python -m tools.probe devices    # i dispositivi dell'account
.venv/bin/python -m tools.probe templates  # i template del pannello, con lo slot
.venv/bin/python -m tools.probe preview    # cosa il server consegnerà al pannello
.venv/bin/python -m tools.probe homepage   # da dove il pannello prende la home
.venv/bin/python -m tools.probe agenda     # pubblica l'agenda con eventi di prova
```

`preview` è la prima cosa da provare quando qualcosa non compare: separa "la
pubblicazione non è arrivata al server" da "il pannello non l'ha ancora scaricata".

## Sviluppo

```bash
python -m venv .venv && .venv/bin/pip install --upgrade pip && .venv/bin/pip install --group dev
.venv/bin/pytest
```

Il codice è diviso in tre strati con una dipendenza sola in una direzione:
`custom_components/switchbot_eink/api/` parla con SwitchBot e non importa niente di Home
Assistant; `layout/` è fatto di funzioni pure che trasformano gli eventi in componenti;
il resto è l'integrazione vera e propria.

## Avvertenza

Questa integrazione usa l'API privata dell'editor web SwitchBot, ricavata per reverse
engineering dai bundle JavaScript pubblici. Non è documentata e SwitchBot può cambiarla o
chiuderla senza preavviso. Tutto ciò che la riguarda sta in
`custom_components/switchbot_eink/api/`.

Progetto non affiliato né sostenuto da SwitchBot / Wonderlabs.

## Licenza

[MIT](LICENSE)
