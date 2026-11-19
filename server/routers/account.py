"""Leaving, and taking your data with you: export and account deletion."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Response, status
from fastapi.responses import JSONResponse

from app.repositories import UserRepository
from server.deps import AuthDep, CurrentUserDep, ServicesDep, TransactionDep
from server.routers.auth import clear_session_cookie
from server.schemas import (
    AccountDeletion,
    AccountExport,
    ExportedAccount,
    ExportedDay,
    ExportedIngredient,
    ExportedMeal,
    PasswordConfirmation,
    RecoveryCode,
)

router = APIRouter(prefix="/api/account", tags=["account"])


@router.get("/export", response_model=AccountExport)
def export_account(
    current: CurrentUserDep, services: ServicesDep, session: TransactionDep
) -> JSONResponse:
    """Everything that is yours, as a JSON file to download: the account,
    every meal with its ingredients, and every planned day."""
    user = UserRepository(session).get(current.id)
    meals = services.meals.list_all_with_ingredients()
    names = {meal.id: meal.name for meal, _ in meals}
    now = datetime.now(UTC)

    export = AccountExport(
        exported_at=now,
        account=ExportedAccount(
            email=current.email,
            is_guest=current.is_guest,
            created_at=user.created_at if user is not None else None,
        ),
        meals=[
            ExportedMeal(
                name=meal.name,
                servings=meal.servings,
                ingredients=[
                    ExportedIngredient(
                        name=ingredient.name, qty=link.qty, unit=link.unit
                    )
                    for link, ingredient in ingredients
                ],
            )
            for meal, ingredients in meals
        ],
        plans=[
            ExportedDay(
                week_start=day.week_start_date,
                day=day.day_of_week,  # pyright: ignore[reportArgumentType]
                meal=names[day.meal_id],
                servings=day.servings,
            )
            for day in services.plans.list_planned()
            if day.meal_id in names
        ],
    )
    filename = f"the-fridge-door-export-{now.date().isoformat()}.json"
    return JSONResponse(
        export.model_dump(mode="json"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/recovery-code")
def replace_recovery_code(
    payload: PasswordConfirmation, current: CurrentUserDep, auth: AuthDep
) -> RecoveryCode:
    """A new recovery code, confirmed with the password; the old one stops
    working. For a code that was lost, or never made."""
    return RecoveryCode(
        recovery_code=auth.replace_recovery_code(current, payload.password)
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    current: CurrentUserDep,
    auth: AuthDep,
    payload: Annotated[AccountDeletion | None, Body()] = None,
) -> Response:
    """Delete the account and everything in it, for good, and sign out.

    An account with a login confirms with its password; a wrong one is a
    401 invalid-credentials, throttled with login. A guest needs nothing.
    """
    auth.delete_account(current, payload.password if payload is not None else None)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    clear_session_cookie(response)
    return response
