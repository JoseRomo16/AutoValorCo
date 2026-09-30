"""Tests for the polite HTTP layer: robots.txt, pauses and retries."""

from collections.abc import Callable

import httpx
import pytest

from autovalor.config import Settings
from autovalor.ingest.polite import (
    PoliteClient,
    RetryableStatusError,
    RobotsDisallowedError,
    RobotsPolicy,
)

ORIGIN = "https://carros.tucarro.com.co"
PAGE = f"{ORIGIN}/vehiculos"
ROBOTS = f"{ORIGIN}/robots.txt"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the suite fast: pauses are asserted through behaviour, not wall clock."""
    monkeypatch.setattr("autovalor.ingest.polite.time.sleep", lambda _seconds: None)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        scraper_min_delay_seconds=0.0,
        scraper_max_delay_seconds=0.0,
    )


def build_client(settings: Settings, handler: Handler) -> PoliteClient:
    transport = httpx.MockTransport(handler)
    http = httpx.Client(
        transport=transport,
        headers={"User-Agent": settings.scraper_user_agent},
        follow_redirects=True,
    )
    return PoliteClient(settings, client=http)


def robots_handler(body: str, *, status_code: int = 200) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(status_code, text=body)
        return httpx.Response(200, text="<html>listing</html>")

    return handler


def test_fetches_allowed_url(settings: Settings) -> None:
    with build_client(settings, robots_handler("User-agent: *\nAllow: /")) as client:
        assert client.get(PAGE).text == "<html>listing</html>"


def test_refuses_disallowed_url(settings: Settings) -> None:
    disallow = "User-agent: *\nDisallow: /vehiculos"
    with (
        build_client(settings, robots_handler(disallow)) as client,
        pytest.raises(RobotsDisallowedError),
    ):
        client.get(PAGE)


def test_missing_robots_means_no_rules(settings: Settings) -> None:
    """A 404 on robots.txt is 'nothing published', so crawling is allowed."""
    with build_client(settings, robots_handler("", status_code=404)) as client:
        assert client.get(PAGE).status_code == 200


def test_unavailable_robots_fails_closed(settings: Settings) -> None:
    """A 5xx means the site is struggling: stay out instead of guessing."""
    with (
        build_client(settings, robots_handler("", status_code=503)) as client,
        pytest.raises(RobotsDisallowedError),
    ):
        client.get(PAGE)


def test_unreachable_robots_fails_closed(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with build_client(settings, handler) as client, pytest.raises(RobotsDisallowedError):
        client.get(PAGE)


def test_robots_is_fetched_once_per_origin(settings: Settings) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="ok")

    with build_client(settings, handler) as client:
        client.get(PAGE)
        client.get(f"{ORIGIN}/otra-pagina")

    assert calls.count("/robots.txt") == 1


def test_sends_identifiable_user_agent(settings: Settings) -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers["User-Agent"])
        return httpx.Response(200, text="User-agent: *\nAllow: /")

    with build_client(settings, handler) as client:
        client.get(PAGE)

    assert all("AutoValorCO" in agent for agent in seen)


def test_retries_retryable_status_then_succeeds(settings: Settings) -> None:
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503, text="try later")
        return httpx.Response(200, text="finally")

    with build_client(settings, handler) as client:
        assert client.get(PAGE).text == "finally"
    assert attempts["count"] == 3


def test_gives_up_after_max_attempts(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(429, text="slow down")

    with build_client(settings, handler) as client, pytest.raises(RetryableStatusError):
        client.get(PAGE)


def test_does_not_retry_client_errors(settings: Settings) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(404, text="gone")

    with build_client(settings, handler) as client, pytest.raises(httpx.HTTPStatusError):
        client.get(PAGE)


def test_honours_crawl_delay() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nAllow: /\nCrawl-delay: 10")

    policy = RobotsPolicy(
        "AutoValorCO/0.1",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert policy.crawl_delay(PAGE) == 10.0


def test_policy_can_be_disabled_explicitly() -> None:
    """Opting out is possible but must be deliberate, e.g. against a local fixture."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="User-agent: *\nDisallow: /")

    policy = RobotsPolicy(
        "AutoValorCO/0.1",
        enabled=False,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    assert policy.can_fetch(PAGE) is True
    assert policy.crawl_delay(PAGE) is None
