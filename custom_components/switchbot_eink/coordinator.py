"""Legge i calendari, rigenera l'agenda e la pubblica quando è cambiata davvero.

Convenzione sui fusi orari, per chi tocca questo file: tutto cio' che finisce
in un `Event` o viene passato a `build_agenda_page` e' **naive e nel fuso
locale di Home Assistant**. Gli eventi con orario arrivano da
`calendar.get_events` con un fuso esplicito (spesso diverso da quello
dell'istanza) e vengono convertiti con `dt_util.as_local(...).replace(tzinfo=
None)`; l'istante "adesso" usato per confrontare e generare la pagina viene
dallo stesso `dt_util.now().replace(tzinfo=None)`. Mischiare datetime aware e
naive in questo modulo o in `layout/agenda.py` rompe gli ordinamenti la' dentro
con un `TypeError` silenzioso solo a runtime.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.client import SwitchBotCanvasClient
from .api.errors import (
    SwitchBotCanvasApiError,
    SwitchBotCanvasAuthError,
    SwitchBotCanvasError,
)
from .api.models import Template as CanvasTemplate
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CALENDARS,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_REFRESH_TOKEN,
    CONF_TEMPLATE_ID,
    CONF_TOKEN_TYPE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_PUBLISH_INTERVAL,
)
from .layout.agenda import FINESTRA_GIORNI, Event, build_agenda_page
from .layout.compile import EntityValue, compile_page, components_hash
from .layout.schema import validate_page

_LOGGER = logging.getLogger(__name__)

type SwitchBotEinkConfigEntry = ConfigEntry[SwitchBotEinkCoordinator]


def _forse_template_sparito(err: SwitchBotCanvasApiError) -> bool:
    """Vero se l'errore puo' significare che il template non esiste piu'.

    Il codice esatto non e' documentato — l'API e' privata — quindi ci si regola
    sull'intervallo. Lo zero e' l'involucro degli errori di rete di `http.py`, e
    tutto cio' che sta da 400 in su e' uno stato HTTP: in nessuno dei due casi il
    backend sta dicendo qualcosa sul template, e trattarli come tale cancella un
    `template_id` valido o ne crea un duplicato sullo slot.
    """
    return 0 < err.code < 400


class SwitchBotEinkCoordinator(DataUpdateCoordinator[None]):
    """Rigenera l'agenda dai calendari scelti e la pubblica se e' cambiata."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: SwitchBotCanvasClient,
    ) -> None:
        interval = entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=max(interval, MIN_PUBLISH_INTERVAL)),
        )
        self._client = client
        self._device_id: str = entry.data[CONF_DEVICE_ID]
        # Serve solo nei messaggi d'errore: con piu' pannelli configurati,
        # sapere quale ha fallito e' meta' della diagnosi.
        self._device_name: str = entry.data.get(CONF_DEVICE_NAME) or self._device_id
        self._template_id: int | None = entry.data.get(CONF_TEMPLATE_ID)
        self._last_hash: str | None = None
        # Consumato una volta sola dal ciclo successivo di `_async_update_data`:
        # una forzatura vale per il giro che l'ha chiesta, non per tutti quelli
        # dopo.
        self._forza_prossimo: bool = False

        self.last_published: datetime | None = None
        self.auth_ok: bool = True
        # Istantanea delle opzioni con cui QUESTA istanza e' stata creata: la
        # usa il listener di ricarica in __init__.py per distinguere "sono
        # cambiate le opzioni" (ricarica) da "e' cambiato solo entry.data"
        # (rinnovo token, id del template — nessuna ricarica, altrimenti si
        # rischia un ciclo fra reload e persistenza).
        self.opzioni_iniziali: dict[str, Any] = dict(entry.options)

    # ---- calendari -> Event ------------------------------------------------

    def _nome_calendario(self, entity_id: str) -> str:
        """`friendly_name` dallo stato dell'entita', o l'entity_id se manca."""
        stato = self.hass.states.get(entity_id)
        if stato is None:
            return entity_id
        return stato.attributes.get("friendly_name", entity_id)

    def _entita_calendario_vive(self) -> list[str]:
        """Le entita' scelte che esistono davvero in questo momento.

        Un calendario rimosso dall'utente (o non ancora caricato all'avvio)
        farebbe fallire `calendar.get_events` per sempre: meglio scartarlo con
        un avviso una volta per ciclo che rompere l'intera pubblicazione.
        """
        scelte = self.config_entry.options.get(CONF_CALENDARS, [])
        vive = [e for e in scelte if self.hass.states.get(e) is not None]
        for mancante in set(scelte) - set(vive):
            _LOGGER.warning(
                "Il calendario %s non esiste piu': lo ignoro finche' non "
                "viene tolto dalle opzioni",
                mancante,
            )
        return vive

    def _calendari_scelti(self) -> list[str]:
        """Nomi dei calendari scelti dall'utente, non quelli che oggi hanno eventi.

        Passarli sempre a `build_agenda_page` evita che i marcatori spariscano
        quando uno dei calendari scelti non ha eventi nella finestra corrente.
        Include anche i calendari momentaneamente inesistenti: e' una scelta
        dell'utente, non una loro proprieta' del giorno.
        """
        entita = self.config_entry.options.get(CONF_CALENDARS, [])
        return [self._nome_calendario(entity_id) for entity_id in entita]

    def _evento_da_payload(
        self, grezzo: Mapping[str, Any], calendario: str
    ) -> Event | None:
        """Converte un evento del servizio, scartandolo se e' illeggibile.

        I calendari sono dati esterni, spesso di servizi altrui: un evento
        malformato non deve portarsi via tutti gli altri. La distinzione fra
        "tutto il giorno" e "con orario" resta sulla lunghezza della stringa
        (10 caratteri per "YYYY-MM-DD"), non su un try/except mirato.
        """
        try:
            start_raw = str(grezzo["start"])
            end_raw = str(grezzo["end"])
            all_day = len(start_raw) <= 10

            if all_day:
                inizio = datetime.combine(date.fromisoformat(start_raw), time.min)
                fine = datetime.combine(date.fromisoformat(end_raw), time.min)
            else:
                inizio = dt_util.as_local(datetime.fromisoformat(start_raw)).replace(
                    tzinfo=None
                )
                fine = dt_util.as_local(datetime.fromisoformat(end_raw)).replace(
                    tzinfo=None
                )

            return Event(
                start=inizio,
                end=fine,
                summary=str(grezzo.get("summary", "")),
                all_day=all_day,
                calendar=calendario,
            )
        except (KeyError, ValueError, TypeError) as err:
            _LOGGER.warning(
                "Evento di %s ignorato, formato inatteso (%s): %r",
                calendario,
                err,
                grezzo,
            )
            return None

    async def _eventi(self) -> list[Event]:
        """Legge gli eventi dei calendari scelti.

        `calendar.get_events` e' l'unico modo supportato per leggerli da fuori:
        le entita' di calendario non espongono gli eventi nel loro stato.
        """
        entita = self._entita_calendario_vive()
        if not entita:
            return []

        inizio = dt_util.start_of_local_day()
        try:
            risposta = await self.hass.services.async_call(
                "calendar",
                "get_events",
                {
                    "entity_id": entita,
                    "start_date_time": inizio,
                    "end_date_time": inizio + timedelta(days=FINESTRA_GIORNI),
                },
                blocking=True,
                return_response=True,
            )
        except HomeAssistantError as err:
            raise UpdateFailed(f"Lettura dei calendari fallita: {err}") from err

        if not isinstance(risposta, dict):
            _LOGGER.warning(
                "calendar.get_events ha risposto con una forma inattesa: %r",
                risposta,
            )
            return []

        eventi: list[Event] = []
        for entity_id, payload in risposta.items():
            if not isinstance(payload, dict):
                _LOGGER.warning(
                    "Risposta di %s in una forma inattesa: %r", entity_id, payload
                )
                continue
            nome = self._nome_calendario(entity_id)
            for grezzo in payload.get("events", []):
                evento = self._evento_da_payload(grezzo, nome)
                if evento is not None:
                    eventi.append(evento)
        return eventi

    # ---- rendering -----------------------------------------------------
    # Oggi irraggiungibili dall'agenda: ogni card che genera e' `text`/
    # `divider` con `template: false` (i titoli sono dati esterni, eseguirli
    # come Jinja sarebbe un'iniezione). Restano perche' la firma di
    # `compile_page` li richiede comunque, e servono al giorno in cui una
    # pagina con contenuti scritti dall'utente tornera' ad affiancare l'agenda.

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

    # ---- pubblicazione ---------------------------------------------------

    def _template(
        self,
        pagina: dict[str, Any],
        template_id: int | None,
        components: list[dict[str, str]],
    ) -> CanvasTemplate:
        return CanvasTemplate(
            template_id=template_id,
            name=pagina["name"],
            page_slot=pagina["page"],
            device_id=self._device_id,
            components=components,
        )

    def _remember_template_id(self, template_id: int) -> None:
        self._template_id = template_id
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_TEMPLATE_ID: template_id},
        )

    def _forget_template_id(self) -> None:
        """Dimentica il template: sul backend non e' piu' scrivibile.

        Successo normale se l'utente ha riordinato o cancellato i template
        dall'app SwitchBot. Un solo tentativo di recupero per ciclo: se anche
        il percorso list/create fallisce, l'eccezione risale come sempre.
        """
        self._template_id = None
        dati = dict(self.config_entry.data)
        dati.pop(CONF_TEMPLATE_ID, None)
        self.hass.config_entries.async_update_entry(self.config_entry, data=dati)

    async def _riusa_o_crea(
        self,
        pagina: dict[str, Any],
        components: list[dict[str, str]],
        templates: list,
    ) -> None:
        """Riusa il template gia' presente sullo slot, altrimenti ne crea uno.

        `templates` e' la lista gia' letta da `list_templates`: mai chiamarlo
        una seconda volta per lo stesso ciclo.
        """
        slot = pagina["page"]
        esistente = [t for t in templates if t.page_slot == slot]
        if esistente:
            template_id = esistente[0].template_id
            await self._client.update_template(
                self._template(pagina, template_id, components)
            )
        else:
            template_id = await self._client.create_template(
                self._template(pagina, None, components)
            )
        self._remember_template_id(template_id)

    async def _write_template(
        self, pagina: dict[str, Any], components: list[dict[str, str]]
    ) -> None:
        """Scrive il contenuto sul template dello slot.

        Se il template esiste già (in cache o sul device), lo aggiorna. Se va
        creato, i componenti veri vanno dentro `create_template`: farlo con un
        segnaposto vuoto e poi chiamare `update_template` sprecherebbe una
        chiamata e lascerebbe una finestra col canvas vuoto.

        Se l'update sul template in cache fallisce con un errore applicativo
        che puo' voler dire "il template non c'e' piu'" (vedi
        `_forse_template_sparito`), si tenta un solo recupero: si rilegge la
        lista e, solo se il template davvero non c'e' piu', si dimentica l'id
        e si riusa o ricrea. Due cancelli, non uno: un codice fuori
        dall'intervallo applicativo (errori di rete, HTTP >= 400) non passa
        nemmeno il primo; se anche cosi' il template risulta ancora presente
        nella lista, l'errore non significava "sparito" e risale com'era.
        """
        if self._template_id is not None:
            try:
                await self._client.update_template(
                    self._template(pagina, self._template_id, components)
                )
                return
            except SwitchBotCanvasApiError as err:
                _LOGGER.warning(
                    "update_template sul template %s ha fallito con codice %s (%s)",
                    self._template_id,
                    err.code,
                    err,
                )
                if not _forse_template_sparito(err):
                    raise

                # Secondo cancello: non creare mai al buio. Se list_templates
                # fallisce a sua volta, non si tenta il recupero: l'eccezione
                # risale cosi' com'e' (async_publish la traduce in
                # UpdateFailed) e si riprova al ciclo dopo.
                templates = await self._client.list_templates(self._device_id)
                if any(t.template_id == self._template_id for t in templates):
                    _LOGGER.warning(
                        "Il template %s esiste ancora: non era sparito, "
                        "l'errore era un altro",
                        self._template_id,
                    )
                    raise

                self._forget_template_id()
                await self._riusa_o_crea(pagina, components, templates)
                return

        templates = await self._client.list_templates(self._device_id)
        await self._riusa_o_crea(pagina, components, templates)

    def _persist_tokens(self) -> None:
        """Ripersiste i token se il client li ha rinnovati da solo.

        Senza questo, al riavvio di Home Assistant si riparte da un token
        gia' scaduto invece che da quello rinnovato.
        """
        tokens = self._client.tokens
        if tokens.access_token == self.config_entry.data.get(CONF_ACCESS_TOKEN):
            return
        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={
                **self.config_entry.data,
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_TOKEN_TYPE: tokens.token_type,
            },
        )

    def _sotto_intervallo_minimo(self, ora_utc: datetime) -> bool:
        """Vero se l'ultima pubblicazione e' troppo recente per farne un'altra.

        Protegge il backend da chiamate ravvicinate, non l'utente: `force`
        scavalca il controllo sull'hash ma non questo.

        Il confine e' esplicitamente incluso nel permesso: a esattamente
        `MIN_PUBLISH_INTERVAL` secondi di distanza il minimo e' gia' rispettato
        e la pubblicazione e' ammessa (`<`, non `<=`). "Minimo 60 secondi fra
        due pubblicazioni" vuol dire che 60 bastano, non che ne servono 61.
        """
        if self.last_published is None:
            return False
        return (ora_utc - self.last_published) < timedelta(
            seconds=MIN_PUBLISH_INTERVAL
        )

    async def async_publish(self, force: bool = False) -> bool:
        """Rigenera l'agenda e la pubblica. Ritorna True solo se ha davvero scritto."""
        eventi = await self._eventi()
        ora = dt_util.now().replace(tzinfo=None)
        scelti = self._calendari_scelti()

        # L'ora di aggiornamento cambia ad ogni minuto: se entrasse nel
        # confronto, l'hash non impedirebbe mai una pubblicazione. Si confronta
        # una pagina senza quella card e si pubblica quella con.
        confronto = validate_page(
            build_agenda_page(eventi, ora, calendars=scelti, stamp=False)
        )
        impronta = components_hash(compile_page(confronto, self._render, self._resolve))

        if not force and impronta == self._last_hash:
            _LOGGER.debug("Agenda invariata, nessuna pubblicazione")
            return False

        ora_utc = dt_util.utcnow()
        if self._sotto_intervallo_minimo(ora_utc):
            _LOGGER.debug(
                "Ultima pubblicazione troppo recente (< %ds), salto",
                MIN_PUBLISH_INTERVAL,
            )
            return False

        pagina = validate_page(build_agenda_page(eventi, ora, calendars=scelti))
        components = compile_page(pagina, self._render, self._resolve)

        try:
            await self._write_template(pagina, components)
            await self._client.release(self._device_id)
        except SwitchBotCanvasAuthError as err:
            self.auth_ok = False
            raise ConfigEntryAuthFailed("Token non piu' valido") from err
        except SwitchBotCanvasError as err:
            raise UpdateFailed(str(err)) from err
        finally:
            self._persist_tokens()

        self.auth_ok = True
        self._last_hash = impronta
        self.last_published = ora_utc
        _LOGGER.debug("Agenda pubblicata: %d componenti", len(components))
        return True

    async def _async_update_data(self) -> None:
        forzato, self._forza_prossimo = self._forza_prossimo, False
        await self.async_publish(force=forzato)

    async def async_forza_pubblicazione(self) -> None:
        """Chiede una pubblicazione forzata passando dal ciclo del coordinator.

        Chiamare `async_publish` direttamente scavalcherebbe la macchina di
        `_async_refresh` che avvia il reauth su token scaduto, notifica le
        entita' diagnostiche e antepone un lucchetto al ciclo periodico:
        quella macchina va attraversata, non aggirata. `force` viaggia con un
        flag a colpo singolo perche' `_async_update_data` non accetta
        argomenti (e' la firma richiesta da `DataUpdateCoordinator`).
        """
        self._forza_prossimo = True
        await self.async_refresh()
        if not self.last_update_success:
            # Il nome del pannello e la causa vera devono stare nel messaggio:
            # e' l'unico testo che chi ha scritto l'automazione vedra' nei log,
            # e con piu' pannelli un "pubblicazione non riuscita" nudo non gli
            # dice ne' quale ne' perche'.
            raise HomeAssistantError(
                f"{self._device_name}: pubblicazione non riuscita "
                f"({self.last_exception})"
            ) from self.last_exception
