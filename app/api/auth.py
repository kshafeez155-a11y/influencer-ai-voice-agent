"""Cookie-based user authentication and account endpoints."""

import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app.auth.security import (
    hash_password,
    new_session_token,
    session_token_hash,
    verify_password,
)
from app.core.settings import get_settings
from app.db.database import get_database


router = APIRouter(prefix="/api/auth", tags=["Authentication"])

SESSION_COOKIE = "tac_session"
SESSION_SECONDS = 60 * 60 * 24 * 30
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_attempt_lock = threading.Lock()
_login_attempts: dict[str, deque[float]] = defaultdict(deque)


class SignupPayload(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=8, max_length=128)
    account_type: str = Field(default="user")


class LoginPayload(BaseModel):
    email: str = Field(min_length=5, max_length=254)
    password: str = Field(min_length=1, max_length=128)


class AccountUpdatePayload(BaseModel):
    display_name: str = Field(min_length=2, max_length=80)


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "role": user["role"],
        "created_at": user["created_at"],
    }


def _normalise_email(value: str) -> str:
    email = value.strip().casefold()
    if not _EMAIL_PATTERN.fullmatch(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    return email


def _set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=SESSION_SECONDS,
        httponly=True,
        secure=settings.app_env.strip().lower() == "production",
        samesite="lax",
        path="/",
    )


def _create_session(response: Response, user_id: int) -> None:
    token = new_session_token()
    get_database().create_user_session(
        token_hash=session_token_hash(token),
        user_id=user_id,
        expires_at=int(time.time()) + SESSION_SECONDS,
    )
    _set_session_cookie(response, token)


def optional_current_user(
    tac_session: Annotated[str | None, Cookie()] = None,
) -> dict | None:
    if not tac_session:
        return None
    return get_database().get_user_by_session(
        session_token_hash(tac_session)
    )


def require_user(
    tac_session: Annotated[str | None, Cookie()] = None,
) -> dict:
    user = optional_current_user(tac_session)
    if user is None:
        raise HTTPException(status_code=401, detail="Sign in to continue.")
    return user


def require_creator(
    tac_session: Annotated[str | None, Cookie()] = None,
) -> dict:
    user = require_user(tac_session)
    if user["role"] != "creator":
        raise HTTPException(
            status_code=403,
            detail="This page is for creator accounts.",
        )
    return user


def _check_login_rate_limit(request: Request, email: str) -> str:
    client = request.client.host if request.client else "unknown"
    key = f"{client}:{email}"
    cutoff = time.monotonic() - 15 * 60
    with _attempt_lock:
        attempts = _login_attempts[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= 10:
            raise HTTPException(
                status_code=429,
                detail="Too many sign-in attempts. Try again in 15 minutes.",
            )
    return key


@router.post("/signup", status_code=201)
async def signup(payload: SignupPayload, response: Response) -> dict:
    email = _normalise_email(payload.email)
    display_name = payload.display_name.strip()
    account_type = payload.account_type.strip().lower()

    if account_type not in {"user", "creator"}:
        raise HTTPException(status_code=422, detail="Choose a fan or creator account.")

    database = get_database()
    try:
        user = database.create_user(
            email=email,
            display_name=display_name,
            password_hash=hash_password(payload.password),
            role=account_type,
        )
    except sqlite3.IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="An account already exists for this email.",
        ) from error

    if account_type == "creator":
        database.create_influencer(
            name=display_name,
            tagline="",
            bio="",
            avatar_url="",
            voice_id="",
            system_prompt="",
            owner_user_id=user["id"],
            is_published=False,
            review_status="draft",
        )

    _create_session(response, user["id"])
    return {"user": public_user(user)}


@router.post("/login")
async def login(
    payload: LoginPayload,
    request: Request,
    response: Response,
) -> dict:
    email = _normalise_email(payload.email)
    attempt_key = _check_login_rate_limit(request, email)
    user = get_database().get_user_by_email(email)

    if user is None or not verify_password(payload.password, user["password_hash"]):
        with _attempt_lock:
            _login_attempts[attempt_key].append(time.monotonic())
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    with _attempt_lock:
        _login_attempts.pop(attempt_key, None)
    _create_session(response, user["id"])
    return {"user": public_user(user)}


@router.post("/logout")
async def logout(
    response: Response,
    tac_session: Annotated[str | None, Cookie()] = None,
) -> dict[str, bool]:
    if tac_session:
        get_database().delete_user_session(session_token_hash(tac_session))
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=get_settings().app_env.strip().lower() == "production",
        httponly=True,
        samesite="lax",
    )
    return {"ok": True}


@router.get("/me")
async def me(
    tac_session: Annotated[str | None, Cookie()] = None,
) -> dict:
    user = require_user(tac_session)
    calls = get_database().list_user_web_calls(user["id"], limit=20)
    return {"user": public_user(user), "recent_calls": calls}


@router.patch("/me")
async def update_me(
    payload: AccountUpdatePayload,
    tac_session: Annotated[str | None, Cookie()] = None,
) -> dict:
    user = require_user(tac_session)
    updated = get_database().update_user_name(
        user["id"], payload.display_name.strip()
    )
    return {"user": public_user(updated)}
