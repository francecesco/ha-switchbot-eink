# SwitchBot E-Ink Home Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Costruire un'integrazione custom Home Assistant che pubblichi una dashboard di stato della casa sul pannello e-ink 7.5" del SwitchBot E-Ink Home Dashboard (SKU `W8902500`).

**Architecture:** Tre strati con dipendenza unidirezionale. Lo strato `api/` parla l'API privata del canvas editor SwitchBot e non importa nulla da Home Assistant, così è eseguibile e diagnosticabile da riga di comando. Lo strato `layout/` è un compilatore puro che trasforma una definizione YAML dichiarativa più i valori degli stati in componenti nel wire format. Lo strato Home Assistant contiene solo config flow, coordinator, servizi ed entità diagnostiche.

**Tech Stack:** Python 3.13, `aiohttp`, `voluptuous`, `pytest`, `pytest-asyncio`, `aioresponses`, `pytest-homeassistant-custom-component`.

**Spec:** `docs/superpowers/specs/2026-08-22-switchbot-eink-ha-design.md`

## Global Constraints

Valori esatti, copiati dalla spec. Ogni task li assume validi.

- Account base URL: `https://account.api.switchbot.net`
- Backend base URL: `https://wonderlabs.{region}.api.switchbot.net/productbiz`
- Regioni valide: `us`, `ap`, `eu` — default `us`, installazione target `eu`
- `clientId`: `pg6fbtxbi7q3o2n4zba852d5lh`
- `serviceId`: `weather_station`
- `deviceInfo` di login: `{"deviceName":"Web","deviceId":"hub-web","appVersion":"0.0.0","model":"Web"}`
- Device type del pannello: `W1070000` (la SKU `W8902500` non compare mai sul filo)
- Envelope backend: `{"resultCode":100,...,"data":...}` — successo se `resultCode == 100`
- Envelope account: `{"statusCode":100,...,"body":...}` — successo se `statusCode == 100`
- Header `Authorization`: `"{token_type} {access_token}"`, con `token_type` = `Bearer` se assente; **sulla sola regione `eu` il prefisso `Bearer ` va rimosso**
- Canvas: 800 × 480, `gray4`, `safeTop` 64, `safeBottom` 44 → area utile **800 × 372**
- `css` ed `extra` di ogni componente viaggiano come **stringhe JSON**, non come oggetti
- `id` di un componente: stringa che matcha `^[1-9]\d*$`, valore ≤ 2147483647, unica nel template
- Mappatura slot: `home` → `templateType` 1 e `sortOrder` 1; `custom1`…`custom4` → `templateType` 0 e `sortOrder` 1…4
- `sortOrder` sempre presente in `create`; in `update` solo se `> 0` **e** `templateType == 0`
- Intervallo minimo fra due pubblicazioni: 60 secondi
- Tutte le chiamate API sono `POST` con `content-type: application/json`

## File Structure

```
custom_components/switchbot_eink/
├── manifest.json           metadati integrazione
├── const.py                domain, chiavi di config, default
├── __init__.py             setup/unload della config entry
├── config_flow.py          setup iniziale, opzioni, reauth
├── coordinator.py          scheduling, hash, pubblicazione
├── sensor.py               entità diagnostica: ultima pubblicazione
├── binary_sensor.py        entità diagnostica: stato autenticazione
├── services.yaml           descrizione servizi
├── strings.json            testi del config flow
├── translations/
│   ├── en.json
│   └── it.json
├── api/                    STRATO 1 — nessun import da homeassistant
│   ├── __init__.py         riesporta client ed errori
│   ├── const.py            endpoint, regioni, costanti di login
│   ├── errors.py           gerarchia delle eccezioni
│   ├── envelope.py         funzioni pure: header auth, base url, unwrap
│   ├── http.py             client HTTP asincrono con retry su 401
│   ├── auth.py             login, refresh, userinfo
│   ├── models.py           dataclass Device, Template, TemplateSummary
│   └── client.py           facciata: dispositivi e template
└── layout/                 STRATO 2 — funzioni pure, nessuna I/O
    ├── __init__.py
    ├── const.py            geometria canvas, whitelist, tipi widget
    ├── grid.py             griglia 12×6 → pixel
    ├── widgets.py          card astratta → componente wire
    ├── schema.py           validazione voluptuous della definizione
    └── compile.py          entry point del compilatore

tools/
└── probe.py                CLI di diagnostica e misura sul campo

tests/
├── conftest.py
├── api/
│   ├── test_envelope.py
│   ├── test_http.py
│   ├── test_auth.py
│   └── test_client.py
├── layout/
│   ├── test_grid.py
│   ├── test_widgets.py
│   ├── test_schema.py
│   └── test_compile.py
└── ha/
    ├── test_config_flow.py
    └── test_coordinator.py

docs/superpowers/notes/
└── 2026-08-22-refresh-cadence.md    risultato della misura sul campo

pyproject.toml
hacs.json
README.md
```

Il criterio di divisione: `api/` cambia quando cambia il backend SwitchBot, `layout/` cambia quando cambia il modo in cui l'utente descrive la dashboard, la radice cambia quando cambia Home Assistant. Sono tre ritmi di cambiamento diversi, quindi tre unità separate.

---

### Task 1: Scaffold e funzioni pure di protocollo

**Files:**
- Create: `pyproject.toml`
- Create: `custom_components/switchbot_eink/__init__.py` (vuoto per ora)
- Create: `custom_components/switchbot_eink/api/__init__.py`
- Create: `custom_components/switchbot_eink/api/const.py`
- Create: `custom_components/switchbot_eink/api/errors.py`
- Create: `custom_components/switchbot_eink/api/envelope.py`
- Test: `tests/api/test_envelope.py`

**Interfaces:**
- Consumes: niente, è il primo task.
- Produces: `build_auth_header(access_token: str, token_type: str | None, region: str) -> str`, `backend_base_url(region: str) -> str`, `unwrap_backend(payload: object) -> Any`, `unwrap_account(payload: object) -> Any`, le eccezioni `SwitchBotCanvasError`, `SwitchBotCanvasAuthError`, `SwitchBotCanvasApiError(code, message)`, e tutte le costanti di `api/const.py`.

- [ ] **Step 1: Creare `pyproject.toml`**

```toml
[project]
name = "switchbot-eink"
version = "0.1.0"
description = "Home Assistant custom integration for the SwitchBot E-Ink Home Dashboard"
requires-python = ">=3.13"
dependencies = ["aiohttp>=3.9", "voluptuous>=0.13"]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "aioresponses>=0.7.6",
    "pytest-homeassistant-custom-component>=0.13",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py313"
line-length = 100
```

- [ ] **Step 2: Creare i package vuoti**

```bash
mkdir -p custom_components/switchbot_eink/api custom_components/switchbot_eink/layout tests/api tests/layout tests/ha tools
touch custom_components/switchbot_eink/__init__.py
touch custom_components/switchbot_eink/api/__init__.py
touch custom_components/switchbot_eink/layout/__init__.py
touch tests/__init__.py tests/api/__init__.py tests/layout/__init__.py
```

- [ ] **Step 3: Scrivere il test che fallisce**

File `tests/api/test_envelope.py`:

```python
"""Test delle funzioni pure di protocollo."""
from __future__ import annotations

import pytest

from custom_components.switchbot_eink.api.envelope import (
    backend_base_url,
    build_auth_header,
    unwrap_account,
    unwrap_backend,
)
from custom_components.switchbot_eink.api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
)


def test_auth_header_prefissa_bearer_fuori_dalla_ue() -> None:
    assert build_auth_header("abc123", "Bearer", "us") == "Bearer abc123"


def test_auth_header_usa_bearer_quando_il_tipo_manca() -> None:
    assert build_auth_header("abc123", None, "us") == "Bearer abc123"


def test_auth_header_rimuove_bearer_nella_regione_eu() -> None:
    assert build_auth_header("abc123", "Bearer", "eu") == "abc123"


def test_auth_header_eu_e_insensibile_alle_maiuscole() -> None:
    assert build_auth_header("abc123", "bearer", "eu") == "abc123"


def test_backend_base_url_interpola_la_regione() -> None:
    assert backend_base_url("eu") == "https://wonderlabs.eu.api.switchbot.net/productbiz"


def test_backend_base_url_ripiega_su_us_se_la_regione_e_ignota() -> None:
    assert backend_base_url("xx") == "https://wonderlabs.us.api.switchbot.net/productbiz"


def test_unwrap_backend_restituisce_data_quando_result_code_e_100() -> None:
    assert unwrap_backend({"resultCode": 100, "data": {"ok": True}}) == {"ok": True}


def test_unwrap_backend_solleva_su_result_code_diverso() -> None:
    with pytest.raises(SwitchBotCanvasApiError) as err:
        unwrap_backend({"resultCode": 190, "message": "invalid params"})
    assert err.value.code == 190
    assert err.value.message == "invalid params"


def test_unwrap_backend_solleva_auth_error_su_401() -> None:
    with pytest.raises(SwitchBotCanvasAuthError):
        unwrap_backend({"resultCode": 401, "message": "unauthorized"})


def test_unwrap_backend_rifiuta_payload_non_dizionario() -> None:
    with pytest.raises(SwitchBotCanvasApiError):
        unwrap_backend("nope")


def test_unwrap_account_restituisce_body_quando_status_code_e_100() -> None:
    assert unwrap_account({"statusCode": 100, "body": {"access_token": "t"}}) == {
        "access_token": "t"
    }


def test_unwrap_account_solleva_auth_error_su_status_code_diverso() -> None:
    with pytest.raises(SwitchBotCanvasAuthError):
        unwrap_account({"statusCode": 160, "message": "wrong password"})


def test_unwrap_account_solleva_se_il_body_manca() -> None:
    with pytest.raises(SwitchBotCanvasAuthError):
        unwrap_account({"statusCode": 100})
```

- [ ] **Step 4: Eseguire il test e verificare che fallisca**

Run: `pytest tests/api/test_envelope.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.api.envelope'`

- [ ] **Step 5: Scrivere `api/const.py`**

```python
"""Costanti dell'API privata del canvas editor SwitchBot.

Ricavate per reverse engineering dai bundle JavaScript pubblici di
https://e-ink-home-dashboard.switch-bot.com. Non sono documentazione ufficiale.
"""
from __future__ import annotations

from typing import Final

ACCOUNT_BASE_URL: Final = "https://account.api.switchbot.net"
BACKEND_BASE_TEMPLATE: Final = "https://wonderlabs.{region}.api.switchbot.net/productbiz"

CLIENT_ID: Final = "pg6fbtxbi7q3o2n4zba852d5lh"
SERVICE_ID: Final = "weather_station"

REGIONS: Final[tuple[str, ...]] = ("us", "ap", "eu")
DEFAULT_REGION: Final = "us"

DEVICE_TYPE_EINK: Final = "W1070000"
PANEL_ID: Final = "eink-7in3"

DEVICE_INFO: Final[dict[str, str]] = {
    "deviceName": "Web",
    "deviceId": "hub-web",
    "appVersion": "0.0.0",
    "model": "Web",
}

RESULT_OK: Final = 100

PATH_LOGIN: Final = "/account/api/v1/user/login"
PATH_REFRESH: Final = "/account/api/v1/user/token/refresh"
PATH_USERINFO: Final = "/account/api/v1/user/userinfo"

PATH_DEVICE_LIST: Final = "/device/v1/manage/getDeviceList"

PATH_TPL_LIST: Final = "/web/v1/user/templates/list"
PATH_TPL_INFO: Final = "/web/v1/user/templates/info"
PATH_TPL_CREATE: Final = "/web/v1/user/templates/create"
PATH_TPL_UPDATE: Final = "/web/v1/user/templates/update"
PATH_TPL_DEL: Final = "/web/v1/user/templates/del"
PATH_TPL_RELEASE: Final = "/web/v1/user/templates/release"
PATH_TPL_PREVIEW: Final = "/web/v1/user/templates/preview"
```

- [ ] **Step 6: Scrivere `api/errors.py`**

```python
"""Eccezioni dello strato API."""
from __future__ import annotations


class SwitchBotCanvasError(Exception):
    """Errore generico nel dialogo con il backend SwitchBot."""


class SwitchBotCanvasAuthError(SwitchBotCanvasError):
    """Credenziali o token non validi: serve un nuovo login."""


class SwitchBotCanvasApiError(SwitchBotCanvasError):
    """Il backend ha risposto con un codice di errore applicativo."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
```

- [ ] **Step 7: Scrivere `api/envelope.py`**

```python
"""Funzioni pure di protocollo: header, URL, envelope delle risposte.

Nessuna I/O qui dentro, così restano banali da testare.
"""
from __future__ import annotations

import re
from typing import Any

from .const import BACKEND_BASE_TEMPLATE, DEFAULT_REGION, REGIONS, RESULT_OK
from .errors import SwitchBotCanvasApiError, SwitchBotCanvasAuthError

_BEARER_PREFIX = re.compile(r"^Bearer\s+", re.IGNORECASE)


def build_auth_header(access_token: str, token_type: str | None, region: str) -> str:
    """Costruisce il valore dell'header Authorization.

    Il client web usa "{token_type} {access_token}", ma sulla sola regione eu
    rimuove il prefisso Bearer e manda il token nudo. Ignorare questo dettaglio
    produce 401 senza spiegazione.
    """
    header = f"{token_type or 'Bearer'} {access_token}"
    if region == "eu":
        header = _BEARER_PREFIX.sub("", header)
    return header


def backend_base_url(region: str) -> str:
    """URL base del servizio productbiz per la regione data."""
    if region not in REGIONS:
        region = DEFAULT_REGION
    return BACKEND_BASE_TEMPLATE.format(region=region)


def unwrap_backend(payload: object) -> Any:
    """Estrae `data` da un envelope productbiz, sollevando sugli errori."""
    if not isinstance(payload, dict):
        raise SwitchBotCanvasApiError(-1, f"Risposta malformata: {payload!r}")
    code = payload.get("resultCode")
    if code != RESULT_OK:
        message = str(payload.get("message", ""))
        if code == 401:
            raise SwitchBotCanvasAuthError(f"[{code}] {message}")
        raise SwitchBotCanvasApiError(int(code) if code is not None else -1, message)
    return payload.get("data")


def unwrap_account(payload: object) -> Any:
    """Estrae `body` da un envelope dell'account service."""
    if not isinstance(payload, dict):
        raise SwitchBotCanvasAuthError(f"Risposta malformata: {payload!r}")
    code = payload.get("statusCode")
    if code != RESULT_OK:
        raise SwitchBotCanvasAuthError(f"[{code}] {payload.get('message', '')}")
    if "body" not in payload:
        raise SwitchBotCanvasAuthError("L'account service ha risposto senza body")
    return payload["body"]
```

- [ ] **Step 8: Eseguire i test e verificare che passino**

Run: `pytest tests/api/test_envelope.py -v`
Expected: PASS, 13 test

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml custom_components tests
git commit -m "feat(api): aggiungi costanti, errori e funzioni pure di protocollo"
```

---

### Task 2: Client HTTP asincrono con retry su 401

**Files:**
- Create: `custom_components/switchbot_eink/api/http.py`
- Test: `tests/api/test_http.py`

**Interfaces:**
- Consumes: da Task 1 — `unwrap_backend`, `unwrap_account`, `SwitchBotCanvasAuthError`, `SwitchBotCanvasApiError`.
- Produces: `CanvasHttp(session, base_url, unwrap, auth_provider=None, on_unauthorized=None)` con il metodo `async request(path: str, body: dict | None = None) -> Any`. `auth_provider` è un `Callable[[], str | None]`, `on_unauthorized` è un `Callable[[], Awaitable[bool]]` che tenta il refresh e ritorna `True` se è riuscito.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/api/test_http.py`:

