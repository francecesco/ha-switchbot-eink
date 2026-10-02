"""Facciata unica sull'API privata del canvas."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .auth import CanvasAuth, Credentials, Tokens
from .const import (
    DEVICE_TYPE_EINK,
    PATH_DEVICE_LIST,
    PATH_HOMEPAGE_INFO,
    PATH_HOMEPAGE_SAVE,
    PATH_PAGES_LIST,
    PATH_TPL_CREATE,
    PATH_TPL_DEL,
    PATH_TPL_LIST,
    PATH_TPL_PREVIEW,
    PATH_TPL_RELEASE,
    PATH_TPL_UPDATE,
)
from .envelope import build_auth_header, device_base_url, productbiz_base_url, unwrap_backend
from .http import CanvasHttp
from .models import Device, Template, TemplateSummary, sort_order_to_page_slot

_LOGGER = logging.getLogger(__name__)


class SwitchBotCanvasClient:
    """Dispositivi e template. Rinnova il token da solo quando scade.

    Con `credentials` rifa' anche il login quando il refresh token non vale
    piu': senza, quel caso risale come `SwitchBotCanvasAuthError` e tocca
    all'utente reinserire la password.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        region: str,
        tokens: Tokens,
        user_id: str,
        credentials: Credentials | None = None,
    ) -> None:
        self._region = region
        self._tokens = tokens
        self._user_id = user_id
        self._credentials = credentials
        self._auth = CanvasAuth(session, region)
        self._http = CanvasHttp(
            session,
            productbiz_base_url(region),
            unwrap_backend,
            auth_provider=self._auth_header,
            on_unauthorized=self._try_refresh,
        )
        self._device_http = CanvasHttp(
            session,
            device_base_url(region),
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
        """Rinnova l'access token; se il refresh token e' scaduto, rifa' il login.

        Il motivo di ogni fallimento va nei log: e' l'unica traccia che resta
        quando l'utente trova il reauth al mattino.
        """
        try:
            self._tokens = await self._auth.refresh(
                self._user_id, self._tokens.refresh_token
            )
            return True
        except Exception as err:  # noqa: BLE001 — qualsiasi fallimento significa "rifai il login"
            if self._credentials is None:
                _LOGGER.warning(
                    "Rinnovo del token fallito (%s) e password non salvata: "
                    "serve un nuovo accesso",
                    err,
                )
                return False
            _LOGGER.info(
                "Rinnovo del token fallito (%s): rifaccio il login con la "
                "password salvata",
                err,
            )

        try:
            self._tokens = await self._auth.login(
                self._credentials.username, self._credentials.password
            )
        except Exception as err:  # noqa: BLE001 — password cambiata o backend giu'
            _LOGGER.warning("Login automatico fallito: %s", err)
            return False
        return True

    async def list_devices(self) -> list[Device]:
        payload = await self._device_http.request(PATH_DEVICE_LIST)
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
        summaries = []
        for item in items:
            template_type = int(item.get("templateType", 0))
            sort_order = int(item.get("sortOrder", 0))
            summaries.append(
                TemplateSummary(
                    template_id=int(item["templateId"]),
                    name=str(item.get("name", "")),
                    page_slot=sort_order_to_page_slot(sort_order, template_type),
                    template_type=template_type,
                )
            )
        return summaries

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

    async def get_home_page_config(self, device_id: str) -> dict[str, Any]:
        """Da dove il pannello prende la home: `pageSource` "web" o "app"."""
        payload = await self._http.request(PATH_HOMEPAGE_INFO, {"deviceID": device_id})
        return payload or {}

    async def set_home_page_web(self, device_id: str, template_id: int) -> None:
        """Fa mostrare al pannello il template indicato come home."""
        await self._http.request(
            PATH_HOMEPAGE_SAVE,
            {"deviceID": device_id, "pageSource": "web", "templateID": template_id},
        )

    async def list_pages(self, device_id: str) -> list[dict[str, Any]]:
        """Le pagine del page manager, cosi' come arrivano dal backend."""
        payload = await self._http.request(PATH_PAGES_LIST, {"deviceID": device_id})
        return (payload or {}).get("list") or [] if isinstance(payload, dict) else []
