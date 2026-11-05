"""
Test per geo_optimizer.utils.http_async.

Verifica fetch_url_async e fetch_urls_async con mock httpx completi.
Zero calls HTTP reali — tutto simulato con unittest.mock.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from urllib.parse import urlparse

import pytest

# Skip se httpx non disponibile
pytest.importorskip("httpx", reason="httpx non installato (pip install httpx)")

from geo_optimizer.utils.http import MAX_RESPONSE_SIZE, _pinned_getaddrinfo, _pinning_ctx
from geo_optimizer.utils.http_async import _MAX_REDIRECTS, fetch_url_async, fetch_urls_async


@pytest.fixture(autouse=True)
def _mock_async_url_validation(monkeypatch):
    """Rende deterministica la validazione URL nei test async offline."""

    def _fake_resolve(url):
        host = (urlparse(url).hostname or "").lower()
        if host.endswith("example.com"):
            return True, None, ["93.184.216.34"]
        if host in {"localhost", "192.168.1.1", "10.0.0.1", "127.0.0.1"}:
            return False, "blocked for test", []
        return True, None, ["93.184.216.34"]

    def _fake_validate(url):
        ok, reason, _ips = _fake_resolve(url)
        return ok, reason

    monkeypatch.setattr("geo_optimizer.utils.validators.resolve_and_validate_url", _fake_resolve)
    monkeypatch.setattr("geo_optimizer.utils.http_async.resolve_and_validate_url", _fake_resolve, raising=False)
    monkeypatch.setattr("geo_optimizer.utils.validators.validate_public_url", _fake_validate)


# ─── Helper: response httpx mock ─────────────────────────────────────────────


def _mock_response(
    status_code: int = 200, content: bytes = b"<html>ok</html>", headers: dict | None = None
) -> MagicMock:
    """Costruisce un mock di httpx.Response con i campi necessari."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.content = content
    resp.text = content.decode("utf-8", errors="replace")
    resp.headers = headers or {}
    return resp


# ─── Test: fetch_url_async — happy path ──────────────────────────────────────


def test_fetch_url_async_happy_path_restituisce_risposta_e_none():
    """fetch_url_async with a public URL and 200 response returns (response, None)."""
    # Arrange
    mock_resp = _mock_response(200, b"<html>Ciao</html>")

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client._transport = MagicMock()  # impedisce la creazione di un nuovo client
            mock_client_cls.return_value = mock_client
            mock_client.aclose = AsyncMock()

            resp, err = await fetch_url_async("https://example.com", client=mock_client)

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert err is None
    assert resp is mock_resp


def test_fetch_url_async_happy_path_proprio_client_creato():
    """fetch_url_async without an external client creates its own httpx.AsyncClient."""
    # Arrange
    mock_resp = _mock_response(200, b"<html>Ok</html>")

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=mock_resp)
            mock_client_inst.aclose = AsyncMock()
            # Missing attribute: forces creation of a new client
            del mock_client_inst._transport
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert err is None
    assert resp is mock_resp


def test_patched_resolver_uses_async_context_pin():
    token = _pinning_ctx.set({"host": "example.com", "ip": "93.184.216.34", "port": 443})
    try:
        infos = _pinned_getaddrinfo("example.com", 443)
    finally:
        _pinning_ctx.reset(token)

    assert infos[0][4][0] == "93.184.216.34"


def test_fetch_url_async_updates_dns_pin_after_safe_redirect():
    redirect_resp = _mock_response(status_code=302, headers={"location": "https://redirect.example.com/final"})
    final_resp = _mock_response(status_code=200, content=b"ok")
    pins_seen = []

    def _resolve(url):
        host = (urlparse(url).hostname or "").lower()
        if host == "redirect.example.com":
            return True, None, ["93.184.216.35"]
        return True, None, ["93.184.216.34"]

    async def _run():
        with patch("geo_optimizer.utils.validators.resolve_and_validate_url", side_effect=_resolve):
            mock_client = AsyncMock()

            async def _get(url):
                pin = _pinning_ctx.get()
                pins_seen.append((url, pin["ip"] if pin else ""))
                return redirect_resp if len(pins_seen) == 1 else final_resp

            mock_client.get = AsyncMock(side_effect=_get)
            mock_client.aclose = AsyncMock()
            return await fetch_url_async("https://example.com", client=mock_client)

    resp, err = asyncio.run(_run())

    assert err is None
    assert resp is final_resp
    assert pins_seen == [
        ("https://example.com", "93.184.216.34"),
        ("https://redirect.example.com/final", "93.184.216.35"),
    ]


# ─── Test: SSRF — URL iniziale non sicuro ─────────────────────────────────────


def test_fetch_url_async_url_private_restituisce_errore():
    """fetch_url_async blocks URLs pointing to private IPs before fetching."""
    # Arrange / Act
    resp, err = asyncio.run(fetch_url_async("http://192.168.1.1"))

    # Assert
    assert resp is None
    assert err is not None
    assert "Unsafe URL" in err


# ─── Test: redirect verso IP private (SSRF su redirect) ──────────────────────