```python
"""Test del client HTTP."""
from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.switchbot_eink.api.envelope import unwrap_backend
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError
from custom_components.switchbot_eink.api.http import CanvasHttp

BASE = "https://example.test/productbiz"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess


async def test_request_invia_post_json_e_scarta_envelope(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend)
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": {"pong": 1}})
        assert await http.request("/ping", {"a": 1}) == {"pong": 1}


async def test_request_aggiunge_header_authorization(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend, auth_provider=lambda: "tok")
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": None})
        await http.request("/ping")
        request = next(iter(mocked.requests.values()))[0]
        assert request.kwargs["headers"]["Authorization"] == "tok"


async def test_request_omette_authorization_senza_provider(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend)
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": None})
        await http.request("/ping")
        request = next(iter(mocked.requests.values()))[0]
        assert "Authorization" not in request.kwargs["headers"]


async def test_401_http_tenta_il_refresh_e_ripete_una_volta(session) -> None:
    chiamate: list[str] = []

    async def refresh() -> bool:
        chiamate.append("refresh")
        return True

    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        mocked.post(f"{BASE}/ping", payload={"resultCode": 100, "data": {"ok": True}})
        assert await http.request("/ping") == {"ok": True}
    assert chiamate == ["refresh"]


async def test_401_due_volte_solleva_auth_error(session) -> None:
    async def refresh() -> bool:
        return True

    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        mocked.post(f"{BASE}/ping", status=401)
        with pytest.raises(SwitchBotCanvasAuthError):
            await http.request("/ping")


async def test_401_senza_refresh_disponibile_solleva_subito(session) -> None:
    http = CanvasHttp(session, BASE, unwrap_backend, auth_provider=lambda: "tok")
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        with pytest.raises(SwitchBotCanvasAuthError):
            await http.request("/ping")


async def test_refresh_fallito_solleva_auth_error(session) -> None:
    async def refresh() -> bool:
        return False

    http = CanvasHttp(
        session, BASE, unwrap_backend, auth_provider=lambda: "tok", on_unauthorized=refresh
    )
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=401)
        with pytest.raises(SwitchBotCanvasAuthError):
            await http.request("/ping")


async def test_errore_http_generico_solleva_api_error(session) -> None:
    from custom_components.switchbot_eink.api.errors import SwitchBotCanvasApiError

    http = CanvasHttp(session, BASE, unwrap_backend)
    with aioresponses() as mocked:
        mocked.post(f"{BASE}/ping", status=500)
        with pytest.raises(SwitchBotCanvasApiError):
            await http.request("/ping")
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/api/test_http.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.api.http'`

- [ ] **Step 3: Scrivere `api/http.py`**

```python
"""Client HTTP asincrono per il backend SwitchBot."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from .errors import SwitchBotCanvasApiError, SwitchBotCanvasAuthError

AuthProvider = Callable[[], str | None]
RefreshCallback = Callable[[], Awaitable[bool]]
Unwrapper = Callable[[object], Any]


class CanvasHttp:
    """POST JSON verso un base URL, con un solo tentativo di refresh su 401."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        base_url: str,
        unwrap: Unwrapper,
        auth_provider: AuthProvider | None = None,
        on_unauthorized: RefreshCallback | None = None,
    ) -> None:
        self._session = session
        self._base_url = base_url.rstrip("/")
        self._unwrap = unwrap
        self._auth_provider = auth_provider
        self._on_unauthorized = on_unauthorized

    async def request(self, path: str, body: dict[str, Any] | None = None) -> Any:
        status, payload = await self._post_once(path, body)

        if status == 401 and self._on_unauthorized is not None:
            if not await self._on_unauthorized():
                raise SwitchBotCanvasAuthError("Refresh del token fallito")
            status, payload = await self._post_once(path, body)

        if status == 401:
            raise SwitchBotCanvasAuthError("Il backend ha risposto 401")
        if status >= 400:
            raise SwitchBotCanvasApiError(status, f"HTTP {status}")

        return self._unwrap(payload)

    async def _post_once(
        self, path: str, body: dict[str, Any] | None
    ) -> tuple[int, object]:
        headers = {"content-type": "application/json"}
        if self._auth_provider is not None:
            token = self._auth_provider()
            if token:
                headers["Authorization"] = token

        try:
            async with self._session.post(
                f"{self._base_url}{path}", headers=headers, json=body
            ) as response:
                if response.status >= 400:
                    return response.status, None
                return response.status, await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise SwitchBotCanvasApiError(0, f"Errore di rete: {err}") from err
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `pytest tests/api/test_http.py -v`
Expected: PASS, 8 test

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_eink/api/http.py tests/api/test_http.py
git commit -m "feat(api): aggiungi client HTTP con retry singolo su 401"
```

---

### Task 3: Autenticazione

**Files:**
- Create: `custom_components/switchbot_eink/api/auth.py`
- Test: `tests/api/test_auth.py`

**Interfaces:**
- Consumes: da Task 1 — `unwrap_account`, costanti; da Task 2 — `CanvasHttp`.
- Produces: dataclass `Tokens(access_token: str, refresh_token: str, token_type: str, expires_in: int, refresh_expires_in: int)`, dataclass `UserInfo(user_id: str, email: str)`, classe `CanvasAuth(session, region)` con `async login(username, password) -> Tokens`, `async refresh(user_id, refresh_token) -> Tokens`, `async user_info(access_header: str) -> UserInfo`.

Il refresh richiede lo `userId`, che si ottiene solo da `/userinfo`: chi consuma questo modulo deve persistere entrambi.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/api/test_auth.py`:

```python
"""Test dell'autenticazione."""
from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.switchbot_eink.api.auth import CanvasAuth
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError

ACCOUNT = "https://account.api.switchbot.net"


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess


async def test_login_restituisce_i_token(session) -> None:
    auth = CanvasAuth(session, "eu")
    with aioresponses() as mocked:
        mocked.post(
            f"{ACCOUNT}/account/api/v1/user/login",
            payload={
                "statusCode": 100,
                "body": {
                    "access_token": "AT",
                    "refresh_token": "RT",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                    "refresh_expires_in": 86400,
                },
            },
        )
        tokens = await auth.login("mario@example.test", "segreta")

    assert tokens.access_token == "AT"
    assert tokens.refresh_token == "RT"
    assert tokens.token_type == "Bearer"
    assert tokens.expires_in == 3600


async def test_login_invia_client_id_e_device_info(session) -> None:
    auth = CanvasAuth(session, "eu")
    with aioresponses() as mocked:
        mocked.post(
            f"{ACCOUNT}/account/api/v1/user/login",
            payload={"statusCode": 100, "body": {"access_token": "AT", "refresh_token": "RT"}},
        )
        await auth.login("mario@example.test", "segreta")
        request = next(iter(mocked.requests.values()))[0]

    body = request.kwargs["json"]
    assert body["clientId"] == "pg6fbtxbi7q3o2n4zba852d5lh"
    assert body["grantType"] == "password"
    assert body["username"] == "mario@example.test"
    assert body["deviceInfo"] == {
        "deviceName": "Web",
        "deviceId": "hub-web",
        "appVersion": "0.0.0",
        "model": "Web",
    }


async def test_login_con_credenziali_errate_solleva_auth_error(session) -> None:
    auth = CanvasAuth(session, "eu")
    with aioresponses() as mocked:
        mocked.post(
            f"{ACCOUNT}/account/api/v1/user/login",
            payload={"statusCode": 160, "message": "wrong password"},
        )
        with pytest.raises(SwitchBotCanvasAuthError):
            await auth.login("mario@example.test", "sbagliata")


async def test_refresh_invia_user_id_e_refresh_token(session) -> None:
    auth = CanvasAuth(session, "eu")
    with aioresponses() as mocked:
        mocked.post(
            f"{ACCOUNT}/account/api/v1/user/token/refresh",
            payload={
                "statusCode": 100,
                "body": {"access_token": "AT2", "token_type": "Bearer", "expires_in": 3600},
            },
        )
        tokens = await auth.refresh("user-1", "RT")
        request = next(iter(mocked.requests.values()))[0]

    assert request.kwargs["json"] == {
        "userId": "user-1",
        "refreshToken": "RT",
        "clientId": "pg6fbtxbi7q3o2n4zba852d5lh",
    }
    assert tokens.access_token == "AT2"
    assert tokens.refresh_token == "RT", "il refresh token va conservato, la risposta non lo ripete"


async def test_user_info_restituisce_id_ed_email(session) -> None:
    auth = CanvasAuth(session, "eu")
    with aioresponses() as mocked:
        mocked.post(
            f"{ACCOUNT}/account/api/v1/user/userinfo",
            payload={"statusCode": 100, "body": {"userID": "user-1", "email": "m@example.test"}},
        )
        info = await auth.user_info("AT")

    assert info.user_id == "user-1"
    assert info.email == "m@example.test"


async def test_user_info_invia_header_senza_bearer_in_eu(session) -> None:
    auth = CanvasAuth(session, "eu")
    with aioresponses() as mocked:
        mocked.post(
            f"{ACCOUNT}/account/api/v1/user/userinfo",
            payload={"statusCode": 100, "body": {"userID": "u", "email": "e"}},
        )
        await auth.user_info("AT")
        request = next(iter(mocked.requests.values()))[0]

    assert request.kwargs["headers"]["Authorization"] == "AT"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/api/test_auth.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.api.auth'`

- [ ] **Step 3: Scrivere `api/auth.py`**

```python
"""Login, refresh del token e profilo utente."""
from __future__ import annotations

from dataclasses import dataclass

import aiohttp

from .const import (
    ACCOUNT_BASE_URL,
    CLIENT_ID,
    DEVICE_INFO,
    PATH_LOGIN,
    PATH_REFRESH,
    PATH_USERINFO,
)
from .envelope import build_auth_header, unwrap_account
from .http import CanvasHttp


@dataclass(frozen=True, slots=True)
class Tokens:
    """Token restituiti dall'account service."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0
    refresh_expires_in: int = 0


@dataclass(frozen=True, slots=True)
class UserInfo:
    """Identità dell'utente autenticato."""

    user_id: str
    email: str


class CanvasAuth:
    """Dialoga con https://account.api.switchbot.net."""

    def __init__(self, session: aiohttp.ClientSession, region: str) -> None:
        self._session = session
        self._region = region

    def _http(self, auth_header: str | None = None) -> CanvasHttp:
        return CanvasHttp(
            self._session,
            ACCOUNT_BASE_URL,
            unwrap_account,
            auth_provider=(lambda: auth_header) if auth_header else None,
        )

    async def login(self, username: str, password: str) -> Tokens:
        """Autentica con email e password e restituisce i token."""
        body = await self._http().request(
            PATH_LOGIN,
            {
                "username": username,
                "password": password,
                "deviceInfo": DEVICE_INFO,
                "grantType": "password",
                "clientId": CLIENT_ID,
            },
        )
        return Tokens(
            access_token=body["access_token"],
            refresh_token=body["refresh_token"],
            token_type=body.get("token_type", "Bearer"),
            expires_in=int(body.get("expires_in", 0)),
            refresh_expires_in=int(body.get("refresh_expires_in", 0)),
        )

    async def refresh(self, user_id: str, refresh_token: str) -> Tokens:
        """Rinnova l'access token. Il refresh token non viene ripetuto dalla risposta."""
        body = await self._http().request(
            PATH_REFRESH,
            {"userId": user_id, "refreshToken": refresh_token, "clientId": CLIENT_ID},
        )
        return Tokens(
            access_token=body["access_token"],
            refresh_token=refresh_token,
            token_type=body.get("token_type", "Bearer"),
            expires_in=int(body.get("expires_in", 0)),
        )

    async def user_info(self, access_token: str, token_type: str = "Bearer") -> UserInfo:
        """Recupera userID ed email, necessari per il refresh."""
        header = build_auth_header(access_token, token_type, self._region)
        body = await self._http(header).request(PATH_USERINFO)
        return UserInfo(user_id=str(body["userID"]), email=str(body.get("email", "")))
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `pytest tests/api/test_auth.py -v`
Expected: PASS, 6 test

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_eink/api/auth.py tests/api/test_auth.py
git commit -m "feat(api): aggiungi login, refresh e recupero del profilo"
```

---

### Task 4: Modelli e facciata del client

**Files:**
- Create: `custom_components/switchbot_eink/api/models.py`
- Create: `custom_components/switchbot_eink/api/client.py`
- Modify: `custom_components/switchbot_eink/api/__init__.py`
- Test: `tests/api/test_client.py`

**Interfaces:**
- Consumes: da Task 1–3 — costanti, `unwrap_backend`, `backend_base_url`, `build_auth_header`, `CanvasHttp`, `CanvasAuth`, `Tokens`.
- Produces:
  - `Device(device_id: str, device_name: str, device_type: str, is_share: bool)`
  - `TemplateSummary(template_id: int, name: str, page_slot: str)`
  - `Template(template_id: int | None, name: str, page_slot: str, device_id: str, components: list[dict])` con proprietà `template_type: int` e `sort_order: int`
  - `page_slot_to_sort_order(page_slot: str) -> int` e `page_slot_to_template_type(page_slot: str) -> int`
  - `SwitchBotCanvasClient(session, region, tokens, user_id)` con `async list_devices() -> list[Device]`, `async list_eink_devices() -> list[Device]`, `async list_templates(device_id) -> list[TemplateSummary]`, `async create_template(t: Template) -> int`, `async update_template(t: Template) -> None`, `async delete_template(template_id, device_id) -> None`, `async release(device_id) -> None`, `async preview(template_id, device_id) -> dict`

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/api/test_client.py`:

```python
"""Test dei modelli e della facciata del client."""
from __future__ import annotations

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.api.client import SwitchBotCanvasClient
from custom_components.switchbot_eink.api.models import (
    Template,
    page_slot_to_sort_order,
    page_slot_to_template_type,
)

BASE = "https://wonderlabs.eu.api.switchbot.net/productbiz"
TOKENS = Tokens(access_token="AT", refresh_token="RT", token_type="Bearer")


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as sess:
        yield sess


@pytest.fixture
def client(session):
    return SwitchBotCanvasClient(session, "eu", TOKENS, user_id="user-1")


def test_slot_home_mappa_su_template_type_1() -> None:
    assert page_slot_to_template_type("home") == 1
    assert page_slot_to_sort_order("home") == 1


def test_slot_custom_mappa_su_template_type_0() -> None:
    assert page_slot_to_template_type("custom3") == 0
    assert page_slot_to_sort_order("custom3") == 3


def test_slot_sconosciuto_ha_sort_order_zero() -> None:
    assert page_slot_to_sort_order("unassigned") == 0


async def test_list_eink_devices_filtra_per_tipo_e_condivisione(client) -> None:
    with aioresponses() as mocked:
        mocked.post(
            f"{BASE}/device/v1/manage/getDeviceList",
            payload={
                "resultCode": 100,
                "data": [
                    {"deviceID": "A", "deviceName": "Pannello", "deviceType": "W1070000",
                     "isShare": False},
                    {"deviceID": "B", "deviceName": "Condiviso", "deviceType": "W1070000",
                     "isShare": True},
                    {"deviceID": "C", "deviceName": "Meter", "deviceType": "WoMeter",
                     "isShare": False},
                ],
            },
        )
        devices = await client.list_eink_devices()

    assert [d.device_id for d in devices] == ["A"]


async def test_create_template_invia_sort_order_e_restituisce_id(client) -> None:
    template = Template(
        template_id=None,
        name="Casa",
        page_slot="custom1",
        device_id="A",
        components=[{"id": "1", "type": "text", "name": "t", "css": "{}", "extra": "{}"}],
    )
    with aioresponses() as mocked:
        mocked.post(
            f"{BASE}/web/v1/user/templates/create",
            payload={"resultCode": 100, "data": {"templateId": 77}},
        )
        template_id = await client.create_template(template)
        request = next(iter(mocked.requests.values()))[0]

    body = request.kwargs["json"]
    assert body["sortOrder"] == 1
    assert body["templateType"] == 0
    assert body["enabled"] is True
    assert body["deviceID"] == "A"
    assert body["components"][0]["css"] == "{}"
    assert template_id == 77


async def test_update_template_include_sort_order_per_le_pagine_custom(client) -> None:
    template = Template(
        template_id=77, name="Casa", page_slot="custom2", device_id="A", components=[]
    )
    with aioresponses() as mocked:
        mocked.post(
            f"{BASE}/web/v1/user/templates/update", payload={"resultCode": 100, "data": None}
        )
        await client.update_template(template)
        request = next(iter(mocked.requests.values()))[0]

    body = request.kwargs["json"]
    assert body["templateId"] == 77
    assert body["sortOrder"] == 2


async def test_update_template_omette_sort_order_per_la_home(client) -> None:
    template = Template(
        template_id=77, name="Home", page_slot="home", device_id="A", components=[]
    )
    with aioresponses() as mocked:
        mocked.post(
            f"{BASE}/web/v1/user/templates/update", payload={"resultCode": 100, "data": None}
        )
        await client.update_template(template)
        request = next(iter(mocked.requests.values()))[0]

    assert "sortOrder" not in request.kwargs["json"]


async def test_release_invia_solo_il_device_id(client) -> None:
    with aioresponses() as mocked:
        mocked.post(
            f"{BASE}/web/v1/user/templates/release", payload={"resultCode": 100, "data": None}
        )
        await client.release("A")
        request = next(iter(mocked.requests.values()))[0]

    assert request.kwargs["json"] == {"deviceID": "A"}


async def test_header_authorization_senza_bearer_in_eu(client) -> None:
    with aioresponses() as mocked:
        mocked.post(
            f"{BASE}/web/v1/user/templates/release", payload={"resultCode": 100, "data": None}
        )
        await client.release("A")
        request = next(iter(mocked.requests.values()))[0]

    assert request.kwargs["headers"]["Authorization"] == "AT"


