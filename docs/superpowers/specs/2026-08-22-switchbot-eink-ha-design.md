# SwitchBot E-Ink Home Dashboard come dashboard Home Assistant

**Data:** 2026-08-22
**Dispositivo:** SwitchBot E-Ink Home Dashboard / Weather Station, SKU `W8902500` (serie `W890250x`)
**Stato:** design approvato, da implementare

## Obiettivo

Usare il pannello e-ink da 7.5" come dashboard di stato della casa pilotata da Home
Assistant: temperature, stato dei dispositivi, consumi, avvisi. Il contenuto meteo
nativo non interessa e viene sostituito.

Non-obiettivi: sostituire il firmware, funzionare senza cloud SwitchBot, controllare
dispositivi dal pannello.

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

Base URL: `https://wonderlabs.{region}.api.switchbot.net/productbiz`, con
`region` ∈ `us` | `ap` | `eu` (default `us`; per l'Italia `eu`).
Account service: `https://account.api.switchbot.net`.

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

| Path | Body | Note |
|---|---|---|
| `/device/v1/manage/getDeviceList` | — | filtrare `deviceType == "W1070000"` e `isShare == false` |
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

### Il canvas

| Proprietà | Valore |
|---|---|
| Risoluzione | 800 × 480 |
| Modalità colore | `gray4` — 4 livelli di grigio |
| Safe area | `safeTop: 64`, `safeBottom: 44` |
| **Area utilizzabile** | **800 × 372** |

Resta da determinare sul campo se l'origine `y = 0` di un componente coincida con il
bordo fisico dello schermo o con il bordo inferiore della status bar. Il renderer
dell'editor calcola l'area utile come `height - safeTop - safeBottom`, il che suggerisce
la seconda, ma l'ambiguità va sciolta con una misura prima di fissare la griglia.

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

Griglia di **12 colonne × 6 righe** sull'area utile 800 × 372, con gutter configurabile
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

### Strato 3 — integrazione Home Assistant

**Config flow.** Chiede email, password e regione; fa il login, elenca i dispositivi
`W1070000`, fa scegliere quale. Persiste `refresh_token`, `user_id`, `device_id`,
`region` — **non la password**. Se il refresh token viene revocato, parte un reauth flow.

**Coordinator.** `DataUpdateCoordinator` con `update_interval` configurabile dalle
opzioni (default 15 minuti). Ad ogni ciclo: renderizza i template, compila i componenti,
calcola un hash stabile della lista. Se l'hash è identico all'ultimo pubblicato, non
chiama niente. Altrimenti `update_template` seguito da `release`.

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

**La cadenza di aggiornamento del dispositivo non è nota.** La documentazione SwitchBot
dice: *"Canvas pushed to backend. Long-press the device button 2s to refresh now."* Il
"now" lascia intendere che esista comunque un polling periodico — è un e-ink a batteria,
sarebbe strano il contrario — ma non è confermato. Se il pannello si aggiornasse solo
alla pressione del pulsante, il progetto perderebbe gran parte del suo valore.

Mitigazione: **è il primo task del piano di implementazione**, prima di scrivere
l'integrazione. Si pubblica un template con un timestamp, si lascia il dispositivo
fermo, e si misura ogni quanto il timestamp cambia da solo. Il risultato determina il
default di `update_interval` e, nel caso peggiore, fa riconsiderare l'intero approccio.

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
