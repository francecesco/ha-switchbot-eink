"""Test del coordinator: agenda dai calendari, hash, token, errori, ciclo di vita."""
from __future__ import annotations

import json
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import voluptuous as vol
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.switchbot_eink.api.auth import Tokens
from custom_components.switchbot_eink.api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
)
from custom_components.switchbot_eink.api.models import TemplateSummary
from custom_components.switchbot_eink.const import (
    CONF_ACCESS_TOKEN,
    CONF_CALENDARS,
    CONF_DEVICE_ID,
    CONF_REFRESH_TOKEN,
    CONF_TEMPLATE_ID,
    CONF_TOKEN_TYPE,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
    MIN_PUBLISH_INTERVAL,
)
from custom_components.switchbot_eink.coordinator import SwitchBotEinkCoordinator
from custom_components.switchbot_eink.layout.agenda import (
    FINESTRA_GIORNI,
    build_agenda_page,
)

TOKENS = Tokens(access_token="AT", refresh_token="RT", token_type="Bearer")

DATI_BASE = {
    CONF_DEVICE_ID: "DEV1",
    CONF_ACCESS_TOKEN: "AT",
    CONF_REFRESH_TOKEN: "RT",
    CONF_TOKEN_TYPE: "Bearer",
}

# Istante fisso per congelare l'orologio in tutti i test che dipendono da
# "adesso": un'ora assoluta del giorno farebbe sparire o restare gli eventi
# scritti come offset a seconda di quando gira la suite (il filtro sui
# conclusi), e un evento a "now + 30 min" scritto senza congelare l'orologio
# fallisce fra le 23:30 e mezzanotte, quando l'offset scavalca il giorno.
# E' il terzo caso di questo accoppiamento nel progetto.
ADESSO_UTC = "2026-08-23T20:24:00+00:00"  # 13:24 locale in US/Pacific (fuso di test)


def _registra_get_events(hass: HomeAssistant, risposta: dict) -> list[dict]:
    """Registra un `calendar.get_events` finto; ritorna le richieste ricevute."""
    richieste: list[dict] = []

    async def handler(call):
        richieste.append(dict(call.data))
        return risposta

    hass.services.async_register(
        "calendar", "get_events", handler, supports_response=SupportsResponse.ONLY
    )
    return richieste


def _con_un_evento(
    hass: HomeAssistant,
    entity_id: str = "calendar.lavoro",
    nome: str = "Lavoro",
    minuti_da_ora: int = 30,
    durata_minuti: int = 60,
) -> list[dict]:
    """Registra un calendario con un evento oggi, ancorato a dt_util.now().

    Va sempre usato con l'orologio congelato (`freezer.move_to(ADESSO_UTC)`):
    l'offset da "adesso" risolve il problema dell'ora assoluta ma non quello
    del confine di mezzanotte, che solo congelare l'istante elimina.
    """
    hass.states.async_set(entity_id, "on", {"friendly_name": nome})
    adesso = dt_util.now()
    inizio = adesso + timedelta(minutes=minuti_da_ora)
    fine = inizio + timedelta(minutes=durata_minuti)
    return _registra_get_events(
        hass,
        {
            entity_id: {
                "events": [
                    {
                        "start": inizio.isoformat(),
                        "end": fine.isoformat(),
                        "summary": "Riunione",
                    }
                ]
            }
        },
    )


def _testi_delle_card(template) -> set:
    return {
        json.loads(c["extra"])["content"].get("text") for c in template.components
    }


@pytest.fixture
def entry():
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
        options={CONF_CALENDARS: ["calendar.lavoro"]},
    )


@pytest.fixture
def client():
    mock = MagicMock()
    mock.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Agenda", page_slot="home")]
    )
    mock.create_template = AsyncMock(return_value=77)
    mock.update_template = AsyncMock()
    mock.release = AsyncMock()
    mock.tokens = TOKENS
    return mock