async def test_header_authorization_con_bearer_in_us(session) -> None:
    client_us = SwitchBotCanvasClient(session, "us", TOKENS, user_id="user-1")
    base_us = "https://wonderlabs.us.api.switchbot.net/productbiz"
    with aioresponses() as mocked:
        mocked.post(
            f"{base_us}/web/v1/user/templates/release",
            payload={"resultCode": 100, "data": None},
        )
        await client_us.release("A")
        request = next(iter(mocked.requests.values()))[0]

    assert request.kwargs["headers"]["Authorization"] == "Bearer AT"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/api/test_client.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.api.models'`

- [ ] **Step 3: Scrivere `api/models.py`**

```python
"""Modelli di dominio dell'API canvas."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

_CUSTOM_SLOT = re.compile(r"^custom([1-4])$")


def page_slot_to_template_type(page_slot: str) -> int:
    """1 per la home, 0 per le pagine custom."""
    return 1 if page_slot == "home" else 0


def page_slot_to_sort_order(page_slot: str) -> int:
    """home → 1, custom1..custom4 → 1..4, tutto il resto → 0."""
    if page_slot == "home":
        return 1
    match = _CUSTOM_SLOT.match(page_slot)
    return int(match.group(1)) if match else 0


@dataclass(frozen=True, slots=True)
class Device:
    """Un dispositivo dell'account."""

    device_id: str
    device_name: str
    device_type: str
    is_share: bool

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> Device:
        return cls(
            device_id=str(payload["deviceID"]),
            device_name=str(payload.get("deviceName", "")),
            device_type=str(payload.get("deviceType", "")),
            is_share=bool(payload.get("isShare", False)),
        )


@dataclass(frozen=True, slots=True)
class TemplateSummary:
    """Voce della lista dei template."""

    template_id: int
    name: str
    page_slot: str


@dataclass(slots=True)
class Template:
    """Un template pronto per essere inviato.

    `components` contiene già i componenti nel wire format, con `css` ed `extra`
    serializzati come stringhe JSON.
    """

    template_id: int | None
    name: str
    page_slot: str
    device_id: str
    components: list[dict[str, Any]] = field(default_factory=list)

    @property
    def template_type(self) -> int:
        return page_slot_to_template_type(self.page_slot)

    @property
    def sort_order(self) -> int:
        return page_slot_to_sort_order(self.page_slot)
```

- [ ] **Step 4: Scrivere `api/client.py`**

```python
"""Facciata unica sull'API privata del canvas."""
from __future__ import annotations

from typing import Any

import aiohttp

from .auth import CanvasAuth, Tokens
from .const import (
    DEVICE_TYPE_EINK,
    PATH_DEVICE_LIST,
    PATH_TPL_CREATE,
    PATH_TPL_DEL,
    PATH_TPL_LIST,
    PATH_TPL_PREVIEW,
    PATH_TPL_RELEASE,
    PATH_TPL_UPDATE,
)
from .envelope import backend_base_url, build_auth_header, unwrap_backend
from .http import CanvasHttp
from .models import Device, Template, TemplateSummary


class SwitchBotCanvasClient:
    """Dispositivi e template. Rinnova il token da solo quando scade."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        region: str,
        tokens: Tokens,
        user_id: str,
    ) -> None:
        self._region = region
        self._tokens = tokens
        self._user_id = user_id
        self._auth = CanvasAuth(session, region)
        self._http = CanvasHttp(
            session,
            backend_base_url(region),
            unwrap_backend,
            auth_provider=self._auth_header,
            on_unauthorized=self._try_refresh,
        )

    @property
    def tokens(self) -> Tokens:
        """Token correnti, da ripersistere dopo un refresh riuscito."""
        return self._tokens

    def _auth_header(self) -> str:
        return build_auth_header(
            self._tokens.access_token, self._tokens.token_type, self._region
        )

    async def _try_refresh(self) -> bool:
        try:
            self._tokens = await self._auth.refresh(
                self._user_id, self._tokens.refresh_token
            )
        except Exception:  # noqa: BLE001 — qualsiasi fallimento significa "rifai il login"
            return False
        return True

    async def list_devices(self) -> list[Device]:
        payload = await self._http.request(PATH_DEVICE_LIST)
        return [Device.from_payload(item) for item in (payload or [])]

    async def list_eink_devices(self) -> list[Device]:
        """Solo i pannelli e-ink di proprietà, non quelli condivisi."""
        return [
            device
            for device in await self.list_devices()
            if device.device_type == DEVICE_TYPE_EINK and not device.is_share
        ]

    async def list_templates(self, device_id: str) -> list[TemplateSummary]:
        payload = await self._http.request(PATH_TPL_LIST, {"deviceID": device_id})
        items = (payload or {}).get("items", []) if isinstance(payload, dict) else []
        return [
            TemplateSummary(
                template_id=int(item["templateId"]),
                name=str(item.get("name", "")),
                page_slot=str(item.get("pageSlot", "unassigned")),
            )
            for item in items
        ]

    async def create_template(self, template: Template) -> int:
        body = {
            "name": template.name,
            "enabled": True,
            "sortOrder": template.sort_order,
            "templateType": template.template_type,
            "components": template.components,
            "deviceID": template.device_id,
        }
        payload = await self._http.request(PATH_TPL_CREATE, body)
        return int(payload["templateId"])

    async def update_template(self, template: Template) -> None:
        if template.template_id is None:
            raise ValueError("update_template richiede un template_id")

        body: dict[str, Any] = {
            "templateId": template.template_id,
            "name": template.name,
            "enabled": True,
            "templateType": template.template_type,
            "components": template.components,
            "deviceID": template.device_id,
        }
        if template.sort_order > 0 and template.template_type == 0:
            body["sortOrder"] = template.sort_order

        await self._http.request(PATH_TPL_UPDATE, body)

    async def delete_template(self, template_id: int, device_id: str) -> None:
        await self._http.request(
            PATH_TPL_DEL, {"templateId": template_id, "deviceID": device_id}
        )

    async def release(self, device_id: str) -> None:
        """Pubblica al dispositivo i template correnti."""
        await self._http.request(PATH_TPL_RELEASE, {"deviceID": device_id})

    async def preview(self, template_id: int, device_id: str) -> dict[str, Any]:
        payload = await self._http.request(
            PATH_TPL_PREVIEW, {"templateId": template_id, "deviceID": device_id}
        )
        return payload or {}
```

- [ ] **Step 5: Scrivere `api/__init__.py`**

```python
"""Client dell'API privata del canvas SwitchBot E-Ink Home Dashboard."""
from __future__ import annotations

from .auth import CanvasAuth, Tokens, UserInfo
from .client import SwitchBotCanvasClient
from .errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
    SwitchBotCanvasError,
)
from .models import Device, Template, TemplateSummary

__all__ = [
    "CanvasAuth",
    "Device",
    "SwitchBotCanvasApiError",
    "SwitchBotCanvasAuthError",
    "SwitchBotCanvasClient",
    "SwitchBotCanvasError",
    "Template",
    "TemplateSummary",
    "Tokens",
    "UserInfo",
]
```

- [ ] **Step 6: Eseguire i test e verificare che passino**

Run: `pytest tests/api -v`
Expected: PASS, 37 test in totale

- [ ] **Step 7: Commit**

```bash
git add custom_components/switchbot_eink/api tests/api
git commit -m "feat(api): aggiungi modelli e facciata per dispositivi e template"
```

---

### Task 5: Sonda di diagnostica e misura sul campo

Questo task ha un output diverso dagli altri: oltre al codice, produce **tre misure sul dispositivo fisico** che condizionano i task successivi. Va eseguito con il pannello a portata di mano.

**Files:**
- Create: `tools/probe.py`
- Create: `docs/superpowers/notes/2026-08-22-refresh-cadence.md`
- Test: `tests/test_probe.py`

**Interfaces:**
- Consumes: da Task 1–4 — `CanvasAuth`, `SwitchBotCanvasClient`, `Template`.
- Produces: `build_clock_component(text: str, component_id: str = "1") -> dict`, riusata nei test del Task 7 come riferimento del wire format.

Le tre domande a cui rispondere:

1. **Cadenza di refresh.** Il pannello si aggiorna da solo? Ogni quanto? È il rischio principale della spec.
2. **Origine delle coordinate.** Un componente a `y = 0` finisce sul bordo fisico dello schermo o sotto la status bar?
3. **`dataMode` per i widget metric.** I default del renderer usano `dataMode: "weather"` per la famiglia Metric. Con `source: "custom"` il backend rispetta il `content` che inviamo, o lo sovrascrive con dati meteo? Se lo sovrascrive, va usato `dataMode: "text"`.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/test_probe.py`:

```python
"""Test del costruttore di componenti della sonda."""
from __future__ import annotations

import json

from tools.probe import build_clock_component


def test_build_clock_component_produce_css_ed_extra_come_stringhe() -> None:
    component = build_clock_component("12:34:56")

    assert isinstance(component["css"], str)
    assert isinstance(component["extra"], str)


def test_build_clock_component_ha_id_numerico_valido() -> None:
    component = build_clock_component("12:34:56")

    assert component["id"] == "1"
    assert component["id"].isdigit()


def test_build_clock_component_posiziona_in_alto_a_sinistra() -> None:
    css = json.loads(build_clock_component("12:34:56")["css"])

    assert css["x"] == 0
    assert css["y"] == 0
    assert css["w"] == 800


def test_build_clock_component_contiene_il_testo() -> None:
    extra = json.loads(build_clock_component("12:34:56")["extra"])

    assert extra["content"]["text"] == "12:34:56"
    assert extra["source"] == "custom"
    assert extra["dataMode"] == "text"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/test_probe.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'tools.probe'`

- [ ] **Step 3: Scrivere `tools/probe.py`**

```python
"""Sonda da riga di comando per il SwitchBot E-Ink Home Dashboard.

Serve a rispondere alle domande che non si possono risolvere leggendo il bundle
JavaScript: ogni quanto il pannello si aggiorna, dove cade l'origine delle
coordinate, e se il backend rispetta il content che inviamo.

Uso:
    export SWITCHBOT_USER=mario@example.test
    export SWITCHBOT_PASS=segreta
    export SWITCHBOT_REGION=eu

    python -m tools.probe devices
    python -m tools.probe clock --slot custom1
    python -m tools.probe origin --slot custom1
    python -m tools.probe metric --slot custom1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from typing import Any

import aiohttp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from custom_components.switchbot_eink.api.auth import CanvasAuth  # noqa: E402
from custom_components.switchbot_eink.api.client import SwitchBotCanvasClient  # noqa: E402
from custom_components.switchbot_eink.api.models import Template  # noqa: E402


def _wire(
    component_id: str,
    widget_type: str,
    name: str,
    css: dict[str, Any],
    extra: dict[str, Any],
) -> dict[str, str]:
    """Impacchetta un componente nel wire format: css ed extra sono stringhe JSON."""
    return {
        "id": component_id,
        "type": widget_type,
        "name": name,
        "css": json.dumps(css, separators=(",", ":")),
        "extra": json.dumps(extra, separators=(",", ":")),
    }


def build_clock_component(text: str, component_id: str = "1") -> dict[str, str]:
    """Un testo grande in alto a sinistra, per leggere l'orario da lontano."""
    return _wire(
        component_id,
        "text",
        "Sonda orologio",
        {"x": 0, "y": 0, "w": 800, "h": 80, "z": 1, "fontSize": 56, "align": "center"},
        {
            "dataMode": "text",
            "source": "custom",
            "refresh": "1h",
            "content": {"text": text},
            "locked": False,
            "visible": True,
        },
    )


def build_origin_components() -> list[dict[str, str]]:
    """Due barre agli estremi verticali, per capire dove cade y = 0.

    Se la barra superiore è visibile per intero, l'origine è sotto la status bar.
    Se è tagliata o nascosta, l'origine coincide con il bordo fisico.
    """
    return [
        _wire(
            "1",
            "text",
            "Bordo alto",
            {"x": 0, "y": 0, "w": 800, "h": 24, "z": 1, "fontSize": 20, "align": "center"},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {"text": "=== ALTO y=0 ==="},
                "locked": False,
                "visible": True,
            },
        ),
        _wire(
            "2",
            "text",
            "Bordo basso",
            {"x": 0, "y": 348, "w": 800, "h": 24, "z": 1, "fontSize": 20, "align": "center"},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {"text": "=== BASSO y=348 ==="},
                "locked": False,
                "visible": True,
            },
        ),
    ]


def build_metric_components() -> list[dict[str, str]]:
    """La stessa tile con due dataMode diversi, per vedere quale conserva il content."""
    base_css = {"w": 240, "h": 84, "z": 1}
    return [
        _wire(
            "1",
            "switchbotMeter",
            "Metric dataMode=text",
            {"x": 40, "y": 40, **base_css},
            {
                "dataMode": "text",
                "source": "custom",
                "refresh": "1h",
                "content": {
                    "icon": "thermo-humidity",
                    "label": "MODO TEXT",
                    "value": "42",
                    "unit": "X",
                },
                "locked": False,
                "visible": True,
            },
        ),
        _wire(
            "2",
            "switchbotMeter",
            "Metric dataMode=weather",
            {"x": 400, "y": 40, **base_css},
            {
                "dataMode": "weather",
                "source": "custom",
                "refresh": "1h",
                "content": {
                    "icon": "thermo-humidity",
                    "label": "MODO WEATHER",
                    "value": "99",
                    "unit": "Y",
                },
                "locked": False,
                "visible": True,
            },
        ),
    ]


async def _connect(session: aiohttp.ClientSession) -> tuple[SwitchBotCanvasClient, str]:
    username = os.environ["SWITCHBOT_USER"]
    password = os.environ["SWITCHBOT_PASS"]
    region = os.environ.get("SWITCHBOT_REGION", "eu")

    auth = CanvasAuth(session, region)
    tokens = await auth.login(username, password)
    info = await auth.user_info(tokens.access_token, tokens.token_type)
    client = SwitchBotCanvasClient(session, region, tokens, info.user_id)

    devices = await client.list_eink_devices()
    if not devices:
        raise SystemExit("Nessun pannello e-ink trovato sull'account")
    print(f"Pannello: {devices[0].device_name} ({devices[0].device_id})")
    return client, devices[0].device_id


async def _publish(
    client: SwitchBotCanvasClient,
    device_id: str,
    slot: str,
    name: str,
    components: list[dict[str, str]],
) -> None:
    """Riusa il template già presente sullo slot, altrimenti ne crea uno."""
    existing = [t for t in await client.list_templates(device_id) if t.page_slot == slot]
    template = Template(
        template_id=existing[0].template_id if existing else None,
        name=name,
        page_slot=slot,
        device_id=device_id,
        components=components,
    )
    if template.template_id is None:
        template.template_id = await client.create_template(template)
        print(f"Creato template {template.template_id} sullo slot {slot}")
    else:
        await client.update_template(template)
        print(f"Aggiornato template {template.template_id} sullo slot {slot}")

    await client.release(device_id)
    print("Pubblicato. Scorri fino alla pagina custom sul dispositivo.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Sonda per il pannello e-ink SwitchBot")
    parser.add_argument(
        "command", choices=["devices", "clock", "origin", "metric", "templates"]
    )
    parser.add_argument("--slot", default="custom1", help="custom1..custom4")
    args = parser.parse_args()

    async with aiohttp.ClientSession() as session:
        client, device_id = await _connect(session)

        if args.command == "devices":
            for device in await client.list_devices():
                print(f"  {device.device_id}  {device.device_type:<12} {device.device_name}")

        elif args.command == "templates":
            for summary in await client.list_templates(device_id):
                print(f"  {summary.template_id}  {summary.page_slot:<12} {summary.name}")

        elif args.command == "clock":
            now = datetime.now().strftime("%H:%M:%S")
            await _publish(
                client, device_id, args.slot, "Sonda orologio", [build_clock_component(now)]
            )
            print(f"Orario pubblicato: {now}")

        elif args.command == "origin":
            await _publish(
                client, device_id, args.slot, "Sonda origine", build_origin_components()
            )

        elif args.command == "metric":
            await _publish(
                client, device_id, args.slot, "Sonda metric", build_metric_components()
            )


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `pytest tests/test_probe.py -v`
Expected: PASS, 4 test

- [ ] **Step 5: Commit del codice della sonda**

```bash
git add tools/probe.py tests/test_probe.py
git commit -m "feat(tools): aggiungi sonda per la misura sul dispositivo"
```

- [ ] **Step 6: Misurare la cadenza di refresh**

```bash
export SWITCHBOT_USER=...  SWITCHBOT_PASS=...  SWITCHBOT_REGION=eu
python -m tools.probe clock --slot custom1
```

Sul dispositivo: scorrere fino alla pagina `custom1`, poi tenere premuto il pulsante 2 secondi per forzare il primo aggiornamento e annotare l'orario mostrato. Ripubblicare senza toccare il pulsante:

