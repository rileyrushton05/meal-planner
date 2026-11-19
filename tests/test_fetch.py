"""Fetching a page someone linked (app/fetch.py), without the network.

DNS is a dictionary and HTTP is an httpx.MockTransport, so every refusal
is tested exactly: what reaches the "network" is what the fetcher sent.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import httpx
import pytest

from app.fetch import MAX_BYTES, FetchRefused, fetch_page

PUBLIC = "93.184.216.34"
PAGE = "<html><body>A recipe</body></html>"

DNS = {
    "recipes.example": [PUBLIC],
    "other.example": ["203.0.114.7"],  # not documentation space: global
    "intranet.example": ["10.0.0.5"],
    "metadata.example": ["169.254.169.254"],
    "loopback.example": ["127.0.0.1"],
    "v6-loopback.example": ["::1"],
    "mapped.example": ["::ffff:127.0.0.1"],
    "mixed.example": [PUBLIC, "192.168.1.1"],
    "v6.example": ["2606:4700::6810:84e5"],
}


def resolve(host: str, port: int) -> list[str]:
    if host in DNS:
        return DNS[host]
    try:  # an IP literal resolves to itself
        import ipaddress

        return [str(ipaddress.ip_address(host))]
    except ValueError:
        raise OSError("no such host") from None


def html(body: str = PAGE, **headers: str) -> httpx.Response:
    return httpx.Response(
        200, headers={"content-type": "text/html; charset=utf-8", **headers}, text=body
    )


class Network:
    """Answers by the Host the request names, and keeps every request."""

    def __init__(self, routes: dict[str, Callable[[httpx.Request], httpx.Response]]):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.routes[request.headers["host"]](request)


def fetch(url: str, network: Network, **options) -> str:
    return fetch_page(
        url, resolve=resolve, transport=httpx.MockTransport(network), **options
    ).html


# --- What is fetched ----------------------------------------------------------------


def test_a_public_page_is_fetched() -> None:
    network = Network({"recipes.example": lambda r: html()})

    assert fetch("https://recipes.example/soup", network) == PAGE


def test_the_address_checked_is_the_address_connected_to() -> None:
    """Not a second lookup at connect time, which could answer differently."""
    network = Network({"recipes.example": lambda r: html()})

    fetch("https://recipes.example/soup?x=1", network)

    (request,) = network.requests
    assert request.url.host == PUBLIC
    assert request.url.path == "/soup"
    assert request.headers["host"] == "recipes.example"
    # The certificate is checked against the name, not the address.
    assert request.extensions["sni_hostname"] == "recipes.example"


def test_an_ipv6_site_is_fetched_by_its_address() -> None:
    network = Network({"v6.example": lambda r: html()})

    fetch("https://v6.example/", network)

    assert network.requests[0].url.host == "2606:4700::6810:84e5"


def test_a_port_other_than_the_default_is_kept() -> None:
    network = Network({"recipes.example:8443": lambda r: html()})

    fetch("https://recipes.example:8443/", network)

    assert network.requests[0].url.port == 8443


def test_the_request_says_what_is_asking() -> None:
    network = Network({"recipes.example": lambda r: html()})

    fetch("https://recipes.example/", network)

    assert "TheFridgeDoor" in network.requests[0].headers["user-agent"]


def test_a_redirect_to_a_public_page_is_followed() -> None:
    network = Network(
        {
            "recipes.example": lambda r: httpx.Response(
                301, headers={"location": "https://other.example/soup"}
            ),
            "other.example": lambda r: html("moved"),
        }
    )

    page = fetch_page(
        "https://recipes.example/old",
        resolve=resolve,
        transport=httpx.MockTransport(network),
    )

    assert (page.url, page.html) == ("https://other.example/soup", "moved")


def test_a_relative_redirect_stays_on_the_site() -> None:
    def site(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/old":
            return httpx.Response(302, headers={"location": "/new"})
        return html("new")

    page = fetch_page(
        "https://recipes.example/old",
        resolve=resolve,
        transport=httpx.MockTransport(Network({"recipes.example": site})),
    )

    assert page.url == "https://recipes.example/new"


# --- What is refused ----------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://intranet.example/",
        "http://metadata.example/latest/meta-data/",
        "http://loopback.example:5432/",
        "http://v6-loopback.example/",
        "http://mapped.example/",
        "http://mixed.example/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/",
        "http://10.1.2.3/",
        "http://100.64.0.1/",  # carrier-grade NAT
        "http://0.0.0.0/",
        "http://224.0.0.1/",
    ],
)
def test_a_private_address_is_refused_before_any_request(url) -> None:
    network = Network({})

    with pytest.raises(FetchRefused, match="can't be fetched from here"):
        fetch(url, network)
    assert network.requests == []


def test_a_redirect_to_a_private_address_is_refused() -> None:
    network = Network(
        {
            "recipes.example": lambda r: httpx.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
        }
    )

    with pytest.raises(FetchRefused, match="can't be fetched from here"):
        fetch("https://recipes.example/", network)
    assert len(network.requests) == 1


def test_endless_redirects_are_refused() -> None:
    network = Network(
        {"recipes.example": lambda r: httpx.Response(302, headers={"location": "/"})}
    )

    with pytest.raises(FetchRefused, match="redirects too many times"):
        fetch("https://recipes.example/", network)
    assert len(network.requests) == 6


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("file:///etc/passwd", "starts with http"),
        ("ftp://recipes.example/", "starts with http"),
        ("gopher://recipes.example/", "starts with http"),
        ("javascript:alert(1)", "starts with http"),
        ("recipes.example/soup", "starts with http"),
        ("https://user:secret@recipes.example/", "without a username"),
        ("https://no-such-site.example/", "couldn't be found"),
        ("http://recipes.example:notaport/", "isn't a web address"),
        ("http://[not-an-address/", "couldn't be found"),
    ],
)
def test_links_that_are_not_public_web_pages_are_refused(url, message) -> None:
    with pytest.raises(FetchRefused, match=message):
        fetch(url, Network({}))


def test_an_oversized_body_is_refused_part_way() -> None:
    sent: list[int] = []

    def chunks() -> Iterator[bytes]:
        for _ in range(100):
            sent.append(1)
            yield b"x" * 100_000

    network = Network(
        {
            "recipes.example": lambda r: httpx.Response(
                200, headers={"content-type": "text/html"}, content=chunks()
            )
        }
    )

    with pytest.raises(FetchRefused, match="too large"):
        fetch("https://recipes.example/", network)
    # Stopped just past the limit, not after reading all 10 MB.
    assert len(sent) <= MAX_BYTES // 100_000 + 1


def test_an_oversized_body_it_announces_is_refused_unread() -> None:
    network = Network(
        {"recipes.example": lambda r: html(**{"content-length": str(MAX_BYTES + 1)})}
    )

    with pytest.raises(FetchRefused, match="too large"):
        fetch("https://recipes.example/", network)


@pytest.mark.parametrize(
    "content_type", ["application/json", "image/png", "application/pdf", ""]
)
def test_anything_but_html_is_refused(content_type) -> None:
    network = Network(
        {
            "recipes.example": lambda r: httpx.Response(
                200, headers={"content-type": content_type}, content=b"{}"
            )
        }
    )

    with pytest.raises(FetchRefused, match="isn't a web page"):
        fetch("https://recipes.example/", network)


def test_xhtml_counts_as_a_page() -> None:
    network = Network(
        {
            "recipes.example": lambda r: httpx.Response(
                200, headers={"content-type": "application/xhtml+xml"}, text=PAGE
            )
        }
    )

    assert fetch("https://recipes.example/", network) == PAGE


def test_a_timeout_is_refused() -> None:
    def slow(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(FetchRefused, match="too long"):
        fetch("https://recipes.example/", Network({"recipes.example": slow}))


def test_a_page_that_trickles_in_is_cut_off_at_five_seconds_in_all() -> None:
    """Each chunk arrives inside any per-read timeout, but the whole page
    must not take longer than five seconds."""
    now = [0.0]

    def trickle() -> Iterator[bytes]:
        for _ in range(100):
            now[0] += 1.0
            yield b"<p>"

    network = Network(
        {
            "recipes.example": lambda r: httpx.Response(
                200, headers={"content-type": "text/html"}, content=trickle()
            )
        }
    )

    with pytest.raises(FetchRefused, match="too long"):
        fetch("https://recipes.example/", network, clock=lambda: now[0])
    assert now[0] <= 6


@pytest.mark.parametrize(
    ("status", "message"),
    [
        (404, "no page at that link"),
        (500, r"error \(500\)"),
        # Real recipe sites answered 402 and 403 when tried, 2026-11-19.
        (402, "doesn't let apps read its recipes"),
        (403, "doesn't let apps read its recipes"),
        (429, "doesn't let apps read its recipes"),
    ],
)
def test_an_error_page_is_refused_and_says_what_to_do(status, message) -> None:
    network = Network({"recipes.example": lambda r: httpx.Response(status, text="no")})

    with pytest.raises(FetchRefused, match=message):
        fetch("https://recipes.example/", network)


def test_a_site_that_cannot_be_reached_is_refused() -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(FetchRefused, match="couldn't be reached"):
        fetch("https://recipes.example/", Network({"recipes.example": down}))


# --- The fixture server's exemption ---------------------------------------------------


def test_one_named_origin_may_skip_the_address_check() -> None:
    """For the end-to-end tests' local fixture server, and nothing else."""
    network = Network({"127.0.0.1:4175": lambda r: html()})

    fetch(
        "http://127.0.0.1:4175/recipe.html",
        network,
        unchecked_origin="http://127.0.0.1:4175",
    )

    with pytest.raises(FetchRefused):
        fetch(
            "http://127.0.0.1:4176/", network, unchecked_origin="http://127.0.0.1:4175"
        )
