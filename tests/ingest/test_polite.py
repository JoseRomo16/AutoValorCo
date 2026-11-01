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
    VerificationWallError,
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


def wall_handler(location: str, *, status_code: int = 302) -> Handler:
    """Answer robots.txt normally and redirect every page to ``location``."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if str(request.url) == location:
            # What the wall actually serves: a 200 with a page asking for verification.
            return httpx.Response(200, text="<html>verifica tu cuenta</html>")
        return httpx.Response(status_code, headers={"Location": location})

    return handler


def test_detects_the_verification_wall(settings: Settings) -> None:
    """The 2026-10-26 shape: 302 to /gz/account-verification, which then answers 200."""
    wall = "https://www.mercadolibre.com.co/gz/account-verification"
    with (
        build_client(settings, wall_handler(wall)) as client,
        pytest.raises(VerificationWallError) as caught,
    ):
        client.get(PAGE)

    assert caught.value.url == PAGE
    assert caught.value.final_url == wall


def test_the_wall_is_not_a_recoverable_error(settings: Settings) -> None:
    """Scrapers skip a location on these; the wall must not be mistaken for one."""
    wall = "https://www.mercadolibre.com.co/gz/account-verification"
    with build_client(settings, wall_handler(wall)) as client:
        try:
            client.get(PAGE)
        except VerificationWallError as error:
            assert not isinstance(error, httpx.HTTPError | RetryableStatusError)
            assert not isinstance(error, RobotsDisallowedError)
        else:
            pytest.fail("the wall was not reported")


def test_detects_the_wall_without_a_redirect(settings: Settings) -> None:
    """Asking for the verification URL directly is still the wall, with no history."""
    wall = f"{ORIGIN}/gz/account-verification"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="<html>verifica</html>")

    with build_client(settings, handler) as client, pytest.raises(VerificationWallError):
        client.get(wall)


def test_detects_a_hop_onto_mercadolibre_without_a_marker(settings: Settings) -> None:
    """The host change alone is enough: the wall may move off these two paths."""
    elsewhere = "https://www.mercadolibre.com.co/alguna-pantalla"
    with (
        build_client(settings, wall_handler(elsewhere)) as client,
        pytest.raises(VerificationWallError),
    ):
        client.get(PAGE)


def test_the_wall_is_not_retried(settings: Settings) -> None:
    """A wall that is retried four times is four requests to a site that said no."""
    attempts = {"count": 0}
    wall = "https://www.mercadolibre.com.co/gz/account-verification"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if str(request.url) == wall:
            return httpx.Response(200, text="verifica")
        attempts["count"] += 1
        return httpx.Response(302, headers={"Location": wall})

    with build_client(settings, handler) as client, pytest.raises(VerificationWallError):
        client.get(PAGE)
    assert attempts["count"] == 1


def test_a_normal_page_is_not_a_wall(settings: Settings) -> None:
    """A redirect inside tucarro.com.co is ordinary and must keep working."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        if request.url.path == "/vehiculos":
            return httpx.Response(301, headers={"Location": f"{ORIGIN}/vehiculos/"})
        return httpx.Response(200, text="<html>listing</html>")

    with build_client(settings, handler) as client:
        assert client.get(PAGE).text == "<html>listing</html>"


def test_a_request_that_starts_on_mercadolibre_is_not_a_wall(settings: Settings) -> None:
    """The host rule is about being *sent* there, not about the host itself."""
    page = "https://articulo.mercadolibre.com.co/MCO-123"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text="<html>listing</html>")

    with build_client(settings, handler) as client:
        assert client.get(page).status_code == 200


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