```bash
python -m tools.probe clock --slot custom1   # ripetere ogni 15 minuti
```

Annotare a che ora il pannello cambia da solo. Osservare per almeno 2 ore. Registrare: intervallo osservato, se il refresh avviene solo su pressione, e se cambia a batteria rispetto all'alimentazione USB-C.

- [ ] **Step 7: Misurare l'origine delle coordinate**

```bash
python -m tools.probe origin --slot custom1
```

Fotografare lo schermo. Annotare se la barra `y=0` è interamente visibile, tagliata, o coperta dalla status bar, e lo stesso per la barra `y=348`.

- [ ] **Step 8: Misurare il comportamento di `dataMode`**

```bash
python -m tools.probe metric --slot custom1
```

Annotare quale delle due tile mostra ancora `MODO TEXT` / `42` e `MODO WEATHER` / `99`. Se la tile con `dataMode: "weather"` mostra dati meteo al posto dei nostri, il Task 7 dovrà usare `dataMode: "text"` per tutte le tile.

- [ ] **Step 9: Scrivere le note e adeguare le costanti**

Creare `docs/superpowers/notes/2026-08-22-refresh-cadence.md` con le tre risposte, la data della misura e la versione firmware del pannello (visibile nell'app SwitchBot).

**Gate di decisione:** se il pannello si aggiorna **solo** alla pressione del pulsante, fermarsi e riportarlo. L'approccio va riconsiderato prima di costruire l'integrazione, perché una dashboard che richiede una pressione fisica per aggiornarsi non risolve il problema di partenza.

Altrimenti: annotare l'intervallo misurato, che diventa il default di `DEFAULT_UPDATE_INTERVAL` nel Task 11. Non ha senso ricompilare e pubblicare più spesso di quanto il pannello legga.

- [ ] **Step 10: Commit**

```bash
git add docs/superpowers/notes/2026-08-22-refresh-cadence.md
git commit -m "docs: registra le misure di refresh, origine e dataMode sul dispositivo"
```

---

### Task 6: Geometria del canvas e griglia

**Files:**
- Create: `custom_components/switchbot_eink/layout/const.py`
- Create: `custom_components/switchbot_eink/layout/grid.py`
- Test: `tests/layout/test_grid.py`

**Interfaces:**
- Consumes: niente dagli altri task; lo strato `layout` non importa da `api`.
- Produces: costanti `CANVAS_WIDTH = 800`, `CANVAS_HEIGHT = 480`, `SAFE_TOP = 64`, `SAFE_BOTTOM = 44`, `USABLE_WIDTH = 800`, `USABLE_HEIGHT = 372`, `GRID_COLS = 12`, `GRID_ROWS = 6`, `DEFAULT_GUTTER = 8`; dataclass `Rect(x: int, y: int, w: int, h: int)`; `grid_to_rect(col, row, span_w, span_h, gutter=DEFAULT_GUTTER) -> Rect`; `rect_fits(rect: Rect) -> bool`; `rects_overlap(a: Rect, b: Rect) -> bool`.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/layout/test_grid.py`:

```python
"""Test della griglia."""
from __future__ import annotations

import pytest

from custom_components.switchbot_eink.layout.const import USABLE_HEIGHT, USABLE_WIDTH
from custom_components.switchbot_eink.layout.grid import (
    Rect,
    grid_to_rect,
    rect_fits,
    rects_overlap,
)


def test_prima_cella_parte_dall_origine() -> None:
    rect = grid_to_rect(0, 0, 1, 1)

    assert rect.x == 0
    assert rect.y == 0


def test_span_completo_riempie_l_area_utile() -> None:
    rect = grid_to_rect(0, 0, 12, 6)

    assert rect.w == USABLE_WIDTH
    assert rect.h == USABLE_HEIGHT


def test_tre_colonne_larghe_194_pixel() -> None:
    assert grid_to_rect(0, 0, 3, 1).w == 194


def test_la_quarta_colonna_inizia_dopo_la_gutter() -> None:
    prima = grid_to_rect(0, 0, 3, 1)
    seconda = grid_to_rect(3, 0, 3, 1)

    assert seconda.x == prima.x + prima.w + 8


def test_la_seconda_riga_inizia_dopo_la_gutter() -> None:
    prima = grid_to_rect(0, 0, 1, 1)
    seconda = grid_to_rect(0, 1, 1, 1)

    assert seconda.y == prima.y + prima.h + 8


def test_colonna_fuori_griglia_solleva() -> None:
    with pytest.raises(ValueError, match="colonna"):
        grid_to_rect(12, 0, 1, 1)


def test_span_che_esce_dalla_griglia_solleva() -> None:
    with pytest.raises(ValueError, match="larghezza"):
        grid_to_rect(10, 0, 3, 1)


def test_span_nullo_solleva() -> None:
    with pytest.raises(ValueError, match="almeno 1"):
        grid_to_rect(0, 0, 0, 1)


def test_rect_dentro_l_area_utile_ci_sta() -> None:
    assert rect_fits(Rect(0, 0, 800, 372)) is True


def test_rect_che_sborda_a_destra_non_ci_sta() -> None:
    assert rect_fits(Rect(700, 0, 200, 50)) is False


def test_rect_con_coordinate_negative_non_ci_sta() -> None:
    assert rect_fits(Rect(-1, 0, 100, 50)) is False


def test_rect_adiacenti_non_si_sovrappongono() -> None:
    assert rects_overlap(Rect(0, 0, 100, 50), Rect(100, 0, 100, 50)) is False


def test_rect_incrociati_si_sovrappongono() -> None:
    assert rects_overlap(Rect(0, 0, 100, 50), Rect(50, 20, 100, 50)) is True
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/layout/test_grid.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.layout.const'`

- [ ] **Step 3: Scrivere `layout/const.py`**

```python
"""Geometria del pannello e inventario dei widget.

I valori vengono dal renderer dell'editor web: il pannello `eink-7in3` è
800×480 con una status bar di 64px in alto e 44px in basso.
"""
from __future__ import annotations

from typing import Final

CANVAS_WIDTH: Final = 800
CANVAS_HEIGHT: Final = 480
SAFE_TOP: Final = 64
SAFE_BOTTOM: Final = 44

USABLE_WIDTH: Final = CANVAS_WIDTH
USABLE_HEIGHT: Final = CANVAS_HEIGHT - SAFE_TOP - SAFE_BOTTOM  # 372

GRID_COLS: Final = 12
GRID_ROWS: Final = 6
DEFAULT_GUTTER: Final = 8

# I 19 tipi della famiglia Metric: icona, etichetta, valore, unità.
# I quattro campi sono stringhe libere, quindi sono tile generiche.
METRIC_TYPES: Final[tuple[str, ...]] = (
    "sunTimes",
    "moonPhase",
    "wind",
    "pressure",
    "rainChance",
    "uvIndex",
    "airQuality",
    "visibility",
    "tempRange",
    "aqiValue",
    "pm25",
    "pollen",
    "precipitation",
    "switchbotMeter",
    "switchbotTemperature",
    "feelsLike",
    "switchbotComfort",
    "relativeHumidity",
    "absoluteHumidity",
)

# Tipo usato per le tile generiche quando l'utente non ne sceglie uno.
DEFAULT_METRIC_TYPE: Final = "switchbotMeter"

# Icone note al renderer, utilizzabili in content.icon.
KNOWN_ICONS: Final[tuple[str, ...]] = (
    "sun-times",
    "sun",
    "moon",
    "wind",
    "gauge",
    "rain-chance",
    "uv",
    "air-quality",
    "eye",
    "aqi",
    "temp-range",
    "humidity-drop",
    "thermo-humidity",
)

# Stili ammessi per tipo. Se un tipo non compare qui, passa l'intero style.
STYLE_WHITELIST: Final[dict[str, tuple[str, ...]]] = {
    "text": ("fontSize", "fontWeight", "align", "rotation"),
    "divider": ("rotation",),
    "decorFrame": ("borderWidth", "rotation"),
    "weekday": ("fontSize", "rotation"),
    "dateOnly": ("fontSize", "rotation"),
    "yearOnly": ("fontSize", "rotation"),
    "address": ("fontSize", "rotation"),
    "newsDetail": ("titleFontSize", "bodyFontSize", "rotation"),
    "hackerNewsShowDetail": ("titleFontSize", "bodyFontSize", "rotation"),
    "hackerNewsTopDetail": ("titleFontSize", "bodyFontSize", "rotation"),
}

STYLE_DEFAULTS: Final[dict[str, dict[str, object]]] = {
    "weekday": {"fontSize": 16},
    "dateOnly": {"fontSize": 16},
    "yearOnly": {"fontSize": 16},
    "address": {"fontSize": 16},
}

_METRIC_CONTENT_KEYS: Final[tuple[str, ...]] = ("icon", "label", "value", "unit")

# Chiavi di content ammesse per tipo. relativeHumidity e absoluteHumidity non
# compaiono nella whitelist del client web pur essendo tile Metric: per loro
# passa l'intero content, ed è il comportamento che replichiamo.
CONTENT_WHITELIST: Final[dict[str, tuple[str, ...]]] = {
    **{
        widget_type: _METRIC_CONTENT_KEYS
        for widget_type in METRIC_TYPES
        if widget_type not in ("relativeHumidity", "absoluteHumidity")
    },
    "calendarEventCount": ("title", "unit"),
    "calendarNextEvent": ("title", "text", "unit"),
    "calendarBusyTime": ("title", "text"),
    "calendarWeekStrip": ("unit",),
}

# Colori ammessi dal renderer: il pannello è a 4 livelli di grigio.
COLORS: Final[tuple[str, ...]] = ("black", "white", "gray", "transparent")

MAX_COMPONENT_ID: Final = 2147483647
```

- [ ] **Step 4: Scrivere `layout/grid.py`**

```python
"""Griglia 12×6 sull'area utile del pannello."""
from __future__ import annotations

from dataclasses import dataclass

from .const import (
    DEFAULT_GUTTER,
    GRID_COLS,
    GRID_ROWS,
    USABLE_HEIGHT,
    USABLE_WIDTH,
)


@dataclass(frozen=True, slots=True)
class Rect:
    """Un rettangolo in pixel sull'area utile."""

    x: int
    y: int
    w: int
    h: int


def grid_to_rect(
    col: int, row: int, span_w: int, span_h: int, gutter: int = DEFAULT_GUTTER
) -> Rect:
    """Converte una posizione di griglia in pixel.

    Le celle hanno dimensione frazionaria; arrotondiamo solo alla fine così che
    span adiacenti restino allineati e uno span pieno copra esattamente l'area.
    """
    if span_w < 1 or span_h < 1:
        raise ValueError("span_w e span_h devono valere almeno 1")
    if not 0 <= col < GRID_COLS:
        raise ValueError(f"colonna {col} fuori dalla griglia a {GRID_COLS} colonne")
    if not 0 <= row < GRID_ROWS:
        raise ValueError(f"riga {row} fuori dalla griglia a {GRID_ROWS} righe")
    if col + span_w > GRID_COLS:
        raise ValueError(f"larghezza {span_w} da colonna {col} esce dalla griglia")
    if row + span_h > GRID_ROWS:
        raise ValueError(f"altezza {span_h} da riga {row} esce dalla griglia")

    cell_w = (USABLE_WIDTH - gutter * (GRID_COLS - 1)) / GRID_COLS
    cell_h = (USABLE_HEIGHT - gutter * (GRID_ROWS - 1)) / GRID_ROWS

    return Rect(
        x=round(col * (cell_w + gutter)),
        y=round(row * (cell_h + gutter)),
        w=round(span_w * cell_w + (span_w - 1) * gutter),
        h=round(span_h * cell_h + (span_h - 1) * gutter),
    )


def rect_fits(rect: Rect) -> bool:
    """Vero se il rettangolo sta interamente dentro l'area utile."""
    return (
        rect.x >= 0
        and rect.y >= 0
        and rect.w > 0
        and rect.h > 0
        and rect.x + rect.w <= USABLE_WIDTH
        and rect.y + rect.h <= USABLE_HEIGHT
    )


def rects_overlap(a: Rect, b: Rect) -> bool:
    """Vero se i due rettangoli si intersecano. Il contatto sul bordo non conta."""
    return not (
        a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y
    )
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

Run: `pytest tests/layout/test_grid.py -v`
Expected: PASS, 13 test

- [ ] **Step 6: Commit**

```bash
git add custom_components/switchbot_eink/layout tests/layout/test_grid.py
git commit -m "feat(layout): aggiungi geometria del canvas e griglia 12x6"
```

---

### Task 7: Serializzazione dei componenti nel wire format

**Files:**
- Create: `custom_components/switchbot_eink/layout/widgets.py`
- Test: `tests/layout/test_widgets.py`

**Interfaces:**
- Consumes: da Task 6 — `Rect`, `STYLE_WHITELIST`, `STYLE_DEFAULTS`, `CONTENT_WHITELIST`, `MAX_COMPONENT_ID`.
- Produces: `to_wire(component_id: str, widget_type: str, name: str, rect: Rect, content: dict, style: dict | None = None, data_mode: str = "text", z: int = 1) -> dict[str, str]` e `validate_component_id(component_id: str) -> str`.

Se la misura del Task 5 avesse mostrato che `dataMode: "weather"` sovrascrive il `content`, il default `data_mode="text"` è già quello giusto e non serve cambiare nulla.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/layout/test_widgets.py`:

```python
"""Test della serializzazione nel wire format."""
from __future__ import annotations

import json

import pytest

from custom_components.switchbot_eink.layout.grid import Rect
from custom_components.switchbot_eink.layout.widgets import to_wire, validate_component_id

RECT = Rect(10, 20, 200, 80)


def test_css_ed_extra_sono_stringhe_json() -> None:
    wire = to_wire("1", "text", "Titolo", RECT, {"text": "ciao"})

    assert isinstance(wire["css"], str)
    assert isinstance(wire["extra"], str)
    json.loads(wire["css"])
    json.loads(wire["extra"])


def test_css_contiene_la_geometria() -> None:
    css = json.loads(to_wire("1", "text", "Titolo", RECT, {"text": "ciao"})["css"])

    assert css["x"] == 10
    assert css["y"] == 20
    assert css["w"] == 200
    assert css["h"] == 80
    assert css["z"] == 1


def test_extra_contiene_data_content_e_flag() -> None:
    extra = json.loads(to_wire("1", "text", "Titolo", RECT, {"text": "ciao"})["extra"])

    assert extra["dataMode"] == "text"
    assert extra["source"] == "custom"
    assert extra["refresh"] == "1h"
    assert extra["content"] == {"text": "ciao"}
    assert extra["locked"] is False
    assert extra["visible"] is True


def test_lo_stile_di_text_e_filtrato_dalla_whitelist() -> None:
    css = json.loads(
        to_wire(
            "1",
            "text",
            "Titolo",
            RECT,
            {"text": "ciao"},
            style={"fontSize": 24, "padding": 12, "radius": 4},
        )["css"]
    )

    assert css["fontSize"] == 24
    assert "padding" not in css, "padding non è nella whitelist di text"
    assert "radius" not in css


def test_un_tipo_senza_whitelist_conserva_tutto_lo_stile() -> None:
    css = json.loads(
        to_wire(
            "1",
            "switchbotMeter",
            "Tile",
            RECT,
            {"label": "Salotto", "value": "21", "unit": "°C"},
            style={"padding": 12, "iconSize": 48},
        )["css"]
    )

    assert css["padding"] == 12
    assert css["iconSize"] == 48


def test_i_default_di_stile_si_applicano_prima_della_whitelist() -> None:
    css = json.loads(to_wire("1", "weekday", "Giorno", RECT, {})["css"])

    assert css["fontSize"] == 16


def test_lo_stile_esplicito_vince_sul_default() -> None:
    css = json.loads(to_wire("1", "weekday", "Giorno", RECT, {}, style={"fontSize": 32})["css"])

    assert css["fontSize"] == 32


def test_il_content_delle_tile_metric_e_filtrato() -> None:
    extra = json.loads(
        to_wire(
            "1",
            "switchbotMeter",
            "Tile",
            RECT,
            {"icon": "gauge", "label": "L", "value": "V", "unit": "U", "extraneo": "x"},
        )["extra"]
    )

    assert extra["content"] == {"icon": "gauge", "label": "L", "value": "V", "unit": "U"}


def test_il_content_filtrato_omette_le_chiavi_assenti() -> None:
    extra = json.loads(
        to_wire("1", "switchbotMeter", "Tile", RECT, {"label": "L", "value": "V"})["extra"]
    )

    assert extra["content"] == {"label": "L", "value": "V"}


def test_data_mode_e_configurabile() -> None:
    extra = json.loads(
        to_wire("1", "text", "T", RECT, {"text": "x"}, data_mode="clock")["extra"]
    )

    assert extra["dataMode"] == "clock"


def test_id_numerico_valido_passa() -> None:
    assert validate_component_id("42") == "42"


def test_id_non_numerico_solleva() -> None:
    with pytest.raises(ValueError, match="intero positivo"):
        validate_component_id("a1b2-uuid")


def test_id_zero_solleva() -> None:
    with pytest.raises(ValueError, match="intero positivo"):
        validate_component_id("0")


def test_id_oltre_il_massimo_solleva() -> None:
    with pytest.raises(ValueError, match="2147483647"):
        validate_component_id("2147483648")


def test_to_wire_rifiuta_un_id_non_valido() -> None:
    with pytest.raises(ValueError):
        to_wire("uuid-non-valido", "text", "T", RECT, {"text": "x"})
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/layout/test_widgets.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.layout.widgets'`

- [ ] **Step 3: Scrivere `layout/widgets.py`**

```python
"""Serializzazione di un componente nel wire format del backend.

Due dettagli che è facile sbagliare e che il backend non perdona:
`css` ed `extra` viaggiano come stringhe JSON, e l'`id` deve essere una stringa
che rappresenta un intero positivo, altrimenti collassa a "0" e tutti i
componenti si sovrascrivono a vicenda.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .const import (
    CONTENT_WHITELIST,
    MAX_COMPONENT_ID,
    STYLE_DEFAULTS,
    STYLE_WHITELIST,
)
from .grid import Rect

_NUMERIC_ID = re.compile(r"^[1-9]\d*$")


def validate_component_id(component_id: str) -> str:
    """Verifica che l'id sia accettabile per il backend."""
    if not _NUMERIC_ID.match(component_id):
        raise ValueError(
            f"id componente {component_id!r}: serve un intero positivo come stringa"
        )
    if int(component_id) > MAX_COMPONENT_ID:
        raise ValueError(f"id componente {component_id!r}: supera {MAX_COMPONENT_ID}")
    return component_id


def _filter_style(widget_type: str, style: dict[str, Any]) -> dict[str, Any]:
    merged = {**STYLE_DEFAULTS.get(widget_type, {}), **style}
    allowed = STYLE_WHITELIST.get(widget_type)
    if allowed is None:
        return merged
    return {key: merged[key] for key in allowed if key in merged}


def _filter_content(widget_type: str, content: dict[str, Any]) -> dict[str, Any]:
    allowed = CONTENT_WHITELIST.get(widget_type)
    if allowed is None:
        return dict(content)
    return {key: content[key] for key in allowed if key in content}


def to_wire(
    component_id: str,
    widget_type: str,
    name: str,
    rect: Rect,
    content: dict[str, Any],
    style: dict[str, Any] | None = None,
    data_mode: str = "text",
    z: int = 1,
) -> dict[str, str]:
    """Produce il componente pronto da inserire in `Template.components`."""
    validate_component_id(component_id)

    css: dict[str, Any] = {
        "x": rect.x,
        "y": rect.y,
        "w": rect.w,
        "h": rect.h,
        "z": z,
        **_filter_style(widget_type, style or {}),
    }

    extra: dict[str, Any] = {
        "dataMode": data_mode,
        "source": "custom",
        "refresh": "1h",
        "content": _filter_content(widget_type, content),
        "locked": False,
        "visible": True,
    }

    return {
        "id": component_id,
        "type": widget_type,
        "name": name,
        "css": json.dumps(css, separators=(",", ":"), ensure_ascii=False),
        "extra": json.dumps(extra, separators=(",", ":"), ensure_ascii=False),
    }
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `pytest tests/layout/test_widgets.py -v`
Expected: PASS, 14 test

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_eink/layout/widgets.py tests/layout/test_widgets.py
git commit -m "feat(layout): serializza i componenti nel wire format"
```

---

### Task 8: Schema della definizione YAML

**Files:**
- Create: `custom_components/switchbot_eink/layout/schema.py`
- Test: `tests/layout/test_schema.py`

**Interfaces:**
- Consumes: da Task 6 — `GRID_COLS`, `GRID_ROWS`, `METRIC_TYPES`, `KNOWN_ICONS`, `COLORS`.
- Produces: `PAGE_SCHEMA` (voluptuous), `CARD_TYPES = ("metric", "text", "divider", "frame", "image")`, e `validate_page(raw: dict) -> dict` che normalizza e solleva `vol.Invalid`.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/layout/test_schema.py`:

```python
"""Test della validazione della definizione YAML."""
from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.switchbot_eink.layout.schema import validate_page


def test_pagina_minima_valida() -> None:
    page = validate_page(
        {"page": "custom1", "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}]}
    )

    assert page["page"] == "custom1"
    assert page["cards"][0]["type"] == "text"


def test_il_nome_ha_un_default() -> None:
    page = validate_page(
        {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [0, 0, 1, 1]}]}
    )

    assert page["name"] == "Home Assistant"