def test_fetch_url_async_redirect_verso_ip_private_restituisce_errore():
    """fetch_url_async blocks redirects pointing to internal networks (anti-SSRF)."""
    # Arrange
    redirect_resp = _mock_response(
        status_code=301,
        headers={"location": "http://10.0.0.1/secret"},
    )

    async def _run():
        # Prima validazione: URL pubblico ok
        # Seconda validazione (redirect target): non sicuro
        validate_results = [(True, None), (False, "Private IP")]
        call_count = 0

        def _validate(url):
            nonlocal call_count
            result = validate_results[min(call_count, len(validate_results) - 1)]
            call_count += 1
            return result

        with (
            patch("geo_optimizer.utils.validators.validate_public_url", side_effect=_validate),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=redirect_resp)
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert "unsafe" in err.lower() or "Redirect" in err


# ─── Test: troppi redirect ────────────────────────────────────────────────────


def test_fetch_url_async_troppi_redirect_restituisce_errore():
    """fetch_url_async restituisce errore dopo il numero massimo di redirect."""
    # Arrange: every response is a valid redirect to itself
    redirect_resp = _mock_response(
        status_code=302,
        headers={"location": "https://example.com/next"},
    )

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            # Always returns redirect — forces limit to be exceeded
            mock_client_inst.get = AsyncMock(return_value=redirect_resp)
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert str(_MAX_REDIRECTS) in err


# ─── Test: redirect senza Location header ─────────────────────────────────────


def test_fetch_url_async_redirect_senza_location_restituisce_errore():
    """fetch_url_async handles redirects without a Location header."""
    # Arrange
    redirect_resp = _mock_response(status_code=301, headers={})

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=redirect_resp)
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert "Location" in err or "location" in err.lower()


# ─── Test: TimeoutException ───────────────────────────────────────────────────


def test_fetch_url_async_timeout_restituisce_errore_con_secondi():
    """fetch_url_async handles httpx.TimeoutException and includes the seconds."""
    import httpx

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com", timeout=10)

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert "10s" in err or "Timeout" in err


# ─── Test: ConnectError ───────────────────────────────────────────────────────


def test_fetch_url_async_connect_error_restituisce_errore():
    """fetch_url_async handles httpx.ConnectError."""
    import httpx

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert "Connection" in err or "connect" in err.lower()


# ─── Test: response troppo grande (body) ──────────────────────────────────────


def test_fetch_url_async_risposta_troppo_grande_restituisce_errore():
    """fetch_url_async rifiuta risposte con body superiore a max_size."""
    # Arrange: content > max_size
    corpo_enorme = b"x" * (MAX_RESPONSE_SIZE + 1)
    mock_resp = _mock_response(200, corpo_enorme)

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=mock_resp)
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert "too large" in err.lower() or "large" in err.lower()


# ─── Test: response troppo grande (Content-Length header) ─────────────────────


def test_fetch_url_async_content_length_troppo_grande_restituisce_errore():
    """fetch_url_async rifiuta risposte con Content-Length > max_size."""
    # Arrange: content piccolo ma Content-Length dichiarato enorme
    mock_resp = _mock_response(
        200,
        b"piccolo",
        headers={"content-length": str(MAX_RESPONSE_SIZE + 1)},
    )

    async def _run():
        with (
            patch("geo_optimizer.utils.validators.validate_public_url", return_value=(True, None)),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=mock_resp)
            mock_client_inst.aclose = AsyncMock()
            mock_client_cls.return_value = mock_client_inst

            resp, err = await fetch_url_async("https://example.com")

        return resp, err

    resp, err = asyncio.run(_run())

    # Assert
    assert resp is None
    assert err is not None
    assert "too large" in err.lower() or "large" in err.lower()


# ─── Test: fetch_urls_async — mix successo/fallimento ─────────────────────────


def test_fetch_urls_async_mix_successo_e_fallimento():
    """fetch_urls_async correctly handles URLs that succeed and URLs that fail."""
    # Arrange
    mock_resp_ok = _mock_response(200, b"<html>Ok</html>")

    # URL di test
    url_ok = "https://example.com"
    url_private = "http://127.0.0.1"

    async def _run():
        # validate_public_url: ok per example.com, fails per 127.0.0.1
        def _validate(url):
            if "127.0.0.1" in url:
                return False, "Private IP"
            return True, None

        with (
            patch("geo_optimizer.utils.validators.validate_public_url", side_effect=_validate),
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_client_inst = AsyncMock()
            mock_client_inst.get = AsyncMock(return_value=mock_resp_ok)
            mock_client_inst.aclose = AsyncMock()
            # Supporta context manager
            mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
            mock_client_inst.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_inst

            results = await fetch_urls_async([url_ok, url_private])

        return results

    results = asyncio.run(_run())

    # Assert
    assert url_ok in results
    assert url_private in results

    # URL pubblico: successo
    resp_ok, err_ok = results[url_ok]
    assert err_ok is None
    assert resp_ok is not None

    # URL private: fallimento per SSRF
    resp_fail, err_fail = results[url_private]
    assert resp_fail is None
    assert err_fail is not None
    assert "Unsafe URL" in err_fail


def test_fetch_urls_async_lista_vuota_restituisce_dict_vuoto():
    """fetch_urls_async con lista vuota restituisce dizionario vuoto."""

    async def _run():
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client_inst = AsyncMock()
            mock_client_inst.__aenter__ = AsyncMock(return_value=mock_client_inst)
            mock_client_inst.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_client_inst

            return await fetch_urls_async([])

    results = asyncio.run(_run())

    # Assert
    assert results == {}
