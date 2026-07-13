"""
auth_routes.py - Email/password web account authentication.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.account_service import (
    create_password_reset,
    login_user,
    logout_session,
    register_user,
    reset_password,
    verify_email,
)
from app.core.permissions import require_auth

router = APIRouter()


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class VerifyEmailRequest(BaseModel):
    token: str


def _session_token_from_request(request: Request) -> str:
    token = request.headers.get("X-Session-Token")
    if token:
        return token
    authorization = request.headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return ""


@router.post("/auth/register", tags=["Auth"])
async def register(body: RegisterRequest):
    return register_user(email=body.email, password=body.password, name=body.name)


@router.post("/auth/login", tags=["Auth"])
async def login(body: LoginRequest):
    return login_user(email=body.email, password=body.password)


@router.post("/auth/verify-email", tags=["Auth"])
async def verify_email_route(body: VerifyEmailRequest):
    return verify_email(body.token)


@router.post("/auth/logout", tags=["Auth"])
async def logout(request: Request):
    require_auth(request)
    logout_session(_session_token_from_request(request))
    return {"message": "Logged out"}


@router.get("/auth/me", tags=["Auth"])
async def me(request: Request):
    user = require_auth(request)
    return {"user": user}


@router.post("/auth/forgot-password", tags=["Auth"])
async def forgot_password(body: ForgotPasswordRequest):
    return create_password_reset(body.email)


@router.post("/auth/reset-password", tags=["Auth"])
async def reset_password_route(body: ResetPasswordRequest):
    return reset_password(token=body.token, new_password=body.new_password)