def test_slot_non_valido_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page({"page": "custom9", "cards": []})


def test_card_metric_richiede_entity_o_value() -> None:
    with pytest.raises(vol.Invalid, match="entity"):
        validate_page(
            {"page": "custom1", "cards": [{"type": "metric", "grid": [0, 0, 3, 1]}]}
        )


def test_card_metric_con_entity_valida() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "label": "Salotto",
                    "icon": "temp-range",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert page["cards"][0]["entity"] == "sensor.salotto_temperatura"


def test_card_metric_con_value_esplicito_valida() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {"type": "metric", "value": "{{ 1 + 1 }}", "label": "L", "grid": [0, 0, 3, 1]}
            ],
        }
    )

    assert page["cards"][0]["value"] == "{{ 1 + 1 }}"


def test_grid_e_position_insieme_rifiutati() -> None:
    with pytest.raises(vol.Invalid, match="grid.*position|position.*grid"):
        validate_page(
            {
                "page": "custom1",
                "cards": [
                    {
                        "type": "text",
                        "text": "x",
                        "grid": [0, 0, 1, 1],
                        "position": [0, 0, 100, 50],
                    }
                ],
            }
        )


def test_card_senza_grid_ne_position_rifiutata() -> None:
    with pytest.raises(vol.Invalid, match="grid|position"):
        validate_page({"page": "custom1", "cards": [{"type": "text", "text": "x"}]})


def test_grid_con_quattro_interi_richiesta() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [0, 0, 1]}]}
        )


def test_colonna_oltre_la_griglia_rifiutata() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom1", "cards": [{"type": "text", "text": "x", "grid": [12, 0, 1, 1]}]}
        )


def test_tipo_di_card_sconosciuto_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {"page": "custom1", "cards": [{"type": "grafico", "grid": [0, 0, 1, 1]}]}
        )


def test_colore_non_supportato_rifiutato() -> None:
    with pytest.raises(vol.Invalid):
        validate_page(
            {
                "page": "custom1",
                "cards": [
                    {
                        "type": "text",
                        "text": "x",
                        "grid": [0, 0, 1, 1],
                        "style": {"textColor": "rosso"},
                    }
                ],
            }
        )


def test_widget_metric_esplicito_accettato() -> None:
    page = validate_page(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "widget": "pressure",
                    "value": "1013",
                    "label": "Pressione",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert page["cards"][0]["widget"] == "pressure"
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/layout/test_schema.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.layout.schema'`

- [ ] **Step 3: Scrivere `layout/schema.py`**

```python
"""Validazione della definizione dichiarativa della dashboard."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from .const import COLORS, DEFAULT_METRIC_TYPE, GRID_COLS, GRID_ROWS, METRIC_TYPES

CARD_TYPES: tuple[str, ...] = ("metric", "text", "divider", "frame", "image")
PAGE_SLOTS: tuple[str, ...] = ("custom1", "custom2", "custom3", "custom4")

DEFAULT_PAGE_NAME = "Home Assistant"


def _grid_tuple(value: Any) -> list[int]:
    """Valida [colonna, riga, larghezza, altezza] contro i limiti della griglia."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise vol.Invalid("grid deve essere [colonna, riga, larghezza, altezza]")
    col, row, span_w, span_h = (int(item) for item in value)
    if not 0 <= col < GRID_COLS:
        raise vol.Invalid(f"colonna {col} fuori dalle {GRID_COLS} colonne")
    if not 0 <= row < GRID_ROWS:
        raise vol.Invalid(f"riga {row} fuori dalle {GRID_ROWS} righe")
    if span_w < 1 or col + span_w > GRID_COLS:
        raise vol.Invalid(f"larghezza {span_w} da colonna {col} esce dalla griglia")
    if span_h < 1 or row + span_h > GRID_ROWS:
        raise vol.Invalid(f"altezza {span_h} da riga {row} esce dalla griglia")
    return [col, row, span_w, span_h]


def _position_tuple(value: Any) -> list[int]:
    """Valida [x, y, w, h] in pixel."""
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise vol.Invalid("position deve essere [x, y, larghezza, altezza] in pixel")
    return [int(item) for item in value]


STYLE_SCHEMA = vol.Schema(
    {
        vol.Optional("fontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("fontWeight"): vol.All(int, vol.Range(min=100, max=900)),
        vol.Optional("align"): vol.In(("left", "center", "right")),
        vol.Optional("rotation"): vol.All(int, vol.Range(min=0, max=359)),
        vol.Optional("padding"): vol.All(int, vol.Range(min=0, max=64)),
        vol.Optional("radius"): vol.All(int, vol.Range(min=0, max=64)),
        vol.Optional("borderWidth"): vol.All(int, vol.Range(min=0, max=16)),
        vol.Optional("iconSize"): vol.In((16, 24, 32, 48, 64, 96)),
        vol.Optional("numberFontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("labelFontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("unitFontSize"): vol.All(int, vol.Range(min=8, max=200)),
        vol.Optional("textColor"): vol.In(COLORS),
        vol.Optional("backgroundColor"): vol.In(COLORS),
        vol.Optional("borderColor"): vol.In(COLORS),
        vol.Optional("fit"): vol.In(("contain", "cover")),
    }
)

CARD_SCHEMA = vol.Schema(
    {
        vol.Required("type"): vol.In(CARD_TYPES),
        vol.Optional("grid"): _grid_tuple,
        vol.Optional("position"): _position_tuple,
        vol.Optional("style", default=dict): STYLE_SCHEMA,
        vol.Optional("z", default=1): int,
        # metric
        vol.Optional("widget", default=DEFAULT_METRIC_TYPE): vol.In(METRIC_TYPES),
        vol.Optional("entity"): str,
        vol.Optional("icon"): str,
        vol.Optional("label"): str,
        vol.Optional("value"): str,
        vol.Optional("unit"): str,
        # text
        vol.Optional("text"): str,
        # image
        vol.Optional("src"): str,
        vol.Optional("alt"): str,
    }
)

PAGE_SCHEMA = vol.Schema(
    {
        vol.Required("page"): vol.In(PAGE_SLOTS),
        vol.Optional("name", default=DEFAULT_PAGE_NAME): str,
        vol.Required("cards"): [CARD_SCHEMA],
    }
)


def _check_card_invariants(card: dict[str, Any], index: int) -> None:
    has_grid = "grid" in card
    has_position = "position" in card

    if has_grid and has_position:
        raise vol.Invalid(f"card {index}: grid e position sono mutuamente esclusivi")
    if not has_grid and not has_position:
        raise vol.Invalid(f"card {index}: serve grid oppure position")

    if card["type"] == "metric" and "entity" not in card and "value" not in card:
        raise vol.Invalid(f"card {index}: una metric richiede entity oppure value")
    if card["type"] == "text" and "text" not in card:
        raise vol.Invalid(f"card {index}: una text richiede il campo text")
    if card["type"] == "image" and "src" not in card:
        raise vol.Invalid(f"card {index}: una image richiede il campo src")


def validate_page(raw: dict[str, Any]) -> dict[str, Any]:
    """Valida e normalizza la definizione di una pagina."""
    page: dict[str, Any] = PAGE_SCHEMA(raw)
    for index, card in enumerate(page["cards"]):
        _check_card_invariants(card, index)
    return page
```

- [ ] **Step 4: Eseguire i test e verificare che passino**

Run: `pytest tests/layout/test_schema.py -v`
Expected: PASS, 13 test

- [ ] **Step 5: Commit**

```bash
git add custom_components/switchbot_eink/layout/schema.py tests/layout/test_schema.py
git commit -m "feat(layout): valida la definizione dichiarativa della pagina"
```

---

### Task 9: Compilatore della pagina

**Files:**
- Create: `custom_components/switchbot_eink/layout/compile.py`
- Modify: `custom_components/switchbot_eink/layout/__init__.py`
- Test: `tests/layout/test_compile.py`

**Interfaces:**
- Consumes: da Task 6 — `Rect`, `grid_to_rect`, `rect_fits`, `rects_overlap`, `DEFAULT_METRIC_TYPE`; da Task 7 — `to_wire`; da Task 8 — `validate_page`.
- Produces:
  - `LayoutError(Exception)`
  - `EntityValue(state: str, unit: str | None)`
  - `compile_page(page: dict, render: Renderer, resolve: EntityResolver) -> list[dict[str, str]]` dove `Renderer = Callable[[str], str]` e `EntityResolver = Callable[[str], EntityValue | None]`
  - `components_hash(components: list[dict[str, str]]) -> str`

Le due callback tengono il compilatore libero da Home Assistant: chi lo chiama passa il renderer Jinja e il lettore di stati. Nei test sono lambda.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/layout/test_compile.py`:

```python
"""Test del compilatore."""
from __future__ import annotations

import json

import pytest

from custom_components.switchbot_eink.layout.compile import (
    EntityValue,
    LayoutError,
    compile_page,
    components_hash,
)
from custom_components.switchbot_eink.layout.schema import validate_page

STATI = {
    "sensor.salotto_temperatura": EntityValue("21.4", "°C"),
    "sensor.lavatrice": EntityValue("in funzione", None),
}


def render_identita(template: str) -> str:
    return template


def risolvi(entity_id: str) -> EntityValue | None:
    return STATI.get(entity_id)


def compila(raw: dict) -> list[dict[str, str]]:
    return compile_page(validate_page(raw), render_identita, risolvi)


def test_una_card_text_produce_un_componente() -> None:
    componenti = compila(
        {"page": "custom1", "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}]}
    )

    assert len(componenti) == 1
    assert componenti[0]["type"] == "text"
    assert json.loads(componenti[0]["extra"])["content"]["text"] == "ciao"


def test_gli_id_sono_numerici_progressivi_e_unici() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "text", "text": "a", "grid": [0, 0, 4, 1]},
                {"type": "text", "text": "b", "grid": [0, 1, 4, 1]},
                {"type": "text", "text": "c", "grid": [0, 2, 4, 1]},
            ],
        }
    )

    assert [c["id"] for c in componenti] == ["1", "2", "3"]


def test_una_metric_con_entity_prende_stato_e_unita() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "label": "Salotto",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    content = json.loads(componenti[0]["extra"])["content"]
    assert content["value"] == "21.4"
    assert content["unit"] == "°C"
    assert content["label"] == "Salotto"


def test_un_value_esplicito_vince_sullo_stato_dell_entita() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "value": "99",
                    "label": "L",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert json.loads(componenti[0]["extra"])["content"]["value"] == "99"


def test_un_unit_esplicito_vince_su_quella_dell_entita() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto_temperatura",
                    "unit": "gradi",
                    "label": "L",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )

    assert json.loads(componenti[0]["extra"])["content"]["unit"] == "gradi"


def test_entita_sconosciuta_mostra_un_trattino() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "metric", "entity": "sensor.inesistente", "label": "L",
                 "grid": [0, 0, 3, 1]}
            ],
        }
    )

    assert json.loads(componenti[0]["extra"])["content"]["value"] == "—"


def test_il_widget_predefinito_di_una_metric_e_switchbot_meter() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [{"type": "metric", "value": "1", "label": "L", "grid": [0, 0, 3, 1]}],
        }
    )

    assert componenti[0]["type"] == "switchbotMeter"


def test_i_campi_testuali_passano_dal_renderer() -> None:
    chiamate: list[str] = []

    def render_tracciante(template: str) -> str:
        chiamate.append(template)
        return template.upper()

    componenti = compile_page(
        validate_page(
            {
                "page": "custom1",
                "cards": [{"type": "text", "text": "ciao {{ x }}", "grid": [0, 0, 4, 1]}],
            }
        ),
        render_tracciante,
        risolvi,
    )

    assert chiamate == ["ciao {{ x }}"]
    assert json.loads(componenti[0]["extra"])["content"]["text"] == "CIAO {{ X }}"


def test_position_in_pixel_usata_cosi_com_e() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [{"type": "text", "text": "x", "position": [100, 50, 300, 40]}],
        }
    )

    css = json.loads(componenti[0]["css"])
    assert (css["x"], css["y"], css["w"], css["h"]) == (100, 50, 300, 40)


