"""Security headers on every API response.

The API only ever returns JSON, so its policy can be stricter than the web
page's: nothing it sends should be rendered, framed, sniffed into another
type, or cached. Set here rather than left to the platform, so the rules
travel with the code, are tested, and hold wherever the app runs.

The web page has its own policy, in ``vercel.json``: in production the page
is served by Vercel's CDN, not by this app, so that is the only place its
headers can be set. ``tests/test_security_headers.py`` checks both.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

API_SECURITY_HEADERS: dict[str, str] = {
    # Nothing in a response may load or run anything, and no page, ours or
    # anyone's, may frame it.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    # A response is exactly the type it says (JSON), never guessed at.
    "X-Content-Type-Options": "nosniff",
    # frame-ancestors' predecessor, for browsers that predate it.
    "X-Frame-Options": "DENY",
    # Requests from here tell other sites nothing about where they came from.
    "Referrer-Policy": "no-referrer",
    # Other sites cannot embed a response (say, as an image or script) to
    # read it with the visitor's cookies.
    "Cross-Origin-Resource-Policy": "same-origin",
    # Responses are one person's data, read with their session cookie: never
    # kept by a shared cache, or by the browser for the back button.
    "Cache-Control": "no-store",
}


class SecurityHeadersMiddleware:
    """Add ``API_SECURITY_HEADERS`` to every HTTP response.

    Pure ASGI, like the request-id middleware, and installed outside the
    error handling, so a 500 written there carries the headers too. A header
    a route sets itself is left as the route set it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in API_SECURITY_HEADERS.items():
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
