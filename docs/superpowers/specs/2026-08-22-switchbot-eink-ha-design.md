# SwitchBot E-Ink Home Dashboard come dashboard Home Assistant

**Data:** 2026-08-22
**Dispositivo:** SwitchBot E-Ink Home Dashboard / Weather Station, SKU `W8902500` (serie `W890250x`)
**Stato:** design approvato, da implementare

## Obiettivo

Usare il pannello e-ink da 7.5" come schermo informativo di casa pilotato da Home
Assistant. Il contenuto meteo nativo non interessa e viene sostituito.

**Contenuto principale: un'agenda** che fonde i calendari di Home Assistant scelti
dall'utente in un'unica schermata, con oggi in evidenza e i due giorni successivi in
sintesi.

Questa scelta viene da un vincolo misurato, non da una preferenza: il pannello si
riconnette e si aggiorna **ogni tre ore** (documentato dal supporto SwitchBot, e
coerente con le nostre prove sul campo). Uno stato dei dispositivi vecchio fino a tre
ore sarebbe peggio di nessuno stato; un'agenda, che cambia lentamente, regge benissimo
quella cadenza. Chi vuole il dato adesso tiene premuto due secondi il pulsante.

Resta possibile comporre a mano pagine con card di stato, temperature e consumi: il
compilatore le supporta. L'agenda e' il contenuto predefinito, non l'unico.

Non-obiettivi: sostituire il firmware, funzionare senza cloud SwitchBot, controllare
dispositivi dal pannello, mostrare stati che cambiano piu' in fretta di quanto il
pannello sappia leggerli.

## Vincolo di partenza

Il dispositivo è chiuso: firmware firmato, aggiornato OTA dal cloud SwitchBot, nessun
dump pubblico. Riflashare non è una strada percorribile e non serve: SwitchBot espone
due meccanismi per scrivere sullo schermo.

1. **`customPage` sulla OpenAPI pubblica** (`api.switch-bot.com/v1.1`): testo semplice,
   ~300 byte UTF-8, niente a capo, emoji base. È un ticker, non una dashboard. Scartato
   come meccanismo principale; resta utile come fallback e per messaggi estemporanei.
2. **API privata del canvas editor** (`e-ink-home-dashboard.switch-bot.com`): widget
   posizionati liberamente su un canvas. È la base di questo progetto.

Tutto ciò che segue sull'API privata è stato ricavato per reverse engineering dai bundle
JavaScript pubblici dell'editor web (`index-*.js`, `eink-renderer-*.js`). Non è
documentazione ufficiale e può cambiare senza preavviso.

## L'API privata

Ci sono **tre** URL base, non uno. Confonderli è costoso: una rotta inesistente
su API Gateway di AWS risponde `403` con un messaggio sulle firme SigV4, che
sembra un problema di autenticazione e non lo è.

| Servizio | Base |
|---|---|
| Account | `https://account.api.switchbot.net` |
| Dispositivi | `https://wonderlabs.{region}.api.switchbot.net` |
| Template | `https://wonderlabs.{region}.api.switchbot.net/productbiz` |