def test_position_fuori_dall_area_utile_solleva() -> None:
    with pytest.raises(LayoutError, match="esce dall'area utile"):
        compila(
            {
                "page": "custom1",
                "cards": [{"type": "text", "text": "x", "position": [700, 0, 200, 40]}],
            }
        )


def test_card_sovrapposte_sollevano() -> None:
    with pytest.raises(LayoutError, match="si sovrappongono"):
        compila(
            {
                "page": "custom1",
                "cards": [
                    {"type": "text", "text": "a", "position": [0, 0, 200, 100]},
                    {"type": "text", "text": "b", "position": [100, 50, 200, 100]},
                ],
            }
        )


def test_card_adiacenti_non_sollevano() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "text", "text": "a", "position": [0, 0, 200, 100]},
                {"type": "text", "text": "b", "position": [200, 0, 200, 100]},
            ],
        }
    )

    assert len(componenti) == 2


def test_divider_e_frame_non_hanno_content() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "divider", "grid": [0, 0, 12, 1]},
                {"type": "frame", "grid": [0, 1, 6, 2]},
            ],
        }
    )

    assert componenti[0]["type"] == "divider"
    assert componenti[1]["type"] == "decorFrame"
    assert json.loads(componenti[0]["extra"])["content"] == {}


def test_image_porta_src_e_alt() -> None:
    componenti = compila(
        {
            "page": "custom1",
            "cards": [
                {"type": "image", "src": "https://esempio.test/a.png", "alt": "grafico",
                 "grid": [0, 0, 6, 3]}
            ],
        }
    )

    content = json.loads(componenti[0]["extra"])["content"]
    assert content["src"] == "https://esempio.test/a.png"
    assert content["alt"] == "grafico"


def test_hash_stabile_a_parita_di_componenti() -> None:
    definizione = {
        "page": "custom1",
        "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}],
    }

    assert components_hash(compila(definizione)) == components_hash(compila(definizione))


def test_hash_diverso_se_il_contenuto_cambia() -> None:
    uno = compila(
        {"page": "custom1", "cards": [{"type": "text", "text": "a", "grid": [0, 0, 4, 1]}]}
    )
    due = compila(
        {"page": "custom1", "cards": [{"type": "text", "text": "b", "grid": [0, 0, 4, 1]}]}
    )

    assert components_hash(uno) != components_hash(due)
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/layout/test_compile.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.layout.compile'`

- [ ] **Step 3: Scrivere `layout/compile.py`**

```python
"""Compila una definizione di pagina in componenti wire format.

Funzione pura: il rendering dei template e la lettura degli stati arrivano da
due callback, così questo modulo non dipende da Home Assistant e si testa senza.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .grid import Rect, grid_to_rect, rect_fits, rects_overlap
from .widgets import to_wire

VALORE_ASSENTE = "—"

# Mappa dai tipi di card astratti ai tipi di widget del renderer.
_WIDGET_BY_CARD_TYPE: dict[str, str] = {
    "text": "text",
    "divider": "divider",
    "frame": "decorFrame",
    "image": "image",
}


class LayoutError(Exception):
    """La definizione è sintatticamente valida ma non produce un canvas sensato."""


@dataclass(frozen=True, slots=True)
class EntityValue:
    """Stato di un'entità, già in forma di stringa."""

    state: str
    unit: str | None


Renderer = Callable[[str], str]
EntityResolver = Callable[[str], EntityValue | None]


def _rect_for(card: dict[str, Any]) -> Rect:
    if "grid" in card:
        col, row, span_w, span_h = card["grid"]
        return grid_to_rect(col, row, span_w, span_h)
    x, y, w, h = card["position"]
    return Rect(x, y, w, h)


def _content_for(
    card: dict[str, Any], render: Renderer, resolve: EntityResolver
) -> dict[str, Any]:
    card_type = card["type"]

    if card_type in ("divider", "frame"):
        return {}

    if card_type == "image":
        content = {"src": render(card["src"])}
        if "alt" in card:
            content["alt"] = render(card["alt"])
        return content

    if card_type == "text":
        return {"text": render(card["text"])}

    # metric
    entity_value = resolve(card["entity"]) if "entity" in card else None

    if "value" in card:
        value = render(card["value"])
    elif entity_value is not None:
        value = entity_value.state
    else:
        value = VALORE_ASSENTE

    content: dict[str, Any] = {"value": value}

    if "label" in card:
        content["label"] = render(card["label"])
    if "icon" in card:
        content["icon"] = card["icon"]

    if "unit" in card:
        content["unit"] = render(card["unit"])
    elif entity_value is not None and entity_value.unit:
        content["unit"] = entity_value.unit

    return content


def _widget_type_for(card: dict[str, Any]) -> str:
    if card["type"] == "metric":
        return card["widget"]
    return _WIDGET_BY_CARD_TYPE[card["type"]]


def compile_page(
    page: dict[str, Any], render: Renderer, resolve: EntityResolver
) -> list[dict[str, str]]:
    """Trasforma una pagina validata nella lista di componenti da inviare."""
    componenti: list[dict[str, str]] = []
    rettangoli: list[tuple[int, Rect]] = []

    for index, card in enumerate(page["cards"]):
        try:
            rect = _rect_for(card)
        except ValueError as err:
            raise LayoutError(f"card {index}: {err}") from err

        if not rect_fits(rect):
            raise LayoutError(
                f"card {index}: il rettangolo {rect} esce dall'area utile 800x372"
            )

        for altro_index, altro_rect in rettangoli:
            if rects_overlap(rect, altro_rect):
                raise LayoutError(
                    f"le card {altro_index} e {index} si sovrappongono"
                )

        rettangoli.append((index, rect))

        widget_type = _widget_type_for(card)
        componenti.append(
            to_wire(
                component_id=str(index + 1),
                widget_type=widget_type,
                name=f"{page['name']} #{index + 1}",
                rect=rect,
                content=_content_for(card, render, resolve),
                style=card.get("style", {}),
                z=card.get("z", 1),
            )
        )

    return componenti


def components_hash(components: list[dict[str, str]]) -> str:
    """Impronta stabile della lista, per non ripubblicare un canvas identico."""
    canonical = json.dumps(components, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

- [ ] **Step 4: Scrivere `layout/__init__.py`**

```python
"""Compilatore della dashboard: definizione dichiarativa → wire format."""
from __future__ import annotations

from .compile import EntityValue, LayoutError, compile_page, components_hash
from .schema import CARD_TYPES, PAGE_SLOTS, validate_page

__all__ = [
    "CARD_TYPES",
    "PAGE_SLOTS",
    "EntityValue",
    "LayoutError",
    "compile_page",
    "components_hash",
    "validate_page",
]
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

Run: `pytest tests/layout -v`
Expected: PASS, 56 test in totale

- [ ] **Step 6: Commit**

```bash
git add custom_components/switchbot_eink/layout tests/layout
git commit -m "feat(layout): compila le pagine validate in componenti wire"
```

---

### Task 10: Manifest, costanti e config flow

**Files:**
- Create: `custom_components/switchbot_eink/manifest.json`
- Create: `custom_components/switchbot_eink/const.py`
- Create: `custom_components/switchbot_eink/config_flow.py`
- Create: `custom_components/switchbot_eink/strings.json`
- Create: `custom_components/switchbot_eink/translations/en.json`
- Create: `custom_components/switchbot_eink/translations/it.json`
- Create: `tests/conftest.py`
- Test: `tests/ha/test_config_flow.py`

**Interfaces:**
- Consumes: da Task 3 — `CanvasAuth`, `Tokens`, `UserInfo`; da Task 4 — `SwitchBotCanvasClient`, `Device`; da Task 1 — `SwitchBotCanvasAuthError`.
- Produces: `DOMAIN = "switchbot_eink"`, le chiavi `CONF_REGION`, `CONF_ACCESS_TOKEN`, `CONF_REFRESH_TOKEN`, `CONF_TOKEN_TYPE`, `CONF_USER_ID`, `CONF_DEVICE_ID`, `CONF_DEVICE_NAME`, `CONF_TEMPLATE_ID`, `CONF_PAGE_SLOT`, `CONF_UPDATE_INTERVAL`, `DEFAULT_UPDATE_INTERVAL`, `MIN_PUBLISH_INTERVAL`, e la classe `SwitchBotEinkConfigFlow`.

- [ ] **Step 1: Scrivere `custom_components/switchbot_eink/manifest.json`**

```json
{
  "domain": "switchbot_eink",
  "name": "SwitchBot E-Ink Home Dashboard",
  "codeowners": [],
  "config_flow": true,
  "documentation": "https://github.com/fnegretti/switchbot-eink",
  "integration_type": "device",
  "iot_class": "cloud_push",
  "issue_tracker": "https://github.com/fnegretti/switchbot-eink/issues",
  "requirements": [],
  "version": "0.1.0"
}
```

- [ ] **Step 2: Scrivere `custom_components/switchbot_eink/const.py`**

`DEFAULT_UPDATE_INTERVAL` va allineato alla cadenza misurata nel Task 5: pubblicare più spesso di quanto il pannello legga è lavoro sprecato.

```python
"""Costanti dell'integrazione."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "switchbot_eink"

CONF_REGION: Final = "region"
CONF_USERNAME: Final = "username"
CONF_ACCESS_TOKEN: Final = "access_token"
CONF_REFRESH_TOKEN: Final = "refresh_token"
CONF_TOKEN_TYPE: Final = "token_type"
CONF_USER_ID: Final = "user_id"
CONF_DEVICE_ID: Final = "device_id"
CONF_DEVICE_NAME: Final = "device_name"
CONF_TEMPLATE_ID: Final = "template_id"
CONF_PAGE_SLOT: Final = "page_slot"
CONF_UPDATE_INTERVAL: Final = "update_interval"

# Da allineare alla cadenza misurata sul dispositivo (Task 5).
DEFAULT_UPDATE_INTERVAL: Final = 900  # secondi
MIN_PUBLISH_INTERVAL: Final = 60  # secondi, vincolo di spec

DEFAULT_PAGE_SLOT: Final = "custom1"

SERVICE_REFRESH: Final = "refresh"
SERVICE_PUSH_TEXT: Final = "push_text"
```

- [ ] **Step 3: Scrivere il test che fallisce**

File `tests/conftest.py`:

```python
"""Fixture condivise."""
from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Consente a Home Assistant di caricare custom_components nei test."""
    yield
```

File `tests/ha/__init__.py`: vuoto.

File `tests/ha/test_config_flow.py`:

```python
"""Test del config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.switchbot_eink.api.auth import Tokens, UserInfo
from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError
from custom_components.switchbot_eink.api.models import Device
from custom_components.switchbot_eink.const import (
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_USER_ID,
    DOMAIN,
)

TOKENS = Tokens(access_token="AT", refresh_token="RT", token_type="Bearer")
UTENTE = UserInfo(user_id="user-1", email="mario@example.test")
PANNELLO = Device(
    device_id="DEV1", device_name="Cucina", device_type="W1070000", is_share=False
)

CREDENZIALI = {
    "username": "mario@example.test",
    "password": "segreta",
    "region": "eu",
}

PERCORSO_AUTH = "custom_components.switchbot_eink.config_flow.CanvasAuth"
PERCORSO_CLIENT = "custom_components.switchbot_eink.config_flow.SwitchBotCanvasClient"


def _mock_auth(mock_cls) -> None:
    istanza = mock_cls.return_value
    istanza.login = AsyncMock(return_value=TOKENS)
    istanza.user_info = AsyncMock(return_value=UTENTE)


def _mock_client(mock_cls, devices=None) -> None:
    istanza = mock_cls.return_value
    istanza.list_eink_devices = AsyncMock(
        return_value=[PANNELLO] if devices is None else devices
    )


async def test_flusso_completo_crea_la_entry(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device"

    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Cucina"
    assert result["data"][CONF_REFRESH_TOKEN] == "RT"
    assert result["data"][CONF_USER_ID] == "user-1"
    assert result["data"][CONF_DEVICE_ID] == "DEV1"


async def test_la_password_non_viene_persistita(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )
        await hass.async_block_till_done()

    assert "password" not in result["data"]


async def test_credenziali_errate_mostrano_l_errore(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(side_effect=SwitchBotCanvasAuthError("no"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_nessun_pannello_interrompe_il_flusso(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client, devices=[])
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_devices_found"


async def test_lo_stesso_dispositivo_non_si_configura_due_volte(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data={}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    with patch(PERCORSO_AUTH) as auth, patch(PERCORSO_CLIENT) as client:
        _mock_auth(auth)
        _mock_client(client)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], CREDENZIALI
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_DEVICE_ID: "DEV1"}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_riscrive_i_token_senza_creare_una_entry(
    hass: HomeAssistant,
) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import (
        CONF_ACCESS_TOKEN,
        CONF_DEVICE_NAME,
        CONF_REGION,
        CONF_TOKEN_TYPE,
        CONF_USERNAME,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "eu",
            CONF_USERNAME: "mario@example.test",
            CONF_ACCESS_TOKEN: "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            CONF_TOKEN_TYPE: "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            CONF_DEVICE_NAME: "Cucina",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(PERCORSO_AUTH) as auth:
        _mock_auth(auth)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "nuova"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_ACCESS_TOKEN] == "AT"
    assert entry.data[CONF_REFRESH_TOKEN] == "RT"


async def test_reauth_con_password_errata_mostra_l_errore(hass: HomeAssistant) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import CONF_REGION

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={
            CONF_REGION: "eu",
            "access_token": "vecchio",
            CONF_REFRESH_TOKEN: "vecchio-rt",
            "token_type": "Bearer",
            CONF_USER_ID: "user-1",
            CONF_DEVICE_ID: "DEV1",
            "username": "mario@example.test",
        },
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    with patch(PERCORSO_AUTH) as auth:
        auth.return_value.login = AsyncMock(side_effect=SwitchBotCanvasAuthError("no"))
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"password": "sbagliata"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
```

Il reauth ha bisogno dell'email per rifare il login, ma la entry salva solo i token. Va quindi persistito anche `CONF_USERNAME` — è un identificativo, non un segreto — e il passo di reauth chiede la sola password.

- [ ] **Step 4: Eseguire il test e verificare che fallisca**

Run: `pytest tests/ha/test_config_flow.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.config_flow'`

- [ ] **Step 5: Scrivere `config_flow.py`**

```python
"""Config flow dell'integrazione."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api.auth import CanvasAuth, Tokens
from .api.client import SwitchBotCanvasClient
from .api.const import REGIONS
from .api.errors import SwitchBotCanvasError
from .api.models import Device
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    CONF_USERNAME,
    DOMAIN,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required("username"): str,
        vol.Required("password"): str,
        vol.Required("region", default="eu"): vol.In(REGIONS),
    }
)

STEP_REAUTH_SCHEMA = vol.Schema({vol.Required("password"): str})


class SwitchBotEinkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Login, scelta del pannello, e nessuna password su disco."""

    VERSION = 1

    def __init__(self) -> None:
        self._tokens: Tokens | None = None
        self._user_id: str | None = None
        self._region: str = "eu"
        self._username: str = ""
        self._devices: list[Device] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Chiede le credenziali e verifica che ci sia almeno un pannello."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        session = async_get_clientsession(self.hass)
        self._region = user_input["region"]
        self._username = user_input["username"]
        auth = CanvasAuth(session, self._region)

        try:
            tokens = await auth.login(user_input["username"], user_input["password"])
            info = await auth.user_info(tokens.access_token, tokens.token_type)
            client = SwitchBotCanvasClient(session, self._region, tokens, info.user_id)
            devices = await client.list_eink_devices()
        except SwitchBotCanvasError:
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_USER_SCHEMA,
                errors={"base": "invalid_auth"},
            )

        if not devices:
            return self.async_abort(reason="no_devices_found")

        self._tokens = tokens
        self._user_id = info.user_id
        self._devices = devices

        return await self.async_step_device()

    async def async_step_device(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fa scegliere quale pannello pilotare."""
        assert self._tokens is not None and self._user_id is not None

        if user_input is None:
            return self.async_show_form(
                step_id="device",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_DEVICE_ID): vol.In(
                            {d.device_id: d.device_name for d in self._devices}
                        )
                    }
                ),
            )

        device_id = user_input[CONF_DEVICE_ID]
        await self.async_set_unique_id(device_id)
        self._abort_if_unique_id_configured()

        device = next(d for d in self._devices if d.device_id == device_id)

        return self.async_create_entry(
            title=device.device_name or "SwitchBot E-Ink",
            data={
                CONF_REGION: self._region,
                CONF_USERNAME: self._username,
                CONF_ACCESS_TOKEN: self._tokens.access_token,
                CONF_REFRESH_TOKEN: self._tokens.refresh_token,
                CONF_TOKEN_TYPE: self._tokens.token_type,
                CONF_USER_ID: self._user_id,
                CONF_DEVICE_ID: device.device_id,
                CONF_DEVICE_NAME: device.device_name,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Il refresh token non è più valido: serve di nuovo la password."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Rifà il login e riscrive i soli token, senza toccare il resto."""
        entry = self._get_reauth_entry()

        if user_input is None:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_SCHEMA,
                description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
            )

        region = entry.data[CONF_REGION]
        auth = CanvasAuth(async_get_clientsession(self.hass), region)

        try:
            tokens = await auth.login(
                entry.data[CONF_USERNAME], user_input["password"]
            )
            info = await auth.user_info(tokens.access_token, tokens.token_type)
        except SwitchBotCanvasError:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=STEP_REAUTH_SCHEMA,
                errors={"base": "invalid_auth"},
                description_placeholders={"username": entry.data.get(CONF_USERNAME, "")},
            )

        return self.async_update_reload_and_abort(
            entry,
            data_updates={
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_TOKEN_TYPE: tokens.token_type,
                CONF_USER_ID: info.user_id,
            },
        )
```

