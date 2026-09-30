"""Polite HTTP access layer shared by every scraper.

The project's data rules require honouring ``robots.txt``, pausing a random amount of
time between requests, sending an identifiable user-agent and avoiding aggressive
parallelism. Those rules live here, in a single client, so that no scraper can bypass
them by accident.
"""

import random
import ssl
import time
from types import TracebackType
from typing import Self
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

import httpx
import truststore

from autovalor.config import Settings, get_settings

DEFAULT_TIMEOUT = 20.0
"""Per-request timeout in seconds."""

MAX_ATTEMPTS = 4
"""Total attempts per URL, including the first one."""

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
"""Status codes worth retrying with backoff; anything else fails immediately."""

_ALLOW_ALL = ("User-agent: *", "Allow: /")
_DISALLOW_ALL = ("User-agent: *", "Disallow: /")


class RobotsDisallowedError(RuntimeError):
    """Raised when ``robots.txt`` forbids fetching a URL."""

    def __init__(self, url: str) -> None:
        """Record the URL that was refused."""
        super().__init__(f"robots.txt disallows fetching {url}")
        self.url = url


class RetryableStatusError(RuntimeError):
    """Raised for a response worth retrying, so tenacity can back off."""

    def __init__(self, url: str, status_code: int) -> None:
        """Record the URL and the status that triggered the retry."""
        super().__init__(f"{url} returned retryable status {status_code}")
        self.url = url
        self.status_code = status_code


def origin_of(url: str) -> str:
    """Return the ``scheme://host`` prefix of ``url``."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}"


def tls_verification(settings: Settings | None = None) -> ssl.SSLContext | bool:
    """Return the ``verify`` argument for httpx.

    Defaults to httpx's bundled CA set. On networks that inspect TLS the bundle does
    not contain the interception root, so ``AUTOVALOR_USE_SYSTEM_CERTS=true`` switches
    verification to the operating system store — still verified, just a different
    trust anchor.
    """
    config = settings if settings is not None else get_settings()
    if not config.use_system_certs:
        return True
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def build_http_client(settings: Settings | None = None) -> httpx.Client:
    """Return an httpx client with the identifiable user-agent and configured TLS."""
    config = settings if settings is not None else get_settings()
    return httpx.Client(
        headers={"User-Agent": config.scraper_user_agent},
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        verify=tls_verification(config),
    )


class RobotsPolicy:
    """Per-origin ``robots.txt`` cache.

    Follows RFC 9309 for unreachable files: a 4xx means "no rules published", so
    everything is allowed, while a 5xx or a network failure means the site is unhappy
    and we stay out entirely rather than guessing.
    """

    def __init__(
        self,
        user_agent: str,
        *,
        enabled: bool = True,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
        verify: ssl.SSLContext | bool = True,
    ) -> None:
        """Build a policy for ``user_agent``, optionally reusing an HTTP client."""
        self._user_agent = user_agent
        self._enabled = enabled
        self._timeout = timeout
        self._client = client
        self._verify = verify
        self._parsers: dict[str, RobotFileParser] = {}

    def can_fetch(self, url: str) -> bool:
        """Return whether ``url`` may be fetched with the configured user-agent."""
        if not self._enabled:
            return True
        return self._parser_for(url).can_fetch(self._user_agent, url)

    def crawl_delay(self, url: str) -> float | None:
        """Return the ``Crawl-delay`` advertised for our user-agent, if any."""
        if not self._enabled:
            return None
        delay = self._parser_for(url).crawl_delay(self._user_agent)
        return None if delay is None else float(delay)

    def _parser_for(self, url: str) -> RobotFileParser:
        origin = origin_of(url)
        if origin not in self._parsers:
            self._parsers[origin] = self._load(origin)
        return self._parsers[origin]

    def _load(self, origin: str) -> RobotFileParser:
        parser = RobotFileParser()
        try:
            response = self._fetch(f"{origin}/robots.txt")
        except httpx.HTTPError:
            parser.parse(_DISALLOW_ALL)
            return parser

        if response.status_code == httpx.codes.OK:
            parser.parse(response.text.splitlines())
        elif response.is_client_error:
            parser.parse(_ALLOW_ALL)
        else:
            parser.parse(_DISALLOW_ALL)
        return parser

    def _fetch(self, robots_url: str) -> httpx.Response:
        headers = {"User-Agent": self._user_agent}
        if self._client is not None:
            return self._client.get(robots_url, headers=headers, follow_redirects=True)
        return httpx.get(
            robots_url,
            headers=headers,
            timeout=self._timeout,
            follow_redirects=True,
            verify=self._verify,
        )


class PoliteClient:
    """HTTP client that throttles itself and refuses disallowed URLs.

    Example:
        >>> with PoliteClient() as client:  # doctest: +SKIP
        ...     html = client.get("https://carros.tucarro.com.co/").text
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        client: httpx.Client | None = None,
        robots: RobotsPolicy | None = None,
    ) -> None:
        """Build a client; injected ``client``/``robots`` are for tests and reuse."""
        self._settings = settings if settings is not None else get_settings()
        self._owns_client = client is None
        self._client = client if client is not None else self._build_client()
        self._robots = (
            robots
            if robots is not None
            else RobotsPolicy(
                self._settings.scraper_user_agent,
                enabled=self._settings.scraper_respect_robots,
                client=self._client,
            )
        )
        self._last_request_at: float | None = None

    def _build_client(self) -> httpx.Client:
        return build_http_client(self._settings)

    def get(self, url: str) -> httpx.Response:
        """Fetch ``url`` after checking robots.txt and waiting out the pause.

        Raises:
            RobotsDisallowedError: If ``robots.txt`` forbids the URL.
            httpx.HTTPStatusError: For non-retryable error responses.
            RetryableStatusError: If every retry of a 429/5xx was exhausted.
        """
        if not self._robots.can_fetch(url):
            raise RobotsDisallowedError(url)
        self._wait_turn(url)
        return self._get_with_retries(url)

    def _wait_turn(self, url: str) -> None:
        """Sleep so that consecutive requests are separated by a random pause."""
        # Jitter between requests, not a security decision: random.uniform is fine.
        pause = random.uniform(
            self._settings.scraper_min_delay_seconds,
            self._settings.scraper_max_delay_seconds,
        )
        advertised = self._robots.crawl_delay(url)
        if advertised is not None:
            pause = max(pause, advertised)

        if self._last_request_at is not None:
            pause -= time.monotonic() - self._last_request_at
        if pause > 0:
            time.sleep(pause)

    def _get_with_retries(self, url: str) -> httpx.Response:
        backoff = 1.0
        for attempt in range(1, MAX_ATTEMPTS + 1):
            self._last_request_at = time.monotonic()
            try:
                response = self._client.get(url)
            except httpx.TransportError:
                if attempt == MAX_ATTEMPTS:
                    raise
            else:
                if response.status_code not in RETRYABLE_STATUS:
                    response.raise_for_status()
                    return response
                if attempt == MAX_ATTEMPTS:
                    raise RetryableStatusError(url, response.status_code)
                backoff = max(backoff, _retry_after(response))

            time.sleep(backoff)
            backoff *= 2

        raise RetryableStatusError(url, 0)  # unreachable, keeps the type checker happy

    def close(self) -> None:
        """Close the underlying transport if this client owns it."""
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        """Enter the context manager."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the client on exit."""
        self.close()


def _retry_after(response: httpx.Response) -> float:
    """Return the ``Retry-After`` delay in seconds, or ``0`` when absent or relative."""
    raw = response.headers.get("Retry-After")
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0
