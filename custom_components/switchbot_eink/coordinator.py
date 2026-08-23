"""Legge i calendari, rigenera l'agenda e la pubblica quando è cambiata davvero."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.template import Template
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api.client import SwitchBotCanvasClient
from .api.errors import SwitchBotCanvasAuthError, SwitchBotCanvasError
from .api.models import Template as CanvasTemplate
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_CALENDARS,
    CONF_DEVICE_ID,
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
            name=DOMAIN,
            update_interval=timedelta(seconds=max(interval, MIN_PUBLISH_INTERVAL)),
        )
        self.entry = entry
        self._client = client
        self._device_id: str = entry.data[CONF_DEVICE_ID]
        self._template_id: int | None = entry.data.get(CONF_TEMPLATE_ID)
        self._last_hash: str | None = None

        self.last_published: datetime | None = None
        self.auth_ok: bool = True

    # ---- calendari -> Event ------------------------------------------------

    def _nome_calendario(self, entity_id: str) -> str:
        """`friendly_name` dallo stato dell'entita', o l'entity_id se manca."""
        stato = self.hass.states.get(entity_id)
        if stato is None:
            return entity_id
        return stato.attributes.get("friendly_name", entity_id)

    def _calendari_scelti(self) -> list[str]:
        """Nomi dei calendari scelti dall'utente, non quelli che oggi hanno eventi.

        Passarli sempre a `build_agenda_page` evita che i marcatori spariscano
        quando uno dei calendari scelti non ha eventi nella finestra corrente.
        """
        entita = self.entry.options.get(CONF_CALENDARS, [])
        return [self._nome_calendario(entity_id) for entity_id in entita]

    @staticmethod
    def _evento_da_payload(grezzo: dict[str, Any], calendario: str) -> Event:
        """Converte le due forme che `calendar.get_events` restituisce.

        Un evento con orario ha `start`/`end` come stringhe ISO con fuso; uno di
        tutto il giorno le ha come sole date "YYYY-MM-DD" (10 caratteri): la
        distinzione e' sulla lunghezza, non su un try/except.
        """
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

    async def _eventi(self) -> list[Event]:
        """Legge gli eventi dei calendari scelti.

        `calendar.get_events` e' l'unico modo supportato per leggerli da fuori:
        le entita' di calendario non espongono gli eventi nel loro stato.
        """
        entita = self.entry.options.get(CONF_CALENDARS, [])
        if not entita:
            return []

        inizio = dt_util.start_of_local_day()
        risposta = await self.hass.services.async_call(
            "calendar",
            "get_events",
            {
                "entity_id": list(entita),
                "start_date_time": inizio,
                "end_date_time": inizio + timedelta(days=FINESTRA_GIORNI),
            },
            blocking=True,
            return_response=True,
        )

        eventi: list[Event] = []
        for entity_id, payload in (risposta or {}).items():
            nome = self._nome_calendario(entity_id)
            for grezzo in payload.get("events", []):
                eventi.append(self._evento_da_payload(grezzo, nome))
        return eventi

    # ---- rendering -----------------------------------------------------

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

    async def _write_template(
        self, pagina: dict[str, Any], components: list[dict[str, str]]
    ) -> None:
        """Scrive il contenuto sul template dello slot, esattamente una volta.

        Se il template esiste già (in cache o sul device), lo aggiorna. Se va
        creato, i componenti veri vanno dentro `create_template`: farlo con un
        segnaposto vuoto e poi chiamare `update_template` sprecherebbe una
        chiamata e lascerebbe una finestra col canvas vuoto.
        """
        slot = pagina["page"]

        if self._template_id is not None:
            await self._client.update_template(
                CanvasTemplate(
                    template_id=self._template_id,
                    name=pagina["name"],
                    page_slot=slot,
                    device_id=self._device_id,
                    components=components,
                )
            )
            return

        existing = [
            summary
            for summary in await self._client.list_templates(self._device_id)
            if summary.page_slot == slot
        ]
        if existing:
            template_id = existing[0].template_id
            await self._client.update_template(
                CanvasTemplate(
                    template_id=template_id,
                    name=pagina["name"],
                    page_slot=slot,
                    device_id=self._device_id,
                    components=components,
                )
            )
        else:
            template_id = await self._client.create_template(
                CanvasTemplate(
                    template_id=None,
                    name=pagina["name"],
                    page_slot=slot,
                    device_id=self._device_id,
                    components=components,
                )
            )

        self._template_id = template_id
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={**self.entry.data, CONF_TEMPLATE_ID: template_id},
        )

    def _persist_tokens(self) -> None:
        """Ripersiste i token se il client li ha rinnovati da solo.

        Senza questo, al riavvio di Home Assistant si riparte da un token
        gia' scaduto invece che da quello rinnovato.
        """
        tokens = self._client.tokens
        if tokens.access_token == self.entry.data.get(CONF_ACCESS_TOKEN):
            return
        self.hass.config_entries.async_update_entry(
            self.entry,
            data={
                **self.entry.data,
                CONF_ACCESS_TOKEN: tokens.access_token,
                CONF_REFRESH_TOKEN: tokens.refresh_token,
                CONF_TOKEN_TYPE: tokens.token_type,
            },
        )

    async def async_publish(self, force: bool = False) -> bool:
        """Rigenera l'agenda e la pubblica. Ritorna True solo se ha davvero scritto."""
        eventi = await self._eventi()
        ora = dt_util.now().replace(tzinfo=None)
        pagina = validate_page(
            build_agenda_page(eventi, ora, calendars=self._calendari_scelti())
        )

        components = compile_page(pagina, self._render, self._resolve)
        current_hash = components_hash(components)

        if not force and current_hash == self._last_hash:
            _LOGGER.debug("Agenda invariata, nessuna pubblicazione")
            return False

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
        self._last_hash = current_hash
        self.last_published = dt_util.utcnow()
        _LOGGER.debug("Agenda pubblicata: %d componenti", len(components))
        return True

    async def _async_update_data(self) -> None:
        await self.async_publish()
