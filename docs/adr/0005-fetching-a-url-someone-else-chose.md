# 0005: Recipe import connects to the address it checked

## Context

Import fetches a page from a link the user pastes. A server that fetches
arbitrary URLs can be pointed at its own network: cloud metadata, a
database, an admin port (server-side request forgery). Checking the
hostname's address first is not enough: DNS can answer the check with a
public address and the connection with a private one (DNS rebinding).

## Decision

`app/fetch.py` resolves the name, refuses unless every address is public
(private, loopback, link-local, carrier-grade NAT, reserved, multicast and
IPv4-mapped forms all refused), then **connects to the address it checked**,
sending the name as the Host header and as the TLS server name, so the
certificate is still verified. Redirects are followed by hand, each checked
the same way, up to five. http and https only; 5 seconds, 2 MB and HTML
only; 20 imports per user per hour, failures included.

## Alternatives rejected

- **An allowlist of recipe sites.** Safe, but most links would be refused.
- **Check, then let the HTTP client resolve again.** The rebinding gap.

## Consequences

- Each refusal is a test that never touches the network
  (`tests/test_fetch.py`), and live sites were checked by hand.
- Sites that refuse non-browser clients get a plain message suggesting
  paste. The client never pretends to be a browser.