Aggiungere `from collections.abc import Mapping` in cima al file.

- [ ] **Step 6: Scrivere `strings.json` e le traduzioni**

File `custom_components/switchbot_eink/strings.json`:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "SwitchBot E-Ink Home Dashboard",
        "description": "Accedi con il tuo account SwitchBot. La password non viene salvata: viene conservato solo il token di rinnovo.",
        "data": {
          "username": "Email",
          "password": "Password",
          "region": "Regione"
        }
      },
      "device": {
        "title": "Scegli il pannello",
        "data": {
          "device_id": "Pannello"
        }
      },
      "reauth_confirm": {
        "title": "Accedi di nuovo",
        "description": "Il token di {username} non è più valido. Inserisci la password per rinnovarlo.",
        "data": {
          "password": "Password"
        }
      }
    },
    "error": {
      "invalid_auth": "Credenziali non valide o servizio non raggiungibile."
    },
    "abort": {
      "no_devices_found": "Nessun pannello e-ink trovato su questo account.",
      "already_configured": "Questo pannello è già configurato.",
      "reauth_successful": "Autenticazione rinnovata."
    }
  }
}
```

File `custom_components/switchbot_eink/translations/en.json`:

```json
{
  "config": {
    "step": {
      "user": {
        "title": "SwitchBot E-Ink Home Dashboard",
        "description": "Sign in with your SwitchBot account. Your password is not stored — only the refresh token is kept.",
        "data": {
          "username": "Email",
          "password": "Password",
          "region": "Region"
        }
      },
      "device": {
        "title": "Choose the panel",
        "data": {
          "device_id": "Panel"
        }
      },
      "reauth_confirm": {
        "title": "Sign in again",
        "description": "The token for {username} is no longer valid. Enter the password to renew it.",
        "data": {
          "password": "Password"
        }
      }
    },
    "error": {
      "invalid_auth": "Invalid credentials, or the service is unreachable."
    },
    "abort": {
      "no_devices_found": "No e-ink panel found on this account.",
      "already_configured": "This panel is already configured.",
      "reauth_successful": "Authentication renewed."
    }
  }
}
```

File `custom_components/switchbot_eink/translations/it.json`: stesso contenuto di `strings.json`.

- [ ] **Step 7: Eseguire i test e verificare che passino**

Run: `pytest tests/ha/test_config_flow.py -v`
Expected: PASS, 7 test

- [ ] **Step 8: Commit**

```bash
git add custom_components/switchbot_eink tests/conftest.py tests/ha
git commit -m "feat(ha): aggiungi manifest, costanti e config flow"
```

---

### Task 11: Coordinator e setup della entry

**Files:**
- Create: `custom_components/switchbot_eink/coordinator.py`
- Modify: `custom_components/switchbot_eink/__init__.py`
- Test: `tests/ha/test_coordinator.py`

**Interfaces:**
- Consumes: da Task 4 — `SwitchBotCanvasClient`, `Template`, `TemplateSummary`; da Task 9 — `compile_page`, `components_hash`, `EntityValue`, `LayoutError`; da Task 10 — tutte le costanti.
- Produces: `SwitchBotEinkCoordinator(hass, entry, client, page)` con `async_publish(force: bool = False) -> bool` (ritorna `True` se ha pubblicato), gli attributi `last_published: datetime | None` e `auth_ok: bool`, e il type alias `SwitchBotEinkConfigEntry = ConfigEntry[SwitchBotEinkCoordinator]`.

La pagina arriva da `configuration.yaml` sotto la chiave `switchbot_eink`, validata con `validate_page` del Task 8.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/ha/test_coordinator.py`:

```python
"""Test del coordinator."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant

from custom_components.switchbot_eink.api.models import TemplateSummary
from custom_components.switchbot_eink.coordinator import SwitchBotEinkCoordinator
from custom_components.switchbot_eink.layout.schema import validate_page

PAGINA = validate_page(
    {
        "page": "custom1",
        "name": "Casa",
        "cards": [{"type": "text", "text": "ciao", "grid": [0, 0, 4, 1]}],
    }
)


@pytest.fixture
def entry():
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import (
        CONF_DEVICE_ID,
        CONF_TEMPLATE_ID,
        DOMAIN,
    )

    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={CONF_DEVICE_ID: "DEV1", CONF_TEMPLATE_ID: 77},
    )


@pytest.fixture
def client():
    mock = MagicMock()
    mock.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Casa", page_slot="custom1")]
    )
    mock.create_template = AsyncMock(return_value=77)
    mock.update_template = AsyncMock()
    mock.release = AsyncMock()
    return mock


async def test_la_prima_pubblicazione_aggiorna_e_rilascia(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client, PAGINA)

    assert await coordinator.async_publish() is True
    client.update_template.assert_awaited_once()
    client.release.assert_awaited_once_with("DEV1")


async def test_non_ripubblica_se_l_hash_non_cambia(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client, PAGINA)

    await coordinator.async_publish()
    client.update_template.reset_mock()
    client.release.reset_mock()

    assert await coordinator.async_publish() is False
    client.update_template.assert_not_awaited()
    client.release.assert_not_awaited()


async def test_force_ripubblica_anche_a_hash_invariato(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    coordinator = SwitchBotEinkCoordinator(hass, entry, client, PAGINA)

    await coordinator.async_publish()
    client.release.reset_mock()

    assert await coordinator.async_publish(force=True) is True
    client.release.assert_awaited_once()


async def test_crea_il_template_se_lo_slot_e_vuoto(hass: HomeAssistant, client) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.switchbot_eink.const import CONF_DEVICE_ID, DOMAIN

    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data={CONF_DEVICE_ID: "DEV1"})
    entry.add_to_hass(hass)
    client.list_templates = AsyncMock(return_value=[])

    coordinator = SwitchBotEinkCoordinator(hass, entry, client, PAGINA)
    await coordinator.async_publish()

    client.create_template.assert_awaited_once()
    client.update_template.assert_not_awaited()


async def test_lo_stato_di_una_entity_finisce_nel_canvas(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    hass.states.async_set(
        "sensor.salotto", "21.4", {"unit_of_measurement": "°C"}
    )
    pagina = validate_page(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "metric",
                    "entity": "sensor.salotto",
                    "label": "Salotto",
                    "grid": [0, 0, 3, 1],
                }
            ],
        }
    )
    coordinator = SwitchBotEinkCoordinator(hass, entry, client, pagina)
    await coordinator.async_publish()

    template = client.update_template.await_args.args[0]
    assert "21.4" in template.components[0]["extra"]
    assert "°C" in template.components[0]["extra"]


async def test_i_template_jinja_vengono_renderizzati(
    hass: HomeAssistant, entry, client
) -> None:
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.lavatrice", "in funzione")
    pagina = validate_page(
        {
            "page": "custom1",
            "cards": [
                {
                    "type": "text",
                    "text": "Lavatrice: {{ states('sensor.lavatrice') }}",
                    "grid": [0, 0, 6, 1],
                }
            ],
        }
    )
    coordinator = SwitchBotEinkCoordinator(hass, entry, client, pagina)
    await coordinator.async_publish()

    template = client.update_template.await_args.args[0]
    assert "Lavatrice: in funzione" in template.components[0]["extra"]


async def test_auth_ok_diventa_falso_dopo_un_errore_di_autenticazione(
    hass: HomeAssistant, entry, client
) -> None:
    from custom_components.switchbot_eink.api.errors import SwitchBotCanvasAuthError

    entry.add_to_hass(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasAuthError("scaduto"))
    coordinator = SwitchBotEinkCoordinator(hass, entry, client, PAGINA)

    with pytest.raises(SwitchBotCanvasAuthError):
        await coordinator.async_publish()

    assert coordinator.auth_ok is False
```

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/ha/test_coordinator.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'custom_components.switchbot_eink.coordinator'`

- [ ] **Step 3: Scrivere `coordinator.py`**

```python
"""Ricompila la dashboard e la pubblica quando è cambiata davvero."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .api.client import SwitchBotCanvasClient
from .api.errors import SwitchBotCanvasAuthError
from .api.models import Template as CanvasTemplate
from .const import (
    CONF_DEVICE_ID,
    CONF_TEMPLATE_ID,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_PUBLISH_INTERVAL,
)
from .layout.compile import EntityValue, compile_page, components_hash

_LOGGER = logging.getLogger(__name__)

type SwitchBotEinkConfigEntry = ConfigEntry[SwitchBotEinkCoordinator]


class SwitchBotEinkCoordinator(DataUpdateCoordinator[None]):
    """Pubblica il canvas a intervalli, saltando i cicli in cui nulla è cambiato."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SwitchBotCanvasClient,
        page: dict[str, Any],
    ) -> None:
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(interval, MIN_PUBLISH_INTERVAL)),
        )
        self._entry = entry
        self._client = client
        self._page = page
        self._device_id: str = entry.data[CONF_DEVICE_ID]
        self._template_id: int | None = entry.data.get(CONF_TEMPLATE_ID)
        self._last_hash: str | None = None

        self.last_published: datetime | None = None
        self.auth_ok: bool = True

    def _render(self, template_text: str) -> str:
        """Renderizza un campo con il motore di template di Home Assistant."""
        if "{{" not in template_text and "{%" not in template_text:
            return template_text
        return str(Template(template_text, self.hass).async_render(parse_result=False))

    def _resolve(self, entity_id: str) -> EntityValue | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        return EntityValue(
            state=state.state,
            unit=state.attributes.get("unit_of_measurement"),
        )

    async def _ensure_template_id(self) -> int:
        """Riusa il template già presente sullo slot, altrimenti ne crea uno."""
        if self._template_id is not None:
            return self._template_id

        slot = self._page["page"]
        existing = [
            summary
            for summary in await self._client.list_templates(self._device_id)
            if summary.page_slot == slot
        ]
        if existing:
            self._template_id = existing[0].template_id
        else:
            self._template_id = await self._client.create_template(
                CanvasTemplate(
                    template_id=None,
                    name=self._page["name"],
                    page_slot=slot,
                    device_id=self._device_id,
                    components=[],
                )
            )

        self.hass.config_entries.async_update_entry(
            self._entry,
            data={**self._entry.data, CONF_TEMPLATE_ID: self._template_id},
        )
        return self._template_id

    async def async_publish(self, force: bool = False) -> bool:
        """Compila e pubblica. Ritorna True solo se ha davvero scritto."""
        components = compile_page(self._page, self._render, self._resolve)
        current_hash = components_hash(components)

        if not force and current_hash == self._last_hash:
            _LOGGER.debug("Canvas invariato, nessuna pubblicazione")
            return False

        template_id = await self._ensure_template_id()
        template = CanvasTemplate(
            template_id=template_id,
            name=self._page["name"],
            page_slot=self._page["page"],
            device_id=self._device_id,
            components=components,
        )

        try:
            await self._client.update_template(template)
            await self._client.release(self._device_id)
        except SwitchBotCanvasAuthError:
            self.auth_ok = False
            raise

        self.auth_ok = True
        self._last_hash = current_hash
        self.last_published = dt_util.utcnow()
        _LOGGER.debug("Canvas pubblicato: %d componenti", len(components))
        return True

    async def _async_update_data(self) -> None:
        await self.async_publish()
```

- [ ] **Step 4: Scrivere `__init__.py`**

```python
"""Integrazione SwitchBot E-Ink Home Dashboard."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api.auth import Tokens
from .api.client import SwitchBotCanvasClient
from .api.errors import SwitchBotCanvasAuthError, SwitchBotCanvasError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    DOMAIN,
)
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator
from .layout.schema import PAGE_SCHEMA, validate_page

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: PAGE_SCHEMA}, extra=vol.ALLOW_EXTRA
)

_PAGE_KEY = f"{DOMAIN}_page"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Legge la definizione della dashboard da configuration.yaml."""
    if DOMAIN in config:
        hass.data[_PAGE_KEY] = validate_page(dict(config[DOMAIN]))
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: SwitchBotEinkConfigEntry
) -> bool:
    """Avvia il client e il coordinator."""
    page = hass.data.get(_PAGE_KEY)
    if page is None:
        raise ConfigEntryNotReady(
            "Manca la definizione della dashboard: aggiungi la chiave "
            "switchbot_eink in configuration.yaml"
        )

    tokens = Tokens(
        access_token=entry.data[CONF_ACCESS_TOKEN],
        refresh_token=entry.data[CONF_REFRESH_TOKEN],
        token_type=entry.data.get(CONF_TOKEN_TYPE, "Bearer"),
    )
    client = SwitchBotCanvasClient(
        async_get_clientsession(hass),
        entry.data[CONF_REGION],
        tokens,
        entry.data[CONF_USER_ID],
    )

    coordinator = SwitchBotEinkCoordinator(hass, entry, client, page)

    try:
        await coordinator.async_config_entry_first_refresh()
    except SwitchBotCanvasAuthError as err:
        raise ConfigEntryAuthFailed("Token non più valido") from err
    except SwitchBotCanvasError as err:
        raise ConfigEntryNotReady(str(err)) from err

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _persist_tokens(hass, entry, client)
    return True


def _persist_tokens(
    hass: HomeAssistant, entry: ConfigEntry, client: SwitchBotCanvasClient
) -> None:
    """Salva i token aggiornati dopo un eventuale refresh automatico."""
    tokens = client.tokens
    if tokens.access_token == entry.data[CONF_ACCESS_TOKEN]:
        return
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_ACCESS_TOKEN: tokens.access_token,
            CONF_REFRESH_TOKEN: tokens.refresh_token,
            CONF_TOKEN_TYPE: tokens.token_type,
        },
    )


async def async_unload_entry(
    hass: HomeAssistant, entry: SwitchBotEinkConfigEntry
) -> bool:
    """Scarica la entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
```

- [ ] **Step 5: Eseguire i test e verificare che passino**

Run: `pytest tests/ha -v`
Expected: PASS, 14 test

- [ ] **Step 6: Commit**

```bash
git add custom_components/switchbot_eink/coordinator.py custom_components/switchbot_eink/__init__.py tests/ha
git commit -m "feat(ha): aggiungi coordinator con pubblicazione condizionata all'hash"
```

---

### Task 12: Servizi ed entità diagnostiche

**Files:**
- Create: `custom_components/switchbot_eink/services.yaml`
- Create: `custom_components/switchbot_eink/sensor.py`
- Create: `custom_components/switchbot_eink/binary_sensor.py`
- Modify: `custom_components/switchbot_eink/__init__.py`
- Test: `tests/ha/test_services.py`

**Interfaces:**
- Consumes: da Task 11 — `SwitchBotEinkCoordinator`, `SwitchBotEinkConfigEntry`; da Task 10 — `SERVICE_REFRESH`, `SERVICE_PUSH_TEXT`, `DOMAIN`.
- Produces: i servizi `switchbot_eink.refresh` e `switchbot_eink.push_text`, l'entità `sensor.<device>_ultima_pubblicazione` e l'entità `binary_sensor.<device>_autenticazione`, più il metodo `SwitchBotEinkCoordinator.async_push_text(card_name: str, text: str) -> None`.

- [ ] **Step 1: Scrivere il test che fallisce**

File `tests/ha/test_services.py`:

```python
"""Test dei servizi e delle entità diagnostiche."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant

from custom_components.switchbot_eink.api.models import TemplateSummary
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_REGION,
    CONF_TEMPLATE_ID,
    CONF_TOKEN_TYPE,
    CONF_USER_ID,
    DOMAIN,
    SERVICE_PUSH_TEXT,
    SERVICE_REFRESH,
)

CONFIG_YAML = {
    DOMAIN: {
        "page": "custom1",
        "name": "Casa",
        "cards": [
            {"type": "text", "text": "statico", "grid": [0, 0, 6, 1]},
            {"type": "text", "text": "avviso", "grid": [0, 1, 6, 1], "name": "avvisi"},
        ],
    }
}

