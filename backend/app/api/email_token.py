"""
Self-service token registration/recovery by email.

No login is required. The token is delivered only to the submitted email
address. This is intended for trusted/internal deployments until SSO or email
verification is added.
"""
from __future__ import annotations

import re

from fastapi import APIRouter
from pydantic import BaseModel, Field, field_validator

from app.core.email_service import email_debug_return_token_enabled, send_token_email
from app.core.key_service import get_or_create_user_key_by_email

router = APIRouter()

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailTokenRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        email = value.strip().lower()
        if not EMAIL_RE.match(email):
            raise ValueError("invalid email")
        return email


class EmailTokenResponse(BaseModel):
    message: str
    email: str
    created: bool
    email_sent: bool
    delivery_detail: str
    key: str | None = None


def _issue_email_token(email: str, purpose: str) -> EmailTokenResponse:
    token_data = get_or_create_user_key_by_email(email)
    token = token_data.get("key")
    delivery = send_token_email(email, token or "", purpose)
    response = EmailTokenResponse(
        message="Token created and sent" if token_data.get("created") else "Token sent",
        email=email,
        created=bool(token_data.get("created")),
        email_sent=delivery.sent,
        delivery_detail=delivery.detail,
    )
    if email_debug_return_token_enabled():
        response.key = token
    return response


@router.post("/email-token/register", response_model=EmailTokenResponse, summary="Register token by email")
async def register_token(body: EmailTokenRequest):
    """Create a user token for this email if needed, then email it."""
    return _issue_email_token(body.email, purpose="register")


@router.post("/email-token/recover", response_model=EmailTokenResponse, summary="Recover token by email")
async def recover_token(body: EmailTokenRequest):
    """Email the existing token for this email, creating one if it does not exist."""
    return _issue_email_token(body.email, purpose="recover")
