"""Operator authentication, role authorisation and the ARM/EXECUTE interlock.

Prototype scheme: two static bearer tokens from the environment
(OPERATOR_TOKEN, ADMIN_TOKEN). Production would use per-user identities
(OIDC) and hardware-backed keys - tracked as risk R-11.
"""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import Header, HTTPException, Request, status

from shared.schemas import CommandType

from .config import Settings


class Role(StrEnum):
    OPERATOR = "operator"
    ADMIN = "admin"


@dataclass(frozen=True, slots=True)
class Principal:
    name: str
    role: Role


def _match(token: str, expected: str) -> bool:
    return bool(expected) and hmac.compare_digest(token.encode(), expected.encode())


def authenticate(settings: Settings, authorization: str | None) -> Principal:
    if not settings.operator_token and not settings.admin_token:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "commanding disabled: OPERATOR_TOKEN/ADMIN_TOKEN not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:].strip()
    if _match(token, settings.admin_token):
        return Principal("admin", Role.ADMIN)
    if _match(token, settings.operator_token):
        return Principal("operator", Role.OPERATOR)
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token", headers={"WWW-Authenticate": "Bearer"})


def require_operator(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    return authenticate(request.app.state.settings, authorization)


def require_admin(request: Request, authorization: str | None = Header(default=None)) -> Principal:
    p = authenticate(request.app.state.settings, authorization)
    if p.role is not Role.ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin role required for safety-critical commands")
    return p


@dataclass
class Arm:
    arm_id: str
    type: CommandType
    args: dict[str, Any]
    principal: str
    expires_monotonic: float


class ArmStore:
    """Step 1 (ARM) records intent; step 2 (EXECUTE) must follow within the timeout,
    by the same principal. Each arm can be executed at most once."""

    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._arms: dict[str, Arm] = {}
        self._lock = threading.Lock()

    def arm(self, ctype: CommandType, args: dict[str, Any], principal: Principal) -> Arm:
        a = Arm(secrets.token_urlsafe(12), ctype, args, principal.name, time.monotonic() + self.timeout_s)
        with self._lock:
            self._purge()
            self._arms[a.arm_id] = a
        return a

    def consume(self, arm_id: str, principal: Principal) -> Arm:
        with self._lock:
            self._purge()
            a = self._arms.pop(arm_id, None)
        if a is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "unknown or expired arm id - re-arm the command")
        if a.principal != principal.name:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "arm belongs to a different principal")
        return a

    def _purge(self) -> None:
        now = time.monotonic()
        for k in [k for k, a in self._arms.items() if a.expires_monotonic < now]:
            del self._arms[k]
