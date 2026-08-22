"""Utilità condivise dai test dello strato API."""
from __future__ import annotations


def response_sequence(*responses):
    """Restituisce risposte diverse a chiamate successive sullo stesso URL."""
    iterator = iter(responses)

    async def _side_effect(method, url, data):
        return next(iterator)

    return _side_effect