`region` ∈ `us` | `ap` | `eu` (default `us`; per l'Italia `eu`). La differenza fra
le ultime due è visibile nel bundle del client web, dove il client dei template si
costruisce con `J(e,t)` = `ut(e,t) + "/productbiz"` mentre quello dei dispositivi
usa `ut(e,t)` da solo.

Il modo di verificare a quale base risponde una rotta, senza credenziali: una
richiesta con un token fasullo ottiene `401` se la rotta esiste e `403` se non
esiste.

Tutte le chiamate sono `POST` con `content-type: application/json` e header
`Authorization: <access_token>`.

Il client web costruisce il valore dell'header come `"{token_type} {access_token}"`, con
`token_type` che vale `Bearer` quando assente.

**Attenzione alla regione `eu`.** Su quella regione, e solo su quella, il prefisso
`Bearer ` viene poi **rimosso**, e l'header diventa il token nudo. Essendo
l'installazione italiana su `eu`, è il caso da implementare per primo, ed è un candidato
naturale a far fallire il login in modo poco diagnosticabile se lo si ignora.

### Autenticazione

Costanti del client web:

| Nome | Valore |
|---|---|
| account base URL | `https://account.api.switchbot.net` |
| `clientId` | `pg6fbtxbi7q3o2n4zba852d5lh` |
| `serviceId` | `weather_station` |

| Path | Body | Risposta |
|---|---|---|
| `/account/api/v1/user/login` | `{username, password, deviceInfo, grantType:"password", clientId}` | `{statusCode:100, body:{access_token, refresh_token, token_type, expires_in, refresh_expires_in}}` |
| `/account/api/v1/user/token/refresh` | `{userId, refreshToken, clientId}` | `{access_token, token_type, expires_in}` |
| `/account/api/v1/user/userinfo` | — | `{userID, email, ...}` |

`deviceInfo` di default nel client web è
`{deviceName:"Web", deviceId:"hub-web", appVersion:"0.0.0", model:"Web"}`.

Il refresh richiede lo `userId`, che si ottiene da `/userinfo`: va quindi persistito
insieme al refresh token.

L'account service usa l'envelope `{statusCode, message, body}` con `statusCode == 100`
come successo. Il `productbiz` usa invece `{resultCode, message, data}` con
`resultCode == 100`. Sono due convenzioni diverse: il client deve gestirle entrambe.

Su `401` il client web tenta un refresh e poi ripete la richiesta una volta sola.

### Dispositivi e template

Salvo `getDeviceList`, tutti i path che seguono stanno sulla base **template**.

| Path | Body | Note |
|---|---|---|
| `/device/v1/manage/getDeviceList` | — | **sulla base dispositivi, non su productbiz**; filtrare `deviceType == "W1070000"` e `isShare == false` |
| `/web/v1/user/templates/list` | `{deviceID}` | |
| `/web/v1/user/templates/info` | `{templateId, deviceID}` | |
| `/web/v1/user/templates/create` | vedi sotto | ritorna il template con `templateId` |
| `/web/v1/user/templates/update` | vedi sotto | |
| `/web/v1/user/templates/del` | `{templateId, deviceID}` | |
| `/web/v1/user/templates/release` | `{deviceID}` | **pubblica al dispositivo** |
| `/web/v1/user/templates/preview` | `{templateId, deviceID}` | ritorna `{webcustomData, statusBar, language, timeZone}` |
| `/web/v1/common/templates` | `{}` | galleria dei template pubblici |

`W1070000` è il device type interno; `W8902500` è la SKU commerciale. Il tipo di
pannello associato è `eink-7in3`.

Body di `create`:

```json
{ "name": "...", "enabled": true, "sortOrder": 1, "templateType": 0,
  "components": [ ... ], "deviceID": "...", "commonTemplateID": null }
```

Body di `update`:

```json
{ "templateId": 123, "name": "...", "enabled": true, "sortOrder": 1,
  "templateType": 0, "components": [ ... ], "deviceID": "..." }
```

`templateType` è `0` per le pagine custom e `1` per la home; con `templateType == 1` il
`sortOrder` è forzato a 1. In `create` il `sortOrder` è sempre presente; in `update`
viene incluso solo quando è maggiore di 0 **e** `templateType` è 0, cioè solo per le
pagine custom.

Mappatura slot → `sortOrder`: `home` → 1 (con `templateType: 1`), `custom1`…`custom4` →
1…4, qualsiasi altro valore → 0.

La risposta di `list` **non contiene lo slot**: ogni voce ha `sortOrder` e
`templateType`, e lo slot va ricavato da entrambi. Un item reale, senza i componenti:

```json
{ "templateId": 580, "name": "Untitled template", "sortOrder": 1, "templateType": 0,
  "deviceID": "AABBCCDDEEFF", "enabled": true,
  "createdAt": "2026-07-14T10:55:49Z", "updatedAt": "2026-07-14T10:55:49Z" }
```

Guardare il solo `sortOrder` non basta: la home e `custom1` hanno entrambe
`sortOrder: 1` e si distinguono unicamente per `templateType`. Confonderle
significa sovrascrivere la schermata principale dell'utente. Mappatura inversa:
`templateType == 1` → `home`; altrimenti `sortOrder` 1…4 → `custom1`…`custom4`;
tutto il resto → non assegnato.

Creare un template su uno slot già occupato fallisce con
`191 sortOrder already exists for this device`: sugli slot occupati si aggiorna,
non si crea.

### Il canvas

| Proprietà | Valore |
|---|---|
| Risoluzione | 800 × 480 |
| Modalità colore | `gray4` — 4 livelli di grigio |
| Barra di stato | verticale, a sinistra, larga **240 px** |
| **Area utilizzabile** | **560 × 380, con origine in `x = 240`, `y = 0`** |

**Questi numeri sono misurati sul dispositivo, non dedotti dal bundle web.** Il renderer
dell'editor dichiara `safeTop: 64` e `safeBottom: 44` e calcola l'area utile come
`height - safeTop - safeBottom`: descrive una geometria diversa, e per questo pannello è
sbagliato. Sul dispositivo reale non c'è nessuna fascia orizzontale riservata — `y = 0` è
visibile — mentre il firmware disegna una barra **verticale a sinistra** con data, ora e
meteo della città dell'account. È la stessa `statusBar` che compare nella risposta di
`preview`, quella che porta il campo `city`.

Misura, con la sonda `tools/probe.py`:

- comando `ruler`, tacche numerate ogni 40 px poi ogni 10: la prima coordinata `x`
  leggibile per intero è **240**; sull'asse `y` si legge da `0`, e un'etichetta che
  comincia a `370` risulta tagliata a metà;
- comando `frame`, quattro angoli sul rettangolo `240,0 - 800,370`: tutti e quattro
  visibili per intero, con margine residuo in basso.

Conseguenza sull'architettura: lo strato `layout/` resta uno spazio di coordinate puro
con origine in `(0, 0)` e dimensioni 560 × 380 — chi scrive una pagina non deve sapere
che esiste una barra laterale. La traduzione in coordinate fisiche avviene una volta
sola, in `layout/grid.py:to_canvas`, chiamata dal compilatore al momento di serializzare
il componente.

### Formato di un componente

**`css` ed `extra` sono stringhe JSON, non oggetti.** Il serializzatore del client web
chiude entrambi con `JSON.stringify` prima di inviarli, e il deserializzatore li riapre
con `JSON.parse`. Inviarli come oggetti annidati è l'errore più probabile in fase di
implementazione.

```json
{ "id": "17", "type": "text", "name": "Stato lavatrice",
  "css":   "{\"x\":0,\"y\":0,\"w\":200,\"h\":80,\"z\":1,\"fontSize\":24}",
  "extra": "{\"dataMode\":\"text\",\"source\":\"custom\",\"refresh\":\"1h\",\"content\":{\"text\":\"...\"},\"locked\":false,\"visible\":true}" }
```

Una volta decodificato, `css` fonde geometria e stile in un oggetto piatto, mentre
`extra` contiene il blocco `data` più `content`, `locked`, `visible`.

L'**`id` deve essere una stringa che rappresenta un intero positivo**, validata contro
`/^[1-9]\d*$/` e con valore massimo 2147483647; deve essere unico all'interno del
template. Qualsiasi altro valore — un UUID, per esempio — viene serializzato come `"0"`,
il che fa collidere tutti i componenti fra loro.

Chiavi di stile ammesse: `backgroundColor`, `textColor`, `borderColor` (solo
`black` | `white` | `gray` | `transparent`), `borderWidth`, `radius`, `padding`,
`fontSize`, `fontWeight`, `align` (`left`|`center`|`right`), `iconSize`,
`numberFontSize`, `labelFontSize`, `unitFontSize`, `titleFontSize`, `bodyFontSize`,
`fit`, `rotation`, `layout`, `fillBox`.

Alcuni tipi hanno una whitelist di stili che il client web applica prima di serializzare
— per esempio `text` manda solo `fontSize`, `fontWeight`, `align`, `rotation`. Va
replicata, altrimenti si rischia di inviare campi che il backend rifiuta.

`data.source` ∈ `custom` | `template` | `switchbot` | `url` | `none`, con campi
opzionali `url` e `switchBotDeviceId` e un `refresh` (es. `"1h"`). Usiamo sempre
`source: "custom"`: i valori li scriviamo noi.

`data.dataMode` ∈ `text`, `weather`, `schedule`, `calendar`, `scheduleBusy`,
`scheduleWeather`, `stock`, `countDown`, `journalism`, `hacker`, `aisuggest`,
`quotations`, `customPutComponent`, `rubbish`, `clock`, `dailyTemp`, `tempHumi`.

### Widget utilizzabili

Categorie presenti nel renderer: `Basic`, `Metric`, `Weather`, `Forecast`, `Calendar`,
`System`, `Life`, `News`, `Stock`, `AISuggest`, `deviceSelf`.

Quelli che servono a noi:

| Tipo | Contenuto | Uso |
|---|---|---|
| `text` | `{text}` | testo libero, con `fontSize`/`fontWeight`/`align` |
| `divider` | `{}` | linea separatrice |
| `decorFrame` | `{}` | cornice, per raggruppare visivamente |
| `image` | `{src, alt, placeholder}` | finisce in un `<img src>` |
| famiglia Metric | `{icon, label, value, unit}` | KPI tile |

La famiglia Metric conta 19 tipi (`switchbotMeter`, `switchbotTemperature`, `feelsLike`,
`switchbotComfort`, `relativeHumidity`, `absoluteHumidity`, `tempRange`, `sunTimes`,
`moonPhase`, `wind`, `pressure`, `rainChance`, `uvIndex`, `airQuality`, `visibility`,
`aqiValue`, `pm25`, `pollen`, `precipitation`). I quattro campi di `content` sono
stringhe libere: sono di fatto tile generiche, e il nome del tipo determina solo i
default. L'icona si sceglie con `content.icon` dal set nativo, che include alias come
`sun-times`, `sun`, `moon`, `wind`, `gauge`, `rain-chance`, `uv`, `air-quality`, `eye`,
`aqi`.

## Architettura

Tre strati, con una dipendenza sola in una direzione: strato 3 → strato 2 → strato 1.

```
custom_components/switchbot_eink/
├── api/            strato 1 — client dell'API privata, zero import da homeassistant
│   ├── client.py       sessione HTTP, envelope, retry su 401
│   ├── auth.py         login e refresh del token
│   ├── models.py       dataclass di template e componenti
│   └── const.py        endpoint, regioni, device type
├── layout/         strato 2 — compilatore, funzione pura
│   ├── schema.py       validazione della definizione YAML (voluptuous)
│   ├── grid.py         griglia 12x6 → pixel
│   ├── widgets.py      card astratte → wire format, con whitelist di stile
│   ├── agenda.py       eventi di calendario → definizione di pagina
│   └── compile.py      entry point: definizione + stati → lista componenti
├── config_flow.py  strato 3
├── coordinator.py
├── __init__.py
├── services.yaml
└── manifest.json
```

**Perché questa divisione.** Lo strato 1 è l'unico che sa che l'API è privata e non
documentata: quando SwitchBot cambierà qualcosa, si romperà solo lì, e si potrà
diagnosticare eseguendolo da riga di comando senza avviare Home Assistant. Lo strato 2 è
una funzione pura — stessi input, stesso JSON — quindi si testa con golden file e senza
rete, che è dove sta la maggior parte della logica fastidiosa (posizionamento, troncamenti,
whitelist). Lo strato 3 contiene solo ciò che è genuinamente accoppiato a Home Assistant.

### Strato 1 — client API

Interfaccia pubblica:

```python
class SwitchBotCanvasClient:
    async def login(username: str, password: str) -> Tokens
    async def refresh(refresh_token: str) -> Tokens
    async def list_devices() -> list[Device]
    async def list_templates(device_id: str) -> list[TemplateSummary]
    async def get_template(template_id: int, device_id: str) -> Template
    async def create_template(template: Template) -> Template
    async def update_template(template: Template) -> None
    async def delete_template(template_id: int, device_id: str) -> None
    async def release(device_id: str) -> None
    async def preview(template_id: int, device_id: str) -> Preview
```

Usa `aiohttp` con la `ClientSession` condivisa di Home Assistant. Solleva
`SwitchBotCanvasAuthError` su credenziali o token non validi e
`SwitchBotCanvasApiError(result_code, message)` su envelope con codice diverso da 100,
così il config flow e il coordinator possono distinguere i due casi.

### Strato 2 — compilatore layout

Griglia di **12 colonne × 6 righe** sull'area utile 560 × 380, con gutter configurabile
(default 8 px). Una cella misura circa 66 × 62 px.

```yaml
switchbot_eink:
  page: custom1
  name: "Casa"
  cards:
    - type: metric
      entity: sensor.soggiorno_temperatura
      icon: temp-range
      label: Soggiorno
      unit: "°C"
      grid: [0, 0, 3, 1]          # colonna, riga, larghezza, altezza

    - type: text
      text: "Lavatrice: {{ states('sensor.lavatrice') }}"
      grid: [0, 1, 6, 1]
      style: { fontSize: 20, align: left }

    - type: divider
      grid: [0, 2, 12, 1]

    - type: text
      text: "Aggiornato {{ now().strftime('%H:%M') }}"
      position: [600, 340, 200, 24]   # escape hatch in pixel
      style: { fontSize: 14, align: right }
```

Tipi di card astratti: `metric`, `text`, `divider`, `frame`, `image`. Ognuno mappa su uno
o più widget nativi; `metric` sceglie un tipo della famiglia Metric coerente con l'icona
richiesta.

`grid` e `position` sono mutuamente esclusivi. `entity` è zucchero sintattico: se
presente e `value` è assente, `value` diventa lo stato dell'entità e `unit` la sua
`unit_of_measurement`. Ogni campo testuale (`text`, `label`, `value`, `unit`) passa dal
motore di template di Home Assistant, quindi Jinja è disponibile ovunque.

Il compilatore valida che nessuna card esca dall'area utile e che due card non si
sovrappongano, segnalando l'errore in fase di setup invece di produrre un canvas rotto.

### Strato 2b — generatore dell'agenda

L'agenda non e' un tipo di card nuovo: e' un **generatore** che produce la stessa
struttura di pagina che lo schema gia' valida e che il compilatore gia' sa tradurre.
Nessun percorso parallelo, nessuna duplicazione della validazione.

```
eventi dai calendari HA  ->  build_agenda_page()  ->  definizione di pagina
                                                       -> validate_page -> compile_page
```

Vive in `layout/agenda.py` ed e' puro come il resto dello strato: niente import di Home
Assistant, niente import di `api/`. Riceve dataclass proprie, non oggetti di HA.

**Origine dei dati.** L'integrazione chiama il servizio `calendar.get_events` con
`return_response=True`, passando le entita' scelte e la finestra temporale. E' l'unico
modo supportato per leggere i calendari dall'esterno del loro componente.

**Modello dell'evento.** Una dataclass immutabile:

```python
@dataclass(frozen=True, slots=True)
class Event:
    start: datetime
    end: datetime
    summary: str
    all_day: bool
    calendar: str      # nome amichevole dell'entita' di origine
```

**Finestra.** Tre giorni: oggi e i due successivi.

**Impaginazione**, in coordinate dell'area utile (560 × 380), tramite `position`: una
lista non e' una griglia, e le sei righe da 62 px sono troppo grosse per righe da 34.

| Elemento | Rettangolo | Corpo |
|---|---|---|
| Intestazione `OGGI · sabato 23 agosto` | `[0, 0, 560, 32]` | 24 |
| Filetto | `[0, 34, 560, 2]` | — |
| Marcatore calendario (evento *i*) | `[0, 44 + 34i, 12, 30]` | 18 |
| Ora (evento *i*) | `[16, 44 + 34i, 72, 30]`, a destra | 22 |
| Titolo (evento *i*) | `[96, 44 + 34i, 464, 30]` | 22 |
| `+N altri` | `[360, 248, 200, 24]`, a destra | 16 |
| Filetto | `[0, 278, 560, 2]` | — |
| Giorno successivo 1 | `[0, 288, 560, 28]` | 16 |
| Giorno successivo 2 | `[0, 318, 560, 28]` | 16 |
| `agg. HH:MM` | `[360, 352, 200, 22]`, a destra | 13 |

Oggi ospita **al massimo sei eventi**. Il settimo e successivi diventano la riga
`+N altri`: dire che c'e' dell'altro e' meglio che farlo sparire in silenzio.

**Riga di aggiornamento.** L'ora dell'ultima pubblicazione, in basso a destra, non e' un
ornamento: con una cadenza di lettura di tre ore lo schermo puo' mostrare dati vecchi, e
senza quella riga chi guarda non ha modo di distinguere un'agenda fresca da una di
stamattina. Uno schermo vecchio deve restare leggibile *come* vecchio.

**Troncamento.** I titoli che eccedono la larghezza vengono tagliati e chiusi con `…`.
La larghezza disponibile in caratteri si stima come `larghezza_px / (CHAR_WIDTH_RATIO *
corpo)`, con `CHAR_WIDTH_RATIO = 0.52` — una costante unica, dichiaratamente
approssimativa, da tarare con una prova sul pannello. Il valore vive in un posto solo
proprio perche' e' da tarare.

**Piu' calendari.** Quando l'utente ne seleziona piu' di uno, gli eventi si fondono in
ordine cronologico e ciascuno porta un marcatore di **al massimo due caratteri**,
derivato dal nome del calendario: iniziale maiuscola, estesa a due lettere in caso di
collisione, e a una cifra progressiva se ancora ambigua. La derivazione e' deterministica
e testabile. Con un solo calendario il marcatore non compare e i 16 px tornano al titolo.

Il marcatore e' testuale e non cromatico perche' il pannello offre solo `black`, `white`,
`gray` e `transparent`: due tonalita' utili per il testo non bastano a distinguere piu'
di due calendari.

**Stato vuoto.** Nessun evento nella finestra produce una riga sola, centrata: `Nessun
evento nei prossimi 3 giorni`. Uno schermo vuoto deve sembrare una risposta, non un
guasto.

### Strato 3 — integrazione Home Assistant

**Config flow.** Chiede email, password e regione; fa il login, elenca i dispositivi
`W1070000`, fa scegliere quale. Persiste `refresh_token`, `user_id`, `device_id`,
`region` — **non la password**. Se il refresh token viene revocato, parte un reauth flow.

**Opzioni.** Due voci: quali calendari mostrare — scelta multipla fra le entità
`calendar.*` esistenti — e ogni quanto ripubblicare. Cambiarle ricarica la entry, senza
riavviare Home Assistant.

**Coordinator.** `DataUpdateCoordinator` con `update_interval` configurabile dalle
opzioni (default 15 minuti). Ad ogni ciclo: legge gli eventi dei calendari scelti con
`calendar.get_events`, genera la pagina con `build_agenda_page`, la valida, la compila,
e calcola un hash stabile della lista. Se l'hash è identico all'ultimo pubblicato, non
chiama niente. Altrimenti `update_template` seguito da `release`.

**Perché ripubblicare più spesso di quanto il pannello legga.** Il pannello si sveglia
ogni tre ore e prende ciò che trova sul server in quell'istante. Pubblicare ogni 15
minuti significa che al risveglio trova dati vecchi al massimo di 15 minuti; pubblicare
ogni tre ore significa fino a tre ore. Allineare la pubblicazione alla cadenza di lettura
sarebbe quindi un errore, non un'ottimizzazione.

L'hash evita di bruciare chiamate quando nulla è cambiato. Sull'API privata non c'è un
rate limit documentato; la OpenAPI pubblica raccomanda di non superare una chiamata al
minuto, quindi restiamo conservativi e imponiamo comunque un intervallo minimo di 60
secondi tra due pubblicazioni.

**Servizi.**

- `switchbot_eink.refresh` — forza ricompilazione e pubblicazione, ignorando l'hash.
- `switchbot_eink.push_text` — scorciatoia che scrive un testo su una card nominata,
  per le automazioni ("è arrivato un pacco").

**Entità diagnostiche.** Un `sensor` con l'ora dell'ultima pubblicazione riuscita e un
`binary_sensor` per lo stato di autenticazione, così i fallimenti sono visibili in HA
invece che solo nei log.

## Rischi

**~~La cadenza di aggiornamento del dispositivo non è nota.~~ Risolto: tre ore.** Il
supporto SwitchBot documenta che il pannello si riconnette e aggiorna i dati **ogni tre
ore**, con la pressione lunga del pulsante come aggiornamento immediato. La misura sul
campo è coerente: con un contenuto nuovo sul server, dopo dieci minuti il pannello
mostrava ancora quello vecchio. Il campo `refresh` del componente (`"1h"`, `"5m"`) viene
conservato dal backend ma non risulta influenzare la cadenza del dispositivo.

Conseguenza, ed è la ragione della scelta di contenuto: uno stato dei dispositivi vecchio
fino a tre ore sarebbe fuorviante, un'agenda no. Il rischio non è stato eliminato — è
stato assorbito scegliendo un contenuto che lo tollera.

**L'API è privata e non documentata.** Può cambiare o essere chiusa senza preavviso.
Mitigazione: confinata nello strato 1, con test che documentano il formato atteso.

**Il login richiede le credenziali dell'account SwitchBot.** Mitigazione: la password
non viene mai persistita, solo il refresh token.

**Resa su 4 livelli di grigio.** Layout troppo densi o font piccoli diventano
illeggibili. Mitigazione: l'endpoint `preview` restituisce il canvas renderizzato dal
backend e permette di verificare il risultato senza attendere il refresh del pannello.

## Strategia di test

- **Strato 2, unit test.** Il grosso della copertura. Definizione YAML → JSON atteso,
  con golden file. Casi: mappatura griglia → pixel, card fuori area, sovrapposizioni,
  whitelist di stile per tipo, rendering dei template Jinja, entità non disponibile.
- **Strato 1, test con HTTP mockato.** Envelope `resultCode`/`statusCode`, refresh su
  401 con retry singolo, mappatura degli errori. Le risposte di esempio vengono da
  chiamate reali registrate durante lo spike.
- **Strato 3, test di integrazione HA.** Config flow felice e con credenziali errate,
  reauth, coordinator che non pubblica a hash invariato.
- **Verifica manuale end-to-end.** `preview` per il controllo visivo, poi pubblicazione
  reale sul dispositivo.

## Fuori scopo, per dopo

- `data.source: "url"`, che farebbe fare il polling al backend SwitchBot verso un
  endpoint di HA. Elimina il push periodico ma il formato di risposta atteso è ignoto e
  richiede HA raggiungibile da internet.
- Un `image` a tutto schermo con una dashboard renderizzata da HA. Massima libertà
  grafica, ma serve un renderer e un URL pubblico.
- I due pulsanti fisici del dispositivo come trigger di automazioni HA.