@pytest.fixture
def coordinator(hass: HomeAssistant, entry, client) -> SwitchBotEinkCoordinator:
    """Un'istanza pronta, per i test che non dipendono da un istante congelato."""
    entry.add_to_hass(hass)
    return SwitchBotEinkCoordinator(hass, entry, client)


# ---- pubblicazione, hash, force, ciclo di vita -----------------------------


async def test_la_prima_pubblicazione_aggiorna_e_rilascia(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish() is True
    client.update_template.assert_awaited_once()
    client.release.assert_awaited_once_with("DEV1")


async def test_non_ripubblica_se_l_hash_non_cambia(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    await coordinatore.async_publish()
    client.update_template.reset_mock()
    client.release.reset_mock()

    assert await coordinatore.async_publish() is False
    client.update_template.assert_not_awaited()
    client.release.assert_not_awaited()


async def test_l_ora_di_aggiornamento_non_e_nell_hash(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Regressione: la card 'agg. HH:MM' cambia ad ogni minuto. Se entrasse
    nel confronto, l'hash non impedirebbe mai una pubblicazione."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish() is True
    client.update_template.reset_mock()
    client.release.reset_mock()
    freezer.tick(timedelta(minutes=3))

    assert await coordinatore.async_publish() is False
    client.update_template.assert_not_awaited()


async def test_force_ripubblica_anche_a_hash_invariato(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    await coordinatore.async_publish()
    client.release.reset_mock()
    freezer.tick(timedelta(seconds=MIN_PUBLISH_INTERVAL + 1))

    assert await coordinatore.async_publish(force=True) is True
    client.release.assert_awaited_once()


async def test_force_ravvicinati_rispettano_l_intervallo_minimo(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish(force=True) is True
    client.release.reset_mock()
    freezer.tick(timedelta(seconds=10))

    assert await coordinatore.async_publish(force=True) is False
    client.release.assert_not_awaited()


async def test_force_distanziati_pubblicano_entrambi(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish(force=True) is True
    client.release.reset_mock()
    freezer.tick(timedelta(seconds=MIN_PUBLISH_INTERVAL + 1))

    assert await coordinatore.async_publish(force=True) is True
    client.release.assert_awaited_once()


async def test_un_intervallo_di_esattamente_60_secondi_e_ammesso(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Il confine e' incluso nel permesso: "minimo 60 secondi" vuol dire che
    60 bastano, non che ne servono 61. Un `<=` al posto del `<` bloccherebbe
    proprio questo caso."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish(force=True) is True
    client.release.reset_mock()
    freezer.tick(timedelta(seconds=MIN_PUBLISH_INTERVAL))

    assert await coordinatore.async_publish(force=True) is True
    client.release.assert_awaited_once()


async def test_last_published_viene_aggiornato(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert coordinatore.last_published is None
    await coordinatore.async_publish()
    assert coordinatore.last_published == dt_util.utcnow()


def test_config_entry_e_passato_alla_classe_base(coordinator, entry) -> None:
    """Senza questo, `coordinator.config_entry` arriva da una ContextVar e nei
    test (dove non c'e' nessun setup in corso) resta `None`."""
    assert coordinator.config_entry is entry


def test_forget_template_id_ripulisce_anche_entry_data(coordinator, entry) -> None:
    """Dimenticarlo solo in memoria (`coordinator._template_id`) e non anche
    nella entry persistita significa ritrovarselo al prossimo riavvio."""
    assert entry.data[CONF_TEMPLATE_ID] == 77  # dalla fixture

    coordinator._forget_template_id()

    assert coordinator._template_id is None
    assert CONF_TEMPLATE_ID not in entry.data


def _agenda_con_la_pagina_reale_rotta(*args, **kwargs):
    """Come `build_agenda_page`, ma rompe solo la pagina che verrebbe
    pubblicata (`stamp` assente o True), lasciando intatta quella di
    confronto (`stamp=False`).

    Serve a verificare che `validate_page` sia davvero sul percorso della
    pagina pubblicata: un conteggio delle chiamate (`call_count == 2`) e'
    fragile, si rompe alla prima rifattorizzazione innocua che aggiunga o
    tolga una chiamata. Un comportamento osservabile — la scrittura non deve
    avvenire se la pagina reale e' invalida — non dipende da quante volte la
    funzione e' chiamata.
    """
    pagina = build_agenda_page(*args, **kwargs)
    if kwargs.get("stamp", True):
        pagina["cards"].append({"type": "non-esiste-questo-tipo-di-card"})
    return pagina


async def test_una_pagina_pubblicata_invalida_impedisce_la_scrittura(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Se `validate_page` non venisse chiamata sulla pagina reale prima di
    compilarla, una card invalida (qui: un tipo inesistente) arriverebbe
    intatta a `compile_page` invece di far fallire subito `async_publish`."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    with patch(
        "custom_components.switchbot_eink.coordinator.build_agenda_page",
        side_effect=_agenda_con_la_pagina_reale_rotta,
    ):
        with pytest.raises(vol.Invalid):
            await coordinatore.async_publish()

    client.update_template.assert_not_awaited()
    client.release.assert_not_awaited()


# ---- creazione/riuso/recupero del template ---------------------------------


async def test_crea_il_template_se_lo_slot_e_vuoto(
    hass: HomeAssistant, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=dict(DATI_BASE))
    entry.add_to_hass(hass)
    client.list_templates = AsyncMock(return_value=[])

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinatore.async_publish() is True

    client.create_template.assert_awaited_once()
    client.update_template.assert_not_awaited()

    template_creato = client.create_template.await_args.args[0]
    assert template_creato.components  # mai [], o il canvas resterebbe vuoto
    assert entry.data[CONF_TEMPLATE_ID] == 77  # id restituito dal mock


async def test_riusa_un_template_gia_presente_sullo_slot(
    hass: HomeAssistant, client, freezer
) -> None:
    """Nessun `template_id` in cache, ma uno esiste gia' sul device per lo
    slot: va aggiornato quello, non ricreato un altro."""
    freezer.move_to(ADESSO_UTC)
    entry = MockConfigEntry(domain=DOMAIN, unique_id="DEV1", data=dict(DATI_BASE))
    entry.add_to_hass(hass)
    client.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=55, name="Vecchia", page_slot="home")]
    )

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinatore.async_publish() is True

    client.update_template.assert_awaited_once()
    client.create_template.assert_not_awaited()
    template_aggiornato = client.update_template.await_args.args[0]
    assert template_aggiornato.template_id == 55
    assert entry.data[CONF_TEMPLATE_ID] == 55


# Il codice vero con cui il backend segnala "template non esiste piu'" non e'
# documentato (l'API e' privata). 150 e' solo un rappresentante illustrativo
# di "codice applicativo positivo sotto 400": qualunque valore in quella fascia
# esercita la stessa logica in `_forse_template_sparito`.
CODICE_APPLICATIVO_TEMPLATE_SPARITO = 150


async def test_il_template_cancellato_dall_app_viene_ricreato(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Se il backend rifiuta l'update con un codice applicativo (0 < codice <
    400) e lo slot risulta davvero vuoto rileggendo la lista, un solo
    tentativo di recupero: dimenticare l'id e ripartire da list/create."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)  # CONF_TEMPLATE_ID = 77, ora invalido sul backend
    _con_un_evento(hass)
    client.update_template = AsyncMock(
        side_effect=SwitchBotCanvasApiError(
            CODICE_APPLICATIVO_TEMPLATE_SPARITO, "template not exist"
        )
    )
    client.list_templates = AsyncMock(return_value=[])  # lo slot e' davvero vuoto
    client.create_template = AsyncMock(return_value=999)

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinatore.async_publish() is True

    client.create_template.assert_awaited_once()
    assert entry.data[CONF_TEMPLATE_ID] == 999


async def test_errore_di_rete_non_tenta_il_recupero(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Codice 0: e' l'involucro di `api/http.py` per un errore di trasporto,
    non dice niente sul template. Recuperare qui cancellerebbe un
    `template_id` valido per un guasto che non lo riguarda."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.update_template = AsyncMock(
        side_effect=SwitchBotCanvasApiError(0, "Errore di rete: boom")
    )

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinatore.async_publish()

    client.list_templates.assert_not_awaited()
    client.create_template.assert_not_awaited()
    assert entry.data[CONF_TEMPLATE_ID] == 77


async def test_errore_429_non_tenta_il_recupero(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """429 e' uno stato HTTP (>= 400): il backend sta chiedendo di rallentare,
    non sta dicendo che il template e' sparito. Recuperare qui raddoppierebbe
    le chiamate proprio quando serve il contrario."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasApiError(429, "HTTP 429"))

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinatore.async_publish()

    client.list_templates.assert_not_awaited()
    client.create_template.assert_not_awaited()
    assert entry.data[CONF_TEMPLATE_ID] == 77


async def test_recupero_con_list_templates_che_fallisce_non_crea(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Il secondo cancello: se anche `list_templates` fallisce, non si crea
    al buio. L'eccezione risale cosi' com'e' e si riprova al ciclo dopo."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.update_template = AsyncMock(
        side_effect=SwitchBotCanvasApiError(
            CODICE_APPLICATIVO_TEMPLATE_SPARITO, "boh"
        )
    )
    client.list_templates = AsyncMock(
        side_effect=SwitchBotCanvasApiError(0, "Errore di rete: boom")
    )

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinatore.async_publish()

    client.create_template.assert_not_awaited()


async def test_recupero_con_template_ancora_presente_non_crea(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Se il template rifiutato dall'update e' ancora nella lista, non era
    sparito: l'errore era un altro, e va rilanciato com'era."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)  # CONF_TEMPLATE_ID = 77
    _con_un_evento(hass)
    client.update_template = AsyncMock(
        side_effect=SwitchBotCanvasApiError(
            CODICE_APPLICATIVO_TEMPLATE_SPARITO, "boh"
        )
    )
    client.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Agenda", page_slot="home")]
    )

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    with pytest.raises(UpdateFailed):
        await coordinatore.async_publish()

    client.create_template.assert_not_awaited()
    assert entry.data[CONF_TEMPLATE_ID] == 77


async def test_recupero_con_altro_template_sullo_slot_lo_riusa(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Il template rifiutato non c'e' piu', ma un altro occupa gia' lo slot:
    va riusato, non creato un duplicato."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)  # CONF_TEMPLATE_ID = 77
    _con_un_evento(hass)
    client.update_template = AsyncMock(
        side_effect=[
            SwitchBotCanvasApiError(CODICE_APPLICATIVO_TEMPLATE_SPARITO, "boh"),
            None,
        ]
    )
    client.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=999, name="Altro", page_slot="home")]
    )

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinatore.async_publish() is True

    assert client.update_template.await_count == 2
    secondo_tentativo = client.update_template.await_args_list[1].args[0]
    assert secondo_tentativo.template_id == 999
    client.create_template.assert_not_awaited()
    assert entry.data[CONF_TEMPLATE_ID] == 999


# ---- errori: auth, transitori --------------------------------------------


async def test_auth_ok_diventa_falso_e_scatena_il_reauth(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasAuthError("scaduto"))
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinatore.async_publish()

    assert coordinatore.auth_ok is False


async def test_auth_ok_torna_vero_dopo_un_recupero(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasAuthError("scaduto"))
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinatore.async_publish()
    assert coordinatore.auth_ok is False

    client.update_template = AsyncMock()  # il login e' stato rifatto altrove
    freezer.tick(timedelta(seconds=MIN_PUBLISH_INTERVAL + 1))

    assert await coordinatore.async_publish(force=True) is True
    assert coordinatore.auth_ok is True


async def test_errore_transitorio_diventa_updatefailed(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.update_template = AsyncMock(side_effect=SwitchBotCanvasApiError(500, "boom"))
    client.list_templates = AsyncMock(
        return_value=[TemplateSummary(template_id=77, name="Agenda", page_slot="home")]
    )
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    with pytest.raises(UpdateFailed):
        await coordinatore.async_publish()


# ---- conversione degli eventi (unita', diretta su _evento_da_payload) -----


def test_evento_di_tutto_il_giorno_e_riconosciuto(coordinator) -> None:
    evento = coordinator._evento_da_payload(
        {"start": "2026-08-23", "end": "2026-08-24", "summary": "Ferie"}, "Lavoro"
    )
    assert evento is not None
    assert evento.all_day is True


def test_evento_con_orario_non_e_tutto_il_giorno(coordinator) -> None:
    evento = coordinator._evento_da_payload(
        {
            "start": "2026-08-23T09:00:00+00:00",
            "end": "2026-08-23T10:00:00+00:00",
            "summary": "Riunione",
        },
        "Lavoro",
    )
    assert evento is not None
    assert evento.all_day is False


def test_start_e_end_non_sono_scambiati(coordinator) -> None:
    evento = coordinator._evento_da_payload(
        {
            "start": "2026-08-23T09:00:00+00:00",
            "end": "2026-08-23T10:00:00+00:00",
            "summary": "x",
        },
        "Lavoro",
    )
    assert evento is not None
    assert evento.start < evento.end


def test_il_titolo_arriva_dal_summary(coordinator) -> None:
    evento = coordinator._evento_da_payload(
        {
            "start": "2026-08-23T09:00:00+00:00",
            "end": "2026-08-23T10:00:00+00:00",
            "summary": "Colloquio",
        },
        "Lavoro",
    )
    assert evento is not None
    assert evento.summary == "Colloquio"


def test_l_orario_viene_convertito_al_fuso_locale(coordinator) -> None:
    """L'istanza di test e' in US/Pacific (PDT, UTC-7 il 23 agosto): un evento
    alle 23:00 UTC deve arrivare come le 16:00 locali, non restare naive alle
    23 come se il fuso non fosse mai stato applicato."""
    evento = coordinator._evento_da_payload(
        {
            "start": "2026-08-23T23:00:00+00:00",
            "end": "2026-08-24T00:00:00+00:00",
            "summary": "x",
        },
        "Lavoro",
    )
    assert evento is not None
    assert evento.start.hour == 16


def test_un_evento_senza_end_viene_scartato(coordinator) -> None:
    evento = coordinator._evento_da_payload(
        {"start": "2026-08-23T09:00:00+00:00", "summary": "Rotto"}, "Lavoro"
    )
    assert evento is None


def test_un_evento_con_data_illeggibile_viene_scartato(coordinator) -> None:
    evento = coordinator._evento_da_payload(
        {"start": "non-una-data", "end": "boh", "summary": "Rotto"}, "Lavoro"
    )
    assert evento is None


async def test_un_evento_malformato_non_azzera_l_agenda(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    """Un evento rotto costa il suo evento, non l'intera pagina."""
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    hass.states.async_set("calendar.lavoro", "on", {"friendly_name": "Lavoro"})
    adesso = dt_util.now()
    inizio = adesso + timedelta(minutes=30)
    fine = inizio + timedelta(minutes=60)
    _registra_get_events(
        hass,
        {
            "calendar.lavoro": {
                "events": [
                    {
                        "start": inizio.isoformat(),
                        "end": fine.isoformat(),
                        "summary": "Riunione",
                    },
                    {"start": "non-una-data", "summary": "Rotto"},
                ]
            }
        },
    )
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish() is True
    template = client.update_template.await_args.args[0]
    testi = _testi_delle_card(template)
    assert any(t and "Riunione" in t for t in testi)


async def test_un_calendario_inesistente_viene_ignorato(
    hass: HomeAssistant, client, freezer
) -> None:
    """Un calendario tolto dall'utente non deve rompere il ciclo per sempre."""
    freezer.move_to(ADESSO_UTC)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
        options={CONF_CALENDARS: ["calendar.lavoro", "calendar.fantasma"]},
    )
    entry.add_to_hass(hass)
    hass.states.async_set("calendar.lavoro", "on", {"friendly_name": "Lavoro"})
    # "calendar.fantasma" non ha nessuno stato: e' come se fosse stato rimosso.
    richieste = _registra_get_events(hass, {"calendar.lavoro": {"events": []}})

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish() is True
    assert richieste[0]["entity_id"] == ["calendar.lavoro"]


# ---- argomenti della chiamata al servizio ----------------------------------


async def test_la_richiesta_al_servizio_include_tutti_i_calendari_e_la_finestra(
    hass: HomeAssistant, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
        options={CONF_CALENDARS: ["calendar.lavoro", "calendar.personale"]},
    )
    entry.add_to_hass(hass)
    hass.states.async_set("calendar.lavoro", "on", {"friendly_name": "Lavoro"})
    hass.states.async_set("calendar.personale", "on", {"friendly_name": "Personale"})
    richieste = _registra_get_events(hass, {})

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    await coordinatore.async_publish()

    assert len(richieste) == 1
    chiamata = richieste[0]
    assert set(chiamata["entity_id"]) == {"calendar.lavoro", "calendar.personale"}
    inizio_atteso = dt_util.start_of_local_day()
    assert chiamata["start_date_time"] == inizio_atteso
    assert chiamata["end_date_time"] - chiamata["start_date_time"] == timedelta(
        days=FINESTRA_GIORNI
    )


# ---- marcatori e agenda vuota -----------------------------------------------


async def test_nessun_calendario_scelto_produce_l_agenda_vuota_senza_eccezioni(
    hass: HomeAssistant, client, freezer
) -> None:
    """Stato iniziale dopo l'installazione: nessuna eccezione, agenda vuota."""
    freezer.move_to(ADESSO_UTC)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
    )
    entry.add_to_hass(hass)
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert await coordinatore.async_publish() is True

    template = client.update_template.await_args.args[0]
    assert any(
        testo and "Nessun evento nei prossimi 3 giorni" in testo
        for testo in _testi_delle_card(template)
    )


async def test_i_marcatori_restano_anche_se_un_calendario_non_ha_eventi(
    hass: HomeAssistant, client, freezer
) -> None:
    """`calendars` deve arrivare dalle opzioni, non dedotto dagli eventi presenti.

    Due calendari scelti, uno solo con un evento oggi: il marcatore deve
    comunque comparire. Se `calendars` non venisse passato a
    `build_agenda_page`, i nomi verrebbero dedotti dai soli eventi effettivi
    (un solo calendario) e i marcatori sparirebbero del tutto.
    """
    freezer.move_to(ADESSO_UTC)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data={**DATI_BASE, CONF_TEMPLATE_ID: 77},
        options={CONF_CALENDARS: ["calendar.lavoro", "calendar.personale"]},
    )
    entry.add_to_hass(hass)
    hass.states.async_set("calendar.personale", "on", {"friendly_name": "Personale"})
    _con_un_evento(hass)

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)
    assert await coordinatore.async_publish() is True

    template = client.update_template.await_args.args[0]
    assert "L" in _testi_delle_card(template)


# ---- opzioni e intervallo di pianificazione --------------------------------


async def test_l_intervallo_minimo_e_imposto_anche_se_le_opzioni_lo_violano(
    hass: HomeAssistant, client
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="DEV1",
        data=dict(DATI_BASE),
        options={CONF_UPDATE_INTERVAL: 10},
    )
    entry.add_to_hass(hass)

    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    assert coordinatore.update_interval == timedelta(seconds=MIN_PUBLISH_INTERVAL)


async def test_i_token_rinnovati_vengono_ripersistiti(
    hass: HomeAssistant, entry, client, freezer
) -> None:
    freezer.move_to(ADESSO_UTC)
    entry.add_to_hass(hass)
    _con_un_evento(hass)
    client.tokens = Tokens(access_token="NUOVO", refresh_token="RT2", token_type="Bearer")
    coordinatore = SwitchBotEinkCoordinator(hass, entry, client)

    await coordinatore.async_publish()

    assert entry.data[CONF_ACCESS_TOKEN] == "NUOVO"
    assert entry.data[CONF_REFRESH_TOKEN] == "RT2"
