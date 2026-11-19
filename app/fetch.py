"""Fetching a web page someone asked for, without letting them aim the
server at anything they could not reach themselves.

A URL from a user, fetched by the server, is the classic server-side
request forgery: "http://169.254.169.254/" asks a cloud's metadata service
for credentials, and "http://localhost:5432/" probes a database. So:

- **http and https only**, on any port, with no credentials in the URL.
- **Public addresses only.** Every address the name resolves to must be a
  global unicast address; one private, loopback, link-local, reserved,
  shared or multicast address refuses the URL.
- **The checked address is the one connected to.** The request goes to
  the IP that passed, with the name sent as the Host header and as the TLS
  server name, so the certificate is still verified against the name. A
  second DNS lookup at connect time could otherwise answer differently
  (DNS rebinding).
- **Every redirect is checked the same way**, at most five of them.
- **5 seconds in all, 2 MB at most, HTML only.** The body is read in
  chunks and abandoned the moment either limit passes, so a slow or huge
  answer costs at most that.

Every refusal raises FetchRefused with a sentence for the person.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass

import httpx

MAX_BYTES = 2_000_000
TIMEOUT_SECONDS = 5.0
MAX_REDIRECTS = 5
_REDIRECTS = {301, 302, 303, 307, 308}
_HTML = {"text/html", "application/xhtml+xml"}
#: Says what is asking, as a polite client does. No contact details: the
#: request is made for whoever pasted the link.
USER_AGENT = "TheFridgeDoor/1.0 (recipe import; fetches one page a person linked)"

#: (host, port) -> every address the host resolves to.
Resolver = Callable[[str, int], Iterable[str]]


class FetchRefused(Exception):
    """The page was not fetched; the message says why, for the person."""


@dataclass(frozen=True, slots=True)
class Page:
    #: Where the page was finally found, after any redirects.
    url: str
    html: str


def fetch_page(
    url: str,
    *,
    resolve: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
    unchecked_origin: str | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Page:
    """Fetch an HTML page under the rules above.

    `unchecked_origin` ("http://127.0.0.1:4175") is one origin whose
    address is not checked, for the end-to-end tests' fixture server. The
    caller decides when that is allowed; never in production.
    `resolve`, `transport` and `clock` are for tests.
    """
    resolve = resolve or _resolve
    deadline = clock() + TIMEOUT_SECONDS
    current = _parse(url)

    with httpx.Client(transport=transport, follow_redirects=False) as client:
        for _ in range(MAX_REDIRECTS + 1):
            request = _pinned_request(client, current, resolve, unchecked_origin)
            remaining = deadline - clock()
            if remaining <= 0:
                raise FetchRefused("The page took too long to load.")
            request.extensions["timeout"] = httpx.Timeout(remaining).as_dict()
            try:
                response = client.send(request, stream=True)
            except httpx.TimeoutException:
                raise FetchRefused("The page took too long to load.") from None
            except httpx.HTTPError:
                raise FetchRefused("That site couldn't be reached.") from None

            try:
                location = response.headers.get("location")
                if response.status_code in _REDIRECTS and location:
                    current = _parse(str(current.join(location)))
                    continue
                return Page(str(current), _read(response, deadline, clock))
            finally:
                response.close()

    raise FetchRefused("That link redirects too many times.")


def _parse(url: str) -> httpx.URL:
    try:
        parsed = httpx.URL(url.strip())
    except httpx.InvalidURL:
        raise FetchRefused("That isn't a web address.") from None
    if parsed.scheme not in {"http", "https"} or not parsed.host:
        raise FetchRefused("Use a link that starts with http:// or https://.")
    if parsed.userinfo:
        raise FetchRefused("Use a link without a username or password in it.")
    return parsed


def _pinned_request(
    client: httpx.Client,
    url: httpx.URL,
    resolve: Resolver,
    unchecked_origin: str | None,
) -> httpx.Request:
    """A request to `url`, addressed to an IP that has passed the check."""
    port = url.port or (443 if url.scheme == "https" else 80)
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    if unchecked_origin and _origin(url) == unchecked_origin.rstrip("/"):
        return client.build_request("GET", url, headers=headers)

    address = _public_address(url.host, port, resolve)
    # The name, as the site expects it, goes in Host (with a port only if
    # it is not the default) and as the TLS server name.
    headers["Host"] = url.netloc.decode("ascii")
    request = client.build_request(
        "GET", url.copy_with(host=str(address)), headers=headers
    )
    if url.scheme == "https":
        request.extensions["sni_hostname"] = url.host
    return request


def _public_address(
    host: str, port: int, resolve: Resolver
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        addresses = [ipaddress.ip_address(a) for a in resolve(host, port)]
    except (OSError, ValueError):
        raise FetchRefused("That site couldn't be found.") from None
    if not addresses:
        raise FetchRefused("That site couldn't be found.")
    # Every one, not just the first: which one a connection would use is
    # not up to us, so one private answer is enough to refuse.
    if not all(_is_public(a) for a in addresses):
        raise FetchRefused("That address can't be fetched from here.")
    return addresses[0]


def _is_public(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    return address.is_global and not address.is_multicast


def _resolve(host: str, port: int) -> list[str]:
    return [
        str(info[4][0])
        for info in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    ]


def _origin(url: httpx.URL) -> str:
    port = f":{url.port}" if url.port else ""
    return f"{url.scheme}://{url.host}{port}"


def _read(response: httpx.Response, deadline: float, clock: Callable[[], float]) -> str:
    if response.status_code >= 400:
        raise FetchRefused(f"The site answered with an error ({response.status_code}).")
    if response.status_code != 200:
        raise FetchRefused("The site didn't send a page.")
    media_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type not in _HTML:
        raise FetchRefused("That link isn't a web page.")
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BYTES:
        raise FetchRefused("That page is too large to read.")

    body = bytearray()
    try:
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_BYTES:
                raise FetchRefused("That page is too large to read.")
            if clock() > deadline:
                raise FetchRefused("The page took too long to load.")
    except httpx.TimeoutException:
        raise FetchRefused("The page took too long to load.") from None
    except httpx.HTTPError:
        raise FetchRefused("The page stopped loading part-way.") from None
    try:
        return body.decode(response.encoding or "utf-8", errors="replace")
    except LookupError:  # a charset Python has never heard of
        return body.decode("utf-8", errors="replace")
