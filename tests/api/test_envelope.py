"""Test delle funzioni pure di protocollo."""
from __future__ import annotations

import pytest

from custom_components.switchbot_eink.api.envelope import (
    build_auth_header,
    device_base_url,
    normalize_region,
    productbiz_base_url,
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


def test_auth_header_rimuove_bearer_anche_con_regione_maiuscola() -> None:
    assert build_auth_header("abc123", "Bearer", "EU") == "abc123"


def test_normalize_region_accetta_maiuscole_e_spazi() -> None:
    assert normalize_region(" EU ") == "eu"


def test_normalize_region_rifiuta_una_regione_sconosciuta() -> None:
    with pytest.raises(ValueError, match="sconosciuta"):
        normalize_region("xx")


def test_productbiz_base_url_interpola_la_regione() -> None:
    assert productbiz_base_url("eu") == "https://wonderlabs.eu.api.switchbot.net/productbiz"


def test_productbiz_base_url_ripiega_su_us_se_la_regione_e_ignota() -> None:
    assert productbiz_base_url("xx") == "https://wonderlabs.us.api.switchbot.net/productbiz"


def test_device_base_url_non_ha_il_suffisso_productbiz() -> None:
    """Il servizio dispositivi vive sull'host nudo: con /productbiz la rotta non esiste."""
    assert device_base_url("eu") == "https://wonderlabs.eu.api.switchbot.net"


def test_device_base_url_ripiega_su_us_se_la_regione_e_ignota() -> None:
    assert device_base_url("xx") == "https://wonderlabs.us.api.switchbot.net"


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