DATA = {
    CONF_REGION: "eu",
    CONF_ACCESS_TOKEN: "AT",
    CONF_REFRESH_TOKEN: "RT",
    CONF_TOKEN_TYPE: "Bearer",
    CONF_USER_ID: "user-1",
    CONF_DEVICE_ID: "DEV1",
    CONF_DEVICE_NAME: "Cucina",
    CONF_TEMPLATE_ID: 77,
}


@pytest.fixture
def client_mock():
    mock = MagicMock()
    mock.tokens = MagicMock(access_token="AT", refresh_token="RT", token_type="Bearer")
    mock.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Casa", page_slot="custom1")]
    )
    mock.update_template = AsyncMock()
    mock.release = AsyncMock()
    return mock


async def _setup(hass: HomeAssistant, client_mock):
    from homeassistant.setup import async_setup_component
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=DATA)
    entry.add_to_hass(hass)

    with patch(
        "custom_components.switchbot_eink.SwitchBotCanvasClient", return_value=client_mock
    ):
        assert await async_setup_component(hass, DOMAIN, CONFIG_YAML)
        await hass.async_block_till_done()
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    return entry


async def test_i_servizi_sono_registrati(hass: HomeAssistant, client_mock) -> None:
    await _setup(hass, client_mock)

    assert hass.services.has_service(DOMAIN, SERVICE_REFRESH)
    assert hass.services.has_service(DOMAIN, SERVICE_PUSH_TEXT)


async def test_refresh_ripubblica_anche_senza_modifiche(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)
    client_mock.release.reset_mock()

    await hass.services.async_call(DOMAIN, SERVICE_REFRESH, {}, blocking=True)
    await hass.async_block_till_done()

    client_mock.release.assert_awaited()


async def test_push_text_sostituisce_il_testo_della_card(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)
    client_mock.update_template.reset_mock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_PUSH_TEXT,
        {"card": "avvisi", "text": "pacco consegnato"},
        blocking=True,
    )
    await hass.async_block_till_done()

    template = client_mock.update_template.await_args.args[0]
    assert "pacco consegnato" in template.components[1]["extra"]


async def test_il_sensore_di_ultima_pubblicazione_esiste(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    assert hass.states.get("sensor.cucina_ultima_pubblicazione") is not None


async def test_il_binary_sensor_di_autenticazione_e_a_posto(
    hass: HomeAssistant, client_mock
) -> None:
    await _setup(hass, client_mock)

    stato = hass.states.get("binary_sensor.cucina_autenticazione")
    assert stato is not None
    assert stato.state == "off", "off significa nessun problema per la classe PROBLEM"
```

Il campo `name` su una card non è ancora previsto dallo schema del Task 8: va aggiunto qui.

- [ ] **Step 2: Eseguire il test e verificare che fallisca**

Run: `pytest tests/ha/test_services.py -v`
Expected: FAIL con `AssertionError` sulla presenza dei servizi

- [ ] **Step 3: Aggiungere il campo `name` allo schema delle card**

In `custom_components/switchbot_eink/layout/schema.py`, dentro `CARD_SCHEMA`, dopo la riga `vol.Required("type"): vol.In(CARD_TYPES),`:

```python
        vol.Optional("name"): str,
```

- [ ] **Step 4: Aggiungere `async_push_text` al coordinator**

In `custom_components/switchbot_eink/coordinator.py`, aggiungere il metodo alla classe `SwitchBotEinkCoordinator`, subito prima di `_async_update_data`:

```python
    async def async_push_text(self, card_name: str, text: str) -> None:
        """Sovrascrive il testo di una card e ripubblica.

        L'override vive in memoria: sopravvive ai cicli del coordinator ma non
        a un riavvio di Home Assistant, che è il comportamento giusto per un
        avviso estemporaneo.
        """
        for card in self._page["cards"]:
            if card.get("name") == card_name:
                if card["type"] != "text":
                    raise ValueError(f"la card {card_name!r} non è di tipo text")
                card["text"] = text
                break
        else:
            raise ValueError(f"nessuna card si chiama {card_name!r}")

        await self.async_publish(force=True)
```

- [ ] **Step 5: Scrivere `services.yaml`**

```yaml
refresh:
  name: Aggiorna la dashboard
  description: >-
    Ricompila la dashboard e la pubblica sul pannello, anche se il contenuto
    non è cambiato.

push_text:
  name: Scrivi su una card
  description: >-
    Sostituisce il testo di una card di tipo text e ripubblica subito.
    L'override resta finché Home Assistant non viene riavviato.
  fields:
    card:
      name: Card
      description: Il valore del campo name della card da modificare.
      required: true
      example: avvisi
      selector:
        text:
    text:
      name: Testo
      description: Il nuovo testo da mostrare.
      required: true
      example: Pacco consegnato
      selector:
        text:
```

- [ ] **Step 6: Scrivere `sensor.py`**

```python
"""Entità diagnostica: quando è avvenuta l'ultima pubblicazione."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator

DESCRIPTION = SensorEntityDescription(
    key="last_published",
    translation_key="last_published",
    name="Ultima pubblicazione",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LastPublishedSensor(entry.runtime_data, entry)])


class LastPublishedSensor(CoordinatorEntity[SwitchBotEinkCoordinator], SensorEntity):
    """Orario dell'ultima pubblicazione riuscita."""

    _attr_has_entity_name = False

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = DESCRIPTION
        device_id = entry.data[CONF_DEVICE_ID]
        device_name = entry.data.get(CONF_DEVICE_NAME, "SwitchBot E-Ink")
        self._attr_unique_id = f"{device_id}_last_published"
        self._attr_name = f"{device_name} ultima pubblicazione"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="SwitchBot",
            model="E-Ink Home Dashboard (W8902500)",
        )

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.last_published
```

- [ ] **Step 7: Scrivere `binary_sensor.py`**

```python
"""Entità diagnostica: lo stato dell'autenticazione."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_DEVICE_ID, CONF_DEVICE_NAME, DOMAIN
from .coordinator import SwitchBotEinkConfigEntry, SwitchBotEinkCoordinator

DESCRIPTION = BinarySensorEntityDescription(
    key="auth",
    translation_key="auth",
    name="Autenticazione",
    device_class=BinarySensorDeviceClass.PROBLEM,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SwitchBotEinkConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AuthBinarySensor(entry.runtime_data, entry)])


class AuthBinarySensor(
    CoordinatorEntity[SwitchBotEinkCoordinator], BinarySensorEntity
):
    """Acceso quando il token non è più valido: è una classe PROBLEM."""

    _attr_has_entity_name = False

    def __init__(
        self, coordinator: SwitchBotEinkCoordinator, entry: SwitchBotEinkConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = DESCRIPTION
        device_id = entry.data[CONF_DEVICE_ID]
        device_name = entry.data.get(CONF_DEVICE_NAME, "SwitchBot E-Ink")
        self._attr_unique_id = f"{device_id}_auth"
        self._attr_name = f"{device_name} autenticazione"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=device_name,
            manufacturer="SwitchBot",
            model="E-Ink Home Dashboard (W8902500)",
        )

    @property
    def is_on(self) -> bool:
        return not self.coordinator.auth_ok
```

- [ ] **Step 8: Registrare i servizi in `__init__.py`**

Aggiungere gli import in cima a `custom_components/switchbot_eink/__init__.py`:

```python
from homeassistant.core import ServiceCall

from .const import SERVICE_PUSH_TEXT, SERVICE_REFRESH
```

Aggiungere la funzione dopo `async_setup_entry`:

```python
def _register_services(hass: HomeAssistant) -> None:
    """Registra i servizi una sola volta, alla prima entry configurata."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    def _coordinators() -> list[SwitchBotEinkCoordinator]:
        return [
            entry.runtime_data
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ]

    async def handle_refresh(call: ServiceCall) -> None:
        for coordinator in _coordinators():
            await coordinator.async_publish(force=True)

    async def handle_push_text(call: ServiceCall) -> None:
        card = call.data["card"]
        text = call.data["text"]
        for coordinator in _coordinators():
            await coordinator.async_push_text(card, text)

    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH, handle_refresh, schema=vol.Schema({})
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PUSH_TEXT,
        handle_push_text,
        schema=vol.Schema({vol.Required("card"): cv.string, vol.Required("text"): cv.string}),
    )
```

Aggiungere `from homeassistant.config_entries import ConfigEntry, ConfigEntryState` in cima (sostituendo l'import esistente di `ConfigEntry`), e chiamare `_register_services(hass)` in `async_setup_entry`, subito prima di `return True`.

- [ ] **Step 9: Eseguire i test e verificare che passino**

Run: `pytest tests/ha -v`
Expected: PASS, 19 test

- [ ] **Step 10: Eseguire l'intera suite**

Run: `pytest -v`
Expected: PASS, tutti i test

- [ ] **Step 11: Commit**

```bash
git add custom_components/switchbot_eink tests/ha/test_services.py
git commit -m "feat(ha): aggiungi servizi refresh e push_text con entita' diagnostiche"
```

---

### Task 13: Confezionamento HACS e documentazione

**Files:**
- Create: `hacs.json`
- Create: `README.md`
- Create: `examples/dashboard.yaml`
- Create: `.github/workflows/test.yml`

**Interfaces:**
- Consumes: tutto quanto precede.
- Produces: un repository installabile via HACS come integrazione custom.

- [ ] **Step 1: Scrivere `hacs.json`**

```json
{
  "name": "SwitchBot E-Ink Home Dashboard",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2026.1.0"
}
```

- [ ] **Step 2: Scrivere `examples/dashboard.yaml`**

```yaml
# Da incollare in configuration.yaml.
# Area utile: 800x372 px, griglia 12 colonne x 6 righe.
switchbot_eink:
  page: custom1
  name: Casa

  cards:
    - type: text
      text: "CASA — {{ now().strftime('%H:%M') }}"
      grid: [0, 0, 12, 1]
      style:
        fontSize: 40
        align: center

    - type: divider
      grid: [0, 1, 12, 1]

    - type: metric
      entity: sensor.soggiorno_temperatura
      icon: temp-range
      label: Soggiorno
      grid: [0, 2, 3, 1]

    - type: metric
      entity: sensor.camera_temperatura
      icon: temp-range
      label: Camera
      grid: [3, 2, 3, 1]

    - type: metric
      entity: sensor.umidita_bagno
      icon: humidity-drop
      label: Bagno
      grid: [6, 2, 3, 1]

    - type: metric
      entity: sensor.consumo_istantaneo
      icon: gauge
      label: Consumo
      grid: [9, 2, 3, 1]

    - type: text
      name: avvisi
      text: >-
        {% if is_state('binary_sensor.finestra_cucina', 'on') %}
        Finestra cucina aperta
        {% else %}
        Tutto chiuso
        {% endif %}
      grid: [0, 3, 12, 1]
      style:
        fontSize: 24

    - type: text
      text: "Lavatrice: {{ states('sensor.lavatrice') }}"
      grid: [0, 4, 6, 1]
      style:
        fontSize: 20

    - type: text
      text: "Aggiornato {{ now().strftime('%H:%M') }}"
      grid: [6, 4, 6, 1]
      style:
        fontSize: 20
        align: right
```

- [ ] **Step 3: Scrivere `README.md`**

````markdown
# SwitchBot E-Ink Home Dashboard per Home Assistant

Trasforma il pannello e-ink da 7.5" del SwitchBot E-Ink Home Dashboard
(SKU `W8902500`) in una dashboard di stato della casa pilotata da Home
Assistant.

Il dispositivo non viene modificato: l'integrazione usa l'API del canvas
editor di SwitchBot per comporre una delle quattro pagine custom.

## Come funziona

Home Assistant legge i suoi stati, compone un canvas di 800×372 pixel a
quattro livelli di grigio e lo pubblica sul pannello. Pubblica solo quando il
contenuto è davvero cambiato.

## Requisiti

- Un SwitchBot E-Ink Home Dashboard con firmware 2.0 o successivo
- App SwitchBot 9.28 o successiva
- Un account SwitchBot con il dispositivo già aggiunto
- Home Assistant 2026.1 o successivo

## Installazione

Via HACS: aggiungere questo repository come integrazione custom, installarlo e
riavviare Home Assistant.

Manualmente: copiare `custom_components/switchbot_eink` nella cartella
`custom_components` della propria configurazione e riavviare.

## Configurazione

Prima la dashboard, in `configuration.yaml`. Vedere `examples/dashboard.yaml`
per un esempio completo:

```yaml
switchbot_eink:
  page: custom1
  name: Casa
  cards:
    - type: metric
      entity: sensor.soggiorno_temperatura
      icon: temp-range
      label: Soggiorno
      grid: [0, 0, 3, 1]
```

Poi l'integrazione, da **Impostazioni → Dispositivi e servizi → Aggiungi
integrazione → SwitchBot E-Ink Home Dashboard**. Servono email, password e
regione dell'account SwitchBot. La password non viene salvata: dopo il login
resta memorizzato solo il token di rinnovo.

## Il modello di layout

L'area utile è 800×372 px, divisa in una griglia di 12 colonne per 6 righe.
Ogni card dichiara `grid: [colonna, riga, larghezza, altezza]`, oppure
`position: [x, y, larghezza, altezza]` in pixel quando la griglia non basta.

Tipi di card disponibili:

| Tipo | Campi | Note |
|---|---|---|
| `metric` | `entity` o `value`, `label`, `icon`, `unit`, `widget` | tile con icona, etichetta, valore e unità |
| `text` | `text` | testo libero |
| `divider` | — | linea separatrice |
| `frame` | — | cornice |
| `image` | `src`, `alt` | immagine da URL |

I campi `text`, `label`, `value` e `unit` passano dal motore di template di
Home Assistant, quindi accettano Jinja.

Icone disponibili: `sun-times`, `sun`, `moon`, `wind`, `gauge`, `rain-chance`,
`uv`, `air-quality`, `eye`, `aqi`, `temp-range`, `humidity-drop`,
`thermo-humidity`.

I colori sono limitati a `black`, `white`, `gray` e `transparent`: il pannello
ha quattro livelli di grigio.

## Servizi

`switchbot_eink.refresh` ricompila e pubblica, anche a contenuto invariato.

`switchbot_eink.push_text` sostituisce il testo di una card che abbia un campo
`name`, e pubblica subito:

```yaml
action: switchbot_eink.push_text
data:
  card: avvisi
  text: Pacco consegnato
```

## Diagnostica

Lo strato API si può eseguire da solo, senza Home Assistant:

```bash
export SWITCHBOT_USER=... SWITCHBOT_PASS=... SWITCHBOT_REGION=eu
python -m tools.probe devices
python -m tools.probe templates
python -m tools.probe clock
```

## Avvertenza

Questa integrazione usa l'API privata del canvas editor SwitchBot, ricavata per
reverse engineering dai bundle JavaScript pubblici. Non è documentazione
ufficiale e SwitchBot può cambiarla o chiuderla senza preavviso. Tutto ciò che
la riguarda è confinato in `custom_components/switchbot_eink/api/`.

Progetto non affiliato né sostenuto da SwitchBot / Wonderlabs.
````

- [ ] **Step 4: Scrivere `.github/workflows/test.yml`**

```yaml
name: test

on:
  push:
    branches: [main]
  pull_request:

jobs:
  pytest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - run: pip install -e ".[dev]"
      - run: pytest -v
```

- [ ] **Step 5: Verificare che la suite passi da pulito**

Run: `pytest -v`
Expected: PASS, tutti i test

- [ ] **Step 6: Commit**

```bash
git add hacs.json README.md examples .github
git commit -m "docs: aggiungi confezionamento HACS, README ed esempio di dashboard"
```

---

## Ordine di esecuzione e dipendenze

I task 1 → 4 costruiscono lo strato API e vanno in sequenza. Il **Task 5 è un gate**: la misura sul dispositivo può cambiare le decisioni successive, quindi non va saltato né rimandato. I task 6 → 9 costruiscono lo strato layout e sono indipendenti dallo strato API, quindi potrebbero procedere in parallelo ai primi quattro. I task 10 → 12 dipendono da entrambi gli strati. Il task 13 chiude.

## Cosa fare se il gate del Task 5 fallisce

Se il pannello si aggiorna solo alla pressione del pulsante, questi restano gli approcci alternativi, in ordine di plausibilità:

1. Verificare se un `release` ripetuto o un cambio di `sortOrder` inducano un refresh.
2. Controllare se l'app SwitchBot esponga un'impostazione di frequenza di aggiornamento, e in caso rileggere `getDeviceList` per vedere se il valore compare nel payload.
3. Ripiegare sul comando `customPage` della OpenAPI pubblica, che ha un percorso di consegna diverso: 300 byte di testo, ma se si aggiorna da solo è comunque meglio di niente.

In tutti e tre i casi: fermarsi, riportare, e decidere insieme prima di proseguire.
