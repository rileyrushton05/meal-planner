"""RFC 9457 Problem Details for every error the API returns.

Each error is ``application/problem+json`` with a stable ``type`` URN, a
short ``title``, the ``status``, a ``detail`` sentence written for the person
using the app, and the request path as ``instance``. Validation errors add
``invalid_params``. ``detail`` is what the frontend shows, so it is always a
complete sentence and never contains internals.

New ``type`` values are part of the API contract: add them, never rename them.
"""

from __future__ import annotations

import logging
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.exceptions import (
    AlreadySignedUpError,
    CrossSiteRequestError,
    DuplicateNameError,
    EmailTakenError,
    IngredientNotOnMealError,
    InvalidCredentialsError,
    InvalidDayError,
    InvalidEmailError,
    MealNotFoundError,
    MealPlannerError,
    NoLoginError,
    NotSignedInError,
    TooManyAttemptsError,
    UnitMismatchError,
    WeakPasswordError,
)

PROBLEM_MEDIA_TYPE = "application/problem+json"
_TYPE_PREFIX = "urn:meal-planner:problem:"

logger = logging.getLogger("meal_planner.api")


class InvalidParam(BaseModel):
    name: str
    reason: str


class Problem(BaseModel):
    """The body of every error response."""

    type: str
    title: str
    status: int
    detail: str
    instance: str
    invalid_params: list[InvalidParam] | None = None


def problem_type(slug: str) -> str:
    return f"{_TYPE_PREFIX}{slug}"


def problem_response(
    request: Request | str,
    *,
    status: int,
    slug: str,
    detail: str,
    title: str | None = None,
    invalid_params: list[InvalidParam] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """`request` may be the path itself, for callers below the routing layer
    that have an ASGI scope rather than a Request."""
    problem = Problem(
        type=problem_type(slug),
        title=title or HTTPStatus(status).phrase,
        status=status,
        detail=detail,
        instance=request if isinstance(request, str) else request.url.path,
        invalid_params=invalid_params,
    )
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


#: Domain error -> (status, type slug). The message the error carries is the
#: detail, verbatim: it was written for the user.
_DOMAIN_ERRORS: dict[type[MealPlannerError], tuple[int, str]] = {
    MealNotFoundError: (404, "meal-not-found"),
    IngredientNotOnMealError: (404, "ingredient-not-on-meal"),
    DuplicateNameError: (409, "duplicate-name"),
    UnitMismatchError: (409, "unit-mismatch"),
    InvalidDayError: (422, "invalid-day"),
    WeakPasswordError: (422, "weak-password"),
    InvalidEmailError: (422, "invalid-email"),
    NotSignedInError: (401, "not-signed-in"),
    InvalidCredentialsError: (401, "invalid-credentials"),
    CrossSiteRequestError: (403, "cross-site-request"),
    EmailTakenError: (409, "email-taken"),
    AlreadySignedUpError: (409, "already-signed-up"),
    NoLoginError: (409, "no-login"),
    TooManyAttemptsError: (429, "too-many-attempts"),
}

#: Shown for any validation failure. Field-level reasons are in
#: invalid_params, for clients that want them.
_VALIDATION_DETAIL = "Some of those values aren't valid. Check them and try again."


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, MealPlannerError)
    status, slug = next(
        (mapping for kind, mapping in _DOMAIN_ERRORS.items() if isinstance(exc, kind)),
        (400, "domain-error"),
    )
    headers = (
        {"Retry-After": str(exc.retry_after_seconds)}
        if isinstance(exc, TooManyAttemptsError)
        else None
    )
    return problem_response(
        request, status=status, slug=slug, detail=str(exc), headers=headers
    )


async def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    params = [
        InvalidParam(
            name=".".join(str(part) for part in error["loc"]),
            reason=error["msg"],
        )
        for error in exc.errors()
    ]
    return problem_response(
        request,
        status=422,
        slug="request-validation",
        title="Request validation failed",
        detail=_VALIDATION_DETAIL,
        invalid_params=params,
    )


async def _http_error(request: Request, exc: Exception) -> JSONResponse:
    """Framework errors: unknown routes, wrong methods, and HTTPException
    raised by a handler with a message of its own."""
    assert isinstance(exc, StarletteHTTPException)
    phrase = HTTPStatus(exc.status_code).phrase
    detail = (
        exc.detail if isinstance(exc.detail, str) and exc.detail != phrase else None
    )
    return problem_response(
        request,
        status=exc.status_code,
        slug=phrase.lower().replace(" ", "-"),
        detail=detail or f"{phrase}.",
        headers=getattr(exc, "headers", None),
    )


async def _integrity_error(request: Request, exc: Exception) -> JSONResponse:
    """A constraint the repositories did not check first, such as two
    requests racing to create the same name. The request's transaction has
    already rolled back, so this is a conflict rather than a crash."""
    assert isinstance(exc, IntegrityError)
    logger.warning(
        "%s %s violated a database constraint: %s",
        request.method,
        request.url.path,
        exc.orig,
    )
    return problem_response(
        request,
        status=409,
        slug="conflict",
        detail="That change conflicts with existing data. Refresh and try again.",
    )


class UnexpectedErrorMiddleware:
    """Turn any unhandled exception into a sanitised 500 problem.

    Middleware rather than an ``Exception`` handler: Starlette serves that
    handler from its outermost layer, outside the request-context
    middleware, so the response lost its request id and the error log lost
    its correlation. Installed inside ``RequestContextMiddleware``, this
    keeps both.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            # Anything else is a bug: the traceback goes to the logs, and the
            # client gets a message in the usual shape without internals.
            logger.exception(
                "%s %s failed unexpectedly", scope["method"], scope["path"]
            )
            if response_started:
                # Too late to replace the response; let the server close it.
                raise
            response = problem_response(
                scope["path"],
                status=500,
                slug="internal",
                detail="Something went wrong on our side. Please try again.",
            )
            await response(scope, receive, send)


def install_problem_handlers(app: FastAPI) -> None:
    """Map every expected kind of error to a problem response. Unexpected
    ones are handled by `UnexpectedErrorMiddleware`."""
    app.add_exception_handler(MealPlannerError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(IntegrityError, _integrity_error)


def document_problem_responses(app: FastAPI) -> None:
    """Make the OpenAPI document tell the truth about errors.

    FastAPI documents validation failures as its own ``HTTPValidationError``
    in ``application/json``, which this API never returns. This replaces
    every 4xx and 5xx response with ``Problem`` in
    ``application/problem+json``, and adds a ``default`` response so the
    statuses a route does not list (404, 409, 500) are covered too. The
    generated TypeScript types then describe errors as the client sees them.
    """
    build = app.openapi

    def openapi() -> dict:
        if app.openapi_schema:
            return app.openapi_schema
        schema = build()
        problem_schema = Problem.model_json_schema(
            ref_template="#/components/schemas/{model}"
        )
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        components.update(problem_schema.pop("$defs", {}))
        components["Problem"] = problem_schema

        problem_content = {
            PROBLEM_MEDIA_TYPE: {"schema": {"$ref": "#/components/schemas/Problem"}}
        }
        for operations in schema.get("paths", {}).values():
            for operation in operations.values():
                responses = operation.setdefault("responses", {})
                for code, response in responses.items():
                    if code[0] in "45":
                        response["content"] = problem_content
                responses["default"] = {
                    "description": "Problem Details (RFC 9457)",
                    "content": problem_content,
                }

        for unused in ("HTTPValidationError", "ValidationError"):
            components.pop(unused, None)
        app.openapi_schema = schema
        return schema

    app.openapi = openapi  # type: ignore[method-assign]
