import urllib.request

import pytest

import geoip


class _FakeResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


def test_ip_lookup_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(b"FI\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert geoip._ip_lookup("1.1.1.1") == "FI"


def test_ip_lookup_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_urlopen(url: str, timeout: float) -> _FakeResponse:
        return _FakeResponse(b"not-a-country\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert geoip._ip_lookup("2.2.2.2") is None


def test_ip_lookup_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_urlopen(url: str, timeout: float) -> _FakeResponse:
        calls.append(url)
        return _FakeResponse(b"FI\n")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    assert geoip._ip_lookup("3.3.3.3") == "FI"
    assert geoip._ip_lookup("3.3.3.3") == "FI"
    assert len(calls) == 1
