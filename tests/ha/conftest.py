"""Fixture per i soli test che hanno bisogno di un'istanza di Home Assistant."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Consente a Home Assistant di caricare custom_components nei test."""
    yield
